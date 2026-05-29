from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from services.errors import AppError
from services.template_runtime import extract_template_placeholders
from services.template_type_store import normalize_template_type

TEMPLATE_VISIBILITIES = {"personal", "shared"}


class TemplateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._atomic_write([])

    def _read_raw(self) -> list[dict[str, object]]:
        self._ensure_file()
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            return []
        except (json.JSONDecodeError, OSError):
            return []

    def _atomic_write(self, payload: list[dict[str, object]]) -> None:
        directory = self.path.parent
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp_path, self.path)
        except OSError as exc:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise AppError(
                code="SAVE_FAILED",
                message="Could not save template. Check disk space.",
                status_code=500,
            ) from exc

    @staticmethod
    def _normalize_visibility(value: object) -> str:
        visibility = str(value or "personal").strip().lower()
        if visibility not in TEMPLATE_VISIBILITIES:
            return "personal"
        return visibility

    @staticmethod
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

    def _decorate_template(self, idx: int, template: dict[str, object]) -> dict[str, object]:
        item = dict(template)
        item["index"] = idx
        item["visibility"] = self._normalize_visibility(item.get("visibility"))
        owner_id = item.get("owner_id")
        item["owner_id"] = str(owner_id) if owner_id else None
        item["tags"] = self._normalize_tags(item.get("tags"))
        placeholders = item.get("placeholders")
        if not isinstance(placeholders, list):
            placeholders = []
        clean_placeholders = [str(token).strip() for token in placeholders if str(token).strip()]
        if not clean_placeholders:
            clean_placeholders = extract_template_placeholders(str(item.get("content", "")))
        item["placeholders"] = clean_placeholders
        return item

    def _decorate_templates(self, raw: list[dict[str, object]]) -> list[dict[str, object]]:
        indexed = [self._decorate_template(idx, template) for idx, template in enumerate(raw)]
        indexed.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return indexed

    @staticmethod
    def _is_visible_to_user(
        template: dict[str, object],
        *,
        user_id: str | None,
        role: str,
    ) -> bool:
        if role == "admin":
            return True
        if template.get("visibility") == "shared":
            return True
        return bool(user_id and template.get("owner_id") == user_id)

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
        with self._lock:
            raw = self._read_raw()

        indexed = self._decorate_templates(raw)
        return [
            item
            for item in indexed
            if self._is_visible_to_user(item, user_id=user_id, role=role)
        ]

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

        with self._lock:
            data = self._read_raw()
            created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            target_owner_id = owner_id if clean_visibility == "personal" else None
            normalized_tags = self._normalize_tags(tags or [])
            payload = {
                "name": clean_name,
                "type": clean_type,
                "content": clean_content,
                "visibility": clean_visibility,
                "owner_id": target_owner_id,
                "tags": normalized_tags,
                "placeholders": extract_template_placeholders(clean_content),
                "created_at": created_at,
            }

            matches = [
                idx
                for idx, item in enumerate(data)
                if normalize_template_type(str(item.get("type", ""))) == clean_type
            ]
            if matches and clean_visibility == "shared":
                shared_matches = [
                    idx
                    for idx in matches
                    if self._normalize_visibility(data[idx].get("visibility")) == "shared"
                ]
                if shared_matches:
                    keep_idx = shared_matches[-1]
                    data[keep_idx] = payload
                else:
                    data.append(payload)
                    keep_idx = len(data) - 1
                duplicate_shared = set(shared_matches[:-1]) if shared_matches else set()
                if duplicate_shared:
                    data = [item for idx, item in enumerate(data) if idx not in duplicate_shared]
                    keep_idx = keep_idx - sum(1 for idx in duplicate_shared if idx < keep_idx)
                saved_index = keep_idx
            elif matches and clean_visibility == "personal":
                personal_matches = [
                    idx
                    for idx in matches
                    if self._normalize_visibility(data[idx].get("visibility")) == "personal"
                    and str(data[idx].get("owner_id") or "") == str(target_owner_id or "")
                ]
                if personal_matches:
                    keep_idx = personal_matches[-1]
                    data[keep_idx] = payload
                else:
                    data.append(payload)
                    keep_idx = len(data) - 1
                duplicate_personal = set(personal_matches[:-1]) if personal_matches else set()
                if duplicate_personal:
                    data = [item for idx, item in enumerate(data) if idx not in duplicate_personal]
                    keep_idx = keep_idx - sum(1 for idx in duplicate_personal if idx < keep_idx)
                saved_index = keep_idx
            else:
                data.append(payload)
                saved_index = len(data) - 1
            self._atomic_write(data)
            return saved_index

    def normalize_global_one_per_type(self) -> int:
        with self._lock:
            data = self._read_raw()
            keep_by_group: dict[tuple[str, str, str], int] = {}
            for idx, item in enumerate(data):
                template_type = normalize_template_type(str(item.get("type", "")))
                if not template_type:
                    continue
                visibility = self._normalize_visibility(item.get("visibility"))
                owner_id = str(item.get("owner_id") or "") if visibility == "personal" else ""
                group_key = (template_type, visibility, owner_id)
                existing_idx = keep_by_group.get(group_key)
                if existing_idx is None:
                    keep_by_group[group_key] = idx
                    continue
                keep_by_group[group_key] = idx

            keep_indices = set(keep_by_group.values())
            normalized = [item for idx, item in enumerate(data) if idx in keep_indices]
            removed = len(data) - len(normalized)
            if removed > 0:
                self._atomic_write(normalized)
            return removed

    def delete_template(
        self,
        storage_index: int,
        *,
        actor_id: str | None = None,
        role: str = "admin",
    ) -> None:
        with self._lock:
            data = self._read_raw()
            if storage_index < 0 or storage_index >= len(data):
                raise AppError(
                    code="INDEX_OUT_OF_RANGE",
                    message="Template index is out of range.",
                    status_code=404,
                )
            decorated = self._decorate_template(storage_index, data[storage_index])
            if not self._can_delete_template(decorated, actor_id=actor_id, role=role):
                raise AppError(
                    code="FORBIDDEN",
                    message="You can only delete personal templates you own.",
                    status_code=403,
                )
            del data[storage_index]
            self._atomic_write(data)
