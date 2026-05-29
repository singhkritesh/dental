from __future__ import annotations

import re
from typing import Mapping


PRACTICE_ROLE = "Siligent Dental provider team at a U.S. dental practice"

_PURPOSE_INSTRUCTIONS: dict[str, str] = {
    "appointment_reminder": "Remind the patient about an upcoming appointment and what to do next.",
    "appointment_confirmation": "Confirm, reschedule, or clarify appointment timing and next steps.",
    "cancellation_confirmation": "Confirm the cancellation and provide clear rescheduling guidance.",
    "balance_due_notice": "Communicate outstanding balance details and payment options clearly.",
    "billing_inquiry": "Answer billing questions and explain charges or payment next steps.",
    "insurance_update_request": "Request or confirm insurance details needed to process care or claims.",
    "insurance_update": "Request or confirm insurance details needed to process care or claims.",
    "referral_letter": "Provide referral-related information and expected follow-up steps.",
    "records_request": "Acknowledge records request and explain release or delivery process.",
    "new_patient_welcome": "Welcome a new patient and outline onboarding expectations.",
    "post_treatment_follow_up": "Follow up after treatment, give safe next steps, and escalate when needed.",
    "post_treatment_followup": "Follow up after treatment, give safe next steps, and escalate when needed.",
    "general_inquiry_response": "Answer a general patient inquiry directly and politely.",
    "general_inquiry": "Answer a general patient inquiry directly and politely.",
    "denial_followup": "Respond regarding denial or appeal follow-up with required documentation steps.",
}

_PURPOSE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "appointment_reminder": ("appointment", "reminder", "scheduled", "visit"),
    "appointment_confirmation": ("appointment", "confirm", "scheduled", "reschedule", "cancel"),
    "cancellation_confirmation": ("cancel", "cancellation", "reschedule", "appointment"),
    "balance_due_notice": ("balance", "payment", "invoice", "amount", "due"),
    "billing_inquiry": ("bill", "billing", "balance", "charge", "payment"),
    "insurance_update_request": ("insurance", "member id", "group", "coverage", "payer"),
    "insurance_update": ("insurance", "member id", "group", "coverage", "payer"),
    "referral_letter": ("referral", "specialist", "records", "provider"),
    "records_request": ("records", "release", "x-ray", "xray", "request"),
    "new_patient_welcome": ("welcome", "new patient", "forms", "appointment"),
    "post_treatment_follow_up": ("treatment", "follow-up", "follow up", "healing", "symptoms"),
    "post_treatment_followup": ("treatment", "follow-up", "follow up", "healing", "symptoms"),
    "general_inquiry_response": ("hello", "question", "inquiry", "thank"),
    "general_inquiry": ("hello", "question", "inquiry", "thank"),
    "denial_followup": ("denial", "appeal", "claim", "reconsideration"),
}

_DISALLOWED_ROLE_MARKERS: tuple[str, ...] = (
    "as an ai",
    "as a language model",
    "i am an ai",
    "i'm an ai",
    "cannot access your records directly",
)

_FIRST_PERSON_PRACTICE_RE = re.compile(r"(?i)\b(we|our|us)\b")

_GREETING_PATTERN = re.compile(
    r"(?mi)^\s*(dear|hello|hi|good\s+(morning|afternoon|evening))\b"
)
_SUBJECT_PATTERN = re.compile(r"(?mi)^\s*subject\s*:\s*\S+")
_CLOSING_PATTERN = re.compile(
    r"(?mi)\b(sincerely|best regards|regards|thank you|warm regards)\b"
)
_SIGNATURE_PATTERN = re.compile(
    r"(?mi)\b(siligent dental|provider team|our practice)\b"
)


def normalize_purpose_label(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def resolve_purpose_instruction(purpose_label: str) -> str:
    normalized = normalize_purpose_label(purpose_label)
    return _PURPOSE_INSTRUCTIONS.get(
        normalized,
        "Write a clear patient-ready message that stays focused on the requested email purpose.",
    )


def build_enforced_email_prompt(
    *,
    base_prompt: str,
    purpose_label: str,
    purpose_instruction: str | None = None,
) -> str:
    rule = purpose_instruction or resolve_purpose_instruction(purpose_label)
    return (
        "SYSTEM ENFORCEMENT (NON-NEGOTIABLE):\n"
        f"- Identity lock: You are the logged-in provider user at {PRACTICE_ROLE}.\n"
        "- You are not describing this user; you are this user while drafting.\n"
        "- Write only as this user and never step outside this role.\n"
        "- Voice: Use practice voice (we/our practice) and professional patient-facing language.\n"
        f"- Required purpose: {purpose_label}.\n"
        f"- Purpose enforcement: {rule}\n"
        "- If key details are missing, ask concise follow-up questions while staying within that purpose.\n"
        "- Do not mention AI, model limitations, or internal system behavior.\n"
        "- Output only final email text.\n\n"
        "BASE TEMPLATE INSTRUCTIONS:\n"
        f"{base_prompt}"
    )


def is_role_and_purpose_compliant(
    *,
    draft: str,
    purpose_label: str,
) -> bool:
    text = draft.strip()
    if not text:
        return False

    lowered = text.lower()
    if any(marker in lowered for marker in _DISALLOWED_ROLE_MARKERS):
        return False
    if not _FIRST_PERSON_PRACTICE_RE.search(text):
        return False

    normalized_purpose = normalize_purpose_label(purpose_label)
    keywords = _PURPOSE_KEYWORDS.get(normalized_purpose, ())
    if keywords and not any(keyword in lowered for keyword in keywords):
        return False
    if not _has_required_email_structure(text):
        return False
    return True


def _has_required_email_structure(text: str) -> bool:
    if not _SUBJECT_PATTERN.search(text):
        return False
    if not _GREETING_PATTERN.search(text):
        return False
    if not _CLOSING_PATTERN.search(text):
        return False
    if not _SIGNATURE_PATTERN.search(text):
        return False
    return True


def build_rewrite_prompt(
    *,
    base_prompt: str,
    draft: str,
    purpose_label: str,
    purpose_instruction: str | None = None,
) -> str:
    rule = purpose_instruction or resolve_purpose_instruction(purpose_label)
    return (
        "The previous draft did not fully comply with role/purpose constraints.\n"
        f"Rewrite it as the logged-in provider user at {PRACTICE_ROLE}.\n"
        "Do not narrate about the role; write directly from that role.\n"
        f"Required purpose: {purpose_label}\n"
        f"Purpose rule: {rule}\n"
        "Required email structure: Subject line, greeting, clear body, next step, and professional sign-off.\n"
        "Keep factual details that already exist. Do not add new facts.\n"
        "Use clear patient-facing language and output final email text only.\n\n"
        "ORIGINAL TEMPLATE INSTRUCTIONS:\n"
        f"{base_prompt}\n\n"
        "DRAFT TO REWRITE:\n"
        f"{draft}"
    )


def generate_with_guardrails(
    *,
    ollama_client: object,
    base_prompt: str,
    model_name: str | None,
    purpose_label: str,
    purpose_instruction: str | None = None,
    images: list[str] | None = None,
    rewrite_attempts: int = 1,
) -> str:
    guarded_prompt = build_enforced_email_prompt(
        base_prompt=base_prompt,
        purpose_label=purpose_label,
        purpose_instruction=purpose_instruction,
    )
    draft = ollama_client.generate(
        guarded_prompt,
        model_name=model_name,
        images=images if images else None,
    )
    if is_role_and_purpose_compliant(draft=draft, purpose_label=purpose_label):
        return draft

    attempts = max(0, int(rewrite_attempts))
    rewritten = draft
    for _ in range(attempts):
        rewrite_prompt = build_rewrite_prompt(
            base_prompt=base_prompt,
            draft=rewritten,
            purpose_label=purpose_label,
            purpose_instruction=purpose_instruction,
        )
        rewritten = ollama_client.generate(
            rewrite_prompt,
            model_name=model_name,
            images=images if images else None,
        )
        if is_role_and_purpose_compliant(draft=rewritten, purpose_label=purpose_label):
            return rewritten
    return rewritten


def purpose_catalog() -> Mapping[str, str]:
    return dict(_PURPOSE_INSTRUCTIONS)
