import { useMemo, useState } from "react";

type RuntimeFieldsEditorProps = {
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  suggestedKeys?: string[];
  title?: string;
  helperText?: string;
};

function toFriendlyLabel(token: string): string {
  return token
    .replace(/[._-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function normalizeKey(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^a-z0-9_.-]/g, "")
    .slice(0, 80);
}

export function RuntimeFieldsEditor({
  values,
  onChange,
  suggestedKeys = [],
  title = "Patient and case details",
  helperText = "Fill in known details. You can add more fields if needed.",
}: RuntimeFieldsEditorProps) {
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");

  const suggestedSet = useMemo(
    () => new Set(suggestedKeys.map((item) => item.trim()).filter(Boolean)),
    [suggestedKeys]
  );

  const orderedKeys = useMemo(() => {
    const fromValues = Object.keys(values);
    const unique = new Set<string>([...suggestedKeys, ...fromValues]);
    return Array.from(unique).filter(Boolean);
  }, [suggestedKeys, values]);

  function updateKeyValue(key: string, nextValue: string) {
    onChange({ ...values, [key]: nextValue });
  }

  function removeKey(key: string) {
    const next = { ...values };
    delete next[key];
    onChange(next);
  }

  function addCustomField() {
    const cleanKey = normalizeKey(newKey);
    if (!cleanKey) {
      return;
    }
    onChange({
      ...values,
      [cleanKey]: newValue.trim(),
    });
    setNewKey("");
    setNewValue("");
  }

  return (
    <div className="runtime-fields-editor">
      <p className="helper">
        <strong>{title}</strong>
      </p>
      <p className="helper">{helperText}</p>
      {orderedKeys.length > 0 ? (
        <div className="runtime-fields-grid">
          {orderedKeys.map((key) => (
            <div className="runtime-field-row" key={key}>
              <label>
                {toFriendlyLabel(key)}
                <input
                  value={values[key] ?? ""}
                  onChange={(event) => updateKeyValue(key, event.target.value)}
                  placeholder={`Enter ${toFriendlyLabel(key).toLowerCase()}`}
                />
              </label>
              {!suggestedSet.has(key) ? (
                <button
                  className="secondary-btn"
                  type="button"
                  onClick={() => removeKey(key)}
                  aria-label={`Remove ${key}`}
                >
                  Remove
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="helper">No suggested fields yet. Add a field below.</p>
      )}

      <div className="inline-actions">
        <input
          value={newKey}
          onChange={(event) => setNewKey(event.target.value)}
          placeholder="Field name (example: patient_name)"
        />
        <input
          value={newValue}
          onChange={(event) => setNewValue(event.target.value)}
          placeholder="Value"
        />
        <button className="secondary-btn" type="button" onClick={addCustomField} disabled={!normalizeKey(newKey)}>
          Add Field
        </button>
      </div>
    </div>
  );
}
