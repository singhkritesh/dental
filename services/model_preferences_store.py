from __future__ import annotations

from pathlib import Path
from typing import Any

from services.file_store import JsonFileStore


DEFAULT_USE_CASES = (
    "denial_letters",
    "insurance_verification",
    "email_drafting",
    "email_thread",
    "document_ingestion",
)


class ModelPreferencesStore:
    def __init__(self, path: Path, default_model: str) -> None:
        self.default_model = default_model
        self._store = JsonFileStore(
            path,
            {
                "use_global_model_for_all": True,
                "global_model": default_model,
                "per_use_case": {},
            },
        )

    def get(self) -> dict[str, Any]:
        payload = self._store.read()
        if not isinstance(payload, dict):
            return {
                "use_global_model_for_all": True,
                "global_model": self.default_model,
                "per_use_case": {},
            }
        use_global = bool(payload.get("use_global_model_for_all", True))
        global_model = str(payload.get("global_model", "")).strip() or self.default_model
        raw_map = payload.get("per_use_case", {})
        per_use_case: dict[str, str] = {}
        if isinstance(raw_map, dict):
            for key, value in raw_map.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if key_text and value_text:
                    per_use_case[key_text] = value_text
        return {
            "use_global_model_for_all": use_global,
            "global_model": global_model,
            "per_use_case": per_use_case,
        }

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        use_global = bool(payload.get("use_global_model_for_all", True))
        global_model = str(payload.get("global_model", "")).strip() or self.default_model

        raw_map = payload.get("per_use_case", {})
        per_use_case: dict[str, str] = {}
        if isinstance(raw_map, dict):
            for key, value in raw_map.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if key_text and value_text:
                    per_use_case[key_text] = value_text

        stored = {
            "use_global_model_for_all": use_global,
            "global_model": global_model,
            "per_use_case": per_use_case,
        }
        self._store.write(stored)
        return stored

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
