from __future__ import annotations

import re
from dataclasses import dataclass

from services.errors import AppError

_DATE_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_DATE_SLASH_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
_DATE_MONTH_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
    r"\d{1,2}(?:,\s*\d{4})?\b",
    re.IGNORECASE,
)
_TIME_RE = re.compile(r"\b\d{1,2}:\d{2}\s?(?:am|pm|AM|PM)?\b")
_CURRENCY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{2})?\b")
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\w)"
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_ID_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9-]*\d[A-Za-z0-9-]*\b")
_PROCEDURE_CODE_RE = re.compile(r"\b[A-Za-z]\d{4}\b")

_SAFE_FACT_VALUES = {
    "not provided",
    "not available",
    "n/a",
}


@dataclass(frozen=True)
class GroundingResult:
    factual_values: list[str]
    ungrounded_values: list[str]


def _normalize_text(value: str) -> str:
    lowered = value.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _normalize_digits(value: str) -> str:
    return re.sub(r"\D+", "", value)


def _extract_factual_values(text: str) -> list[str]:
    matches: list[str] = []
    patterns = (
        _DATE_ISO_RE,
        _DATE_SLASH_RE,
        _DATE_MONTH_RE,
        _TIME_RE,
        _CURRENCY_RE,
        _PHONE_RE,
        _EMAIL_RE,
        _ID_RE,
        _PROCEDURE_CODE_RE,
    )
    for pattern in patterns:
        matches.extend(pattern.findall(text))
    unique: list[str] = []
    seen: set[str] = set()
    for item in matches:
        clean = str(item).strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        unique.append(clean)
    return unique


def _build_trusted_bundles(sources: list[str]) -> tuple[str, str]:
    trusted_text = "\n".join([item for item in sources if item]).strip()
    return _normalize_text(trusted_text), _normalize_digits(trusted_text)


def _is_fact_grounded(fact: str, *, trusted_text: str, trusted_digits: str) -> bool:
    normalized = _normalize_text(fact)
    if not normalized or normalized in _SAFE_FACT_VALUES:
        return True
    if normalized in trusted_text:
        return True

    digits = _normalize_digits(fact)
    if len(digits) >= 4 and digits in trusted_digits:
        return True
    return False


def evaluate_draft_grounding(
    *,
    draft: str,
    trusted_sources: list[str],
) -> GroundingResult:
    factual_values = _extract_factual_values(draft)
    if not factual_values:
        return GroundingResult(factual_values=[], ungrounded_values=[])
    trusted_text, trusted_digits = _build_trusted_bundles(trusted_sources)
    ungrounded = [
        value
        for value in factual_values
        if not _is_fact_grounded(value, trusted_text=trusted_text, trusted_digits=trusted_digits)
    ]
    return GroundingResult(
        factual_values=factual_values,
        ungrounded_values=ungrounded,
    )


def enforce_draft_grounding_or_raise(
    *,
    draft: str,
    trusted_sources: list[str],
    use_case: str,
) -> None:
    result = evaluate_draft_grounding(draft=draft, trusted_sources=trusted_sources)
    if not result.ungrounded_values:
        return

    values_preview = ", ".join(result.ungrounded_values[:6])
    raise AppError(
        code="UNGROUNDED_FACTS",
        message=(
            f"Generated {use_case} output contains ungrounded factual values: {values_preview}. "
            "Provide these facts via uploaded source documents or runtime fields."
        ),
        status_code=422,
    )
