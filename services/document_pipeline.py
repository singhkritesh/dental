from __future__ import annotations

import base64
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from pypdf import PdfReader
except ModuleNotFoundError:  # pragma: no cover - environment dependent
    PdfReader = None  # type: ignore[assignment]

from services.errors import AppError
from services.prompt_registry import resolve_document_pipeline_prompt
from services.prompt_engine import compose_prompt
from services.verification import extract_json_object


MAX_UPLOAD_FILES = 3
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES_FOR_LLM = 4 * 1024 * 1024

TEXT_EXTENSIONS = {
    ".txt",
    ".eml",
    ".md",
    ".csv",
    ".json",
    ".log",
    ".xml",
    ".yaml",
    ".yml",
    ".rtf",
}
DOCUMENT_EXTENSIONS = {".docx", ".pdf"}
IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".heic",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".gif",
}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
LOW_SIGNAL_TEXTS = {
    "",
    "n/a",
    "none",
    "not provided",
    "document response",
    "generated draft",
    "draft",
}

_SUBJECT_RE = re.compile(r"(?mi)^\s*subject\s*:\s*\S+")
_GREETING_RE = re.compile(r"(?mi)^\s*(dear|hello|hi|good\s+(morning|afternoon|evening))\b")
_CLOSING_RE = re.compile(r"(?mi)\b(sincerely|best regards|regards|thank you|warm regards)\b")
_SIGNATURE_RE = re.compile(r"(?mi)\b(siligent dental|front[- ]office|our practice)\b")
_SALUTATION_RE = re.compile(r"(?mi)^\s*dear\s+.+,")
_RE_LINE_RE = re.compile(r"(?mi)^\s*re\s*:\s*.+")
_BULLET_LINE_RE = re.compile(r"^\s*[-*]\s+")


@dataclass(frozen=True)
class PreparedDocument:
    upload_id: str
    original_name: str
    content_type: str
    size_bytes: int
    extension: str
    extracted_text: str
    image_base64_list: list[str]


@dataclass(frozen=True)
class ExtractedDocumentContent:
    original_name: str
    content_type: str
    size_bytes: int
    extension: str
    extracted_text: str
    image_base64_list: list[str]


def _safe_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def validate_upload_constraints(file_count: int) -> None:
    if file_count < 1:
        raise AppError(
            code="INVALID_FILE_COUNT",
            message="Upload at least one document.",
            status_code=400,
        )
    if file_count > MAX_UPLOAD_FILES:
        raise AppError(
            code="INVALID_FILE_COUNT",
            message=f"A maximum of {MAX_UPLOAD_FILES} files is allowed per generation.",
            status_code=400,
        )


def _decode_text_payload(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("latin-1", errors="ignore")
    return text.strip()


def _extract_text_from_docx(payload: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            content = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise AppError(
            code="UNSUPPORTED_FILE_CONTENT",
            message="Unable to read .docx content.",
            status_code=400,
        ) from exc

    root = ET.fromstring(content)
    texts: list[str] = []
    for node in root.iter():
        if node.tag.endswith("}t") and node.text:
            texts.append(node.text)
    return "\n".join(texts).strip()


def _extract_text_from_pdf(payload: bytes) -> str:
    if PdfReader is None:
        raise AppError(
            code="UNSUPPORTED_FILE_CONTENT",
            message="PDF support is unavailable in this environment.",
            status_code=400,
        )
    try:
        reader = PdfReader(io.BytesIO(payload))
    except Exception as exc:  # pragma: no cover - depends on malformed input
        raise AppError(
            code="UNSUPPORTED_FILE_CONTENT",
            message="Unable to read PDF content.",
            status_code=400,
        ) from exc

    parts: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text.strip():
            parts.append(page_text.strip())
    return "\n\n".join(parts).strip()


def _extract_pdf_images_base64(payload: bytes, max_images: int = 3) -> list[str]:
    if PdfReader is None:
        return []
    try:
        reader = PdfReader(io.BytesIO(payload))
    except Exception:
        return []

    images: list[str] = []
    for page in reader.pages:
        try:
            page_images = getattr(page, "images", [])
        except Exception:
            page_images = []
        for image in page_images:
            try:
                image_bytes = image.data
            except Exception:
                continue
            if not image_bytes:
                continue
            if len(image_bytes) > MAX_IMAGE_BYTES_FOR_LLM:
                continue
            images.append(base64.b64encode(image_bytes).decode("ascii"))
            if len(images) >= max_images:
                return images
    return images


def _extract_text_from_rtf(payload: bytes) -> str:
    text = _decode_text_payload(payload)
    text = re.sub(r"\\par[d]?", "\n", text)
    text = re.sub(r"\\'[0-9a-fA-F]{2}", " ", text)
    text = re.sub(r"\\[a-zA-Z]+\d* ?", " ", text)
    text = re.sub(r"[{}]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_text_from_payload(filename: str, payload: bytes) -> str:
    extension = _safe_extension(filename)
    if extension in IMAGE_EXTENSIONS:
        return ""
    if extension in {".docx"}:
        return _extract_text_from_docx(payload)
    if extension in {".pdf"}:
        return _extract_text_from_pdf(payload)
    if extension in {".rtf"}:
        return _extract_text_from_rtf(payload)
    if extension in TEXT_EXTENSIONS:
        return _decode_text_payload(payload)
    raise AppError(
        code="UNSUPPORTED_FILE_TYPE",
        message=f"File type is not supported: {extension or '<none>'}",
        status_code=400,
    )


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text.lower())
        if len(token) >= 3
    }


def _score_similarity(context: str, template_text: str) -> float:
    context_tokens = _tokenize(context)
    template_tokens = _tokenize(template_text)
    if not context_tokens or not template_tokens:
        return 0.0
    overlap = len(context_tokens & template_tokens)
    return overlap / max(1, len(context_tokens))


def build_document_context(documents: list[PreparedDocument], *, max_chars: int = 14_000) -> str:
    chunks: list[str] = []
    for doc in documents:
        prefix = f"[Document: {doc.original_name}]"
        text = doc.extracted_text.strip()
        if text:
            chunk = f"{prefix}\n{text}"
        else:
            chunk = f"{prefix}\n(No extracted text available.)"
        chunks.append(chunk)
    joined = "\n\n".join(chunks).strip()
    return joined[:max_chars]


def heuristic_detect_template_type(context_text: str, available_types: list[str]) -> tuple[str, float, str]:
    text = context_text.lower()
    keyword_map = [
        ("comprehensive_investment_letter", ["payment options", "orthodontic treatment", "down payment", "retention"]),
        ("invisalign_investment_letter", ["invisalign", "care credit", "monthly payment", "retention"]),
        ("new_patient_forms_sms", ["new patient forms", "fill out", "intake", "arrive"]),
        ("health_history_update_sms", ["health history", "insurance information", "update"]),
        ("appointment_reminder_sms", ["friendly reminder", "appointment reminder", "appt"]),
        ("appointment_confirmation_sms", ["reply c", "confirm", "stoptooptout"]),
        ("rebuttal_letter", ["appeal", "reconsider", "denial", "claim", "payer"]),
        ("denial_letter", ["denial", "co-", "appeal", "insurance"]),
        ("appointment_confirmation", ["appointment", "scheduled", "confirm", "visit"]),
        ("insurance_verification", ["coverage", "member id", "copay", "prior auth"]),
        ("email", ["dear", "hello", "regards", "thanks"]),
    ]
    for template_type, keywords in keyword_map:
        if template_type not in available_types:
            continue
        if any(keyword in text for keyword in keywords):
            return template_type, 0.66, "Keyword heuristic match."
    fallback = available_types[0] if available_types else "email"
    return fallback, 0.4, "Fallback selection due to low-signal input."


def detect_template_type_with_model(
    *,
    prompts_dir: Path,
    ollama_client: object,
    model_name: str,
    available_types: list[str],
    documents: list[PreparedDocument],
) -> tuple[str, float, str]:
    context = build_document_context(documents, max_chars=8_000)
    images: list[str] = []
    for doc in documents:
        images.extend(doc.image_base64_list)
    images = images[:3]
    try:
        prompt = compose_prompt(
            prompts_dir,
            resolve_document_pipeline_prompt("detect_template_type"),
            {
                "available_types": ", ".join(available_types),
                "context_text": context,
            },
        )
        raw = ollama_client.generate(
            prompt,
            model_name=model_name,
            images=images if images else None,
        )
        payload = extract_json_object(raw)
        detected_type = str(payload.get("detected_type", "")).strip().lower()
        confidence_raw = payload.get("confidence", 0.5)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.5
        rationale = str(payload.get("rationale", "Model classification")).strip() or "Model classification"
        if detected_type in available_types:
            return detected_type, max(0.0, min(confidence, 1.0)), rationale
    except Exception:
        pass
    return heuristic_detect_template_type(context, available_types)


def recommend_templates(
    *,
    templates: list[dict[str, Any]],
    detected_template_type: str,
    context_text: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    context_tokens = _tokenize(context_text)
    detected_type = detected_template_type.strip().lower()
    ranked: list[dict[str, Any]] = []
    for item in templates:
        template_type = str(item.get("type", ""))
        template_tags = [
            str(tag).strip().lower()
            for tag in item.get("tags", [])
            if str(tag).strip()
        ]
        base_score = _score_similarity(
            context_text,
            f"{item.get('name', '')}\n{item.get('content', '')}\n{' '.join(template_tags)}",
        )
        if template_type == detected_type:
            base_score += 0.35
        if detected_type and detected_type in template_tags:
            base_score += 0.18
        if context_tokens and template_tags:
            base_score += 0.08 * len(context_tokens & set(template_tags))
        ranked.append(
            {
                "index": int(item.get("index", -1)),
                "name": str(item.get("name", "")),
                "type": template_type,
                "content": str(item.get("content", "")),
                "tags": template_tags,
                "score": round(base_score, 4),
                "reason": "Template type, tag alignment, and content similarity.",
            }
        )

    ranked.sort(key=lambda row: row["score"], reverse=True)
    return ranked[:limit]


def normalize_structured_output(raw: dict[str, Any]) -> dict[str, Any]:
    title = str(raw.get("title", "")).strip() or "Generated Draft"
    purpose = str(raw.get("purpose", "")).strip() or "Document response"
    final_draft = str(raw.get("final_draft", "")).strip()

    key_points_raw = raw.get("key_points", [])
    key_points: list[str] = []
    if isinstance(key_points_raw, list):
        key_points = [str(item).strip() for item in key_points_raw if str(item).strip()]
    elif isinstance(key_points_raw, str) and key_points_raw.strip():
        key_points = [key_points_raw.strip()]

    sections_raw = raw.get("sections", [])
    sections: list[dict[str, str]] = []
    if isinstance(sections_raw, list):
        for item in sections_raw:
            if not isinstance(item, dict):
                continue
            heading = str(item.get("heading", "")).strip()
            content = str(item.get("content", "")).strip()
            if heading and content:
                sections.append({"heading": heading, "content": content})

    action_items_raw = raw.get("action_items", [])
    action_items: list[str] = []
    if isinstance(action_items_raw, list):
        action_items = [str(item).strip() for item in action_items_raw if str(item).strip()]

    if not final_draft:
        section_text = "\n\n".join(
            [f"{item['heading']}\n{item['content']}" for item in sections]
        ).strip()
        final_draft = section_text or purpose

    return {
        "title": title,
        "purpose": purpose,
        "key_points": key_points,
        "sections": sections,
        "action_items": action_items,
        "final_draft": final_draft,
    }


def _is_low_signal_text(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    if normalized in LOW_SIGNAL_TEXTS:
        return True
    return len(normalized) < 12


def _is_summary_bullet_draft(value: str) -> bool:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    bullet_count = sum(1 for line in lines if _BULLET_LINE_RE.match(line))
    if bullet_count < 3:
        return False
    if bullet_count < max(3, int(len(lines) * 0.6)):
        return False
    return not _SUBJECT_RE.search(value)


def _is_draft_structurally_valid(*, template_type: str, final_draft: str) -> bool:
    if _is_low_signal_text(final_draft):
        return False
    if _is_summary_bullet_draft(final_draft):
        return False

    normalized_type = template_type.strip().lower()
    text = final_draft.strip()
    if normalized_type == "email":
        return bool(
            _SUBJECT_RE.search(text)
            and _GREETING_RE.search(text)
            and _CLOSING_RE.search(text)
            and _SIGNATURE_RE.search(text)
        )
    if normalized_type in {"denial_letter", "rebuttal_letter"}:
        has_date = bool(re.search(r"(?m)^\s*\d{4}-\d{2}-\d{2}\s*$", text)) or bool(
            re.search(r"(?mi)\b(january|february|march|april|may|june|july|august|september|october|november|december)\b", text)
        )
        return bool(
            has_date
            and _RE_LINE_RE.search(text)
            and _SALUTATION_RE.search(text)
            and _CLOSING_RE.search(text)
        )
    return bool(_GREETING_RE.search(text) and _CLOSING_RE.search(text))


def _repair_final_draft(
    *,
    prompts_dir: Path,
    ollama_client: object,
    model_name: str,
    detected_template_type: str,
    context_text: str,
    template_content: str,
    final_draft: str,
    images: list[str] | None = None,
) -> str:
    prompt = compose_prompt(
        prompts_dir,
        resolve_document_pipeline_prompt("repair_final_draft"),
        {
            "detected_template_type": detected_template_type,
            "context_text": context_text[:10_000],
            "template_content": template_content[:3000] or "No selected template guidance.",
            "final_draft": final_draft[:6000],
        },
    )
    repaired = ollama_client.generate(
        prompt,
        model_name=model_name,
        images=images if images else None,
    )
    return repaired.strip()


def _extract_context_sentences(context_text: str, *, limit: int = 8) -> list[str]:
    cleaned = context_text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\[Document:[^\]]+\]", " ", cleaned)
    cleaned = re.sub(r"Runtime fields:[\s\S]*$", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(No extracted text available\.\)", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    output: list[str] = []
    seen: set[str] = set()
    for part in parts:
        sentence = part.strip(" -•\n\t")
        if not sentence:
            continue
        if len(sentence) < 18:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(sentence[:240])
        if len(output) >= limit:
            break
    return output


def _default_title_and_purpose(detected_template_type: str) -> tuple[str, str]:
    template_type = detected_template_type.strip().lower()
    if template_type == "appointment_confirmation_sms":
        return (
            "Appointment Confirmation SMS Draft",
            "Draft a concise SMS confirmation with appointment details and opt-out text.",
        )
    if template_type == "appointment_reminder_sms":
        return (
            "Appointment Reminder SMS Draft",
            "Draft a concise reminder SMS with appointment details and opt-out text.",
        )
    if template_type == "health_history_update_sms":
        return (
            "Health History Update SMS Draft",
            "Draft a concise SMS asking the patient to update health history before the visit.",
        )
    if template_type == "new_patient_forms_sms":
        return (
            "New Patient Forms SMS Draft",
            "Draft a concise SMS asking the patient to complete forms before the appointment.",
        )
    if template_type == "comprehensive_investment_letter":
        return (
            "Comprehensive Investment Letter",
            "Prepare a structured comprehensive orthodontic treatment investment and payment options letter.",
        )
    if template_type == "invisalign_investment_letter":
        return (
            "Invisalign Investment Letter",
            "Prepare a structured Invisalign treatment investment and payment options letter.",
        )
    if template_type == "email":
        return (
            "Email Draft",
            "Compose a clear email using facts from the uploaded documents.",
        )
    if template_type in {"rebuttal_letter", "denial_letter"}:
        return (
            "Appeal / Rebuttal Draft",
            "Prepare a structured appeal response using the uploaded case details.",
        )
    if template_type == "appointment_confirmation":
        return (
            "Appointment Confirmation Draft",
            "Draft a confirmation message with appointment-ready details.",
        )
    if template_type == "insurance_verification":
        return (
            "Insurance Verification Summary",
            "Summarize verification findings from provided payer and patient data.",
        )
    return (
        "Generated Draft",
        "Generate a structured communication draft from uploaded material.",
    )


def _build_fallback_sections(
    *,
    detected_template_type: str,
    key_points: list[str],
    context_sentences: list[str],
) -> list[dict[str, str]]:
    summary_sentences = context_sentences[:3]
    if not summary_sentences:
        summary_sentences = ["No clear source text was extracted from the uploaded documents."]
    summary_text = " ".join(summary_sentences)

    template_type = detected_template_type.strip().lower()
    if template_type == "email":
        draft_lines = [
            "Subject: Follow-up on Submitted Document",
            "",
            "Hello,",
            "",
            "Thank you for sharing the document. Here is a concise summary:",
        ]
        for point in key_points[:4]:
            draft_lines.append(f"- {point}")
        draft_lines.extend(
            [
                "",
                "Please let us know if you want this rewritten for a specific recipient or use case.",
                "",
                "Best regards,",
                "Siligent Dental Provider Team",
            ]
        )
        return [
            {"heading": "Document Summary", "content": summary_text},
            {"heading": "Draft Email", "content": "\n".join(draft_lines).strip()},
        ]

    if template_type in {"rebuttal_letter", "denial_letter"}:
        content = "\n".join(
            [
                "This draft references the uploaded case details and supporting facts:",
                *[f"- {point}" for point in key_points[:5]],
            ]
        )
        return [
            {"heading": "Case Summary", "content": summary_text},
            {"heading": "Draft Body", "content": content},
        ]

    return [
        {"heading": "Summary", "content": summary_text},
        {
            "heading": "Draft",
            "content": "\n".join([f"- {point}" for point in key_points[:5]]) or summary_text,
        },
    ]


def _provider_safe_appointment_fallback() -> str:
    return "\n".join(
        [
            "Subject: Appointment Confirmation - Not provided",
            "",
            "Dear Not provided,",
            "",
            "This is to confirm your appointment on Not provided at Not provided.",
            "Provider: Not provided",
            "Location: Not provided",
            "",
            "Please arrive Not provided and bring Not provided.",
            "",
            "If you need to reschedule, contact us at Not provided.",
            "",
            "Sincerely,",
            "Siligent Dental Provider Team",
        ]
    ).strip()


def stabilize_structured_output(
    *,
    structured: dict[str, Any],
    detected_template_type: str,
    context_text: str,
) -> dict[str, Any]:
    title, purpose = _default_title_and_purpose(detected_template_type)

    raw_title = str(structured.get("title", "")).strip()
    if not _is_low_signal_text(raw_title):
        title = raw_title

    raw_purpose = str(structured.get("purpose", "")).strip()
    if not _is_low_signal_text(raw_purpose):
        purpose = raw_purpose

    key_points = [
        str(item).strip()
        for item in structured.get("key_points", [])
        if str(item).strip()
    ]
    context_sentences = _extract_context_sentences(context_text)
    for sentence in context_sentences:
        if len(key_points) >= 5:
            break
        if sentence.lower() in {item.lower() for item in key_points}:
            continue
        key_points.append(sentence)

    if not key_points:
        key_points = ["No concrete details were extracted from the uploaded documents."]

    sections_raw = structured.get("sections", [])
    sections: list[dict[str, str]] = []
    if isinstance(sections_raw, list):
        for item in sections_raw:
            if not isinstance(item, dict):
                continue
            heading = str(item.get("heading", "")).strip()
            content = str(item.get("content", "")).strip()
            if not heading or not content or _is_low_signal_text(content):
                continue
            sections.append({"heading": heading, "content": content})

    if not sections:
        sections = _build_fallback_sections(
            detected_template_type=detected_template_type,
            key_points=key_points,
            context_sentences=context_sentences,
        )

    action_items = [
        str(item).strip()
        for item in structured.get("action_items", [])
        if str(item).strip()
    ]
    if not action_items:
        action_items = [
            "Review the draft for factual accuracy against source files.",
            "Edit recipient-specific names, dates, and identifiers before sending.",
        ]

    final_draft = str(structured.get("final_draft", "")).strip()
    if _is_low_signal_text(final_draft):
        section_text = "\n\n".join(
            [f"{item['heading']}\n{item['content']}" for item in sections]
        ).strip()
        final_draft = section_text or "No draft text available."

    # Guard against invented appointment details when no factual context is available.
    if detected_template_type.strip().lower() == "appointment_confirmation" and not context_sentences:
        final_draft = _provider_safe_appointment_fallback()

    return {
        "title": title,
        "purpose": purpose,
        "key_points": key_points[:5],
        "sections": sections,
        "action_items": action_items[:6],
        "final_draft": final_draft,
    }


def generate_structured_output(
    *,
    prompts_dir: Path,
    ollama_client: object,
    model_name: str,
    detected_template_type: str,
    context_text: str,
    template_content: str,
    documents: list[PreparedDocument],
) -> dict[str, Any]:
    images: list[str] = []
    for doc in documents:
        images.extend(doc.image_base64_list)
    images = images[:3]
    prompt = compose_prompt(
        prompts_dir,
        resolve_document_pipeline_prompt("structured_output"),
        {
            "detected_template_type": detected_template_type,
            "template_content": template_content[:3000],
            "context_text": context_text,
        },
    )
    raw = ollama_client.generate(
        prompt,
        model_name=model_name,
        images=images if images else None,
    )
    payload = extract_json_object(raw)
    normalized = normalize_structured_output(payload)
    stabilized = stabilize_structured_output(
        structured=normalized,
        detected_template_type=detected_template_type,
        context_text=context_text,
    )
    candidate = str(stabilized.get("final_draft", "")).strip()
    if _is_draft_structurally_valid(
        template_type=detected_template_type,
        final_draft=candidate,
    ):
        return stabilized

    try:
        repaired = _repair_final_draft(
            prompts_dir=prompts_dir,
            ollama_client=ollama_client,
            model_name=model_name,
            detected_template_type=detected_template_type,
            context_text=context_text,
            template_content=template_content,
            final_draft=candidate,
            images=images if images else None,
        )
    except Exception:
        return stabilized

    if _is_draft_structurally_valid(
        template_type=detected_template_type,
        final_draft=repaired,
    ):
        stabilized["final_draft"] = repaired
    return stabilized


def extract_document_content(
    *,
    filename: str,
    content_type: str,
    payload: bytes,
) -> ExtractedDocumentContent:
    if not payload:
        raise AppError(
            code="INVALID_FILE",
            message=f"Uploaded file is empty: {filename}",
            status_code=400,
        )
    extension = _safe_extension(filename)
    if extension not in SUPPORTED_EXTENSIONS:
        raise AppError(
            code="UNSUPPORTED_FILE_TYPE",
            message=f"Unsupported file type: {extension or '<none>'}",
            status_code=400,
        )
    if len(payload) > MAX_FILE_SIZE_BYTES:
        raise AppError(
            code="FILE_TOO_LARGE",
            message="File exceeds size limit (20MB).",
            status_code=400,
        )

    extracted_text = extract_text_from_payload(filename, payload)
    image_base64_list: list[str] = []
    if extension in IMAGE_EXTENSIONS:
        if len(payload) <= MAX_IMAGE_BYTES_FOR_LLM:
            image_base64_list = [base64.b64encode(payload).decode("ascii")]
    elif extension == ".pdf":
        image_base64_list = _extract_pdf_images_base64(payload, max_images=3)

    return ExtractedDocumentContent(
        original_name=filename,
        content_type=content_type,
        size_bytes=len(payload),
        extension=extension,
        extracted_text=extracted_text[:30_000],
        image_base64_list=image_base64_list,
    )
