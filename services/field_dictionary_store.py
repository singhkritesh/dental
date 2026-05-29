from __future__ import annotations

import re
from pathlib import Path

from services.errors import AppError
from services.file_store import JsonFileStore

DEFAULT_FIELD_DICTIONARY = [
    {
        "key": "patient_name",
        "label": "Patient Name",
        "aliases": ["name", "full name", "patient full name"],
    },
    {
        "key": "patient_id",
        "label": "Patient ID",
        "aliases": ["chart id", "chart number", "mrn"],
    },
    {
        "key": "member_id",
        "label": "Member ID",
        "aliases": ["insurance member id", "subscriber id", "policy id"],
    },
    {
        "key": "payer_name",
        "label": "Payer Name",
        "aliases": ["insurance company", "carrier", "plan payer"],
    },
    {
        "key": "appointment_date",
        "label": "Appointment Date",
        "aliases": ["visit date", "scheduled date"],
    },
    {
        "key": "appointment_time",
        "label": "Appointment Time",
        "aliases": ["visit time", "scheduled time"],
    },
    {
        "key": "provider_name",
        "label": "Provider Name",
        "aliases": ["doctor name", "dentist", "treating provider"],
    },
    {
        "key": "clinic_phone",
        "label": "Clinic Phone",
        "aliases": ["office phone", "contact number", "phone"],
    },
    {
        "key": "clinic_address",
        "label": "Clinic Address",
        "aliases": ["office address", "location address"],
    },
]


def normalize_field_key(raw_value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", raw_value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def normalize_field_label(raw_value: str) -> str:
    compact = re.sub(r"\s+", " ", raw_value.strip())
    return compact


def normalize_field_alias(raw_value: str) -> str:
    compact = re.sub(r"\s+", " ", raw_value.strip().lower())
    compact = re.sub(r"[^a-z0-9 _-]", "", compact)
    return compact.strip()


def _normalize_entry(raw: object) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    key = normalize_field_key(str(raw.get("key", "")))
    label = normalize_field_label(str(raw.get("label", "")))
    if not key or not label:
        return None

    aliases_raw = raw.get("aliases", [])
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
    return {"key": key, "label": label, "aliases": aliases}


class FieldDictionaryStore:
    def __init__(self, path: Path) -> None:
        self._store = JsonFileStore(path, DEFAULT_FIELD_DICTIONARY)

    def list_entries(self) -> list[dict[str, object]]:
        data = self._store.read()
        if not isinstance(data, list):
            data = DEFAULT_FIELD_DICTIONARY

        entries_by_key: dict[str, dict[str, object]] = {}
        for raw in data:
            normalized = _normalize_entry(raw)
            if not normalized:
                continue
            entries_by_key[str(normalized["key"])] = normalized

        if not entries_by_key:
            for item in DEFAULT_FIELD_DICTIONARY:
                normalized = _normalize_entry(item)
                if normalized:
                    entries_by_key[str(normalized["key"])] = normalized

        entries = list(entries_by_key.values())
        entries.sort(key=lambda item: str(item.get("label", "")).lower())
        return entries

    def upsert_entry(
        self,
        field_key: str,
        *,
        label: str,
        aliases: list[str] | None = None,
    ) -> dict[str, object]:
        normalized_key = normalize_field_key(field_key)
        normalized_label = normalize_field_label(label)
        if not normalized_key:
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

        cleaned_aliases: list[str] = []
        seen_aliases: set[str] = set()
        for item in aliases or []:
            alias = normalize_field_alias(str(item))
            if not alias or alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            cleaned_aliases.append(alias)
        cleaned_aliases.sort()

        entries = self.list_entries()
        updated: list[dict[str, object]] = []
        replaced = False
        for entry in entries:
            if str(entry.get("key", "")) == normalized_key:
                updated.append(
                    {
                        "key": normalized_key,
                        "label": normalized_label,
                        "aliases": cleaned_aliases,
                    }
                )
                replaced = True
            else:
                updated.append(entry)

        if not replaced:
            updated.append(
                {
                    "key": normalized_key,
                    "label": normalized_label,
                    "aliases": cleaned_aliases,
                }
            )
        updated.sort(key=lambda item: str(item.get("label", "")).lower())
        self._store.write(updated)
        return {
            "key": normalized_key,
            "label": normalized_label,
            "aliases": cleaned_aliases,
        }

    def delete_entry(self, field_key: str) -> None:
        normalized_key = normalize_field_key(field_key)
        if not normalized_key:
            raise AppError(
                code="INVALID_FIELD_KEY",
                message="Field key is required.",
                status_code=400,
            )

        entries = self.list_entries()
        filtered = [entry for entry in entries if str(entry.get("key", "")) != normalized_key]
        if len(filtered) == len(entries):
            raise AppError(
                code="FIELD_NOT_FOUND",
                message="Field dictionary entry was not found.",
                status_code=404,
            )
        self._store.write(filtered)
