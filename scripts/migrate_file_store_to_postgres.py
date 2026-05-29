#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.postgres_store import create_postgres_stores
from services.template_runtime import extract_template_placeholders
from services.template_type_store import normalize_template_type


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_dt(raw: object) -> datetime:
    text = str(raw or "").strip()
    if not text:
        return _utc_now()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return _utc_now()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except (json.JSONDecodeError, OSError):
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    output: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                output.append(value)
    return output


def _json_text(value: object) -> str:
    return json.dumps(value)


def _tokenize_for_embedding(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]{2,}", text.lower())


def _build_embedding(text: str, dimensions: int = 384) -> list[float]:
    import hashlib

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


def _normalize_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        tag = str(item).strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    out.sort()
    return out


@dataclass
class MigrationStats:
    users: int = 0
    sessions: int = 0
    templates: int = 0
    template_types: int = 0
    uploads: int = 0
    upload_files_missing: int = 0
    audit_events: int = 0
    model_preferences: int = 0


def migrate(data_dir: Path, database_url: str, default_model: str) -> MigrationStats:
    stores = create_postgres_stores(
        database_url=database_url,
        default_model=default_model,
        uploads_dir=data_dir / "uploads",
    )
    pool = stores._pool
    stats = MigrationStats()
    try:
        users = _read_json(data_dir / "users.json", [])
        sessions = _read_json(data_dir / "sessions.json", [])
        templates = _read_json(data_dir / "templates.json", [])
        template_types = _read_json(data_dir / "template_types.json", [])
        model_preferences = _read_json(data_dir / "model_preferences.json", {})
        uploads = _read_json(data_dir / "uploads_index.json", [])
        audit_events = _read_jsonl(data_dir / "audit_events.jsonl")

        with pool.connection() as conn:
            with conn.cursor() as cur:
                if isinstance(template_types, list):
                    for raw_type in template_types:
                        normalized = normalize_template_type(str(raw_type))
                        if not normalized:
                            continue
                        cur.execute(
                            "INSERT INTO template_types (template_type) VALUES (%s) ON CONFLICT DO NOTHING",
                            (normalized,),
                        )
                        stats.template_types += 1

                if isinstance(model_preferences, dict):
                    use_global = bool(model_preferences.get("use_global_model_for_all", True))
                    global_model = str(model_preferences.get("global_model", "")).strip() or default_model
                    per_use_case = model_preferences.get("per_use_case", {})
                    if not isinstance(per_use_case, dict):
                        per_use_case = {}
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
                        (use_global, global_model, _json_text(per_use_case)),
                    )
                    stats.model_preferences = 1

                if isinstance(users, list):
                    for item in users:
                        if not isinstance(item, dict):
                            continue
                        user_id = str(item.get("id", "")).strip()
                        username = str(item.get("username", "")).strip().lower()
                        salt = str(item.get("password_salt", "")).strip()
                        password_hash = str(item.get("password_hash", "")).strip()
                        role = str(item.get("role", "staff")).strip().lower()
                        if role not in {"admin", "staff"}:
                            role = "staff"
                        created_at = _to_dt(item.get("created_at"))
                        if not user_id or not username or not salt or not password_hash:
                            continue
                        cur.execute(
                            """
                            INSERT INTO users (id, username, password_salt, password_hash, role, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id)
                            DO UPDATE SET
                                username = EXCLUDED.username,
                                password_salt = EXCLUDED.password_salt,
                                password_hash = EXCLUDED.password_hash,
                                role = EXCLUDED.role,
                                created_at = EXCLUDED.created_at
                            """,
                            (user_id, username, salt, password_hash, role, created_at),
                        )
                        stats.users += 1

                if isinstance(sessions, list):
                    for item in sessions:
                        if not isinstance(item, dict):
                            continue
                        token_hash = str(item.get("token_hash", "")).strip()
                        user_id = str(item.get("user_id", "")).strip()
                        if not token_hash or not user_id:
                            continue
                        created_at = _to_dt(item.get("created_at"))
                        expires_at = _to_dt(item.get("expires_at"))
                        cur.execute(
                            """
                            INSERT INTO sessions (token_hash, user_id, created_at, expires_at)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (token_hash)
                            DO UPDATE SET
                                user_id = EXCLUDED.user_id,
                                created_at = EXCLUDED.created_at,
                                expires_at = EXCLUDED.expires_at
                            """,
                            (token_hash, user_id, created_at, expires_at),
                        )
                        stats.sessions += 1

                if isinstance(templates, list):
                    for item in templates:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name", "")).strip()
                        template_type = normalize_template_type(str(item.get("type", "")))
                        content = str(item.get("content", "")).strip()
                        visibility = str(item.get("visibility", "personal")).strip().lower()
                        if visibility not in {"personal", "shared"}:
                            visibility = "personal"
                        owner_id = str(item.get("owner_id", "")).strip() or None
                        if visibility == "shared":
                            owner_id = None
                        tags = _normalize_tags(item.get("tags", []))
                        placeholders_raw = item.get("placeholders")
                        placeholders = placeholders_raw if isinstance(placeholders_raw, list) else []
                        placeholders = [str(token).strip() for token in placeholders if str(token).strip()]
                        if not placeholders:
                            placeholders = extract_template_placeholders(content)
                        created_at = _to_dt(item.get("created_at"))
                        if not name or not template_type or not content:
                            continue

                        cur.execute(
                            """
                            SELECT id FROM templates
                            WHERE name = %s
                              AND type = %s
                              AND content = %s
                              AND visibility = %s
                              AND COALESCE(owner_id, '') = COALESCE(%s, '')
                            ORDER BY id ASC
                            LIMIT 1
                            """,
                            (name, template_type, content, visibility, owner_id),
                        )
                        existing = cur.fetchone()
                        if existing:
                            template_id = int(existing[0])
                            cur.execute(
                                """
                                UPDATE templates
                                SET tags = %s::jsonb, placeholders = %s::jsonb, created_at = %s
                                WHERE id = %s
                                """,
                                (_json_text(tags), _json_text(placeholders), created_at, template_id),
                            )
                        else:
                            cur.execute(
                                """
                                INSERT INTO templates
                                    (name, type, content, visibility, owner_id, tags, placeholders, created_at)
                                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                                RETURNING id
                                """,
                                (
                                    name,
                                    template_type,
                                    content,
                                    visibility,
                                    owner_id,
                                    _json_text(tags),
                                    _json_text(placeholders),
                                    created_at,
                                ),
                            )
                            template_id = int(cur.fetchone()[0])
                        embedding_text = f"{name}\n{template_type}\n{' '.join(tags)}\n{content}"
                        embedding = _build_embedding(embedding_text)
                        cur.execute(
                            """
                            INSERT INTO template_embeddings (template_id, embedding, updated_at)
                            VALUES (%s, %s::vector, NOW())
                            ON CONFLICT (template_id)
                            DO UPDATE SET embedding = EXCLUDED.embedding, updated_at = NOW()
                            """,
                            (template_id, _vector_literal(embedding)),
                        )
                        stats.templates += 1

                uploads_dir = data_dir / "uploads"
                if isinstance(uploads, list):
                    for item in uploads:
                        if not isinstance(item, dict):
                            continue
                        upload_id = str(item.get("id", "")).strip()
                        user_id = str(item.get("user_id", "")).strip()
                        original_name = str(item.get("original_name", "")).strip()
                        stored_name = str(item.get("stored_name", "")).strip()
                        content_type = str(item.get("content_type", "")).strip()
                        sha256 = str(item.get("sha256", "")).strip()
                        size_bytes_raw = str(item.get("size_bytes", "0")).strip()
                        try:
                            size_bytes = int(size_bytes_raw)
                        except ValueError:
                            size_bytes = 0
                        created_at = _to_dt(item.get("created_at"))
                        if not (
                            upload_id
                            and user_id
                            and original_name
                            and stored_name
                            and content_type
                            and sha256
                            and size_bytes >= 0
                        ):
                            continue
                        if not (uploads_dir / stored_name).exists():
                            stats.upload_files_missing += 1
                        cur.execute(
                            """
                            INSERT INTO uploads
                                (id, user_id, original_name, stored_name, content_type, size_bytes, sha256, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id)
                            DO UPDATE SET
                                user_id = EXCLUDED.user_id,
                                original_name = EXCLUDED.original_name,
                                stored_name = EXCLUDED.stored_name,
                                content_type = EXCLUDED.content_type,
                                size_bytes = EXCLUDED.size_bytes,
                                sha256 = EXCLUDED.sha256,
                                created_at = EXCLUDED.created_at
                            """,
                            (
                                upload_id,
                                user_id,
                                original_name,
                                stored_name,
                                content_type,
                                size_bytes,
                                sha256,
                                created_at,
                            ),
                        )
                        stats.uploads += 1

                for event in audit_events:
                    at = _to_dt(event.get("at"))
                    actor_id = str(event.get("actor_id", "")).strip()
                    action = str(event.get("action", "")).strip()
                    outcome = str(event.get("outcome", "ok")).strip() or "ok"
                    details = event.get("details", {})
                    if not isinstance(details, dict):
                        details = {}
                    if not actor_id or not action:
                        continue
                    cur.execute(
                        """
                        INSERT INTO audit_events (at, actor_id, action, outcome, details)
                        SELECT %s, %s, %s, %s, %s::jsonb
                        WHERE NOT EXISTS (
                            SELECT 1
                            FROM audit_events
                            WHERE at = %s
                              AND actor_id = %s
                              AND action = %s
                              AND outcome = %s
                              AND details = %s::jsonb
                            LIMIT 1
                        )
                        """,
                        (
                            at,
                            actor_id,
                            action,
                            outcome,
                            _json_text(details),
                            at,
                            actor_id,
                            action,
                            outcome,
                            _json_text(details),
                        ),
                    )
                    if cur.rowcount > 0:
                        stats.audit_events += 1
    finally:
        stores.close()
    return stats


def _default_database_url() -> str:
    configured = os.getenv("DATABASE_URL", "").strip()
    if configured:
        return configured
    db = os.getenv("POSTGRES_DB", "siligent").strip() or "siligent"
    user = os.getenv("POSTGRES_USER", "siligent").strip() or "siligent"
    password = os.getenv("POSTGRES_PASSWORD", "siligent").strip() or "siligent"
    port = os.getenv("POSTGRES_PORT", "5434").strip() or "5434"
    return f"postgresql://{user}:{password}@localhost:{port}/{db}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate file-based Siligent data into Postgres/pgvector."
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT_DIR / "data"),
        help="Path to file-based data directory (default: ./data).",
    )
    parser.add_argument(
        "--database-url",
        default=_default_database_url(),
        help="Postgres URL. Defaults to DATABASE_URL or localhost postgres env fallback.",
    )
    parser.add_argument(
        "--model-name",
        default=os.getenv("MODEL_NAME", "qwen3.5:4b"),
        help="Default model name used for bootstrap model preferences if missing.",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise SystemExit(f"Data directory not found: {data_dir}")

    stats = migrate(
        data_dir=data_dir,
        database_url=args.database_url,
        default_model=args.model_name,
    )
    print("Migration completed.")
    print(f"  users: {stats.users}")
    print(f"  sessions: {stats.sessions}")
    print(f"  templates: {stats.templates}")
    print(f"  template_types: {stats.template_types}")
    print(f"  model_preferences: {stats.model_preferences}")
    print(f"  uploads: {stats.uploads}")
    print(f"  uploads_missing_files: {stats.upload_files_missing}")
    print(f"  audit_events_inserted: {stats.audit_events}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
