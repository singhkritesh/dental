from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.auth_store import AuthUser
from services.errors import AppError
from services.field_dictionary_store import (
    DEFAULT_FIELD_DICTIONARY,
    normalize_field_alias,
    normalize_field_key,
    normalize_field_label,
)
from services.template_runtime import extract_template_placeholders
from services.template_store import TEMPLATE_VISIBILITIES
from services.template_type_store import DEFAULT_TEMPLATE_TYPES, normalize_template_type

try:
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ModuleNotFoundError:  # pragma: no cover - dependency availability is environment-specific
    ConnectionPool = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]


EMBEDDING_DIMENSIONS = 384


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _normalize_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value:
        tag = str(item).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
    normalized.sort()
    return normalized


def _tokenize_for_embedding(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def _build_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    tokens = _tokenize_for_embedding(text)
    if not tokens:
        return vector
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], byteorder="big") % dimensions
        vector[index] += 1.0
    magnitude = sum(value * value for value in vector) ** 0.5
    if magnitude <= 0:
        return vector
    return [value / magnitude for value in vector]


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


def _normalize_per_use_case(raw_map: object) -> dict[str, str]:
    per_use_case: dict[str, str] = {}
    if not isinstance(raw_map, dict):
        return per_use_case
    for key, value in raw_map.items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if key_text and value_text:
            per_use_case[key_text] = value_text
    return per_use_case


@dataclass
class PostgresStores:
    auth_store: "PostgresAuthStore"
    template_store: "PostgresTemplateStore"
    template_type_store: "PostgresTemplateTypeStore"
    field_dictionary_store: "PostgresFieldDictionaryStore"
    model_preferences_store: "PostgresModelPreferencesStore"
    upload_store: "PostgresUploadStore"
    audit_store: "PostgresAuditStore"
    _pool: Any

    def close(self) -> None:
        self._pool.close()


class PostgresTemplateTypeStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def list_types(self) -> list[str]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT template_type FROM template_types ORDER BY template_type ASC"
                )
                rows = cur.fetchall()
        values = [normalize_template_type(str(row.get("template_type", ""))) for row in rows]
        normalized = [value for value in values if value]
        if not normalized:
            return DEFAULT_TEMPLATE_TYPES[:]
        return normalized


class PostgresFieldDictionaryStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def list_entries(self) -> list[dict[str, object]]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT field_key, label, aliases
                    FROM field_dictionary
                    ORDER BY label ASC, field_key ASC
                    """
                )
                rows = cur.fetchall()

        entries: list[dict[str, object]] = []
        for row in rows:
            key = normalize_field_key(str(row.get("field_key", "")))
            label = normalize_field_label(str(row.get("label", "")))
            if not key or not label:
                continue

            aliases_raw = row.get("aliases")
            aliases: list[str] = []
            seen_aliases: set[str] = set()
            if isinstance(aliases_raw, list):
                for item in aliases_raw:
                    alias = normalize_field_alias(str(item))
                    if not alias or alias in seen_aliases:
                        continue
                    seen_aliases.add(alias)
                    aliases.append(alias)
            aliases.sort()
            entries.append({"key": key, "label": label, "aliases": aliases})

        if entries:
            return entries

        fallback: list[dict[str, object]] = []
        for item in DEFAULT_FIELD_DICTIONARY:
            key = normalize_field_key(str(item.get("key", "")))
            label = normalize_field_label(str(item.get("label", "")))
            if not key or not label:
                continue
            aliases_raw = item.get("aliases", [])
            aliases: list[str] = []
            if isinstance(aliases_raw, list):
                aliases = sorted(
                    {
                        normalize_field_alias(str(alias))
                        for alias in aliases_raw
                        if normalize_field_alias(str(alias))
                    }
                )
            fallback.append({"key": key, "label": label, "aliases": aliases})
        fallback.sort(key=lambda entry: str(entry.get("label", "")).lower())
        return fallback

    def upsert_entry(
        self,
        field_key: str,
        *,
        label: str,
        aliases: list[str] | None = None,
    ) -> dict[str, object]:
        key = normalize_field_key(field_key)
        normalized_label = normalize_field_label(label)
        if not key:
            raise AppError(
                code="INVALID_FIELD_KEY",
                message="Field key is required.",
                status_code=400,
            )
        if not normalized_label:
            raise AppError(
                code="INVALID_FIELD_LABEL",
                message="Field label is required.",
                status_code=400,
            )

        normalized_aliases = sorted(
            {
                normalize_field_alias(str(alias))
                for alias in (aliases or [])
                if normalize_field_alias(str(alias))
            }
        )
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO field_dictionary (field_key, label, aliases, created_at, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW(), NOW())
                    ON CONFLICT (field_key)
                    DO UPDATE SET
                        label = EXCLUDED.label,
                        aliases = EXCLUDED.aliases,
                        updated_at = NOW()
                    """,
                    (key, normalized_label, _safe_json(normalized_aliases)),
                )
        return {"key": key, "label": normalized_label, "aliases": normalized_aliases}

    def delete_entry(self, field_key: str) -> None:
        key = normalize_field_key(field_key)
        if not key:
            raise AppError(
                code="INVALID_FIELD_KEY",
                message="Field key is required.",
                status_code=400,
            )

        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "DELETE FROM field_dictionary WHERE field_key = %s RETURNING field_key",
                    (key,),
                )
                row = cur.fetchone()
        if not row:
            raise AppError(
                code="FIELD_NOT_FOUND",
                message="Field dictionary entry was not found.",
                status_code=404,
            )

    def ensure_type(self, template_type: str) -> str:
        normalized = normalize_template_type(template_type)
        if not normalized:
            raise AppError(
                code="INVALID_TEMPLATE_TYPE",
                message="Template type is required.",
                status_code=400,
            )
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO template_types (template_type) VALUES (%s) ON CONFLICT DO NOTHING",
                    (normalized,),
                )
        return normalized


class PostgresModelPreferencesStore:
    def __init__(self, pool: Any, default_model: str) -> None:
        self._pool = pool
        self.default_model = default_model

    def get(self) -> dict[str, Any]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT use_global_model_for_all, global_model, per_use_case FROM model_preferences WHERE id = 1"
                )
                row = cur.fetchone()
        if not row:
            return {
                "use_global_model_for_all": True,
                "global_model": self.default_model,
                "per_use_case": {},
            }

        use_global = bool(row.get("use_global_model_for_all", True))
        global_model = str(row.get("global_model", "")).strip() or self.default_model
        per_use_case = _normalize_per_use_case(row.get("per_use_case", {}))
        return {
            "use_global_model_for_all": use_global,
            "global_model": global_model,
            "per_use_case": per_use_case,
        }

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        use_global = bool(payload.get("use_global_model_for_all", True))
        global_model = str(payload.get("global_model", "")).strip() or self.default_model
        per_use_case = _normalize_per_use_case(payload.get("per_use_case", {}))
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO model_preferences (id, use_global_model_for_all, global_model, per_use_case, updated_at)
                    VALUES (1, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (id)
                    DO UPDATE SET
                        use_global_model_for_all = EXCLUDED.use_global_model_for_all,
                        global_model = EXCLUDED.global_model,
                        per_use_case = EXCLUDED.per_use_case,
                        updated_at = NOW()
                    """,
                    (use_global, global_model, _safe_json(per_use_case)),
                )
        return {
            "use_global_model_for_all": use_global,
            "global_model": global_model,
            "per_use_case": per_use_case,
        }

    def resolve_model(self, use_case: str, *, override_model: str | None = None) -> str:
        if override_model and override_model.strip():
            return override_model.strip()
        settings = self.get()
        if settings["use_global_model_for_all"]:
            return str(settings["global_model"])
        use_case_model = str(settings["per_use_case"].get(use_case, "")).strip()
        if use_case_model:
            return use_case_model
        return str(settings["global_model"])


class PostgresTemplateStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @staticmethod
    def _decorate_row(row: dict[str, Any]) -> dict[str, object]:
        created_at_raw = row.get("created_at")
        created_at = (
            _to_iso(created_at_raw)
            if isinstance(created_at_raw, datetime)
            else str(created_at_raw or "")
        )
        content = str(row.get("content", ""))
        placeholders_raw = row.get("placeholders")
        placeholders = placeholders_raw if isinstance(placeholders_raw, list) else []
        clean_placeholders = [str(token).strip() for token in placeholders if str(token).strip()]
        if not clean_placeholders:
            clean_placeholders = extract_template_placeholders(content)
        return {
            "index": int(row.get("id", -1)),
            "name": str(row.get("name", "")),
            "type": str(row.get("type", "")),
            "content": content,
            "visibility": str(row.get("visibility", "personal")),
            "owner_id": str(row.get("owner_id")) if row.get("owner_id") else None,
            "tags": _normalize_tags(row.get("tags", [])),
            "placeholders": clean_placeholders,
            "created_at": created_at,
        }

    @staticmethod
    def _can_delete_template(
        template: dict[str, object],
        *,
        actor_id: str | None,
        role: str,
    ) -> bool:
        if role == "admin":
            return True
        return (
            template.get("visibility") == "personal"
            and bool(actor_id)
            and template.get("owner_id") == actor_id
        )

    def list_templates(
        self,
        *,
        user_id: str | None = None,
        role: str = "admin",
    ) -> list[dict[str, object]]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if role == "admin":
                    cur.execute(
                        """
                        SELECT id, name, type, content, visibility, owner_id, tags, placeholders, created_at
                        FROM templates
                        ORDER BY created_at DESC, id DESC
                        """
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, name, type, content, visibility, owner_id, tags, placeholders, created_at
                        FROM templates
                        WHERE visibility = 'shared' OR owner_id = %s
                        ORDER BY created_at DESC, id DESC
                        """,
                        (user_id or "",),
                    )
                rows = cur.fetchall()
        return [self._decorate_row(row) for row in rows]

    def save_template(
        self,
        name: str,
        template_type: str,
        content: str,
        *,
        owner_id: str | None = None,
        visibility: str,
        tags: list[str] | None = None,
    ) -> int:
        clean_name = name.strip()
        clean_content = content.strip()
        clean_type = normalize_template_type(template_type)
        clean_visibility = visibility.strip().lower()
        if not clean_name or not clean_content:
            raise AppError(
                code="MISSING_VARIABLES",
                message="Template name and content are required.",
                status_code=400,
            )
        if not clean_type:
            raise AppError(
                code="INVALID_TEMPLATE_TYPE",
                message="Template type is required.",
                status_code=400,
            )
        if clean_visibility not in TEMPLATE_VISIBILITIES:
            raise AppError(
                code="INVALID_TEMPLATE_VISIBILITY",
                message="Template visibility must be personal or shared.",
                status_code=400,
            )
        if clean_visibility == "personal" and not owner_id:
            raise AppError(
                code="MISSING_TEMPLATE_OWNER",
                message="Personal templates require an owner.",
                status_code=400,
            )

        normalized_tags = _normalize_tags(tags or [])
        placeholders = extract_template_placeholders(clean_content)
        embedding_text = f"{clean_name}\n{clean_type}\n{' '.join(normalized_tags)}\n{clean_content}"
        embedding = _build_embedding(embedding_text)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                target_owner_id = owner_id if clean_visibility == "personal" else None
                if clean_visibility == "shared":
                    cur.execute(
                        """
                        SELECT id
                        FROM templates
                        WHERE type = %s
                          AND visibility = 'shared'
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                        """,
                        (clean_type,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id
                        FROM templates
                        WHERE type = %s
                          AND visibility = 'personal'
                          AND owner_id = %s
                        ORDER BY created_at DESC, id DESC
                        LIMIT 1
                        """,
                        (clean_type, target_owner_id),
                    )
                row = cur.fetchone()
                if row:
                    template_id = int(row["id"])
                    cur.execute(
                        """
                        UPDATE templates
                        SET name = %s,
                            content = %s,
                            visibility = %s,
                            owner_id = %s,
                            tags = %s::jsonb,
                            placeholders = %s::jsonb,
                            created_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            clean_name,
                            clean_content,
                            clean_visibility,
                            target_owner_id,
                            _safe_json(normalized_tags),
                            _safe_json(placeholders),
                            template_id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO templates (name, type, content, visibility, owner_id, tags, placeholders, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, NOW())
                        RETURNING id
                        """,
                        (
                            clean_name,
                            clean_type,
                            clean_content,
                            clean_visibility,
                            target_owner_id,
                            _safe_json(normalized_tags),
                            _safe_json(placeholders),
                        ),
                    )
                    inserted = cur.fetchone()
                    template_id = int(inserted["id"]) if inserted else -1

                if clean_visibility == "shared":
                    cur.execute(
                        """
                        DELETE FROM templates
                        WHERE id <> %s
                          AND type = %s
                          AND visibility = 'shared'
                        """,
                        (template_id, clean_type),
                    )
                else:
                    cur.execute(
                        """
                        DELETE FROM templates
                        WHERE id <> %s
                          AND type = %s
                          AND visibility = 'personal'
                          AND owner_id = %s
                        """,
                        (template_id, clean_type, target_owner_id),
                    )

                cur.execute(
                    """
                    INSERT INTO template_embeddings (template_id, embedding, updated_at)
                    VALUES (%s, %s::vector, NOW())
                    ON CONFLICT (template_id)
                    DO UPDATE SET embedding = EXCLUDED.embedding, updated_at = NOW()
                    """,
                    (template_id, _vector_literal(embedding)),
                )
        return template_id

    def normalize_global_one_per_type(self) -> int:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    WITH ranked AS (
                        SELECT
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY type, visibility, COALESCE(owner_id, '')
                                ORDER BY created_at DESC, id DESC
                            ) AS rn
                        FROM templates
                    ),
                    deleted AS (
                        DELETE FROM templates t
                        USING ranked r
                        WHERE t.id = r.id
                          AND r.rn > 1
                        RETURNING t.id
                    )
                    SELECT COUNT(*) AS total FROM deleted
                    """
                )
                row = cur.fetchone()
        return int(row.get("total", 0) if row else 0)

    def delete_template(
        self,
        storage_index: int,
        *,
        actor_id: str | None = None,
        role: str = "admin",
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, name, type, content, visibility, owner_id, tags, placeholders, created_at
                    FROM templates
                    WHERE id = %s
                    """,
                    (storage_index,),
                )
                row = cur.fetchone()
                if not row:
                    raise AppError(
                        code="INDEX_OUT_OF_RANGE",
                        message="Template index is out of range.",
                        status_code=404,
                    )
                decorated = self._decorate_row(row)
                if not self._can_delete_template(decorated, actor_id=actor_id, role=role):
                    raise AppError(
                        code="FORBIDDEN",
                        message="You can only delete personal templates you own.",
                        status_code=403,
                    )
                cur.execute("DELETE FROM templates WHERE id = %s", (storage_index,))

    def rerank_with_context(
        self,
        ranked_templates: list[dict[str, Any]],
        *,
        context_text: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not ranked_templates:
            return []
        context_embedding = _build_embedding(context_text)
        if not any(context_embedding):
            return ranked_templates[:limit]
        template_ids: list[int] = []
        for item in ranked_templates:
            try:
                template_id = int(item.get("index", -1))
            except (TypeError, ValueError):
                continue
            if template_id >= 0:
                template_ids.append(template_id)
        if not template_ids:
            return ranked_templates[:limit]

        vector_scores: dict[int, float] = {}
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT template_id, 1 - (embedding <=> %s::vector) AS similarity
                    FROM template_embeddings
                    WHERE template_id = ANY(%s)
                    """,
                    (_vector_literal(context_embedding), template_ids),
                )
                rows = cur.fetchall()
        for row in rows:
            template_id = int(row.get("template_id", -1))
            similarity = float(row.get("similarity") or 0.0)
            vector_scores[template_id] = max(0.0, min(1.0, similarity))

        rescored: list[dict[str, Any]] = []
        for item in ranked_templates:
            try:
                template_id = int(item.get("index", -1))
            except (TypeError, ValueError):
                template_id = -1
            base_score = float(item.get("score", 0.0))
            vector_score = vector_scores.get(template_id, 0.0)
            fused_score = round((base_score * 0.65) + (vector_score * 0.35), 4)
            rescored.append(
                {
                    **item,
                    "score": fused_score,
                    "reason": "Template type, tags, lexical match, and pgvector semantic similarity.",
                }
            )

        rescored.sort(key=lambda row: float(row.get("score", 0.0)), reverse=True)
        return rescored[:limit]


class PostgresAuthStore:
    def __init__(
        self,
        pool: Any,
        *,
        session_hours: int = 12,
        pbkdf2_rounds: int = 200_000,
    ) -> None:
        self._pool = pool
        self.session_hours = max(1, session_hours)
        self.pbkdf2_rounds = pbkdf2_rounds

    def bootstrap_required(self) -> bool:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM users")
                row = cur.fetchone()
        return int(row.get("total", 0) if row else 0) == 0

    def _hash_password(self, password: str, salt_hex: str) -> str:
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            self.pbkdf2_rounds,
        )
        return key.hex()

    def _normalize_username(self, username: str) -> str:
        normalized = username.strip().lower()
        if not normalized:
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Username is required.",
                status_code=400,
            )
        return normalized

    def register(
        self,
        username: str,
        password: str,
        *,
        role: str | None = None,
    ) -> AuthUser:
        normalized = self._normalize_username(username)
        if len(password) < 8:
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Password must be at least 8 characters.",
                status_code=400,
            )

        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT id FROM users WHERE username = %s", (normalized,))
                if cur.fetchone():
                    raise AppError(
                        code="USER_EXISTS",
                        message="A user with this username already exists.",
                        status_code=409,
                    )

                cur.execute("SELECT COUNT(*) AS total FROM users")
                row = cur.fetchone()
                total_users = int(row.get("total", 0) if row else 0)
                if total_users == 0:
                    assigned_role = "admin"
                else:
                    assigned_role = (role or "staff").strip().lower()
                    if assigned_role not in {"admin", "staff"}:
                        assigned_role = "staff"

                salt_hex = secrets.token_hex(16)
                password_hash = self._hash_password(password, salt_hex)
                created_at = _utc_now()
                user_id = secrets.token_hex(12)
                cur.execute(
                    """
                    INSERT INTO users (id, username, password_salt, password_hash, role, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (user_id, normalized, salt_hex, password_hash, assigned_role, created_at),
                )

        return AuthUser(
            id=user_id,
            username=normalized,
            role=assigned_role,
            created_at=_to_iso(created_at),
        )

    def authenticate(self, username: str, password: str) -> AuthUser:
        normalized = self._normalize_username(username)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT id, username, password_salt, password_hash, role, created_at
                    FROM users
                    WHERE username = %s
                    """,
                    (normalized,),
                )
                row = cur.fetchone()
        if not row:
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Invalid username or password.",
                status_code=401,
            )
        expected = str(row.get("password_hash", ""))
        salt_hex = str(row.get("password_salt", ""))
        provided = self._hash_password(password, salt_hex)
        if not hmac.compare_digest(expected, provided):
            raise AppError(
                code="INVALID_CREDENTIALS",
                message="Invalid username or password.",
                status_code=401,
            )
        created_at_raw = row.get("created_at")
        created_at = (
            _to_iso(created_at_raw)
            if isinstance(created_at_raw, datetime)
            else str(created_at_raw or "")
        )
        return AuthUser(
            id=str(row.get("id", "")),
            username=str(row.get("username", "")),
            role=str(row.get("role", "staff")),
            created_at=created_at,
        )

    def _cleanup_sessions(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE expires_at <= NOW()")

    def create_session(self, user: AuthUser) -> str:
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = _utc_now()
        expires = now + timedelta(hours=self.session_hours)
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
                cur.execute(
                    """
                    INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (token_hash, user.id, now, expires),
                )
        return token

    def get_user_for_token(self, token: str) -> AuthUser | None:
        if not token.strip():
            return None
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
                cur.execute(
                    """
                    SELECT u.id, u.username, u.role, u.created_at
                    FROM sessions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.token_hash = %s
                    LIMIT 1
                    """,
                    (token_hash,),
                )
                row = cur.fetchone()
        if not row:
            return None
        created_at_raw = row.get("created_at")
        created_at = (
            _to_iso(created_at_raw)
            if isinstance(created_at_raw, datetime)
            else str(created_at_raw or "")
        )
        return AuthUser(
            id=str(row.get("id", "")),
            username=str(row.get("username", "")),
            role=str(row.get("role", "staff")),
            created_at=created_at,
        )

    def revoke_session(self, token: str) -> None:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sessions WHERE expires_at <= NOW()")
                cur.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))


class PostgresUploadStore:
    def __init__(self, pool: Any, uploads_dir: Path) -> None:
        self._pool = pool
        self.uploads_dir = uploads_dir
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(
        self,
        *,
        user_id: str,
        original_name: str,
        content_type: str,
        payload: bytes,
    ) -> dict[str, str]:
        if not payload:
            raise AppError(
                code="INVALID_FILE",
                message=f"Uploaded file is empty: {original_name}",
                status_code=400,
            )
        upload_id = secrets.token_hex(12)
        suffix = Path(original_name).suffix.lower()
        stored_name = f"{upload_id}{suffix}"
        stored_path = self.uploads_dir / stored_name
        stored_path.write_bytes(payload)

        sha256 = hashlib.sha256(payload).hexdigest()
        size = len(payload)
        created_at_dt = _utc_now()
        created_at = _to_iso(created_at_dt)
        record = {
            "id": upload_id,
            "user_id": user_id,
            "original_name": original_name,
            "stored_name": stored_name,
            "content_type": content_type,
            "size_bytes": str(size),
            "sha256": sha256,
            "created_at": created_at,
        }
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO uploads (
                            id, user_id, original_name, stored_name,
                            content_type, size_bytes, sha256, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            upload_id,
                            user_id,
                            original_name,
                            stored_name,
                            content_type,
                            size,
                            sha256,
                            created_at_dt,
                        ),
                    )
        except Exception as exc:
            try:
                stored_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise AppError(
                code="SAVE_FAILED",
                message="Failed to persist upload metadata.",
                status_code=500,
            ) from exc
        return record


class PostgresAuditStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def log(
        self,
        *,
        actor_id: str,
        action: str,
        outcome: str = "ok",
        details: dict[str, Any] | None = None,
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO audit_events (at, actor_id, action, outcome, details)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        _utc_now(),
                        actor_id,
                        action,
                        outcome,
                        _safe_json(details or {}),
                    ),
                )

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 1000)
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT at, actor_id, action, outcome, details
                    FROM audit_events
                    ORDER BY at DESC, id DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
                rows = cur.fetchall()

        output: list[dict[str, Any]] = []
        for row in reversed(rows):
            at_raw = row.get("at")
            at = _to_iso(at_raw) if isinstance(at_raw, datetime) else str(at_raw or "")
            details_raw = row.get("details")
            details = details_raw if isinstance(details_raw, dict) else {}
            output.append(
                {
                    "at": at,
                    "actor_id": str(row.get("actor_id", "")),
                    "action": str(row.get("action", "")),
                    "outcome": str(row.get("outcome", "ok")),
                    "details": details,
                }
            )
        return output


def _safe_json(value: object) -> str:
    return json.dumps(value)


def _initialize_schema(pool: Any, *, default_model: str) -> None:
    schema_statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'staff')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions (expires_at)",
        """
        CREATE TABLE IF NOT EXISTS template_types (
            template_type TEXT PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS field_dictionary (
            field_key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_field_dictionary_label ON field_dictionary (label)",
        """
        CREATE TABLE IF NOT EXISTS templates (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            content TEXT NOT NULL,
            visibility TEXT NOT NULL CHECK (visibility IN ('personal', 'shared')),
            owner_id TEXT NULL,
            tags JSONB NOT NULL DEFAULT '[]'::jsonb,
            placeholders JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_templates_created_at ON templates (created_at DESC, id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_templates_visibility_owner ON templates (visibility, owner_id)",
        """
        CREATE TABLE IF NOT EXISTS template_embeddings (
            template_id BIGINT PRIMARY KEY REFERENCES templates(id) ON DELETE CASCADE,
            embedding vector(384) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS model_preferences (
            id SMALLINT PRIMARY KEY CHECK (id = 1),
            use_global_model_for_all BOOLEAN NOT NULL DEFAULT TRUE,
            global_model TEXT NOT NULL,
            per_use_case JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS uploads (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_uploads_created_at ON uploads (created_at DESC)",
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id BIGSERIAL PRIMARY KEY,
            at TIMESTAMPTZ NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            outcome TEXT NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_audit_events_at ON audit_events (at DESC, id DESC)",
    ]

    with pool.connection() as conn:
        with conn.cursor() as cur:
            for statement in schema_statements:
                cur.execute(statement)
            cur.execute(
                """
                INSERT INTO model_preferences (id, use_global_model_for_all, global_model, per_use_case, updated_at)
                VALUES (1, TRUE, %s, '{}'::jsonb, NOW())
                ON CONFLICT (id) DO NOTHING
                """,
                (default_model,),
            )
            for template_type in DEFAULT_TEMPLATE_TYPES:
                cur.execute(
                    """
                    INSERT INTO template_types (template_type)
                    VALUES (%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (template_type,),
                )
            for entry in DEFAULT_FIELD_DICTIONARY:
                key = normalize_field_key(str(entry.get("key", "")))
                label = normalize_field_label(str(entry.get("label", "")))
                aliases_raw = entry.get("aliases", [])
                aliases = []
                if isinstance(aliases_raw, list):
                    aliases = sorted(
                        {
                            normalize_field_alias(str(alias))
                            for alias in aliases_raw
                            if normalize_field_alias(str(alias))
                        }
                    )
                if not key or not label:
                    continue
                cur.execute(
                    """
                    INSERT INTO field_dictionary (field_key, label, aliases, created_at, updated_at)
                    VALUES (%s, %s, %s::jsonb, NOW(), NOW())
                    ON CONFLICT (field_key) DO NOTHING
                    """,
                    (key, label, _safe_json(aliases)),
                )


def create_postgres_stores(
    *,
    database_url: str,
    default_model: str,
    uploads_dir: Path,
    session_hours: int = 12,
    db_pool_min_size: int = 1,
    db_pool_max_size: int = 5,
) -> PostgresStores:
    if not database_url.strip():
        raise ValueError("DATABASE_URL is required for postgres stores.")
    if ConnectionPool is None:
        raise RuntimeError(
            "psycopg is not installed. Install requirements to enable postgres storage."
        )

    pool = ConnectionPool(
        conninfo=database_url.strip(),
        min_size=max(1, db_pool_min_size),
        max_size=max(max(1, db_pool_min_size), db_pool_max_size),
        open=True,
    )
    try:
        _initialize_schema(pool, default_model=default_model)
    except Exception:
        pool.close()
        raise

    return PostgresStores(
        auth_store=PostgresAuthStore(pool, session_hours=session_hours),
        template_store=PostgresTemplateStore(pool),
        template_type_store=PostgresTemplateTypeStore(pool),
        field_dictionary_store=PostgresFieldDictionaryStore(pool),
        model_preferences_store=PostgresModelPreferencesStore(pool, default_model),
        upload_store=PostgresUploadStore(pool, uploads_dir),
        audit_store=PostgresAuditStore(pool),
        _pool=pool,
    )
