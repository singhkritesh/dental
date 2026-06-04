from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

PLACEHOLDER_TOKEN_PATTERN = r"[A-Za-z][A-Za-z0-9_.-]{0,79}"
_PLACEHOLDER_PATTERN = re.compile(
    rf"\{{\{{\s*({PLACEHOLDER_TOKEN_PATTERN})\s*\}}\}}|"
    rf"(?<!\{{)\{{({PLACEHOLDER_TOKEN_PATTERN})\}}(?!\}})"
)

RUNTIME_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "claim_or_reference": (
        "claim_id",
        "claim_number",
        "claim_reference",
        "reference_number",
        "reference",
    ),
    "denial_code": ("co_code", "carc", "denial_carc", "adjustment_code"),
    "denial_reason": ("reason_for_denial", "payer_denial_reason", "denial_description"),
    "appeal_basis": ("appeal_reason", "why_appealing", "appeal_rationale"),
    "date_of_service": ("dos", "service_date", "visit_date"),
    "payer_name": ("payer", "insurance_company", "carrier"),
    "payer_address": ("insurance_address", "carrier_address"),
    "procedure_description": ("procedure", "service", "treatment", "treatment_description"),
    "procedure_code": ("code", "cdt_code", "service_code"),
    "provider_name": ("doctor_name", "dentist", "treating_provider"),
    "provider_npi": ("npi", "doctor_npi", "dentist_npi"),
    "clinic_phone": ("office_phone", "phone", "contact_number"),
    "clinic_name": ("office_name", "practice_name"),
    "date_of_birth": ("dob", "patient_dob", "birth_date"),
    "email": ("email_address", "requester_email", "patient_email"),
    "phone": ("phone_number", "patient_phone", "requester_phone"),
    "requester_name": ("sender_name", "contact_name"),
    "office_phone": ("clinic_phone", "practice_phone"),
    "office_email": ("clinic_email", "practice_email"),
}

_ALIAS_TO_CANONICAL = {
    alias: canonical
    for canonical, aliases in RUNTIME_FIELD_ALIASES.items()
    for alias in aliases
}


@dataclass(frozen=True)
class TemplateRenderResult:
    rendered: str
    placeholders: list[str]
    missing: list[str]
    used: dict[str, str]


def extract_template_placeholders(content: str) -> list[str]:
    found: set[str] = set()
    for match in _PLACEHOLDER_PATTERN.finditer(content):
        token = (match.group(1) or match.group(2) or "").strip()
        if token:
            found.add(token)
    return sorted(found)


def normalize_runtime_fields(raw: Mapping[str, Any] | None) -> dict[str, str]:
    if not raw:
        return {}
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        token = str(key).strip()
        if not token:
            continue
        normalized[token] = _coerce_runtime_value(value)
    return normalized


def expand_runtime_field_aliases(runtime_fields: Mapping[str, str] | None) -> dict[str, str]:
    """Add canonical field names for common staff-entered aliases without overwriting explicit values."""
    values = dict(runtime_fields or {})
    lowered_lookup = {key.lower(): key for key in values}

    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        if canonical in values:
            continue
        source_key = lowered_lookup.get(alias)
        if source_key and str(values.get(source_key, "")).strip():
            values[canonical] = values[source_key]

    for canonical, aliases in RUNTIME_FIELD_ALIASES.items():
        if canonical not in values or not str(values.get(canonical, "")).strip():
            continue
        for alias in aliases:
            if alias not in values:
                values[alias] = values[canonical]

    return values


def _coerce_runtime_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value).strip()
    return json.dumps(value, ensure_ascii=False)


def render_template_with_runtime_fields(
    content: str,
    runtime_fields: Mapping[str, str] | None,
    *,
    keep_unresolved: bool = True,
) -> TemplateRenderResult:
    placeholders = extract_template_placeholders(content)
    if not placeholders:
        return TemplateRenderResult(
            rendered=content,
            placeholders=[],
            missing=[],
            used={},
        )

    runtime = dict(runtime_fields or {})
    lower_lookup = {key.lower(): key for key in runtime}
    missing: set[str] = set()
    used: dict[str, str] = {}

    def _replace(match: re.Match[str]) -> str:
        token = (match.group(1) or match.group(2) or "").strip()
        if not token:
            return match.group(0)

        if token in runtime:
            value = runtime[token]
            used[token] = value
            return value

        lowered = token.lower()
        if lowered in lower_lookup:
            resolved_key = lower_lookup[lowered]
            value = runtime[resolved_key]
            used[token] = value
            return value

        missing.add(token)
        return match.group(0) if keep_unresolved else ""

    rendered = _PLACEHOLDER_PATTERN.sub(_replace, content)
    return TemplateRenderResult(
        rendered=rendered,
        placeholders=placeholders,
        missing=sorted(missing),
        used=used,
    )


def runtime_fields_to_context_block(
    runtime_fields: Mapping[str, str] | None,
    *,
    max_chars: int = 4_000,
) -> str:
    values = runtime_fields or {}
    if not values:
        return ""

    lines = ["[Runtime Patient Data]"]
    for key in sorted(values.keys()):
        lines.append(f"- {key}: {values[key]}")
    block = "\n".join(lines)
    return block[:max_chars]


def to_prompt_json(value: Mapping[str, Any], *, max_chars: int = 12_000) -> str:
    """Serialize trusted prompt context deterministically for LLM consumption."""
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return rendered[:max_chars]


def runtime_fields_to_json_context(
    runtime_fields: Mapping[str, str] | None,
    *,
    max_chars: int = 4_000,
) -> str:
    values = {
        key: value
        for key, value in sorted((runtime_fields or {}).items())
        if str(value).strip()
    }
    if not values:
        return ""
    return to_prompt_json(
        {
            "trusted_runtime_fields": values,
            "source_policy": "Use these values as authoritative patient/account data. Do not invent missing values.",
        },
        max_chars=max_chars,
    )
