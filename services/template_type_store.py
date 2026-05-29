from __future__ import annotations

import re
from pathlib import Path

from services.errors import AppError
from services.file_store import JsonFileStore


DEFAULT_TEMPLATE_TYPES = [
    "denial_letter",
    "email",
    "insurance_verification",
    "rebuttal_letter",
    "appointment_confirmation",
    "appointment_confirmation_sms",
    "appointment_reminder_sms",
    "health_history_update_sms",
    "new_patient_forms_sms",
    "comprehensive_investment_letter",
    "invisalign_investment_letter",
]


def normalize_template_type(raw_value: str) -> str:
    normalized = re.sub(r"\s+", "_", raw_value.strip().lower())
    normalized = re.sub(r"[^a-z0-9_-]", "", normalized)
    return normalized.strip("_")


class TemplateTypeStore:
    def __init__(self, path: Path) -> None:
        self._store = JsonFileStore(path, DEFAULT_TEMPLATE_TYPES)

    def list_types(self) -> list[str]:
        data = self._store.read()
        if not isinstance(data, list):
            return DEFAULT_TEMPLATE_TYPES[:]

        normalized: list[str] = []
        for item in data:
            if not isinstance(item, str):
                continue
            value = normalize_template_type(item)
            if value and value not in normalized:
                normalized.append(value)

        if not normalized:
            return DEFAULT_TEMPLATE_TYPES[:]
        for default_type in DEFAULT_TEMPLATE_TYPES:
            if default_type not in normalized:
                normalized.append(default_type)
        return normalized

    def ensure_type(self, template_type: str) -> str:
        normalized = normalize_template_type(template_type)
        if not normalized:
            raise AppError(
                code="INVALID_TEMPLATE_TYPE",
                message="Template type is required.",
                status_code=400,
            )

        all_types = self.list_types()
        if normalized in all_types:
            return normalized
        all_types.append(normalized)
        self._store.write(all_types)
        return normalized
