from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ErrorResponse(BaseModel):
    error: bool = True
    message: str
    code: str


class TextResponse(BaseModel):
    text: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_configured: str
    model_available: bool
    available_models: list[str]


class DenialCode(BaseModel):
    code: str
    description: str


class DenialLetterGenerateRequest(BaseModel):
    denial_code: str = Field(min_length=1)
    patient_name: str = Field(min_length=1)
    date_of_service: date
    procedure_description: str = Field(min_length=1)
    procedure_code: str | None = None
    payer_name: str = Field(min_length=1)
    payer_address: str | None = None
    provider_name: str | None = None
    provider_npi: str | None = None
    model_name: str | None = None


class EmailGenerateRequest(BaseModel):
    scenario: str = Field(min_length=1)
    additional_context: str | None = None
    model_name: str | None = None


class TemplateDraftGenerateRequest(BaseModel):
    template_type: str = Field(min_length=1, max_length=60)
    variable_names: list[str] = Field(min_length=1, max_length=40)
    instructions: str | None = Field(default=None, max_length=3000)
    model_name: str | None = None

    @field_validator("template_type")
    @classmethod
    def normalize_template_type(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("variable_names")
    @classmethod
    def validate_variable_names(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            if not text:
                continue
            if len(text) > 80:
                raise ValueError("Variable names must be 80 characters or fewer.")
            lowered = text.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(text)
        if not cleaned:
            raise ValueError("At least one variable name is required.")
        return cleaned


class InsuranceVerificationRequest(BaseModel):
    payer_name: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    group_number: str | None = None
    patient_dob: date
    plan_type: str | None = None
    model_name: str | None = None


class InsuranceVerificationSummary(BaseModel):
    covered_procedures: list[str]
    estimated_copay: str
    prior_authorization_required: str
    annual_maximum: str
    waiting_periods: str
    notable_exclusions_limitations: str


class InsuranceVerificationResponse(BaseModel):
    summary: InsuranceVerificationSummary
    raw_text: str


class TemplateItem(BaseModel):
    index: int
    name: str
    type: str
    content: str
    visibility: Literal["personal", "shared"] = "shared"
    owner_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    placeholders: list[str] = Field(default_factory=list)
    created_at: str


class SaveTemplateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=60)
    content: str = Field(min_length=1)
    visibility: Literal["personal", "shared"] | None = None
    tags: list[str] | None = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        return value.strip().lower()


class SaveTemplateResponse(BaseModel):
    status: Literal["saved"]
    index: int


class DeleteTemplateResponse(BaseModel):
    status: Literal["deleted"]


class UserInfoResponse(BaseModel):
    id: str
    username: str
    role: Literal["admin", "staff"]
    created_at: str


class RegisterUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    role: Literal["admin", "staff"] | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class AuthTokenResponse(BaseModel):
    token: str
    user: UserInfoResponse


class AuthBootstrapResponse(BaseModel):
    bootstrap_required: bool
    auth_enabled: bool


class TemplateTypeRequest(BaseModel):
    template_type: str = Field(min_length=1, max_length=60)


class TemplateTypesResponse(BaseModel):
    template_types: list[str]


class FieldDictionaryEntry(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list)


class FieldDictionaryResponse(BaseModel):
    entries: list[FieldDictionaryEntry]


class FieldDictionaryUpsertRequest(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    aliases: list[str] | None = None


class FieldDictionaryDeleteResponse(BaseModel):
    status: Literal["deleted"]


class ModelPreferencesPayload(BaseModel):
    use_global_model_for_all: bool
    global_model: str
    per_use_case: dict[str, str]


class SourceDocumentInfo(BaseModel):
    upload_id: str
    original_name: str
    content_type: str
    size_bytes: int
    extension: str
    extracted_text_preview: str


class TemplateRecommendation(BaseModel):
    index: int
    name: str
    type: str
    tags: list[str] = Field(default_factory=list)
    score: float
    reason: str


class EmailThreadAnalysis(BaseModel):
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


class EmailThreadGenerateResponse(BaseModel):
    analysis: EmailThreadAnalysis
    selected_model: str
    selected_template_index: int | None = None
    template_placeholders: list[str] = Field(default_factory=list)
    runtime_fields_used: dict[str, str] = Field(default_factory=dict)
    missing_runtime_fields: list[str] = Field(default_factory=list)
    rendered_template_preview: str = ""
    recommended_templates: list[TemplateRecommendation]
    draft: str
    source_documents: list[SourceDocumentInfo]


class StructuredDraft(BaseModel):
    title: str
    purpose: str
    key_points: list[str]
    sections: list[dict[str, str]]
    action_items: list[str]
    final_draft: str


class DocumentPipelineResponse(BaseModel):
    detected_template_type: str
    detection_confidence: float
    detection_rationale: str
    selected_model: str
    template_placeholders: list[str] = Field(default_factory=list)
    runtime_fields_used: dict[str, str] = Field(default_factory=dict)
    missing_runtime_fields: list[str] = Field(default_factory=list)
    rendered_template_preview: str = ""
    recommended_templates: list[TemplateRecommendation]
    structured_output: StructuredDraft
    source_documents: list[SourceDocumentInfo]


class AuditEventItem(BaseModel):
    at: str
    actor_id: str
    action: str
    outcome: str
    details: dict[str, Any]


class AuditEventsResponse(BaseModel):
    events: list[AuditEventItem]
