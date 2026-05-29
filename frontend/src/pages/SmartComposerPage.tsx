import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

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

function normalizeTemplateTypeInput(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_-]/g, "")
    .replace(/^_+|_+$/g, "");
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

export function SmartComposerPage() {
  const { user, bootstrap } = useAuth();
  const { tasks, runTask, getInFlight } = useGenerationTasks();
  const isAdmin = isAdminContext(user, bootstrap);
  const [searchParams] = useSearchParams();

  const initialModeParam = searchParams.get("mode")?.trim().toLowerCase();
  const initialMode: ComposerMode =
    initialModeParam === "thread" || initialModeParam === "reply_thread"
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
    const raw = window.sessionStorage.getItem(COMPOSER_STATE_STORAGE_KEY);
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as Partial<ComposerPersistedState>;
      const modeValue =
        parsed.mode === "reply_thread" || parsed.mode === "new_draft"
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
  }, [initialMode]);

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

        const prefillType = searchParams.get("templateType")?.trim() ?? "";
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
  }, [mode, searchParams]);

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
      setResult(outcome.result);
      setNotice({ type: "success", message: outcome.successMessage });
      setLoading(false);
      return;
    }
    if (taskState.status === "error") {
      setLoading(false);
    }
  }, [getInFlight, taskState]);

  const normalizedCustomType = useMemo(
    () => normalizeTemplateTypeInput(customTemplateType),
    [customTemplateType]
  );

  const requestedTypeForRequest = useMemo(() => {
    if (mode === "reply_thread") {
      return undefined;
    }
    if (purposeMode === "auto") {
      return undefined;
    }
    if (purposeMode === "existing") {
      return requestedTemplateType.trim() || undefined;
    }
    return normalizedCustomType || undefined;
  }, [mode, normalizedCustomType, purposeMode, requestedTemplateType]);

  const availableTemplatesForSelection = useMemo(() => {
    if (mode === "reply_thread") {
      const ranked = [...templates].sort((a, b) => {
        const aEmail = a.type.includes("email") ? 1 : 0;
        const bEmail = b.type.includes("email") ? 1 : 0;
        return bEmail - aEmail;
      });
      return ranked;
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
  }, [mode, normalizedCustomType, purposeMode, requestedTemplateType, templates]);

  const selectedTemplate = useMemo(() => {
    if (selectedTemplateIndex === undefined) {
      return null;
    }
    return templates.find((item) => item.index === selectedTemplateIndex) ?? null;
  }, [selectedTemplateIndex, templates]);

  useEffect(() => {
    if (
      selectedTemplateIndex !== undefined &&
      !availableTemplatesForSelection.some((item) => item.index === selectedTemplateIndex)
    ) {
      setSelectedTemplateIndex(undefined);
    }
  }, [availableTemplatesForSelection, selectedTemplateIndex]);

  const runtimeFieldCount = Object.keys(compactRuntimeFields(runtimeFields)).length;

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
      : Boolean(threadText.trim()) || files.length > 0);

  const canSaveTemplate = Boolean(editableDraft.trim() && saveAsTemplateName.trim() && !savingTemplate);
  const uploadStepDone = mode === "reply_thread" ? Boolean(threadText.trim() || files.length > 0) : true;
  const purposeStepDone =
    mode === "reply_thread"
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
    setResult(null);

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
          thread_text: threadText,
          files,
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
        <h1>Compose</h1>
        <p>Single-page flow: Upload, choose purpose, fill details, review, then generate and edit draft.</p>
      </header>

      {notice ? <Notice type={notice.type} message={notice.message} /> : null}

      <div className="wizard-steps" aria-label="Compose steps">
        <div className={stepClass(uploadStepDone ? "done" : "active")}>
          <span className="wizard-step-index">1</span>
          Upload
        </div>
        <div
          className={stepClass(
            purposeStepDone ? "done" : uploadStepDone ? "active" : "pending"
          )}
        >
          <span className="wizard-step-index">2</span>
          Purpose
        </div>
        <div
          className={stepClass(
            detailsStepDone ? "done" : purposeStepDone ? "active" : "pending"
          )}
        >
          <span className="wizard-step-index">3</span>
          Details
        </div>
        <div
          className={stepClass(
            reviewStepDone ? "done" : detailsStepDone || purposeStepDone ? "active" : "pending"
          )}
        >
          <span className="wizard-step-index">4</span>
          Review
        </div>
        <div className={stepClass(draftStepDone ? "done" : reviewStepDone ? "active" : "pending")}>
          <span className="wizard-step-index">5</span>
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
              <option value="reply_thread">Reply to Email Thread</option>
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
                  Model (admin override)
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
                  onChange={() => setPurposeMode("existing")}
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
            <p className="helper">
              For thread replies, intent is detected automatically from thread text and uploads.
            </p>
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

        <div className="panel">
          <h2>3. Fill Details</h2>
          <RuntimeFieldsEditor
            values={runtimeFields}
            onChange={setRuntimeFields}
            suggestedKeys={selectedTemplate?.placeholders ?? []}
            title="Patient and case details (optional)"
            helperText="Add any details you already know to personalize the draft."
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
          <h2>4. Review and Generate</h2>
          <p>
            <strong>Workflow:</strong> {mode === "new_draft" ? "New Draft from Documents" : "Reply to Email Thread"}
          </p>
          <p>
            <strong>Files:</strong> {files.length}
          </p>
          {mode === "reply_thread" ? (
            <p>
              <strong>Thread text:</strong> {threadText.trim() ? "Provided" : "Not provided"}
            </p>
          ) : (
            <p>
              <strong>Purpose:</strong> {requestedTypeForRequest ?? "auto-detect"}
            </p>
          )}
          <p>
            <strong>Preferred template:</strong>{" "}
            {selectedTemplate ? `[${selectedTemplate.index}] ${selectedTemplate.name}` : "No explicit template selected"}
          </p>
          <p>
            <strong>Runtime fields:</strong> {runtimeFieldCount}
          </p>
          <button className="primary-btn" type="button" onClick={() => void onGenerate()} disabled={!canGenerate}>
            {loading ? "Generating draft..." : "Generate draft"}
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
          <h2>5. Draft</h2>
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

              {resultMissingRuntimeFields(result).length > 0 ? (
                <Notice
                  type="info"
                  message={`Missing runtime fields: ${resultMissingRuntimeFields(result).join(", ")}`}
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
