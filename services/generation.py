from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from services.constants import (
    DENIAL_REQUIRED_FIELDS,
    VERIFICATION_REQUIRED_FIELDS,
)
from services.email_guardrails import generate_with_guardrails
from services.errors import AppError
from services.prompt_registry import (
    INSURANCE_VERIFICATION_PROMPT,
    resolve_denial_prompt,
    resolve_email_prompt,
)
from services.prompt_engine import compose_prompt, validate_required_fields
from services.verification import (
    enforce_grounded_verification_summary,
    extract_json_object,
    normalize_verification_summary,
)


_DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2}(?:,\s*\d{4})?)\b",
    re.IGNORECASE,
)
_TIME_PATTERN = re.compile(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"(?:\+?\d{1,2}\s*)?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}\b")
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CURRENCY_PATTERN = re.compile(r"(?:\$|USD\s*)\d[\d,]*(?:\.\d{2})?\b", re.IGNORECASE)


def payer_to_filename(payer_name: str) -> str:
    cleaned = re.sub(r"\s+", "_", payer_name.strip().lower())
    return f"{cleaned}.txt"


def filename_to_payer_display(filename: str) -> str:
    stem = Path(filename).stem
    return " ".join(part.capitalize() for part in stem.split("_"))


def list_available_payers(payer_refs_dir: Path) -> list[str]:
    files = sorted(payer_refs_dir.glob("*.txt"))
    return [filename_to_payer_display(path.name) for path in files]


def _resolve_payer_reference_path(payer_refs_dir: Path, payer_name: str) -> Path:
    if not payer_name.strip():
        raise AppError(
            code="MISSING_VARIABLES",
            message="Payer name is required.",
            status_code=400,
        )

    # Accept common payer-name characters and block path separators/traversal tokens.
    if not re.fullmatch(r"[A-Za-z0-9 _-]+", payer_name.strip()):
        raise AppError(
            code="PAYER_REFERENCE_INVALID_NAME",
            message="Payer name contains unsupported characters.",
            status_code=400,
        )

    filename = payer_to_filename(payer_name)
    path = (payer_refs_dir / filename).resolve()
    try:
        path.relative_to(payer_refs_dir.resolve())
    except ValueError as exc:
        raise AppError(
            code="PAYER_REFERENCE_INVALID_NAME",
            message="Payer name resolves outside payer reference directory.",
            status_code=400,
        ) from exc
    return path


def load_payer_reference(payer_refs_dir: Path, payer_name: str) -> str:
    path = _resolve_payer_reference_path(payer_refs_dir, payer_name)
    if not path.exists():
        raise AppError(
            code="PAYER_REFERENCE_NOT_FOUND",
            message=(
                "No reference data available for this payer. "
                "Please contact your administrator to add it."
            ),
            status_code=422,
        )
    return path.read_text(encoding="utf-8")


def generate_denial_letter(
    prompts_dir: Path,
    ollama_client: object,
    denial_code: str,
    variables: dict[str, str],
    model_name: str | None = None,
) -> str:
    validate_required_fields(variables, DENIAL_REQUIRED_FIELDS)
    template_name = resolve_denial_prompt(denial_code)
    prompt = compose_prompt(prompts_dir, template_name, variables)
    return ollama_client.generate(prompt, model_name=model_name)


def generate_email_draft(
    prompts_dir: Path,
    ollama_client: object,
    scenario_label: str,
    additional_context: str,
    model_name: str | None = None,
) -> str:
    template_name = resolve_email_prompt(scenario_label)
    if not template_name:
        raise AppError(
            code="MISSING_VARIABLES",
            message=f"Unknown email scenario: {scenario_label}",
            status_code=400,
        )
    prompt = compose_prompt(
        prompts_dir,
        template_name,
        {
            "additional_context": additional_context.strip() or "No additional context provided.",
            "today_date": date.today().isoformat(),
        },
    )
    return generate_with_guardrails(
        ollama_client=ollama_client,
        base_prompt=prompt,
        model_name=model_name,
        purpose_label=scenario_label,
    )


def _to_natural_variable_token(name: str) -> str:
    cleaned = re.sub(r"[\[\]\{\}]+", "", name).strip()
    cleaned = re.sub(r"[_\-.]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        raise AppError(
            code="MISSING_VARIABLES",
            message="Variable names cannot be empty.",
            status_code=400,
        )
    natural = " ".join(word.capitalize() for word in cleaned.split(" "))
    return f"[[{natural}]]"


def _strip_markdown_fence(text: str) -> str:
    body = text.strip()
    if body.startswith("```") and body.endswith("```"):
        lines = body.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return body


def _token_label_from_token(token: str) -> str:
    label = token.removeprefix("[[").removesuffix("]]").strip()
    return re.sub(r"\s+", " ", label)


def _normalize_placeholder_syntax(text: str, tokens: list[str]) -> str:
    normalized = text
    for token in tokens:
        label = _token_label_from_token(token)
        if not label:
            continue
        patterns = [
            re.compile(rf"\[\[\s*{re.escape(label)}\s*\]\]", re.IGNORECASE),
            re.compile(rf"\{{\{{\s*{re.escape(label)}\s*\}}\}}", re.IGNORECASE),
            re.compile(rf"\{{\s*{re.escape(label)}\s*\}}", re.IGNORECASE),
        ]
        for pattern in patterns:
            normalized = pattern.sub(token, normalized)
    return normalized


def _missing_tokens(text: str, tokens: list[str]) -> list[str]:
    text_casefold = text.casefold()
    missing: list[str] = []
    for token in tokens:
        if token.casefold() not in text_casefold:
            missing.append(token)
    return missing


def _find_literal_outliers(text: str) -> list[str]:
    outliers: list[str] = []
    for pattern in (_DATE_PATTERN, _TIME_PATTERN, _PHONE_PATTERN, _EMAIL_PATTERN, _CURRENCY_PATTERN):
        for match in pattern.findall(text):
            value = match.strip()
            if value and value not in outliers:
                outliers.append(value)
    return outliers[:12]


def _repair_template_to_placeholder_only(
    ollama_client: object,
    *,
    template_type: str,
    draft: str,
    tokens: list[str],
    model_name: str | None,
) -> str:
    token_lines = "\n".join(f"- {token}" for token in tokens)
    prompt = (
        "You are fixing a reusable dental-office template.\n"
        "Rewrite the draft so it uses placeholders instead of literal values.\n\n"
        "Hard rules:\n"
        "1. Keep the same general structure and tone.\n"
        "2. Remove literal dates, times, phone numbers, emails, member IDs, and dollar amounts.\n"
        "3. Replace patient/case-specific facts with these tokens only.\n"
        "4. Use every token at least once where relevant.\n"
        "5. Output only the final template body.\n\n"
        f"Template type: {template_type}\n"
        "Allowed tokens:\n"
        f"{token_lines}\n\n"
        "Draft to repair:\n"
        f"{draft}\n"
    )
    repaired = ollama_client.generate(prompt, model_name=model_name)
    return _strip_markdown_fence(repaired)


def generate_template_draft(
    ollama_client: object,
    template_type: str,
    variable_names: list[str],
    instructions: str | None = None,
    model_name: str | None = None,
) -> str:
    tokens = [_to_natural_variable_token(item) for item in variable_names]
    token_lines = "\n".join(f"- {token}" for token in tokens)
    extra = (instructions or "").strip()

    prompt = (
        "You are Siligent, an experienced dental front-office administrative professional.\n"
        "Write a professional reusable template for the requested use case.\n\n"
        "Rules:\n"
        "1. Output only the template body. Do not add commentary, headings like 'Here is', or markdown fences.\n"
        "2. Do not invent any real names, dates, IDs, addresses, phone numbers, or dollar amounts.\n"
        "3. Use variable tokens for patient/case-specific facts.\n"
        "4. Use each provided token at least once where relevant.\n"
        "5. Keep tone professional, concise, and operationally realistic for a dental office.\n"
        "6. If a detail is unknown, leave it as a variable token instead of fabricating.\n\n"
        f"Template type: {template_type}\n"
        "Provided variable tokens:\n"
        f"{token_lines}\n\n"
        "Output format expectations:\n"
        "- Formal business communication format.\n"
        "- Clear opening, purpose/body, and actionable close.\n"
        "- Ready for staff edits.\n"
    )
    if extra:
        prompt += f"\nAdditional drafting instructions:\n{extra}\n"

    raw = ollama_client.generate(prompt, model_name=model_name)
    draft = _strip_markdown_fence(raw)
    draft = _normalize_placeholder_syntax(draft, tokens)

    missing = _missing_tokens(draft, tokens)
    literal_outliers = _find_literal_outliers(draft)
    if missing or literal_outliers:
        repaired = _repair_template_to_placeholder_only(
            ollama_client,
            template_type=template_type,
            draft=draft,
            tokens=tokens,
            model_name=model_name,
        )
        draft = _normalize_placeholder_syntax(repaired, tokens)
        missing = _missing_tokens(draft, tokens)
        literal_outliers = _find_literal_outliers(draft)

    if missing or literal_outliers:
        problems: list[str] = []
        if missing:
            problems.append(f"missing placeholder token(s): {', '.join(missing)}")
        if literal_outliers:
            problems.append(f"literal value(s) detected: {', '.join(literal_outliers)}")
        raise AppError(
            code="TEMPLATE_DRAFT_INVALID",
            message=(
                "Generated template is not placeholder-safe. "
                + "; ".join(problems)
            ),
            status_code=422,
        )

    return draft


def generate_insurance_verification(
    prompts_dir: Path,
    payer_refs_dir: Path,
    ollama_client: object,
    variables: dict[str, str],
    model_name: str | None = None,
) -> tuple[dict[str, str], str]:
    validate_required_fields(variables, VERIFICATION_REQUIRED_FIELDS)

    reference_text = load_payer_reference(payer_refs_dir, variables["payer_name"])
    prompt = compose_prompt(
        prompts_dir,
        INSURANCE_VERIFICATION_PROMPT,
        {
            "payer_name": variables["payer_name"].strip(),
            "member_id": variables.get("member_id", "").strip(),
            "group_number": variables.get("group_number", "").strip() or "Not provided",
            "patient_dob": variables.get("patient_dob", "").strip(),
            "plan_type": variables.get("plan_type", "").strip() or "Not provided",
            "payer_reference_text": reference_text,
        },
    )
    raw_text = ollama_client.generate(prompt, model_name=model_name)
    parsed = extract_json_object(raw_text)
    summary = normalize_verification_summary(parsed)
    summary = enforce_grounded_verification_summary(summary, reference_text)
    return summary, raw_text
