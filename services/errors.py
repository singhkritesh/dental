from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    code: str
    message: str
    status_code: int = 500

    def to_dict(self) -> dict[str, object]:
        return {"error": True, "message": self.message, "code": self.code}

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"

