from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from services.document_pipeline import _score_similarity, _tokenize
from services.email_guardrails import generate_with_guardrails, has_missing_data_markers
from services.prompt_registry import resolve_email_thread_prompt
from services.prompt_engine import compose_prompt
from services.template_runtime import runtime_fields_to_json_context
from services.verification import extract_json_object

MAX_THREAD_CHARS = 18_000
MAX_LATEST_CHARS = 8_000


@dataclass(frozen=True)
class EmailThreadAnalysis:
    intent: str
    confidence: float
    urgency: str
    tone: str
    thread_summary: str
    latest_message: str
    extracted_entities: dict[str, str]
    missing_fields: list[str]
    risk_flags: list[str]
    recommended_action: str


def normalize_email_thread(raw_text: str, *, max_chars: int = MAX_THREAD_CHARS) -> str:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()[:max_chars]


def extract_latest_message(thread_text: str, *, max_chars: int = MAX_LATEST_CHARS) -> str:
    normalized = normalize_email_thread(thread_text)
    lines = normalized.split("\n")
    latest: list[str] = []

    break_patterns = [
        re.compile(r"^-----\s*Original Message\s*-----", re.IGNORECASE),
        re.compile(r"^On .+ wrote:\s*$", re.IGNORECASE),
        re.compile(r"^From:\s+.+", re.IGNORECASE),
        re.compile(r"^Sent:\s+.+", re.IGNORECASE),
    ]
    signature_patterns = [
        re.compile(r"^--\s*$"),
        re.compile(r"^Sent from my .+", re.IGNORECASE),
        re.compile(r"^Get Outlook for .+", re.IGNORECASE),
    ]

    for line in lines:
        stripped = line.strip()
        if any(pattern.match(stripped) for pattern in break_patterns):
            break
        if any(pattern.match(stripped) for pattern in signature_patterns):
            break
        if stripped.startswith(">"):
            continue
        latest.append(line)

    latest_text = "\n".join(latest).strip()
    return (latest_text or normalized)[:max_chars]


def build_email_thread_context(
    *,
    thread_text: str,
    runtime_fields: Mapping[str, str] | None = None,
) -> str:
    cleaned_thread = normalize_email_thread(thread_text)
    runtime_json = runtime_fields_to_json_context(runtime_fields)
    if runtime_json:
        return (
            "[Email Thread Text]\n"
            f"{cleaned_thread}\n\n"
            "[Structured Runtime Context JSON]\n"
            f"{runtime_json}"
        )
    return f"[Email Thread Text]\n{cleaned_thread}"


def _normalize_intent(raw_value: str) -> str:
    value = re.sub(r"\s+", "_", raw_value.strip().lower())
    value = re.sub(r"[^a-z0-9_-]", "", value)
    return value.strip("_") or "general_inquiry"


def _coerce_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce_entities(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, raw in value.items():
        clean_key = str(key).strip()
        clean_value = str(raw).strip()
        if clean_key and clean_value:
            normalized[clean_key] = clean_value
    return normalized


def normalize_email_thread_analysis(raw: dict[str, Any], *, fallback_text: str) -> EmailThreadAnalysis:
    confidence_raw = raw.get("confidence", 0.45)
    try:
        confidence = float(confidence_raw)
    except (TypeError, ValueError):
        confidence = 0.45

    latest = str(raw.get("latest_message", "")).strip() or extract_latest_message(fallback_text)
    summary = str(raw.get("thread_summary", "")).strip()
    if not summary:
        summary = _summarize_heuristically(fallback_text)

    return EmailThreadAnalysis(
        intent=_normalize_intent(str(raw.get("intent", "general_inquiry"))),
        confidence=max(0.0, min(confidence, 1.0)),
        urgency=str(raw.get("urgency", "normal")).strip().lower() or "normal",
        tone=str(raw.get("tone", "professional")).strip().lower() or "professional",
        thread_summary=summary,
        latest_message=latest,
        extracted_entities=_coerce_entities(raw.get("extracted_entities", {})),
        missing_fields=_coerce_str_list(raw.get("missing_fields", [])),
        risk_flags=_coerce_str_list(raw.get("risk_flags", [])),
        recommended_action=str(raw.get("recommended_action", "Draft a reply for staff review.")).strip()
        or "Draft a reply for staff review.",
    )


def _summarize_heuristically(thread_text: str) -> str:
    latest = extract_latest_message(thread_text)
    collapsed = re.sub(r"\s+", " ", latest).strip()
    if len(collapsed) <= 500:
        return collapsed
    return f"{collapsed[:497]}..."


def heuristic_analyze_email_thread(thread_text: str) -> EmailThreadAnalysis:
    latest = extract_latest_message(thread_text)
    text = latest.lower()
    intent = "general_inquiry"
    risk_flags: list[str] = []
    missing_fields: list[str] = []
    urgency = "normal"

    keyword_intents = [
        ("billing_inquiry", ["balance", "bill", "invoice", "owe", "payment", "charge"]),
        ("insurance_update", ["insurance", "coverage", "member id", "claim", "payer", "eob"]),
        ("appointment_confirmation", ["appointment", "schedule", "reschedule", "cancel", "confirm"]),
        ("records_request", ["records", "x-ray", "xray", "referral", "release"]),
        ("post_treatment_followup", ["pain", "swelling", "bleeding", "medication", "procedure"]),
        ("denial_followup", ["denied", "denial", "appeal", "reconsideration"]),
    ]
    for candidate, keywords in keyword_intents:
        if any(keyword in text for keyword in keywords):
            intent = candidate
            break

    if any(word in text for word in ["pain", "bleeding", "swelling", "emergency"]):
        urgency = "high"
        risk_flags.append("clinical_review")
    if any(word in text for word in ["angry", "frustrated", "upset", "complaint"]):
        risk_flags.append("service_escalation")
    if intent in {"insurance_update", "billing_inquiry"} and "patient_name" not in text:
        missing_fields.append("patient_name")

    return EmailThreadAnalysis(
        intent=intent,
        confidence=0.55,
        urgency=urgency,
        tone="professional",
        thread_summary=_summarize_heuristically(thread_text),
        latest_message=latest,
        extracted_entities={},
        missing_fields=missing_fields,
        risk_flags=risk_flags,
        recommended_action="Draft a reply for staff review.",
    )


def analyze_email_thread_with_model(
    *,
    prompts_dir: Path,
    ollama_client: object,
    model_name: str,
    thread_text: str,
    runtime_fields: Mapping[str, str] | None = None,
    images: list[str] | None = None,
) -> EmailThreadAnalysis:
    context = build_email_thread_context(
        thread_text=thread_text,
        runtime_fields=runtime_fields,
    )
    try:
        prompt = compose_prompt(
            prompts_dir,
            resolve_email_thread_prompt("analyze_thread"),
            {
                "thread_context": context,
            },
        )
        raw = ollama_client.generate(
            prompt,
            model_name=model_name,
            images=images if images else None,
        )
        payload = extract_json_object(raw)
        return normalize_email_thread_analysis(payload, fallback_text=thread_text)
    except Exception:
        return heuristic_analyze_email_thread(thread_text)


def recommend_email_templates(
    *,
    templates: list[dict[str, Any]],
    analysis: EmailThreadAnalysis,
    context_text: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    intent = analysis.intent.strip().lower()
    context_tokens = _tokenize(context_text)
    ranked: list[dict[str, Any]] = []
    for item in templates:
        template_type = str(item.get("type", "")).strip().lower()
        template_tags = [
            str(tag).strip().lower()
            for tag in item.get("tags", [])
            if str(tag).strip()
        ]
        content = str(item.get("content", ""))
        base_score = _score_similarity(
            f"{analysis.intent}\n{analysis.thread_summary}\n{context_text}",
            f"{item.get('name', '')}\n{content}\n{' '.join(template_tags)}",
        )
        if template_type in {"email", intent}:
            base_score += 0.35
        if intent and (intent in template_type or template_type in intent):
            base_score += 0.15
        if intent and intent in template_tags:
            base_score += 0.2
        if context_tokens and template_tags:
            base_score += 0.08 * len(context_tokens & set(template_tags))
        ranked.append(
            {
                "index": int(item.get("index", -1)),
                "name": str(item.get("name", "")),
                "type": template_type,
                "content": content,
                "tags": template_tags,
                "score": round(base_score, 4),
                "reason": "Email intent, tag alignment, and thread similarity.",
            }
        )
    ranked.sort(key=lambda row: row["score"], reverse=True)
    return ranked[:limit]


def generate_email_thread_reply(
    *,
    prompts_dir: Path,
    ollama_client: object,
    model_name: str,
    analysis: EmailThreadAnalysis,
    thread_context: str,
    template_content: str,
    runtime_fields: Mapping[str, str] | None = None,
    images: list[str] | None = None,
) -> str:
    prompt = compose_prompt(
        prompts_dir,
        resolve_email_thread_prompt("generate_reply"),
        {
            "analysis_json": json.dumps(analysis.__dict__, ensure_ascii=False),
            "thread_context": thread_context,
            "template_content": template_content[:3000] or "No selected template.",
            "runtime_context": runtime_fields_to_json_context(runtime_fields) or "No runtime patient/account data supplied.",
        },
    )
    return generate_with_guardrails(
        ollama_client=ollama_client,
        base_prompt=prompt,
        model_name=model_name,
        purpose_label=analysis.intent,
        images=images,
        rewrite_attempts=2,
    )


def build_missing_details_followup_email(
    *,
    analysis: EmailThreadAnalysis,
    runtime_fields: Mapping[str, str] | None = None,
) -> str:
    missing = [item for item in analysis.missing_fields if str(item).strip()]
    if not missing:
        missing = ["the details needed to complete your request"]
    missing_lines = "\n".join(f"- {item.replace('_', ' ')}" for item in missing[:6])
    return (
        f"Subject: Follow-up on your request\n\n"
        "Hello,\n\n"
        "Thank you for reaching out to Siligent Dental. We can help with your request, "
        "but we need a little more information before we can complete it accurately.\n\n"
        f"Please send the following:\n{missing_lines}\n\n"
        "Once we receive those details, we will review and follow up with the next step.\n\n"
        "Best regards,\n"
        "Siligent Dental Provider Team"
    )


def ensure_email_reply_has_no_missing_markers(
    *,
    draft: str,
    analysis: EmailThreadAnalysis,
    runtime_fields: Mapping[str, str] | None = None,
) -> str:
    if not has_missing_data_markers(draft):
        return draft
    return build_missing_details_followup_email(
        analysis=analysis,
        runtime_fields=runtime_fields,
    )
