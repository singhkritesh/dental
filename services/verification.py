from __future__ import annotations

import json
import re
from typing import Any

from services.constants import VERIFICATION_FIELDS
from services.errors import AppError


def extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[idx:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise AppError(
        code="GENERATION_FAILED",
        message="Model returned an unusable verification response.",
        status_code=502,
    )


def _to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
        return normalized or ["Not available"]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return ["Not available"]


def _to_str(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if value is None:
        return "Not available"
    text = str(value).strip()
    return text or "Not available"


_GENERIC_COVERED_VALUES = {
    "not available",
    "none",
    "n/a",
    "unknown",
    "yes",
    "no",
    "covered",
    "not covered",
}

_STOPWORDS = {
    "and",
    "or",
    "the",
    "for",
    "with",
    "from",
    "this",
    "that",
    "plan",
    "service",
    "services",
    "procedure",
    "procedures",
    "code",
    "codes",
    "dental",
}


def _normalize_free_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _is_grounded_procedure(candidate: str, reference_text: str) -> bool:
    normalized_candidate = _normalize_free_text(candidate)
    if not normalized_candidate or normalized_candidate in _GENERIC_COVERED_VALUES:
        return False
    normalized_reference = _normalize_free_text(reference_text)
    if not normalized_reference:
        return False

    if normalized_candidate in normalized_reference:
        return True

    tokens = [
        token
        for token in normalized_candidate.split(" ")
        if len(token) >= 3 and token not in _STOPWORDS
    ]
    if not tokens:
        return False
    matched = sum(1 for token in tokens if token in normalized_reference)
    return matched == len(tokens)


def enforce_grounded_verification_summary(
    summary: dict[str, Any],
    payer_reference_text: str,
) -> dict[str, Any]:
    filtered: dict[str, Any] = dict(summary)
    procedures_raw = summary.get("covered_procedures", [])
    procedures: list[str] = []
    if isinstance(procedures_raw, list):
        for item in procedures_raw:
            value = str(item).strip()
            if not value:
                continue
            if _is_grounded_procedure(value, payer_reference_text):
                procedures.append(value)

    filtered["covered_procedures"] = procedures or ["Not available"]
    for field in (
        "estimated_copay",
        "prior_authorization_required",
        "annual_maximum",
        "waiting_periods",
        "notable_exclusions_limitations",
    ):
        value = str(summary.get(field, "")).strip()
        if not value:
            filtered[field] = "Not available"
            continue
        normalized_value = _normalize_free_text(value)
        if normalized_value in _GENERIC_COVERED_VALUES:
            filtered[field] = "Not available"
            continue
        if _is_grounded_procedure(value, payer_reference_text):
            filtered[field] = value
        else:
            filtered[field] = "Not available"
    return filtered


def normalize_verification_summary(raw: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "covered_procedures": ["covered_procedures", "coveredProcedures"],
        "estimated_copay": ["estimated_copay", "estimatedCoPay", "estimated_copay_or_cost_share"],
        "prior_authorization_required": [
            "prior_authorization_required",
            "priorAuthorizationRequired",
        ],
        "annual_maximum": ["annual_maximum", "annualMaximum"],
        "waiting_periods": ["waiting_periods", "waitingPeriods"],
        "notable_exclusions_limitations": [
            "notable_exclusions_limitations",
            "notableExclusionsLimitations",
        ],
    }

    normalized: dict[str, Any] = {}
    for field in VERIFICATION_FIELDS:
        value = None
        for alias in aliases[field]:
            if alias in raw:
                value = raw[alias]
                break

        if field == "covered_procedures":
            normalized[field] = _to_list(value)
        else:
            normalized[field] = _to_str(value)
    return normalized


def summary_to_text(summary: dict[str, Any]) -> str:
    covered = summary.get("covered_procedures", ["Not available"])
    covered_text = "\n".join([f"- {item}" for item in covered]) if isinstance(covered, list) else "- Not available"
    return (
        "Insurance Verification Summary\n\n"
        f"Covered Procedures:\n{covered_text}\n\n"
        f"Estimated Co-Pay: {summary.get('estimated_copay', 'Not available')}\n"
        f"Prior Authorization Required: {summary.get('prior_authorization_required', 'Not available')}\n"
        f"Annual Maximum: {summary.get('annual_maximum', 'Not available')}\n"
        f"Waiting Periods: {summary.get('waiting_periods', 'Not available')}\n"
        f"Notable Exclusions/Limitations: {summary.get('notable_exclusions_limitations', 'Not available')}\n"
    )
