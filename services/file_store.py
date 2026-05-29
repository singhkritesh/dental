from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from services.errors import AppError


class JsonFileStore:
    def __init__(self, path: Path, default_payload: Any) -> None:
        self.path = path
        self.default_payload = default_payload
        self._lock = threading.Lock()

    def _ensure_file(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._atomic_write(self._clone_default())

    def _clone_default(self) -> Any:
        return json.loads(json.dumps(self.default_payload))

    def _atomic_write(self, payload: Any) -> None:
        directory = self.path.parent
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, indent=2)
            os.replace(tmp_path, self.path)
        except OSError as exc:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise AppError(
                code="SAVE_FAILED",
                message="Could not persist data to local storage.",
                status_code=500,
            ) from exc

    def read(self) -> Any:
        with self._lock:
            self._ensure_file()
            try:
                with self.path.open("r", encoding="utf-8") as file_obj:
                    return json.load(file_obj)
            except (json.JSONDecodeError, OSError):
                return self._clone_default()

    def write(self, payload: Any) -> None:
        with self._lock:
            self._ensure_file()
            self._atomic_write(payload)
