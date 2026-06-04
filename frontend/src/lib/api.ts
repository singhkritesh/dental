import type {
  ApiErrorPayload,
  AuditEventsResponse,
  AuthBootstrapResponse,
  AuthTokenResponse,
  DenialCode,
  DocumentPipelineResponse,
  EmailThreadGenerateResponse,
  FieldDictionaryEntry,
  FieldDictionaryResponse,
  HealthResponse,
  InsuranceVerificationResponse,
  ModelPreferences,
  SaveTemplateResponse,
  TemplateItem,
  TemplateTypesResponse,
  TextResponse,
  UserInfo
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const TOKEN_STORAGE_KEY = "siligent_auth_token";

let authToken = window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? "";

export function setAuthToken(token: string) {
  authToken = token.trim();
  if (authToken) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, authToken);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export function clearAuthToken() {
  setAuthToken("");
}

export function getAuthToken() {
  return authToken;
}

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function parseJsonSafely<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  const hasBody = init.body !== undefined && init.body !== null;
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;

  if (!headers.has("Content-Type") && hasBody && !isFormData) {
    headers.set("Content-Type", "application/json");
  }
  if (API_KEY.trim()) {
    headers.set("X-API-Key", API_KEY.trim());
  }
  if (authToken) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const payload = await parseJsonSafely<ApiErrorPayload>(response);
    throw new ApiError(
      response.status,
      payload?.code ?? "HTTP_ERROR",
      payload?.message ?? `Request failed with status ${response.status}`
    );
  }

  if (response.status === 204) {
    return {} as T;
  }
  const json = await parseJsonSafely<T>(response);
  if (!json) {
    throw new ApiError(response.status, "INVALID_RESPONSE", "Server returned invalid JSON.");
  }
  return json;
}

export const api = {
  getAuthBootstrap(): Promise<AuthBootstrapResponse> {
    return request<AuthBootstrapResponse>("/auth/bootstrap");
  },

  register(payload: {
    username: string;
    password: string;
    role?: "admin" | "staff";
  }): Promise<UserInfo> {
    return request<UserInfo>("/auth/register", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  login(payload: {
    username: string;
    password: string;
  }): Promise<AuthTokenResponse> {
    return request<AuthTokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  logout(): Promise<{ status: string }> {
    return request<{ status: string }>("/auth/logout", { method: "POST" });
  },

  me(): Promise<UserInfo> {
    return request<UserInfo>("/auth/me");
  },

  getHealth(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  getModels(): Promise<string[]> {
    return request<string[]>("/models");
  },

  getEmailScenarios(): Promise<string[]> {
    return request<string[]>("/email-scenarios");
  },

  getModelPreferences(): Promise<ModelPreferences> {
    return request<ModelPreferences>("/model-preferences");
  },

  saveModelPreferences(payload: ModelPreferences): Promise<ModelPreferences> {
    return request<ModelPreferences>("/model-preferences", {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  getTemplateTypes(): Promise<TemplateTypesResponse> {
    return request<TemplateTypesResponse>("/template-types");
  },

  getFieldDictionary(): Promise<FieldDictionaryResponse> {
    return request<FieldDictionaryResponse>("/field-dictionary");
  },

  upsertFieldDictionaryEntry(
    fieldKey: string,
    payload: {
      label: string;
      aliases?: string[];
    }
  ): Promise<FieldDictionaryEntry> {
    return request<FieldDictionaryEntry>(`/field-dictionary/${encodeURIComponent(fieldKey)}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
  },

  deleteFieldDictionaryEntry(fieldKey: string): Promise<{ status: "deleted" }> {
    return request<{ status: "deleted" }>(`/field-dictionary/${encodeURIComponent(fieldKey)}`, {
      method: "DELETE"
    });
  },

  addTemplateType(template_type: string): Promise<TemplateTypesResponse> {
    return request<TemplateTypesResponse>("/template-types", {
      method: "POST",
      body: JSON.stringify({ template_type })
    });
  },

  getDenialCodes(): Promise<DenialCode[]> {
    return request<DenialCode[]>("/denial-codes");
  },

  getPayers(): Promise<string[]> {
    return request<string[]>("/payers");
  },

  generateDenialLetter(payload: {
    denial_code: string;
    patient_name: string;
    date_of_service: string;
    procedure_description: string;
    procedure_code?: string;
    payer_name: string;
    payer_address?: string;
    provider_name?: string;
    provider_npi?: string;
    model_name?: string;
  }): Promise<TextResponse> {
    return request<TextResponse>("/denial-letters/generate", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  generateEmail(payload: {
    scenario: string;
    additional_context?: string;
    model_name?: string;
  }): Promise<TextResponse> {
    return request<TextResponse>("/emails/generate", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  generateEmailThread(payload: {
    thread_text?: string;
    files?: File[];
    selected_template_index?: number;
    model_name?: string;
    runtime_fields?: Record<string, unknown>;
  }): Promise<EmailThreadGenerateResponse> {
    const formData = new FormData();
    if (payload.thread_text) {
      formData.append("thread_text", payload.thread_text);
    }
    for (const file of payload.files ?? []) {
      formData.append("files", file);
    }
    if (payload.selected_template_index !== undefined) {
      formData.append("selected_template_index", String(payload.selected_template_index));
    }
    if (payload.model_name) {
      formData.append("model_name", payload.model_name);
    }
    if (payload.runtime_fields && Object.keys(payload.runtime_fields).length > 0) {
      formData.append("runtime_fields", JSON.stringify(payload.runtime_fields));
    }
    return request<EmailThreadGenerateResponse>("/email-thread/generate", {
      method: "POST",
      body: formData
    });
  },

  generateInsuranceVerification(payload: {
    payer_name: string;
    member_id: string;
    group_number?: string;
    patient_dob: string;
    plan_type?: string;
    requested_procedure?: string;
    requested_condition?: string;
    model_name?: string;
  }): Promise<InsuranceVerificationResponse> {
    return request<InsuranceVerificationResponse>("/insurance-verification/generate", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  generateTemplateDraft(payload: {
    template_type: string;
    variable_names: string[];
    instructions?: string;
    model_name?: string;
  }): Promise<TextResponse> {
    return request<TextResponse>("/templates/generate-draft", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  generateFromDocuments(payload: {
    files?: File[];
    requested_template_type?: string;
    selected_template_index?: number;
    model_name?: string;
    runtime_fields?: Record<string, unknown>;
  }): Promise<DocumentPipelineResponse> {
    const formData = new FormData();
    for (const file of payload.files ?? []) {
      formData.append("files", file);
    }
    if (payload.requested_template_type) {
      formData.append("requested_template_type", payload.requested_template_type);
    }
    if (payload.selected_template_index !== undefined) {
      formData.append("selected_template_index", String(payload.selected_template_index));
    }
    if (payload.model_name) {
      formData.append("model_name", payload.model_name);
    }
    if (payload.runtime_fields && Object.keys(payload.runtime_fields).length > 0) {
      formData.append("runtime_fields", JSON.stringify(payload.runtime_fields));
    }
    return request<DocumentPipelineResponse>("/document-pipeline/generate", {
      method: "POST",
      body: formData
    });
  },

  getTemplates(): Promise<TemplateItem[]> {
    return request<TemplateItem[]>("/templates");
  },

  saveTemplate(payload: {
    name: string;
    type: string;
    content: string;
    visibility?: "personal" | "shared";
    tags?: string[];
  }): Promise<SaveTemplateResponse> {
    return request<SaveTemplateResponse>("/templates", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },

  deleteTemplate(index: number): Promise<{ status: "deleted" }> {
    return request<{ status: "deleted" }>(`/templates/${index}`, {
      method: "DELETE"
    });
  },

  getAuditEvents(limit = 100): Promise<AuditEventsResponse> {
    return request<AuditEventsResponse>(`/audit-events?limit=${limit}`);
  }
};
