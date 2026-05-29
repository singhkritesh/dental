from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class AuditStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(
        self,
        *,
        actor_id: str,
        action: str,
        outcome: str = "ok",
        details: dict[str, Any] | None = None,
    ) -> None:
        event = {
            "at": _utc_iso_now(),
            "actor_id": actor_id,
            "action": action,
            "outcome": outcome,
            "details": details or {},
        }
        with self._lock:
            with self.path.open("a", encoding="utf-8") as file_obj:
                file_obj.write(json.dumps(event, ensure_ascii=True) + "\n")

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as file_obj:
            lines = file_obj.readlines()
        recent_lines = lines[-max(1, limit) :]
        output: list[dict[str, Any]] = []
        for line in recent_lines:
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

