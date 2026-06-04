export type DenialCode = {
  code: string;
  description: string;
};

export type ApiErrorPayload = {
  error: boolean;
  message: string;
  code: string;
  details?: unknown;
};

export type HealthResponse = {
  status: "ok";
  model_configured: string;
  model_available: boolean;
  available_models: string[];
};

export type TextResponse = {
  text: string;
};

export type InsuranceVerificationSummary = {
  coverage_verdict: string;
  verdict_rationale: string;
  requested_procedure: string;
  requested_condition: string;
  covered_procedures: string[];
  estimated_copay: string;
  prior_authorization_required: string;
  annual_maximum: string;
  waiting_periods: string;
  notable_exclusions_limitations: string;
};

export type InsuranceVerificationResponse = {
  summary: InsuranceVerificationSummary;
  raw_text: string;
};

export type TemplateItem = {
  index: number;
  name: string;
  type: string;
  content: string;
  visibility: "personal" | "shared";
  owner_id: string | null;
  tags: string[];
  placeholders: string[];
  created_at: string;
};

export type SaveTemplateResponse = {
  status: "saved";
  index: number;
};

export type AuthBootstrapResponse = {
  bootstrap_required: boolean;
  auth_enabled: boolean;
};

export type UserInfo = {
  id: string;
  username: string;
  role: "admin" | "staff";
  created_at: string;
};

export type AuthTokenResponse = {
  token: string;
  user: UserInfo;
};

export type ModelPreferences = {
  use_global_model_for_all: boolean;
  global_model: string;
  per_use_case: Record<string, string>;
};

export type TemplateTypesResponse = {
  template_types: string[];
};

export type FieldDictionaryEntry = {
  key: string;
  label: string;
  aliases: string[];
};

export type FieldDictionaryResponse = {
  entries: FieldDictionaryEntry[];
};

export type TemplateRecommendation = {
  index: number;
  name: string;
  type: string;
  tags: string[];
  score: number;
  reason: string;
};

export type EmailThreadAnalysis = {
  intent: string;
  confidence: number;
  urgency: string;
  tone: string;
  thread_summary: string;
  latest_message: string;
  extracted_entities: Record<string, string>;
  missing_fields: string[];
  risk_flags: string[];
  recommended_action: string;
};

export type EmailThreadGenerateResponse = {
  analysis: EmailThreadAnalysis;
  selected_model: string;
  selected_template_index: number | null;
  template_placeholders: string[];
  runtime_fields_used: Record<string, string>;
  missing_runtime_fields: string[];
  rendered_template_preview: string;
  recommended_templates: TemplateRecommendation[];
  draft: string;
  source_documents: SourceDocumentInfo[];
};

export type StructuredDraft = {
  title: string;
  purpose: string;
  key_points: string[];
  sections: Array<{ heading: string; content: string }>;
  action_items: string[];
  final_draft: string;
};

export type SourceDocumentInfo = {
  upload_id: string;
  original_name: string;
  content_type: string;
  size_bytes: number;
  extension: string;
  extracted_text_preview: string;
};

export type DocumentPipelineResponse = {
  detected_template_type: string;
  detection_confidence: number;
  detection_rationale: string;
  selected_model: string;
  template_placeholders: string[];
  runtime_fields_used: Record<string, string>;
  missing_runtime_fields: string[];
  rendered_template_preview: string;
  recommended_templates: TemplateRecommendation[];
  structured_output: StructuredDraft;
  source_documents: SourceDocumentInfo[];
};

export type AuditEventItem = {
  at: string;
  actor_id: string;
  action: string;
  outcome: string;
  details: Record<string, unknown>;
};

export type AuditEventsResponse = {
  events: AuditEventItem[];
};
