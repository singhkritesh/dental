from __future__ import annotations

"""
Central prompt registry for the application.

This is the single source of truth for:
- Which prompt file is used for each feature/workflow.
- Which email scenario label maps to which prompt file.
- Which prompt keys are used by the pipeline/thread engines.

Prompt path values are relative to `prompts/` and exclude the `.txt` suffix.
Example:
- "emails/general_inquiry" resolves to prompts/emails/general_inquiry.txt
"""

# Email scenario label shown in UI -> prompt file used for generation.
# Purpose: routine outbound/inbound patient-facing email drafts.
EMAIL_SCENARIO_PROMPTS: dict[str, str] = {
    "Appointment Reminder": "emails/appointment_reminder",
    "Cancellation Confirmation": "emails/cancellation_confirmation",
    "Balance Due Notice": "emails/balance_due",
    "Insurance Update Request": "emails/insurance_update_request",
    "Referral Letter": "emails/referral_letter",
    "New Patient Welcome": "emails/new_patient_welcome",
    "Post-Treatment Follow-Up": "emails/post_treatment_followup",
    "General Inquiry Response": "emails/general_inquiry",
}

# Document pipeline prompt files.
# - detect_template_type: classify uploaded docs into the best drafting purpose.
# - structured_output: generate structured output + final draft text.
# - repair_final_draft: rewrite weak/summary-like drafts into production-ready communication format.
DOCUMENT_PIPELINE_PROMPTS: dict[str, str] = {
    "detect_template_type": "document_pipeline/detect_template_type",
    "structured_output": "document_pipeline/structured_output",
    "repair_final_draft": "document_pipeline/repair_final_draft",
}

# Email thread assistant prompt files.
# - analyze_thread: classify intent/risk and extract thread facts.
# - generate_reply: produce the reply draft.
EMAIL_THREAD_PROMPTS: dict[str, str] = {
    "analyze_thread": "email_thread/analyze_thread",
    "generate_reply": "email_thread/generate_reply",
}

# Insurance verification prompt file (structured JSON summary output).
INSURANCE_VERIFICATION_PROMPT = "insurance_verification"

# Denial letter prompt folder. Actual prompt path is:
# f"{DENIAL_PROMPT_PREFIX}/{denial_code}" -> prompts/denial_letters/{denial_code}.txt
DENIAL_PROMPT_PREFIX = "denial_letters"


def list_email_scenarios() -> list[str]:
    return list(EMAIL_SCENARIO_PROMPTS.keys())


def resolve_email_prompt(scenario_label: str) -> str | None:
    return EMAIL_SCENARIO_PROMPTS.get(scenario_label)


def resolve_denial_prompt(denial_code: str) -> str:
    return f"{DENIAL_PROMPT_PREFIX}/{denial_code.strip()}"


def resolve_document_pipeline_prompt(key: str) -> str:
    value = DOCUMENT_PIPELINE_PROMPTS.get(key)
    if not value:
        raise KeyError(f"Unknown document pipeline prompt key: {key}")
    return value


def resolve_email_thread_prompt(key: str) -> str:
    value = EMAIL_THREAD_PROMPTS.get(key)
    if not value:
        raise KeyError(f"Unknown email thread prompt key: {key}")
    return value
