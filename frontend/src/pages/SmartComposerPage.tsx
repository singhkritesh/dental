import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { Notice } from "../components/Notice";
import { OutputActions } from "../components/OutputActions";
import { RuntimeFieldsEditor } from "../components/RuntimeFieldsEditor";
import { SelectedFilesList } from "../components/SelectedFilesList";
import { TemplateSaveBar } from "../components/TemplateSaveBar";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { resolveErrorMessage } from "../lib/errorMessages";
import { useGenerationTasks } from "../lib/generationTasks";
import { isAdminContext, templateScopeLabel } from "../lib/permissions";
import { compactRuntimeFields, hasRuntimeFields } from "../lib/runtimeFields";
import {
  savePersonalTemplate,
  TemplateSaveInputError,
  validateTemplateSaveInput,
} from "../lib/templateSave";
import { MAX_UPLOAD_FILES, STANDARD_UPLOAD_ACCEPT } from "../lib/uploadConfig";
import type {
  DocumentPipelineResponse,
  EmailThreadGenerateResponse,
  ModelPreferences,
  TemplateItem,
} from "../lib/types";

type ComposerMode = "new_draft" | "reply_thread";
type PurposeMode = "auto" | "existing" | "custom";

type ComposerResult =
  | { kind: "document"; data: DocumentPipelineResponse }
  | { kind: "thread"; data: EmailThreadGenerateResponse };

type ComposerTaskOutcome = {
  result: ComposerResult;
  successMessage: string;
};

type ComposerPersistedState = {
  mode: ComposerMode;
  threadText: string;
  purposeMode: PurposeMode;
  requestedTemplateType: string;
  customTemplateType: string;
  selectedTemplateIndex?: number;
  runtimeFields: Record<string, string>;
  modelName: string;
  saveAsTemplateName: string;
  saveAsTemplateTags: string;
  hadFilesSelected: boolean;
};

type StepState = "pending" | "active" | "done";

const COMPOSER_STATE_STORAGE_KEY = "siligent_smart_composer_state_v2";
const DENIAL_RUNTIME_FIELD_KEYS = [
  "today_date",
  "denial_code",
  "denial_reason",
  "appeal_basis",
  "payer_name",
  "payer_address",
  "patient_name",
  "date_of_service",
  "claim_or_reference",
  "procedure_description",
  "procedure_code",
  "supporting_rationale",
  "provider_name",
  "provider_npi",
];
const EMAIL_REPLY_PURPOSE_OPTIONS = [
  "appointment_confirmation",
  "insurance_update",
  "billing_inquiry",
  "records_request",
  "post_treatment_followup",
  "denial_followup",
  "general_inquiry",
];

const EMAIL_REPLY_PURPOSE_FIELD_KEYS: Record<string, string[]> = {
  appointment_confirmation: [
    "patient_name",
    "requester_name",
    "appointment_date",
    "appointment_time",
    "provider_name",
    "office_phone",
    "next_step",
  ],
  insurance_update: [
    "patient_name",
    "requester_name",
    "payer_name",
    "member_id",
    "group_number",
    "date_of_birth",
    "office_phone",
    "next_step",
  ],
  billing_inquiry: [
    "patient_name",
    "requester_name",
    "account_or_invoice",
    "balance_amount",
    "payment_next_step",
    "office_phone",
    "next_step",
  ],
  records_request: [
    "patient_name",
    "requester_name",
    "records_requested",
    "release_form_status",
    "delivery_method",
    "office_email",
    "next_step",
  ],
  post_treatment_followup: [
    "patient_name",
    "requester_name",
    "procedure_description",
    "symptoms_reported",
    "provider_name",
    "office_phone",
    "next_step",
  ],
  denial_followup: [
    "patient_name",
    "requester_name",
    "payer_name",
    "claim_id",
    "denial_code",
    "denial_reason",
    "next_step",
  ],
  general_inquiry: [
    "patient_name",
    "requester_name",
    "topic",
    "office_phone",
    "office_email",
    "next_step",
  ],
};

const EMAIL_TEMPLATE_TYPE_TO_PURPOSE: Record<string, string> = {
  email: "general_inquiry",
  appointment_confirmation: "appointment_confirmation",
  appointment_reminder: "appointment_confirmation",
  appointment_confirmation_sms: "appointment_confirmation",
  appointment_reminder_sms: "appointment_confirmation",
  cancellation_confirmation: "appointment_confirmation",
  insurance_update_request: "insurance_update",
  insurance_verification: "insurance_update",
  balance_due: "billing_inquiry",
  balance_due_notice: "billing_inquiry",
  referral_letter: "records_request",
  records_request: "records_request",
  new_patient_welcome: "general_inquiry",
  post_treatment_followup: "post_treatment_followup",
  denial_letter: "denial_followup",
  rebuttal_letter: "denial_followup",
};

const EMAIL_PURPOSE_LABELS: Record<string, string> = {
  appointment_confirmation: "Appointment confirmation or scheduling",
  insurance_update: "Insurance update or claim details",
  billing_inquiry: "Billing or balance question",
  records_request: "Records or referral request",
  post_treatment_followup: "Post-treatment follow-up",
  denial_followup: "Denial or appeal follow-up",
  general_inquiry: "General inquiry",
};

const EMAIL_TEMPLATE_PURPOSE_TAGS: Record<string, string[]> = {
  appointment_confirmation: ["appointment", "schedule", "confirmation", "reminder", "cancellation"],
  insurance_update: ["insurance", "payer", "coverage", "member", "claim"],
  billing_inquiry: ["billing", "balance", "payment", "invoice"],
  records_request: ["records", "referral", "release", "xray", "x-ray"],
  post_treatment_followup: ["post", "treatment", "followup", "follow-up", "clinical"],
  denial_followup: ["denial", "appeal", "claim", "rebuttal"],
  general_inquiry: ["general", "inquiry", "email"],
};

const EMAIL_PURPOSE_ORDER = new Map(EMAIL_REPLY_PURPOSE_OPTIONS.map((item, index) => [item, index]));

function labelFromPurpose(value: string): string {
  return EMAIL_PURPOSE_LABELS[value] ?? value.replace(/[_-]+/g, " ");
}

function resolveEmailPurposeFromValue(rawValue: string | undefined): string | undefined {
  const normalized = normalizeTemplateTypeInput(rawValue || "");
  if (!normalized) {
    return undefined;
  }
  if (EMAIL_REPLY_PURPOSE_OPTIONS.includes(normalized)) {
    return normalized;
  }
  return EMAIL_TEMPLATE_TYPE_TO_PURPOSE[normalized];
}

function resolveEmailPurposeFromTemplate(template: TemplateItem | null): string | undefined {
  if (!template) {
    return undefined;
  }
  const direct = resolveEmailPurposeFromValue(template.type);
  if (direct) {
    return direct;
  }
  const searchable = `${template.type} ${template.name} ${(template.tags || []).join(" ")}`.toLowerCase();
  for (const purpose of EMAIL_REPLY_PURPOSE_OPTIONS) {
    const tags = EMAIL_TEMPLATE_PURPOSE_TAGS[purpose] || [];
    if (tags.some((tag) => searchable.includes(tag))) {
      return purpose;
    }
  }
  return undefined;
}

function templateMatchesEmailPurpose(template: TemplateItem, purpose: string): boolean {
  const resolved = resolveEmailPurposeFromTemplate(template);
  if (resolved === purpose) {
    return true;
  }
  const tags = EMAIL_TEMPLATE_PURPOSE_TAGS[purpose] || [];
  const searchable = `${template.type} ${template.name} ${(template.tags || []).join(" ")}`.toLowerCase();
  return tags.some((tag) => searchable.includes(tag));
}

function rankEmailTemplate(template: TemplateItem): number {
  const purpose = resolveEmailPurposeFromTemplate(template) ?? "general_inquiry";
  return EMAIL_PURPOSE_ORDER.get(purpose) ?? 999;
}

function normalizeTemplateTypeInput(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/^_+|_+$/g, "");
}

function normalizeRuntimeFieldKey(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_.-]/g, "")
    .slice(0, 80);
}

function normalizeFieldKeyList(values: string[]): string[] {
  const unique = new Set<string>();
  for (const value of values) {
    const normalized = normalizeRuntimeFieldKey(value);
    if (normalized) {
      unique.add(normalized);
    }
  }
  return Array.from(unique);
}

function resolveModelForMode(
  mode: ComposerMode,
  models: string[],
  prefs: ModelPreferences | null
): string {
  if (!prefs) {
    return models[0] ?? "";
  }
  if (prefs.use_global_model_for_all) {
    return prefs.global_model || models[0] || "";
  }
  const useCase = mode === "reply_thread" ? "email_thread" : "document_ingestion";
  return prefs.per_use_case[useCase] ?? prefs.global_model ?? models[0] ?? "";
}

function resultDraftText(result: ComposerResult | null): string {
  if (!result) {
    return "";
  }
  if (result.kind === "document") {
    return result.data.structured_output.final_draft;
  }
  return result.data.draft;
}

function resultTemplateType(result: ComposerResult): string {
  if (result.kind === "document") {
    return result.data.detected_template_type;
  }
  return result.data.analysis.intent || "email";
}

function resultRecommendedTemplates(result: ComposerResult) {
  return result.kind === "document"
    ? result.data.recommended_templates
    : result.data.recommended_templates;
}

function resultMissingRuntimeFields(result: ComposerResult): string[] {
  return result.kind === "document"
    ? result.data.missing_runtime_fields
    : result.data.missing_runtime_fields;
}

function hasEmailMissingMarkers(text: string): boolean {
  return (
    /\bnot provided\b/i.test(text) ||
    /\{\{\s*[A-Za-z][A-Za-z0-9_. -]{0,79}\s*\}\}/.test(text) ||
    /\{[A-Za-z][A-Za-z0-9_. -]{0,79}\}/.test(text) ||
    /\[\[\s*[A-Za-z][A-Za-z0-9_. -]{0,79}\s*\]\]/.test(text)
  );
}

export function SmartComposerPage() {
  const { user, bootstrap } = useAuth();
  const { tasks, runTask, getInFlight, clearTask } = useGenerationTasks();
  const isAdmin = isAdminContext(user, bootstrap);
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const isDenialLetterRoute = location.pathname === "/denial-letters";
  const forcedTemplateType = isDenialLetterRoute ? "denial_letter" : undefined;

  const initialModeParam = searchParams.get("mode")?.trim().toLowerCase();
  const initialMode: ComposerMode =
    location.pathname === "/email-thread" ||
    initialModeParam === "thread" ||
    initialModeParam === "reply_thread"
      ? "reply_thread"
      : "new_draft";

  const [mode, setMode] = useState<ComposerMode>(initialMode);
  const [files, setFiles] = useState<File[]>([]);
  const [threadText, setThreadText] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [templateTypes, setTemplateTypes] = useState<string[]>([]);
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [preferences, setPreferences] = useState<ModelPreferences | null>(null);

  const [purposeMode, setPurposeMode] = useState<PurposeMode>("auto");
  const [requestedTemplateType, setRequestedTemplateType] = useState("");
  const [customTemplateType, setCustomTemplateType] = useState("");
  const [selectedTemplateIndex, setSelectedTemplateIndex] = useState<number | undefined>(undefined);
  const [runtimeFields, setRuntimeFields] = useState<Record<string, string>>({});

  const [modelName, setModelName] = useState("");
  const [result, setResult] = useState<ComposerResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "error" | "success" | "info"; message: string } | null>(null);

  const [saveAsTemplateName, setSaveAsTemplateName] = useState("");
  const [saveAsTemplateTags, setSaveAsTemplateTags] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [editableDraft, setEditableDraft] = useState("");
  const [isEditingDraft, setIsEditingDraft] = useState(false);
  const taskState = tasks["smart_composer_generate"];

  useEffect(() => {
    if (location.pathname === "/email-thread") {
      setMode("reply_thread");
      return;
    }
    if (location.pathname === "/denial-letters" || location.pathname === "/email-drafting") {
      setMode("new_draft");
    }
  }, [location.pathname]);

  useEffect(() => {
    const raw = window.sessionStorage.getItem(COMPOSER_STATE_STORAGE_KEY);
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as Partial<ComposerPersistedState>;
      const modeValue =
        location.pathname === "/email-thread"
          ? "reply_thread"
          : (parsed.mode === "reply_thread" || parsed.mode === "new_draft")
            ? parsed.mode
            : initialMode;
      setMode(modeValue);
      setThreadText(typeof parsed.threadText === "string" ? parsed.threadText : "");
      setPurposeMode(
        parsed.purposeMode === "existing" || parsed.purposeMode === "custom" || parsed.purposeMode === "auto"
          ? parsed.purposeMode
          : "auto"
      );
      setRequestedTemplateType(
        typeof parsed.requestedTemplateType === "string" ? parsed.requestedTemplateType : ""
      );
      setCustomTemplateType(
        typeof parsed.customTemplateType === "string" ? parsed.customTemplateType : ""
      );
      setSelectedTemplateIndex(
        Number.isInteger(parsed.selectedTemplateIndex)
          ? Number(parsed.selectedTemplateIndex)
          : undefined
      );
      setRuntimeFields(
        parsed.runtimeFields && typeof parsed.runtimeFields === "object" ? parsed.runtimeFields : {}
      );
      setModelName(typeof parsed.modelName === "string" ? parsed.modelName : "");
      setSaveAsTemplateName(
        typeof parsed.saveAsTemplateName === "string" ? parsed.saveAsTemplateName : ""
      );
      setSaveAsTemplateTags(
        typeof parsed.saveAsTemplateTags === "string" ? parsed.saveAsTemplateTags : ""
      );

      if (modeValue === "new_draft" && parsed.hadFilesSelected) {
        setNotice({
          type: "info",
          message:
            "Previous inputs were restored. Please re-upload files to continue generation.",
        });
      }
    } catch {
      window.sessionStorage.removeItem(COMPOSER_STATE_STORAGE_KEY);
    }
  }, [initialMode, location.pathname]);

  useEffect(() => {
    const payload: ComposerPersistedState = {
      mode,
      threadText,
      purposeMode,
      requestedTemplateType,
      customTemplateType,
      selectedTemplateIndex,
      runtimeFields,
      modelName,
      saveAsTemplateName,
      saveAsTemplateTags,
      hadFilesSelected: files.length > 0,
    };
    window.sessionStorage.setItem(COMPOSER_STATE_STORAGE_KEY, JSON.stringify(payload));
  }, [
    mode,
    threadText,
    purposeMode,
    requestedTemplateType,
    customTemplateType,
    selectedTemplateIndex,
    runtimeFields,
    modelName,
    saveAsTemplateName,
    saveAsTemplateTags,
    files.length,
  ]);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [modelsData, templateTypeData, templatesData, prefs] = await Promise.all([
          api.getModels(),
          api.getTemplateTypes(),
          api.getTemplates(),
          api.getModelPreferences(),
        ]);
        if (!active) {
          return;
        }
        setModels(modelsData);
        setTemplateTypes(templateTypeData.template_types);
        setTemplates(templatesData);
        setPreferences(prefs);
        setRequestedTemplateType((current) => current || templateTypeData.template_types[0] || "");
        setModelName((current) => current || resolveModelForMode(mode, modelsData, prefs));

        const routeTemplateType =
          location.pathname === "/denial-letters"
            ? "denial_letter"
            : location.pathname === "/email-drafting"
              ? "email"
              : "";
        const prefillType = searchParams.get("templateType")?.trim() || routeTemplateType;
        const prefillIndexRaw = searchParams.get("templateIndex")?.trim() ?? "";
        if (prefillType) {
          if (templateTypeData.template_types.includes(prefillType)) {
            setPurposeMode("existing");
            setRequestedTemplateType(prefillType);
          } else {
            setPurposeMode("custom");
            setCustomTemplateType(prefillType);
          }
        }
        if (prefillIndexRaw) {
          const parsedIndex = Number(prefillIndexRaw);
          if (
            Number.isInteger(parsedIndex) &&
            parsedIndex >= 0 &&
            templatesData.some((item) => item.index === parsedIndex)
          ) {
            setSelectedTemplateIndex(parsedIndex);
          }
        }
      } catch (error) {
        const message = resolveErrorMessage(error, "Failed to load composer data.");
        if (active) {
          setNotice({ type: "error", message });
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [location.pathname, mode, searchParams]);

  useEffect(() => {
    setModelName(resolveModelForMode(mode, models, preferences));
  }, [mode, models, preferences]);

  useEffect(() => {
    if (!taskState) {
      return;
    }
    if (taskState.status === "running") {
      setLoading(true);
      setNotice({
        type: "info",
        message: "Draft generation is running in the background. This screen will update automatically when complete.",
      });
      const pending = getInFlight<ComposerTaskOutcome>("smart_composer_generate");
      if (!pending) {
        return;
      }
      void pending
        .then((outcome) => {
          if (
            mode === "reply_thread" &&
            outcome.result.kind === "thread" &&
            hasEmailMissingMarkers(resultDraftText(outcome.result))
          ) {
            clearTask("smart_composer_generate");
            setResult(null);
            setEditableDraft("");
            setNotice({
              type: "info",
              message: "A stale email draft was cleared. Generate again to apply the latest safeguards.",
            });
            return;
          }
          setResult(outcome.result);
          setNotice({ type: "success", message: outcome.successMessage });
        })
        .catch((error) => {
          const message = resolveErrorMessage(error, "Generation failed.");
          setNotice({ type: "error", message });
        })
        .finally(() => {
          setLoading(false);
        });
      return;
    }
    if (taskState.status === "success" && taskState.result) {
      const outcome = taskState.result as ComposerTaskOutcome;
      if (
        mode === "reply_thread" &&
        outcome.result.kind === "thread" &&
        hasEmailMissingMarkers(resultDraftText(outcome.result))
      ) {
        clearTask("smart_composer_generate");
        setResult(null);
        setEditableDraft("");
        setNotice({
          type: "info",
          message: "A stale email draft was cleared. Generate again to apply the latest safeguards.",
        });
        setLoading(false);
        return;
      }
      setResult(outcome.result);
      setNotice({ type: "success", message: outcome.successMessage });
      setLoading(false);
      return;
    }
    if (taskState.status === "error") {
      setLoading(false);
    }
  }, [clearTask, getInFlight, mode, taskState]);

  const normalizedCustomType = useMemo(
    () => normalizeTemplateTypeInput(customTemplateType),
    [customTemplateType]
  );

  const requestedTypeForRequest = useMemo(() => {
    if (mode === "reply_thread") {
      return undefined;
    }
    if (forcedTemplateType) {
      return forcedTemplateType;
    }
    if (purposeMode === "auto") {
      return undefined;
    }
    if (purposeMode === "existing") {
      return requestedTemplateType.trim() || undefined;
    }
    return normalizedCustomType || undefined;
  }, [forcedTemplateType, mode, normalizedCustomType, purposeMode, requestedTemplateType]);

  const availableTemplatesForSelection = useMemo(() => {
    if (mode === "reply_thread") {
      const ranked = [...templates].sort((a, b) => {
        const purposeDelta = rankEmailTemplate(a) - rankEmailTemplate(b);
        if (purposeDelta !== 0) {
          return purposeDelta;
        }
        const aEmail = a.type.includes("email") ? 0 : 1;
        const bEmail = b.type.includes("email") ? 0 : 1;
        return aEmail - bEmail;
      });
      if (purposeMode === "existing" && requestedTemplateType.trim()) {
        return ranked.filter((item) => templateMatchesEmailPurpose(item, requestedTemplateType.trim()));
      }
      return ranked;
    }
    if (forcedTemplateType) {
      return templates.filter((item) => item.type === forcedTemplateType);
    }
    if (purposeMode === "auto") {
      return templates;
    }
    if (purposeMode === "existing") {
      return templates.filter((item) => item.type === requestedTemplateType);
    }
    if (!normalizedCustomType) {
      return templates;
    }
    return templates.filter((item) => item.type === normalizedCustomType);
  }, [forcedTemplateType, mode, normalizedCustomType, purposeMode, requestedTemplateType, templates]);

  const selectedTemplate = useMemo(() => {
    if (selectedTemplateIndex === undefined) {
      return null;
    }
    return templates.find((item) => item.index === selectedTemplateIndex) ?? null;
  }, [selectedTemplateIndex, templates]);

  const selectedEmailPurpose = useMemo(() => {
    if (mode !== "reply_thread") {
      return undefined;
    }
    if (selectedTemplate) {
      return resolveEmailPurposeFromTemplate(selectedTemplate);
    }
    if (purposeMode === "existing") {
      return resolveEmailPurposeFromValue(requestedTemplateType);
    }
    return undefined;
  }, [mode, purposeMode, requestedTemplateType, selectedTemplate]);

  const templateForRuntimeFields = useMemo(() => {
    if (selectedTemplate) {
      return selectedTemplate;
    }
    if (mode === "reply_thread") {
      return null;
    }
    if (!requestedTypeForRequest) {
      return null;
    }
    return templates.find((item) => item.type === requestedTypeForRequest) ?? null;
  }, [mode, requestedTypeForRequest, selectedTemplate, templates]);

  useEffect(() => {
    if (
      selectedTemplateIndex !== undefined &&
      !availableTemplatesForSelection.some((item) => item.index === selectedTemplateIndex)
    ) {
      setSelectedTemplateIndex(undefined);
    }
  }, [availableTemplatesForSelection, selectedTemplateIndex]);

  const runtimeFieldCount = Object.keys(compactRuntimeFields(runtimeFields)).length;
  const hasGeneratedThreadContext = Boolean(
    result?.kind === "thread" &&
      (result.data.analysis.latest_message.trim() || result.data.analysis.thread_summary.trim())
  );
  const missingRuntimeFieldKeys = useMemo(
    () => (result ? normalizeFieldKeyList(resultMissingRuntimeFields(result)) : []),
    [result]
  );
  const suggestedRuntimeKeys = useMemo(() => {
    if (mode === "reply_thread") {
      const purposeKeys = selectedEmailPurpose
        ? EMAIL_REPLY_PURPOSE_FIELD_KEYS[selectedEmailPurpose] ?? EMAIL_REPLY_PURPOSE_FIELD_KEYS.general_inquiry
        : [];
      const templateKeys = selectedTemplate?.placeholders ?? [];
      return Array.from(new Set([...purposeKeys, ...templateKeys, ...missingRuntimeFieldKeys]));
    }
    if (templateForRuntimeFields?.placeholders.length) {
      return Array.from(new Set([...templateForRuntimeFields.placeholders, ...missingRuntimeFieldKeys]));
    }
    if (requestedTypeForRequest === "denial_letter") {
      return Array.from(new Set([...DENIAL_RUNTIME_FIELD_KEYS, ...missingRuntimeFieldKeys]));
    }
    return missingRuntimeFieldKeys;
  }, [missingRuntimeFieldKeys, mode, requestedTypeForRequest, selectedEmailPurpose, selectedTemplate, templateForRuntimeFields]);

  useEffect(() => {
    if (missingRuntimeFieldKeys.length === 0) {
      return;
    }
    setRuntimeFields((current) => {
      let changed = false;
      const next = { ...current };
      for (const key of missingRuntimeFieldKeys) {
        if (!(key in next)) {
          next[key] = "";
          changed = true;
        }
      }
      return changed ? next : current;
    });
    setNotice({
      type: "info",
      message: "Some required details are missing. The fields were added below; fill them in and regenerate the draft.",
    });
  }, [missingRuntimeFieldKeys]);

  const canGenerate =
    !loading &&
    files.length <= MAX_UPLOAD_FILES &&
    (mode === "new_draft"
      ? (
          files.length > 0 ||
          selectedTemplateIndex !== undefined ||
          runtimeFieldCount > 0 ||
          Boolean(requestedTypeForRequest)
        )
      : Boolean(threadText.trim()) || files.length > 0 || (runtimeFieldCount > 0 && hasGeneratedThreadContext));

  const canSaveTemplate = Boolean(editableDraft.trim() && saveAsTemplateName.trim() && !savingTemplate);
  const uploadStepDone = mode === "reply_thread" ? Boolean(threadText.trim() || files.length > 0) : true;
  const purposeStepDone =
    mode === "reply_thread" || Boolean(forcedTemplateType)
      ? true
      : purposeMode === "auto" || purposeMode === "existing" || Boolean(normalizedCustomType);
  const detailsStepDone = runtimeFieldCount > 0;
  const reviewStepDone = canGenerate;
  const draftStepDone = Boolean(resultDraftText(result).trim());
  const generationGuidance = canGenerate
    ? "Ready to generate."
    : mode === "new_draft"
      ? "Add at least one source: upload files, pick a template/purpose, or fill runtime details."
      : "Paste thread text or upload at least one file.";
  const workflowTitle =
    mode === "reply_thread"
      ? "Email Exchange"
      : requestedTypeForRequest === "denial_letter"
        ? "Denial Letters"
        : requestedTypeForRequest === "rebuttal_letter"
          ? "Rebuttal Letters"
          : "Document Drafting";
  const workflowDescription =
    mode === "reply_thread"
      ? "Review an email chain and generate a staff-edited reply draft."
      : requestedTypeForRequest === "denial_letter"
        ? "Prepare claim denial letters from templates, runtime fields, and supporting documents."
        : requestedTypeForRequest === "rebuttal_letter"
          ? "Prepare rebuttal letters from claim context, templates, and supporting documents."
          : "Generate a structured draft from templates, runtime fields, and optional uploads.";
  const showPurposeStep = !forcedTemplateType;
  const detailsStepNumber = showPurposeStep ? 3 : 2;
  const reviewStepNumber = showPurposeStep ? 4 : 3;
  const draftStepNumber = showPurposeStep ? 5 : 4;

  function stepClass(state: StepState): string {
    if (state === "done") {
      return "wizard-step done static";
    }
    if (state === "active") {
      return "wizard-step active static";
    }
    return "wizard-step static";
  }

  useEffect(() => {
    if (!result) {
      setEditableDraft("");
      setIsEditingDraft(false);
      return;
    }
    setEditableDraft(resultDraftText(result));
    setIsEditingDraft(false);
  }, [result]);

  function resetForMode(nextMode: ComposerMode) {
    setMode(nextMode);
    setResult(null);
    setNotice(null);
    setFiles([]);
    setThreadText("");
    setRuntimeFields({});
    setSelectedTemplateIndex(undefined);
    if (nextMode === "reply_thread") {
      setPurposeMode("auto");
      setRequestedTemplateType("");
      setCustomTemplateType("");
    }
  }

  function onFilesChange(nextFiles: FileList | null) {
    const picked = nextFiles ? Array.from(nextFiles) : [];
    setFiles(picked.slice(0, MAX_UPLOAD_FILES));
    if (picked.length > MAX_UPLOAD_FILES) {
      setNotice({ type: "info", message: `Only the first ${MAX_UPLOAD_FILES} files were kept.` });
    }
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, fileIndex) => fileIndex !== index));
  }

  async function onGenerate() {
    setNotice(null);
    const previousResult = result;

    if (!canGenerate) {
      setNotice({
        type: "error",
        message:
          mode === "new_draft"
            ? "Add at least one source: upload file(s), choose a template/purpose, or provide runtime details."
            : "Paste thread text or upload at least one thread file.",
      });
      return;
    }

    const compactFields = compactRuntimeFields(runtimeFields);
    const parsedRuntimeFields: Record<string, unknown> | undefined = hasRuntimeFields(compactFields)
      ? compactFields
      : undefined;
    const threadTextForRequest =
      threadText.trim() ||
      (previousResult?.kind === "thread"
        ? previousResult.data.analysis.latest_message.trim() || previousResult.data.analysis.thread_summary.trim()
        : "");

    clearTask("smart_composer_generate");
    setResult(null);
    setLoading(true);
    try {
      const outcome = await runTask<ComposerTaskOutcome>("smart_composer_generate", async () => {
        if (mode === "new_draft") {
          const response = await api.generateFromDocuments({
            files,
            requested_template_type: requestedTypeForRequest,
            selected_template_index: selectedTemplateIndex,
            runtime_fields: parsedRuntimeFields,
            model_name: isAdmin ? modelName || undefined : undefined,
          });
          return {
            result: { kind: "document", data: response },
            successMessage: `Detected purpose: ${response.detected_template_type} (${(response.detection_confidence * 100).toFixed(0)}% confidence).`,
          };
        }

        const response = await api.generateEmailThread({
          thread_text: threadTextForRequest,
          files,
          requested_intent: selectedEmailPurpose,
          selected_template_index: selectedTemplateIndex,
          runtime_fields: parsedRuntimeFields,
          model_name: isAdmin ? modelName || undefined : undefined,
        });
        return {
          result: { kind: "thread", data: response },
          successMessage: `Thread intent: ${response.analysis.intent} (${(response.analysis.confidence * 100).toFixed(0)}% confidence).`,
        };
      });
      setResult(outcome.result);
      setNotice({
        type: "success",
        message: outcome.successMessage,
      });
    } catch (error) {
      const message = resolveErrorMessage(error, "Generation failed.");
      setNotice({ type: "error", message });
    } finally {
      setLoading(false);
    }
  }

  async function onSaveGeneratedTemplate() {
    if (!result) {
      return;
    }
    setSavingTemplate(true);
    try {
      const { cleanContent, cleanName } = validateTemplateSaveInput({
        content: editableDraft,
        name: saveAsTemplateName,
        emptyContentMessage: "Generate a draft before saving a template.",
      });
      await savePersonalTemplate({
        name: cleanName,
        type: resultTemplateType(result),
        content: cleanContent,
        tagsInput: saveAsTemplateTags,
      });
      setSaveAsTemplateName("");
      setSaveAsTemplateTags("");
      setNotice({ type: "success", message: "Draft saved as personal template." });
    } catch (error) {
      const message =
        error instanceof TemplateSaveInputError
          ? error.message
          : resolveErrorMessage(error, "Failed to save template.");
      setNotice({ type: "error", message });
    } finally {
      setSavingTemplate(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>{workflowTitle}</h1>
        <p>{workflowDescription}</p>
      </header>

      {notice ? <Notice type={notice.type} message={notice.message} /> : null}

      <div className={`wizard-steps${showPurposeStep ? "" : " compact"}`} aria-label="Compose steps">
        <div className={stepClass(uploadStepDone ? "done" : "active")}>
          <span className="wizard-step-index">1</span>
          Upload
        </div>
        {showPurposeStep ? (
          <div
            className={stepClass(
              purposeStepDone ? "done" : uploadStepDone ? "active" : "pending"
            )}
          >
            <span className="wizard-step-index">2</span>
            Purpose
          </div>
        ) : null}
        <div
          className={stepClass(
            detailsStepDone ? "done" : purposeStepDone ? "active" : "pending"
          )}
        >
          <span className="wizard-step-index">{detailsStepNumber}</span>
          Details
        </div>
        <div
          className={stepClass(
            reviewStepDone ? "done" : detailsStepDone || purposeStepDone ? "active" : "pending"
          )}
        >
          <span className="wizard-step-index">{reviewStepNumber}</span>
          Review
        </div>
        <div className={stepClass(draftStepDone ? "done" : reviewStepDone ? "active" : "pending")}>
          <span className="wizard-step-index">{draftStepNumber}</span>
          Draft
        </div>
      </div>

      <div className="panel-grid single-col">
        <div className="panel">
          <h2>1. Upload</h2>
          <label>
            What are you creating?
            <select
              value={mode}
              onChange={(event) => resetForMode(event.target.value as ComposerMode)}
            >
              <option value="new_draft">New Draft from Documents</option>
              <option value="reply_thread">Email Exchange Reply</option>
            </select>
          </label>

          {mode === "reply_thread" ? (
            <label>
              Email thread text
              <textarea
                value={threadText}
                onChange={(event) => setThreadText(event.target.value)}
                placeholder="Paste the latest email chain here (most recent message included)."
              />
            </label>
          ) : null}

          <label>
            Upload files (optional, up to {MAX_UPLOAD_FILES})
            <input
              type="file"
              multiple
              accept={STANDARD_UPLOAD_ACCEPT}
              onChange={(event) => onFilesChange(event.target.files)}
            />
          </label>
          <p className="helper">
            Upload is optional. You can generate from templates and runtime details only, or include files for richer context.
          </p>
          <p className="helper">
            Supported types: PDF, DOCX, TXT, RTF, EML, MD, CSV, JSON, LOG, XML, YAML/YML, and images (PNG, JPG,
            JPEG, HEIC, BMP, TIF/TIFF, WEBP, GIF).
          </p>
          <SelectedFilesList files={files} onRemove={removeFile} />
          {files.length > 0 ? (
            <div className="inline-actions">
              <button className="secondary-btn" type="button" onClick={() => setFiles([])}>
                Clear all files
              </button>
            </div>
          ) : null}

          <details>
            <summary>Model options</summary>
            <div className="runtime-fields-grid">
              {!isAdmin ? (
                <p className="helper">
                  Model selection is managed by admins. This run uses your workspace default.
                </p>
              ) : (
                <label>
                  Temporary model override
                  <select value={modelName} onChange={(event) => setModelName(event.target.value)}>
                    {models.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </details>
        </div>

        {showPurposeStep ? (
          <div className="panel">
            <h2>2. Choose Purpose</h2>
            {mode === "new_draft" ? (
            <>
              <label className="checkbox-inline">
                <input
                  type="radio"
                  name="purpose-mode"
                  checked={purposeMode === "auto"}
                  onChange={() => setPurposeMode("auto")}
                />
                Detect purpose automatically
              </label>
              <label className="checkbox-inline">
                <input
                  type="radio"
                  name="purpose-mode"
                  checked={purposeMode === "existing"}
                  onChange={() => {
                    setPurposeMode("existing");
                    setRequestedTemplateType((current) => current || templateTypes[0] || "");
                  }}
                />
                Choose a saved purpose type
              </label>
              {purposeMode === "existing" ? (
                <label>
                  Purpose type
                  <select
                    value={requestedTemplateType}
                    onChange={(event) => setRequestedTemplateType(event.target.value)}
                  >
                    <option value="">Select purpose type</option>
                    {templateTypes.map((typeName) => (
                      <option key={typeName} value={typeName}>
                        {typeName}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <label className="checkbox-inline">
                <input
                  type="radio"
                  name="purpose-mode"
                  checked={purposeMode === "custom"}
                  onChange={() => setPurposeMode("custom")}
                />
                Create a new purpose type
              </label>
              {purposeMode === "custom" ? (
                <label>
                  Custom purpose type
                  <input
                    value={customTemplateType}
                    onChange={(event) => setCustomTemplateType(event.target.value)}
                    placeholder="Example: treatment_authorization_followup"
                  />
                </label>
              ) : null}
            </>
          ) : (
            <>
              <label className="checkbox-inline">
                <input
                  type="radio"
                  name="email-purpose-mode"
                  checked={purposeMode === "auto"}
                  onChange={() => setPurposeMode("auto")}
                />
                Detect email purpose from the thread
              </label>
              <label className="checkbox-inline">
                <input
                  type="radio"
                  name="email-purpose-mode"
                  checked={purposeMode === "existing"}
                  onChange={() => setPurposeMode("existing")}
                />
                Choose the email purpose
              </label>
              {purposeMode === "existing" ? (
                <label>
                  Email purpose
                  <select
                    value={requestedTemplateType}
                    onChange={(event) => setRequestedTemplateType(event.target.value)}
                  >
                    <option value="">Select a purpose</option>
                    {EMAIL_REPLY_PURPOSE_OPTIONS.map((purpose) => (
                      <option key={purpose} value={purpose}>
                        {labelFromPurpose(purpose)}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <p className="helper">
                The selected purpose customizes the fields below and keeps the reply focused. If unsure, leave this on
                auto-detect.
              </p>
            </>
          )}

            <label>
              Preferred template (optional)
              <select
                value={selectedTemplateIndex ?? ""}
                onChange={(event) =>
                  setSelectedTemplateIndex(event.target.value ? Number(event.target.value) : undefined)
                }
              >
                <option value="">No preference</option>
                {availableTemplatesForSelection.map((item) => (
                  <option key={item.index} value={item.index}>
                    [{item.index}] {item.name} ({item.type}, {templateScopeLabel(item)})
                  </option>
                ))}
              </select>
            </label>
          </div>
        ) : null}

        <div className="panel">
          <h2>{detailsStepNumber}. Fill Details</h2>
          <RuntimeFieldsEditor
            values={runtimeFields}
            onChange={setRuntimeFields}
            suggestedKeys={suggestedRuntimeKeys}
            requiredKeys={missingRuntimeFieldKeys}
            requiredLabel="Added for regenerate"
            title={
              mode === "reply_thread"
                ? "Email reply details"
                : requestedTypeForRequest === "denial_letter"
                  ? "Denial letter details"
                  : "Patient and case details"
            }
            helperText={
              mode === "reply_thread"
                ? "Optional before the first generation. If details are missing afterward, the app will add only the fields needed for this email purpose."
                : requestedTypeForRequest === "denial_letter"
                ? "Optional before the first generation. Fill known claim details if you already have them."
                : "Optional before the first generation. The selected template controls which fields appear here."
            }
          />
          {selectedTemplate?.placeholders.length ? (
            <>
              <p className="helper">Fields expected by the selected template</p>
              <div className="chips-wrap">
                {selectedTemplate.placeholders.map((token) => (
                  <span className="chip" key={token}>
                    {`{{${token}}}`}
                  </span>
                ))}
              </div>
            </>
          ) : null}
        </div>

        <div className="panel">
          <h2>{reviewStepNumber}. Review and Generate</h2>
          <p>
            <strong>Workflow:</strong> {mode === "new_draft" ? "New Draft from Documents" : "Reply to Email Thread"}
          </p>
          <p>
            <strong>Files:</strong> {files.length}
          </p>
          {mode === "reply_thread" ? (
            <>
              <p>
                <strong>Email purpose:</strong>{" "}
                {selectedEmailPurpose ? labelFromPurpose(selectedEmailPurpose) : "auto-detect from thread"}
              </p>
              <p>
                <strong>Thread text:</strong> {threadText.trim() ? "Pasted" : "No pasted text"}
              </p>
            </>
          ) : showPurposeStep ? (
            <p>
              <strong>Purpose:</strong> {requestedTypeForRequest ?? "auto-detect"}
            </p>
          ) : null}
          <p>
            <strong>Preferred template:</strong>{" "}
            {selectedTemplate ? `[${selectedTemplate.index}] ${selectedTemplate.name}` : "No explicit template selected"}
          </p>
          <p>
            <strong>Runtime fields:</strong> {runtimeFieldCount}
          </p>
          <button className="primary-btn" type="button" onClick={() => void onGenerate()} disabled={!canGenerate}>
            {loading ? "Generating draft..." : result ? "Regenerate draft" : "Generate draft"}
          </button>
          {!canGenerate ? <p className="helper">{generationGuidance}</p> : null}
          {loading ? (
            <p className="helper">Generation runs in the background and will update output automatically.</p>
          ) : null}
          <button className="secondary-btn" type="button" onClick={() => resetForMode(mode)}>
            Reset this workflow
          </button>
        </div>

        <div className="panel">
          <h2>{draftStepNumber}. Draft</h2>
          {!result ? (
            <p className="placeholder">
              {loading
                ? "Generation in progress. Draft will appear automatically."
                : "Generate a draft to view output."}
            </p>
          ) : (
            <>
              <textarea
                className="output"
                value={editableDraft}
                onChange={(event) => setEditableDraft(event.target.value)}
                readOnly={!isEditingDraft}
              />
              <button
                className="secondary-btn"
                type="button"
                onClick={() => setIsEditingDraft((current) => !current)}
              >
                {isEditingDraft ? "Lock draft" : "Edit draft"}
              </button>
              <p className="helper">
                {isEditingDraft
                  ? "Editing enabled. Save changes before leaving this page."
                  : "Draft is locked. Select \"Edit draft\" to make changes."}
              </p>
              <OutputActions
                text={editableDraft}
                filenamePrefix="composer_draft"
                mode={result.kind === "document" ? "document" : "email"}
              />
              <TemplateSaveBar
                nameValue={saveAsTemplateName}
                tagsValue={saveAsTemplateTags}
                onNameChange={setSaveAsTemplateName}
                onTagsChange={setSaveAsTemplateTags}
                onSave={onSaveGeneratedTemplate}
                disabled={!canSaveTemplate}
                saving={savingTemplate}
                namePlaceholder="Name this template"
              />

              {missingRuntimeFieldKeys.length > 0 ? (
                <Notice
                  type="info"
                  message={`Fill these added fields and regenerate: ${missingRuntimeFieldKeys.join(", ")}`}
                />
              ) : null}

              <details>
                <summary>Recommended templates</summary>
                <ol className="ranking-list">
                  {resultRecommendedTemplates(result).map((item) => (
                    <li key={`${item.index}-${item.name}`}>
                      <strong>{item.name}</strong> ({item.type}) score {item.score.toFixed(3)}
                    </li>
                  ))}
                </ol>
              </details>

              {result.kind === "document" ? (
                <details>
                  <summary>Summary</summary>
                  <h4>{result.data.structured_output.title}</h4>
                  <p>{result.data.structured_output.purpose}</p>
                  <h4>Key Points</h4>
                  <ul>
                    {result.data.structured_output.key_points.map((point) => (
                      <li key={point}>{point}</li>
                    ))}
                  </ul>
                </details>
              ) : (
                <details>
                  <summary>Thread summary</summary>
                  <p>
                    <strong>Intent:</strong> {result.data.analysis.intent} | <strong>Urgency:</strong>{" "}
                    {result.data.analysis.urgency} | <strong>Tone:</strong> {result.data.analysis.tone}
                  </p>
                  <p className="helper">{result.data.analysis.thread_summary}</p>
                  <p className="helper">{result.data.analysis.recommended_action}</p>
                </details>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
