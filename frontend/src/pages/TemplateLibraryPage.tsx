import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Notice } from "../components/Notice";
import { OutputActions } from "../components/OutputActions";
import { RuntimeFieldsEditor } from "../components/RuntimeFieldsEditor";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDraftStore } from "../lib/draftStore";
import { resolveErrorMessage } from "../lib/errorMessages";
import { canManageTemplate, isAdminContext, templateScopeLabel } from "../lib/permissions";
import { compactRuntimeFields } from "../lib/runtimeFields";
import { savePersonalTemplate, TemplateSaveInputError, validateTemplateSaveInput } from "../lib/templateSave";
import { parseTagInput, toTagInput } from "../lib/templateTags";
import { extractTemplatePlaceholders, renderTemplateWithRuntimeFields } from "../lib/templateRuntime";
import {
  applyVariableNormalizationSuggestions,
  canonicalToNaturalTemplate,
  collectVariableNormalizationSuggestions,
  labelFromFieldKey,
  naturalToCanonicalTemplate,
  normalizeFieldKeyFromLabel,
  suggestFieldsFromNarrative,
} from "../lib/templateVariables";
import type { FieldDictionaryEntry, TemplateItem } from "../lib/types";

type LoadTarget = "smart_composer" | "email" | "denial_letter";

function preferredLoadTarget(typeName: string): LoadTarget {
  if (typeName === "email") {
    return "email";
  }
  if (typeName === "denial_letter") {
    return "denial_letter";
  }
  return "smart_composer";
}

function parseAliasesInput(raw: string): string[] {
  const aliases = raw
    .split(",")
    .map((value) => value.trim().toLowerCase())
    .map((value) => value.replace(/\s+/g, " "))
    .filter(Boolean);
  return Array.from(new Set(aliases)).sort();
}

export function TemplateLibraryPage() {
  const navigate = useNavigate();
  const editorRef = useRef<HTMLTextAreaElement | null>(null);
  const createEditorRef = useRef<HTMLTextAreaElement | null>(null);
  const { user, bootstrap } = useAuth();
  const { loadToDenial, loadToEmail } = useDraftStore();
  const isAdmin = isAdminContext(user, bootstrap);

  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [fieldDictionary, setFieldDictionary] = useState<FieldDictionaryEntry[]>([]);
  const [templateTypes, setTemplateTypes] = useState<string[]>([]);
  const [selectedStorageIndex, setSelectedStorageIndex] = useState<number | null>(null);
  const [editedContent, setEditedContent] = useState("");
  const [runtimeFields, setRuntimeFields] = useState<Record<string, string>>({});
  const [newName, setNewName] = useState("");
  const [newTagsInput, setNewTagsInput] = useState("");
  const [newTagEntry, setNewTagEntry] = useState("");
  const [filterQuery, setFilterQuery] = useState("");
  const [filterType, setFilterType] = useState<string>("all");
  const [loadTarget, setLoadTarget] = useState<LoadTarget>("smart_composer");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isSavingCopy, setIsSavingCopy] = useState(false);
  const [isCreatingTemplate, setIsCreatingTemplate] = useState(false);
  const [isGeneratingTemplateDraft, setIsGeneratingTemplateDraft] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [fieldSearch, setFieldSearch] = useState("");
  const [isSavingField, setIsSavingField] = useState(false);
  const [isDeletingField, setIsDeletingField] = useState(false);
  const [showAllCanonicalFields, setShowAllCanonicalFields] = useState(false);
  const [fieldFormKey, setFieldFormKey] = useState("");
  const [fieldFormLabel, setFieldFormLabel] = useState("");
  const [fieldFormAliases, setFieldFormAliases] = useState("");
  const [confirmFieldDelete, setConfirmFieldDelete] = useState(false);
  const [createPurposeMode, setCreatePurposeMode] = useState<"existing" | "custom">("existing");
  const [createType, setCreateType] = useState("");
  const [createCustomType, setCreateCustomType] = useState("");
  const [createName, setCreateName] = useState("");
  const [createTagsInput, setCreateTagsInput] = useState("");
  const [createContent, setCreateContent] = useState("");
  const [createVariableNamesInput, setCreateVariableNamesInput] = useState("");
  const [notice, setNotice] = useState<{ type: "error" | "success" | "info"; message: string } | null>(
    null
  );

  useEffect(() => {
    const raw = window.sessionStorage.getItem("siligent_template_library_state_v1");
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as {
          selectedStorageIndex?: number | null;
          filterQuery?: string;
          filterType?: string;
          loadTarget?: LoadTarget;
        };
        if (typeof parsed.filterQuery === "string") {
          setFilterQuery(parsed.filterQuery);
        }
        if (typeof parsed.filterType === "string") {
          setFilterType(parsed.filterType);
        }
        if (
          parsed.loadTarget === "smart_composer" ||
          parsed.loadTarget === "email" ||
          parsed.loadTarget === "denial_letter"
        ) {
          setLoadTarget(parsed.loadTarget);
        }
        if (parsed.selectedStorageIndex === null || Number.isInteger(parsed.selectedStorageIndex)) {
          setSelectedStorageIndex(
            parsed.selectedStorageIndex === null ? null : Number(parsed.selectedStorageIndex)
          );
        }
      } catch {
        window.sessionStorage.removeItem("siligent_template_library_state_v1");
      }
    }
    void refreshAll();
  }, []);

  useEffect(() => {
    window.sessionStorage.setItem(
      "siligent_template_library_state_v1",
      JSON.stringify({
        selectedStorageIndex,
        filterQuery,
        filterType,
        loadTarget,
      })
    );
  }, [selectedStorageIndex, filterQuery, filterType, loadTarget]);

  async function refreshAll() {
    await Promise.all([refreshTemplates(), refreshFieldDictionary(), refreshTemplateTypes()]);
  }

  async function refreshTemplates() {
    setLoading(true);
    try {
      const data = await api.getTemplates();
      setTemplates(data);
      const selectedStillExists = data.some((item) => item.index === selectedStorageIndex);
      const fallback = data[0]?.index ?? null;
      setSelectedStorageIndex(selectedStillExists ? selectedStorageIndex : fallback);
    } catch (error) {
      setNotice({ type: "error", message: resolveErrorMessage(error, "Failed to load templates.") });
    } finally {
      setLoading(false);
    }
  }

  async function refreshFieldDictionary() {
    try {
      const payload = await api.getFieldDictionary();
      const sorted = [...payload.entries].sort((a, b) => a.label.localeCompare(b.label));
      setFieldDictionary(sorted);
      if (!fieldFormKey && !fieldFormLabel && sorted.length > 0) {
        setFieldFormKey(sorted[0].key);
        setFieldFormLabel(sorted[0].label);
        setFieldFormAliases(sorted[0].aliases.join(", "));
      }
    } catch (error) {
      setNotice({
        type: "error",
        message: resolveErrorMessage(error, "Failed to load field dictionary."),
      });
    }
  }

  async function refreshTemplateTypes() {
    try {
      const payload = await api.getTemplateTypes();
      setTemplateTypes(payload.template_types);
      setCreateType((current) => current || payload.template_types[0] || "");
    } catch (error) {
      setNotice({
        type: "error",
        message: resolveErrorMessage(error, "Failed to load template types."),
      });
    }
  }

  const filteredTemplates = useMemo(() => {
    const query = filterQuery.trim().toLowerCase();
    return templates.filter((item) => {
      if (filterType !== "all" && item.type !== filterType) {
        return false;
      }
      if (!query) {
        return true;
      }
      if (item.name.toLowerCase().includes(query) || item.type.toLowerCase().includes(query)) {
        return true;
      }
      return item.tags.some((tag) => tag.includes(query));
    });
  }, [filterQuery, filterType, templates]);

  const availableTypes = useMemo(() => {
    const types = Array.from(new Set(templates.map((item) => item.type))).filter(Boolean);
    return types.sort((a, b) => a.localeCompare(b));
  }, [templates]);
  const availableTypeOptions = useMemo(() => {
    const merged = Array.from(new Set([...templateTypes, ...availableTypes])).filter(Boolean);
    return merged.sort((a, b) => a.localeCompare(b));
  }, [templateTypes, availableTypes]);

  const selected = useMemo(
    () => templates.find((item) => item.index === selectedStorageIndex) ?? null,
    [templates, selectedStorageIndex]
  );
  const canDeleteSelected = canManageTemplate(selected, user, bootstrap);

  useEffect(() => {
    if (!selected) {
      setEditedContent("");
      setNewTagsInput("");
      setRuntimeFields({});
      return;
    }
    setEditedContent(canonicalToNaturalTemplate(selected.content, fieldDictionary));
    setRuntimeFields({});
    setLoadTarget(preferredLoadTarget(selected.type || ""));
    setNewName(selected.name);
    setNewTagsInput(toTagInput(selected.tags));
    setNewTagEntry("");
    setShowAllCanonicalFields(false);
    setConfirmDelete(false);
  }, [selected?.index]);

  const canonicalConversion = useMemo(
    () => naturalToCanonicalTemplate(editedContent, fieldDictionary),
    [editedContent, fieldDictionary]
  );
  const editedPlaceholders = useMemo(
    () => extractTemplatePlaceholders(canonicalConversion.canonical),
    [canonicalConversion.canonical]
  );
  const normalizationSuggestions = useMemo(
    () => collectVariableNormalizationSuggestions(editedContent, fieldDictionary),
    [editedContent, fieldDictionary]
  );
  const narrativeSuggestions = useMemo(
    () => suggestFieldsFromNarrative(editedContent, fieldDictionary, canonicalConversion.usedKeys),
    [editedContent, fieldDictionary, canonicalConversion.usedKeys]
  );

  const canLoadIntoModule = Boolean(selected && canonicalConversion.canonical.trim());
  const canSaveEditedCopy = Boolean(
    selected &&
      canonicalConversion.canonical.trim() &&
      (newName.trim() || selected.name.trim()) &&
      !isSavingCopy &&
      isAdmin
  );
  const canDeleteNow = Boolean(canDeleteSelected && confirmDelete && !isDeleting);
  const selectedTagInput = selected ? toTagInput(selected.tags) : "";
  const editableTags = useMemo(() => parseTagInput(newTagsInput), [newTagsInput]);
  const previewTagLimit = 6;
  const previewFieldLimit = 4;
  const visibleSelectedTags =
    selected?.tags.slice(0, previewTagLimit) ?? [];
  const hiddenSelectedTagCount = Math.max(0, (selected?.tags.length ?? 0) - previewTagLimit);
  const visibleCanonicalFields = showAllCanonicalFields
    ? editedPlaceholders
    : editedPlaceholders.slice(0, previewFieldLimit);
  const hiddenCanonicalFieldCount = Math.max(0, editedPlaceholders.length - visibleCanonicalFields.length);
  const hasUnsavedChanges = Boolean(
    selected &&
      (canonicalConversion.canonical !== selected.content ||
        (newName.trim() || selected.name) !== selected.name ||
        newTagsInput !== selectedTagInput)
  );
  const createCanonicalConversion = useMemo(
    () => naturalToCanonicalTemplate(createContent, fieldDictionary),
    [createContent, fieldDictionary]
  );
  const createVariableNames = useMemo(() => {
    const raw = createVariableNamesInput
      .split(/[,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    const unique = Array.from(new Set(raw.map((item) => item.toLowerCase())));
    return unique.map((normalized) => {
      const found = raw.find((item) => item.toLowerCase() === normalized);
      return found ?? normalized;
    });
  }, [createVariableNamesInput]);
  const createResolvedType = useMemo(() => {
    if (createPurposeMode === "existing") {
      return createType.trim();
    }
    return normalizeFieldKeyFromLabel(createCustomType).replace(/_/g, "_");
  }, [createPurposeMode, createType, createCustomType]);
  const createPlaceholderTokens = useMemo(
    () => extractTemplatePlaceholders(createCanonicalConversion.canonical),
    [createCanonicalConversion.canonical]
  );
  const canCreateTemplate = Boolean(
    !isCreatingTemplate &&
      createResolvedType &&
      createName.trim() &&
      createCanonicalConversion.canonical.trim()
  );
  const canGenerateTemplateDraft = Boolean(
    !isGeneratingTemplateDraft && createResolvedType && createVariableNames.length > 0
  );

  const filteredFieldDictionary = useMemo(() => {
    const query = fieldSearch.trim().toLowerCase();
    if (!query) {
      return fieldDictionary;
    }
    return fieldDictionary.filter((entry) => {
      if (entry.label.toLowerCase().includes(query) || entry.key.toLowerCase().includes(query)) {
        return true;
      }
      return entry.aliases.some((alias) => alias.toLowerCase().includes(query));
    });
  }, [fieldDictionary, fieldSearch]);

  function insertVariableToken(label: string) {
    const token = `[[${label}]]`;
    const textarea = editorRef.current;
    if (!textarea) {
      setEditedContent((current) => `${current}${current.endsWith("\n") || !current ? "" : "\n"}${token}`);
      return;
    }
    const start = textarea.selectionStart ?? editedContent.length;
    const end = textarea.selectionEnd ?? editedContent.length;
    const next = editedContent.slice(0, start) + token + editedContent.slice(end);
    setEditedContent(next);
    const cursorPosition = start + token.length;
    window.requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(cursorPosition, cursorPosition);
    });
  }

  function insertVariableTokenToCreate(label: string) {
    const token = `[[${label}]]`;
    const textarea = createEditorRef.current;
    if (!textarea) {
      setCreateContent((current) => `${current}${current.endsWith("\n") || !current ? "" : "\n"}${token}`);
      return;
    }
    const start = textarea.selectionStart ?? createContent.length;
    const end = textarea.selectionEnd ?? createContent.length;
    const next = createContent.slice(0, start) + token + createContent.slice(end);
    setCreateContent(next);
    const cursorPosition = start + token.length;
    window.requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(cursorPosition, cursorPosition);
    });
  }

  function setEditableTags(tags: string[]) {
    setNewTagsInput(tags.join(", "));
  }

  function addTagFromEntry() {
    const incoming = parseTagInput(newTagEntry);
    if (!incoming.length) {
      return;
    }
    const merged = Array.from(new Set([...editableTags, ...incoming]));
    setEditableTags(merged);
    setNewTagEntry("");
  }

  function removeTag(tag: string) {
    const next = editableTags.filter((item) => item !== tag);
    setEditableTags(next);
  }

  function onLoadIntoModule() {
    if (!selected) {
      return;
    }
    let contentForModule = canonicalConversion.canonical;
    if (loadTarget !== "smart_composer" && editedPlaceholders.length > 0) {
      const rendered = renderTemplateWithRuntimeFields(
        canonicalConversion.canonical,
        compactRuntimeFields(runtimeFields)
      );
      if (rendered.missing.length > 0) {
        setNotice({
          type: "error",
          message: `Missing runtime fields: ${rendered.missing.join(", ")}`,
        });
        return;
      }
      contentForModule = rendered.rendered;
    }
    if (loadTarget === "smart_composer") {
      navigate(
        `/smart-composer?templateIndex=${selected.index}&templateType=${encodeURIComponent(selected.type)}`
      );
    } else if (loadTarget === "email") {
      loadToEmail(contentForModule);
      navigate("/email-drafting");
    } else {
      loadToDenial(contentForModule);
      navigate("/denial-letters");
    }
  }

  async function onSaveEditedCopy() {
    if (!selected) {
      setNotice({ type: "error", message: "Select a template first." });
      return;
    }
    setIsSavingCopy(true);
    try {
      const { cleanContent, cleanName } = validateTemplateSaveInput({
        content: canonicalConversion.canonical,
        name: newName.trim() || selected.name,
        emptyContentMessage: "Template content cannot be empty.",
      });
      if (!isAdmin) {
        await savePersonalTemplate({
          content: cleanContent,
          name: cleanName,
          type: selected.type,
          tagsInput: newTagsInput,
        });
        setNotice({ type: "success", message: "Personal template saved." });
        await refreshTemplates();
        return;
      }

      await api.saveTemplate({
        name: cleanName,
        type: selected.type,
        content: cleanContent,
        visibility: "shared",
        tags: parseTagInput(newTagsInput),
      });
      if (canonicalConversion.unresolvedLabels.length > 0) {
        setNotice({
          type: "info",
          message: `Template saved. New field keys auto-created: ${canonicalConversion.unresolvedLabels
            .map((label) => normalizeFieldKeyFromLabel(label))
            .join(", ")}`,
        });
      } else {
        setNotice({ type: "success", message: "Template changes saved." });
      }
      await refreshTemplates();
    } catch (error) {
      const message =
        error instanceof TemplateSaveInputError
          ? error.message
          : resolveErrorMessage(error, "Unable to save edited copy.");
      setNotice({ type: "error", message });
    } finally {
      setIsSavingCopy(false);
    }
  }

  async function onDeleteSelected() {
    if (!selected) {
      return;
    }
    if (!canDeleteSelected) {
      setNotice({
        type: "error",
        message: "Only admins can delete shared templates. Staff can delete their own personal drafts.",
      });
      return;
    }
    if (!confirmDelete) {
      setNotice({ type: "error", message: "Confirm deletion first." });
      return;
    }
    setIsDeleting(true);
    try {
      await api.deleteTemplate(selected.index);
      setNotice({ type: "success", message: "Template deleted." });
      setConfirmDelete(false);
      await refreshTemplates();
    } catch (error) {
      setNotice({ type: "error", message: resolveErrorMessage(error, "Unable to delete template.") });
    } finally {
      setIsDeleting(false);
    }
  }

  async function onSaveFieldDictionaryEntry() {
    if (!isAdmin) {
      return;
    }
    const resolvedKey = normalizeFieldKeyFromLabel(fieldFormKey || fieldFormLabel);
    const cleanLabel = fieldFormLabel.trim();
    if (!resolvedKey || !cleanLabel) {
      setNotice({ type: "error", message: "Field key and label are required." });
      return;
    }
    setIsSavingField(true);
    try {
      const saved = await api.upsertFieldDictionaryEntry(resolvedKey, {
        label: cleanLabel,
        aliases: parseAliasesInput(fieldFormAliases),
      });
      await refreshFieldDictionary();
      setFieldFormKey(saved.key);
      setFieldFormLabel(saved.label);
      setFieldFormAliases(saved.aliases.join(", "));
      setConfirmFieldDelete(false);
      setNotice({ type: "success", message: `Field "${saved.label}" saved.` });
    } catch (error) {
      setNotice({
        type: "error",
        message: resolveErrorMessage(error, "Unable to save field dictionary entry."),
      });
    } finally {
      setIsSavingField(false);
    }
  }

  async function onDeleteFieldDictionaryEntry() {
    if (!isAdmin) {
      return;
    }
    const resolvedKey = normalizeFieldKeyFromLabel(fieldFormKey);
    if (!resolvedKey) {
      setNotice({ type: "error", message: "Select a field first." });
      return;
    }
    if (!confirmFieldDelete) {
      setNotice({ type: "error", message: "Confirm field deletion first." });
      return;
    }
    setIsDeletingField(true);
    try {
      await api.deleteFieldDictionaryEntry(resolvedKey);
      await refreshFieldDictionary();
      const fallback = fieldDictionary.find((entry) => entry.key !== resolvedKey);
      if (fallback) {
        setFieldFormKey(fallback.key);
        setFieldFormLabel(fallback.label);
        setFieldFormAliases(fallback.aliases.join(", "));
      } else {
        setFieldFormKey("");
        setFieldFormLabel("");
        setFieldFormAliases("");
      }
      setConfirmFieldDelete(false);
      setNotice({ type: "success", message: `Field "${resolvedKey}" deleted.` });
    } catch (error) {
      setNotice({
        type: "error",
        message: resolveErrorMessage(error, "Unable to delete field dictionary entry."),
      });
    } finally {
      setIsDeletingField(false);
    }
  }

  async function onCreateTemplate() {
    if (!canCreateTemplate) {
      setNotice({
        type: "error",
        message: "Template type, name, and template body are required.",
      });
      return;
    }
    setIsCreatingTemplate(true);
    try {
      const { cleanContent, cleanName } = validateTemplateSaveInput({
        content: createCanonicalConversion.canonical,
        name: createName,
        emptyContentMessage: "Template content cannot be empty.",
      });
      const resolvedType = createResolvedType;
      if (!resolvedType) {
        setNotice({ type: "error", message: "Choose or enter a template type." });
        return;
      }
      if (!isAdmin) {
        await savePersonalTemplate({
          name: cleanName,
          type: resolvedType,
          content: cleanContent,
          tagsInput: createTagsInput,
        });
      } else {
        await api.saveTemplate({
          name: cleanName,
          type: resolvedType,
          content: cleanContent,
          visibility: "shared",
          tags: parseTagInput(createTagsInput),
        });
      }

      setCreateName("");
      setCreateTagsInput("");
      setCreateContent("");
      setCreateVariableNamesInput("");
      setCreateCustomType("");
      if (createPurposeMode === "custom") {
        setCreatePurposeMode("existing");
      }
      await refreshAll();
      setNotice({ type: "success", message: "Template created successfully." });
    } catch (error) {
      const message =
        error instanceof TemplateSaveInputError
          ? error.message
          : resolveErrorMessage(error, "Unable to create template.");
      setNotice({ type: "error", message });
    } finally {
      setIsCreatingTemplate(false);
    }
  }

  async function onGenerateTemplateDraft() {
    if (!canGenerateTemplateDraft) {
      setNotice({
        type: "error",
        message: "Choose a purpose type and add at least one variable name to generate a draft.",
      });
      return;
    }
    setIsGeneratingTemplateDraft(true);
    try {
      const response = await api.generateTemplateDraft({
        template_type: createResolvedType,
        variable_names: createVariableNames,
      });
      setCreateContent(response.text);
      setNotice({ type: "success", message: "Template draft generated. Review and edit before saving." });
    } catch (error) {
      setNotice({ type: "error", message: resolveErrorMessage(error, "Unable to generate template draft.") });
    } finally {
      setIsGeneratingTemplateDraft(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>Template Library</h1>
        <p>Manage one canonical template per purpose type and author variables in natural language tokens.</p>
      </header>

      {notice && <Notice type={notice.type} message={notice.message} />}

      <div className="panel">
        <h2>Quick Template Creator</h2>
        <p className="helper">
          Create templates in 4 simple steps. Advanced editing is available below.
        </p>
        <div className="wizard-steps" aria-label="Template creation steps">
          <div className={`wizard-step static${createResolvedType ? " done" : " active"}`}>
            <span className="wizard-step-index">1</span>
            Purpose
          </div>
          <div className={`wizard-step static${createName.trim() ? " done" : createResolvedType ? " active" : ""}`}>
            <span className="wizard-step-index">2</span>
            Basics
          </div>
          <div
            className={`wizard-step static${
              createCanonicalConversion.canonical.trim() ? " done" : createName.trim() ? " active" : ""
            }`}
          >
            <span className="wizard-step-index">3</span>
            Write
          </div>
          <div
            className={`wizard-step static${
              canCreateTemplate ? " active done" : createCanonicalConversion.canonical.trim() ? " active" : ""
            }`}
          >
            <span className="wizard-step-index">4</span>
            Save
          </div>
          <div className="wizard-step static">
            <span className="wizard-step-index">5</span>
            Use
          </div>
        </div>

        <div className="panel-grid two-col">
          <div className="summary">
            <h3>1. Choose purpose</h3>
            <label className="checkbox-inline">
              <input
                type="radio"
                name="create-purpose-mode"
                checked={createPurposeMode === "existing"}
                onChange={() => setCreatePurposeMode("existing")}
              />
              Use existing purpose type
            </label>
            <label className="checkbox-inline">
              <input
                type="radio"
                name="create-purpose-mode"
                checked={createPurposeMode === "custom"}
                onChange={() => setCreatePurposeMode("custom")}
              />
              Add new purpose type
            </label>
            {createPurposeMode === "existing" ? (
              <label>
                Purpose type
                <select value={createType} onChange={(event) => setCreateType(event.target.value)}>
                  <option value="">Select purpose type</option>
                  {availableTypeOptions.map((typeName) => (
                    <option key={typeName} value={typeName}>
                      {typeName}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <label>
                New purpose type
                <input
                  value={createCustomType}
                  onChange={(event) => setCreateCustomType(event.target.value)}
                  placeholder="example: insurance_follow_up"
                />
              </label>
            )}

            <h3>2. Add basics</h3>
            <label>
              Template name
              <input
                value={createName}
                onChange={(event) => setCreateName(event.target.value)}
                placeholder="example: Insurance Verification Reply"
              />
            </label>
            <label>
              Tags (optional)
              <input
                value={createTagsInput}
                onChange={(event) => setCreateTagsInput(event.target.value)}
                placeholder="example: insurance, verification, frontdesk"
              />
            </label>
          </div>

          <div className="summary">
            <h3>3. Write template</h3>
            <p className="helper">
              Use natural variables like <code>[[Patient Name]]</code>. The app maps to canonical fields automatically.
            </p>
            <label>
              Variable names for AI draft generation
              <input
                value={createVariableNamesInput}
                onChange={(event) => setCreateVariableNamesInput(event.target.value)}
                placeholder="example: patient_name, appointment_date, provider_name"
              />
            </label>
            <div className="inline-actions">
              <button
                className="secondary-btn"
                type="button"
                onClick={() => void onGenerateTemplateDraft()}
                disabled={!canGenerateTemplateDraft}
              >
                {isGeneratingTemplateDraft ? "Generating..." : "Generate Draft With AI"}
              </button>
              {createVariableNames.length > 0 ? (
                <span className="chip">{createVariableNames.length} variable(s)</span>
              ) : (
                <span className="chip">No variables yet</span>
              )}
            </div>
            <label>
              Find field
              <input
                value={fieldSearch}
                onChange={(event) => setFieldSearch(event.target.value)}
                placeholder="Search patient, payer, appointment..."
              />
            </label>
            <div className="chips-wrap">
              {filteredFieldDictionary.slice(0, 10).map((entry) => (
                <button
                  key={`create-${entry.key}`}
                  type="button"
                  className="chip-btn"
                  onClick={() => insertVariableTokenToCreate(entry.label)}
                >
                  + {entry.label}
                </button>
              ))}
            </div>
            <textarea
              ref={createEditorRef}
              className="output"
              value={createContent}
              onChange={(event) => setCreateContent(event.target.value)}
              placeholder="Write your template draft here..."
            />
          </div>
        </div>

        <div className="template-create-footer">
          {createPlaceholderTokens.length > 0 ? (
            <p className="helper">
              Fields detected: {createPlaceholderTokens.map((token) => `{{${token}}}`).join(", ")}
            </p>
          ) : null}
          {createCanonicalConversion.unresolvedLabels.length > 0 ? (
            <Notice
              type="info"
              message={`New field keys will be generated: ${createCanonicalConversion.unresolvedLabels
                .map((label) => normalizeFieldKeyFromLabel(label))
                .join(", ")}`}
            />
          ) : null}
          <div className="inline-actions">
            <button
              className="secondary-btn"
              type="button"
              onClick={() => {
                setCreateName("");
                setCreateTagsInput("");
                setCreateContent("");
                setCreateVariableNamesInput("");
                setCreateCustomType("");
                setCreatePurposeMode("existing");
              }}
            >
              Clear
            </button>
            <button
              className="primary-btn"
              type="button"
              onClick={() => void onCreateTemplate()}
              disabled={!canCreateTemplate}
            >
              {isCreatingTemplate ? "Saving..." : "Save Template"}
            </button>
          </div>
        </div>
      </div>

      <details className="template-advanced-section">
        <summary>Advanced Template Manager</summary>
        <div className="panel-grid two-col">
        <div className="panel">
          <h2>Saved templates</h2>
          {loading ? <p className="placeholder">Loading templates...</p> : null}
          {!loading && templates.length === 0 ? <p className="placeholder">No templates saved yet.</p> : null}
          {templates.length > 0 ? (
            <>
              <div className="template-library-filters">
                <label>
                  Search templates
                  <input
                    value={filterQuery}
                    onChange={(event) => setFilterQuery(event.target.value)}
                    placeholder="e.g. denial, email, insurance"
                  />
                </label>
                <label>
                  Filter by purpose type
                  <select value={filterType} onChange={(event) => setFilterType(event.target.value)}>
                    <option value="all">All types</option>
                    {availableTypes.map((typeValue) => (
                      <option key={typeValue} value={typeValue}>
                        {typeValue}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="template-list" role="listbox" aria-label="Templates">
                {filteredTemplates.map((item) => {
                  const isActive = item.index === selectedStorageIndex;
                  return (
                    <button
                      key={item.index}
                      type="button"
                      className={`template-list-item${isActive ? " active" : ""}`}
                      onClick={() => setSelectedStorageIndex(item.index)}
                    >
                      <div className="template-list-title-row">
                        <strong>{item.name}</strong>
                        <span className="chip">{item.type}</span>
                      </div>
                      <p className="helper">
                        {templateScopeLabel(item)} • {new Date(item.created_at).toLocaleString()}
                      </p>
                    </button>
                  );
                })}
              </div>
              {filteredTemplates.length === 0 ? <p className="helper">No templates match this filter.</p> : null}
            </>
          ) : null}

          {selected ? (
            <div className="template-selected-summary">
              <p className="helper">
                <strong>Type:</strong> {selected.type} | <strong>Scope:</strong> {templateScopeLabel(selected)} |{" "}
                <strong>Created:</strong> {new Date(selected.created_at).toLocaleString()}
              </p>
              {selected.tags.length > 0 ? (
                <div className="template-meta-group">
                  <p className="helper">Purpose tags</p>
                  <div className="chips-wrap template-tag-list">
                    {visibleSelectedTags.map((tag) => (
                      <span className="chip template-tag-chip" key={tag}>
                        #{tag}
                      </span>
                    ))}
                    {hiddenSelectedTagCount > 0 ? (
                      <span className="chip template-tag-chip">+{hiddenSelectedTagCount} more</span>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {editedPlaceholders.length > 0 ? (
                <div className="template-meta-group">
                  <p className="helper">
                    Canonical fields this template expects ({editedPlaceholders.length})
                  </p>
                  <div className="chips-wrap template-field-list">
                    {visibleCanonicalFields.map((token) => (
                      <span className="chip template-field-chip" key={token}>
                        {`{{${token}}}`}
                      </span>
                    ))}
                  </div>
                  {hiddenCanonicalFieldCount > 0 ? (
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={() => setShowAllCanonicalFields((current) => !current)}
                    >
                      {showAllCanonicalFields
                        ? "Show fewer fields"
                        : `Show ${hiddenCanonicalFieldCount} more fields`}
                    </button>
                  ) : null}
                </div>
              ) : null}
              <div className="template-open-workspace">
                <label>
                  Open in workspace
                  <select value={loadTarget} onChange={(event) => setLoadTarget(event.target.value as LoadTarget)}>
                    <option value="smart_composer">Smart Composer (Recommended)</option>
                    <option value="email">Email Drafting</option>
                    <option value="denial_letter">Denial Letters</option>
                  </select>
                </label>
                <button
                  className="secondary-btn"
                  type="button"
                  onClick={onLoadIntoModule}
                  disabled={!canLoadIntoModule}
                >
                  Open selected template
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <div className="panel">
          <h2>Edit canonical template</h2>
          <p className="helper">
            {isAdmin
              ? "Changes update the single canonical template for this purpose type."
              : "You can review templates and save personal variants. Shared canonical templates are admin-managed."}
          </p>
          <p className="helper">
            Use natural field tokens like <code>[[Patient Name]]</code>. The app saves canonical keys like{" "}
            <code>{"{{patient_name}}"}</code>.
          </p>

          <div className="template-variable-toolbar">
            <label>
              Find field
              <input
                value={fieldSearch}
                onChange={(event) => setFieldSearch(event.target.value)}
                placeholder="Search patient, payer, appointment..."
              />
            </label>
            <div className="chips-wrap">
              {filteredFieldDictionary.slice(0, 10).map((entry) => (
                <button
                  key={entry.key}
                  type="button"
                  className="chip-btn"
                  onClick={() => insertVariableToken(entry.label)}
                >
                  + {entry.label}
                </button>
              ))}
            </div>
          </div>

          <textarea
            ref={editorRef}
            className="output"
            value={editedContent}
            onChange={(event) => setEditedContent(event.target.value)}
            placeholder="Select a template to view or edit. Use [[Patient Name]] style fields."
          />
          <OutputActions text={editedContent} filenamePrefix="template_content" />
          {hasUnsavedChanges ? <Notice type="info" message="You have unsaved template changes." /> : null}

          {normalizationSuggestions.length > 0 ? (
            <div className="summary">
              <p className="helper">
                Found {normalizationSuggestions.length} variable formatting improvements.
              </p>
              <button
                className="secondary-btn"
                type="button"
                onClick={() =>
                  setEditedContent(
                    applyVariableNormalizationSuggestions(editedContent, normalizationSuggestions)
                  )
                }
              >
                Normalize variable labels
              </button>
            </div>
          ) : null}

          {narrativeSuggestions.length > 0 ? (
            <div className="summary">
              <p className="helper">Detected field mentions in the template text. Add them as tokens:</p>
              <div className="chips-wrap">
                {narrativeSuggestions.map((entry) => (
                  <button
                    key={entry.key}
                    className="chip-btn"
                    type="button"
                    onClick={() => insertVariableToken(entry.label)}
                  >
                    Add [[{entry.label}]]
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {canonicalConversion.unresolvedLabels.length > 0 ? (
            <Notice
              type="info"
              message={`Unmapped field labels will be saved with generated keys: ${canonicalConversion.unresolvedLabels
                .map((label) => normalizeFieldKeyFromLabel(label))
                .join(", ")}`}
            />
          ) : null}

          {editedPlaceholders.length > 0 ? (
            <RuntimeFieldsEditor
              values={runtimeFields}
              onChange={setRuntimeFields}
              suggestedKeys={editedPlaceholders}
              title="Fill details before opening (optional)"
              helperText="For Email Drafting and Denial Letters, fill these now to open a ready-to-use draft."
            />
          ) : null}

          <div className="template-metadata-editor">
            <label>
              Template name
              <input
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
                placeholder="Template name"
              />
            </label>
            <div className="template-edit-tag-field">
              <span className="field-label">Tags</span>
              <div className="tag-input-row">
                <input
                  value={newTagEntry}
                  onChange={(event) => setNewTagEntry(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === ",") {
                      event.preventDefault();
                      addTagFromEntry();
                    }
                  }}
                  placeholder="Type tag and press Enter (example: urgent)"
                />
                <button
                  className="secondary-btn"
                  type="button"
                  onClick={addTagFromEntry}
                  disabled={!newTagEntry.trim()}
                >
                  Add tag
                </button>
              </div>
            </div>
            {editableTags.length > 0 ? (
              <div className="chips-wrap">
                {editableTags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className="chip-btn removable"
                    onClick={() => removeTag(tag)}
                    title={`Remove tag ${tag}`}
                  >
                    #{tag} ×
                  </button>
                ))}
              </div>
            ) : (
              <p className="helper">No tags added.</p>
            )}
            <div className="inline-actions">
              {isAdmin ? (
                <select value="shared" disabled>
                  <option value="shared">Canonical shared</option>
                </select>
              ) : (
                <span className="chip">Personal copy</span>
              )}
              <button
                className="secondary-btn"
                type="button"
                onClick={onSaveEditedCopy}
                disabled={!canSaveEditedCopy}
              >
                {isSavingCopy ? "Saving..." : isAdmin ? "Save template" : "Save personal copy"}
              </button>
            </div>
          </div>
          <button
            className="secondary-btn"
            type="button"
            onClick={() => {
              if (!selected) {
                return;
              }
              setEditedContent(canonicalToNaturalTemplate(selected.content, fieldDictionary));
              setNewName(selected.name);
              setNewTagsInput(toTagInput(selected.tags));
              setNewTagEntry("");
            }}
            disabled={!selected || !hasUnsavedChanges}
          >
            Revert unsaved changes
          </button>

          <div className="danger-row">
            <label className="checkbox-inline">
              <input
                type="checkbox"
                checked={confirmDelete}
                disabled={!canDeleteSelected || isDeleting}
                onChange={(event) => setConfirmDelete(event.target.checked)}
              />
              I confirm deletion
            </label>
            <button className="danger-btn" type="button" onClick={onDeleteSelected} disabled={!canDeleteNow}>
              {isDeleting ? "Deleting..." : "Delete template"}
            </button>
          </div>
          {!canDeleteSelected && selected ? (
            <p className="helper">Shared templates are governed by admins.</p>
          ) : null}
        </div>
      </div>

      {isAdmin ? (
        <div className="panel">
          <h2>Field dictionary (Admin)</h2>
          <p className="helper">
            Manage reusable field labels and aliases used by tokenized templates and auto-mapping.
          </p>

          <div className="panel-grid two-col">
            <div className="summary">
              <p className="helper">Saved fields</p>
              <div className="template-list">
                {fieldDictionary.map((entry) => (
                  <button
                    key={entry.key}
                    type="button"
                    className={`template-list-item${entry.key === fieldFormKey ? " active" : ""}`}
                    onClick={() => {
                      setFieldFormKey(entry.key);
                      setFieldFormLabel(entry.label);
                      setFieldFormAliases(entry.aliases.join(", "));
                      setConfirmFieldDelete(false);
                    }}
                  >
                    <div className="template-list-title-row">
                      <strong>{entry.label}</strong>
                      <span className="chip">{entry.key}</span>
                    </div>
                    <p className="helper">{entry.aliases.length ? entry.aliases.join(", ") : "No aliases"}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="summary">
              <p className="helper">Edit field</p>
              <label>
                Field key
                <input
                  value={fieldFormKey}
                  onChange={(event) => setFieldFormKey(normalizeFieldKeyFromLabel(event.target.value))}
                  placeholder="patient_name"
                />
              </label>
              <label>
                Field label
                <input
                  value={fieldFormLabel}
                  onChange={(event) => setFieldFormLabel(event.target.value)}
                  placeholder={labelFromFieldKey(fieldFormKey || "patient_name")}
                />
              </label>
              <label>
                Aliases (comma-separated)
                <input
                  value={fieldFormAliases}
                  onChange={(event) => setFieldFormAliases(event.target.value)}
                  placeholder="full name, patient full name"
                />
              </label>
              <div className="inline-actions">
                <button
                  className="secondary-btn"
                  type="button"
                  onClick={onSaveFieldDictionaryEntry}
                  disabled={isSavingField}
                >
                  {isSavingField ? "Saving..." : "Save field"}
                </button>
                <button
                  className="secondary-btn"
                  type="button"
                  onClick={() => {
                    setFieldFormKey("");
                    setFieldFormLabel("");
                    setFieldFormAliases("");
                    setConfirmFieldDelete(false);
                  }}
                >
                  New field
                </button>
              </div>
              <div className="danger-row">
                <label className="checkbox-inline">
                  <input
                    type="checkbox"
                    checked={confirmFieldDelete}
                    onChange={(event) => setConfirmFieldDelete(event.target.checked)}
                  />
                  Confirm field deletion
                </label>
                <button
                  className="danger-btn"
                  type="button"
                  onClick={onDeleteFieldDictionaryEntry}
                  disabled={!fieldFormKey || !confirmFieldDelete || isDeletingField}
                >
                  {isDeletingField ? "Deleting..." : "Delete field"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
      </details>
    </section>
  );
}
