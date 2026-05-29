import type { ReactNode } from "react";

type TemplateSaveBarProps = {
  nameValue: string;
  tagsValue: string;
  onNameChange: (value: string) => void;
  onTagsChange: (value: string) => void;
  onSave: () => void;
  disabled: boolean;
  saving: boolean;
  namePlaceholder?: string;
  tagsPlaceholder?: string;
  idleLabel?: string;
  savingLabel?: string;
  extraControl?: ReactNode;
};

export function TemplateSaveBar({
  nameValue,
  tagsValue,
  onNameChange,
  onTagsChange,
  onSave,
  disabled,
  saving,
  namePlaceholder = "Template name",
  tagsPlaceholder = "Optional labels (example: billing, urgent)",
  idleLabel = "Save Template",
  savingLabel = "Saving...",
  extraControl,
}: TemplateSaveBarProps) {
  return (
    <div className="inline-actions">
      <input
        aria-label="Template name"
        placeholder={namePlaceholder}
        value={nameValue}
        onChange={(event) => onNameChange(event.target.value)}
      />
      <input
        aria-label="Template tags"
        placeholder={tagsPlaceholder}
        value={tagsValue}
        onChange={(event) => onTagsChange(event.target.value)}
      />
      {extraControl}
      <button className="secondary-btn" type="button" onClick={onSave} disabled={disabled}>
        {saving ? savingLabel : idleLabel}
      </button>
    </div>
  );
}
