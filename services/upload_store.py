from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path

from services.errors import AppError
from services.file_store import JsonFileStore


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class UploadStore:
    def __init__(self, uploads_dir: Path, index_path: Path) -> None:
        self.uploads_dir = uploads_dir
        self._store = JsonFileStore(index_path, [])
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
        record = {
            "id": upload_id,
            "user_id": user_id,
            "original_name": original_name,
            "stored_name": stored_name,
            "content_type": content_type,
            "size_bytes": str(size),
            "sha256": sha256,
            "created_at": _utc_iso_now(),
        }
        data = self._store.read()
        if not isinstance(data, list):
            data = []
        data.append(record)
        self._store.write(data)
        return record

