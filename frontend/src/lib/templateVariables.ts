import type { FieldDictionaryEntry } from "./types";

const LEGACY_PLACEHOLDER_TOKEN = "[A-Za-z][A-Za-z0-9_.-]{0,79}";
const LEGACY_PLACEHOLDER_PATTERN = new RegExp(
  `\\{\\{\\s*(${LEGACY_PLACEHOLDER_TOKEN})\\s*\\}\\}|(?<!\\{)\\{(${LEGACY_PLACEHOLDER_TOKEN})\\}(?!\\})`,
  "g"
);
const NATURAL_TOKEN_PATTERN = /\[\[\s*([^[\]]{1,80})\s*\]\]/g;

export type TemplateConversionResult = {
  canonical: string;
  unresolvedLabels: string[];
  usedKeys: string[];
};

export type VariableNormalizationSuggestion = {
  source: string;
  replacement: string;
  reason: string;
};

function normalizePhrase(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizeFieldKeyFromLabel(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function labelFromFieldKey(raw: string): string {
  return raw
    .trim()
    .replace(/[_-]+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

type Lookup = {
  keyToLabel: Map<string, string>;
  phraseToKey: Map<string, string>;
  keys: Set<string>;
};

function buildLookup(entries: FieldDictionaryEntry[]): Lookup {
  const keyToLabel = new Map<string, string>();
  const phraseToKey = new Map<string, string>();
  const keys = new Set<string>();

  for (const entry of entries) {
    const key = normalizeFieldKeyFromLabel(entry.key);
    if (!key) {
      continue;
    }
    keys.add(key);
    keyToLabel.set(key, entry.label.trim() || labelFromFieldKey(key));
    phraseToKey.set(normalizePhrase(key), key);
    phraseToKey.set(normalizePhrase(entry.label), key);
    for (const alias of entry.aliases || []) {
      const normalizedAlias = normalizePhrase(alias);
      if (normalizedAlias) {
        phraseToKey.set(normalizedAlias, key);
      }
    }
  }
  return { keyToLabel, phraseToKey, keys };
}

function resolveFieldKey(raw: string, lookup: Lookup): string | null {
  const normalized = normalizePhrase(raw);
  if (!normalized) {
    return null;
  }
  if (lookup.phraseToKey.has(normalized)) {
    return lookup.phraseToKey.get(normalized) || null;
  }
  if (lookup.keys.has(normalized.replace(/\s+/g, "_"))) {
    return normalized.replace(/\s+/g, "_");
  }
  if (normalized.length >= 4) {
    for (const [phrase, key] of lookup.phraseToKey.entries()) {
      if (phrase.includes(normalized) || normalized.includes(phrase)) {
        return key;
      }
    }
  }
  return null;
}

export function canonicalToNaturalTemplate(
  content: string,
  fields: FieldDictionaryEntry[]
): string {
  const lookup = buildLookup(fields);
  return content.replace(LEGACY_PLACEHOLDER_PATTERN, (...args: string[]) => {
    const token = (args[1] || args[2] || "").trim();
    if (!token) {
      return args[0];
    }
    const resolvedKey = resolveFieldKey(token, lookup) ?? normalizeFieldKeyFromLabel(token);
    if (!resolvedKey) {
      return args[0];
    }
    const label = lookup.keyToLabel.get(resolvedKey) || labelFromFieldKey(resolvedKey);
    return `[[${label}]]`;
  });
}

export function naturalToCanonicalTemplate(
  content: string,
  fields: FieldDictionaryEntry[]
): TemplateConversionResult {
  const lookup = buildLookup(fields);
  const unresolved = new Set<string>();
  const usedKeys = new Set<string>();

  let converted = content.replace(NATURAL_TOKEN_PATTERN, (...args: string[]) => {
    const label = (args[1] || "").trim();
    if (!label) {
      return args[0];
    }
    const resolvedKey = resolveFieldKey(label, lookup) ?? normalizeFieldKeyFromLabel(label);
    if (!resolvedKey) {
      return args[0];
    }
    usedKeys.add(resolvedKey);
    if (!resolveFieldKey(label, lookup)) {
      unresolved.add(label);
    }
    return `{{${resolvedKey}}}`;
  });

  converted = converted.replace(LEGACY_PLACEHOLDER_PATTERN, (...args: string[]) => {
    const token = (args[1] || args[2] || "").trim();
    if (!token) {
      return args[0];
    }
    const resolvedKey = resolveFieldKey(token, lookup) ?? normalizeFieldKeyFromLabel(token);
    if (!resolvedKey) {
      return args[0];
    }
    usedKeys.add(resolvedKey);
    return `{{${resolvedKey}}}`;
  });

  return {
    canonical: converted,
    unresolvedLabels: Array.from(unresolved).sort(),
    usedKeys: Array.from(usedKeys).sort(),
  };
}

export function collectVariableNormalizationSuggestions(
  content: string,
  fields: FieldDictionaryEntry[]
): VariableNormalizationSuggestion[] {
  const lookup = buildLookup(fields);
  const suggestions = new Map<string, VariableNormalizationSuggestion>();

  for (const match of content.matchAll(NATURAL_TOKEN_PATTERN)) {
    const full = match[0];
    const label = (match[1] || "").trim();
    if (!label) {
      continue;
    }
    const resolvedKey = resolveFieldKey(label, lookup);
    if (!resolvedKey) {
      continue;
    }
    const targetLabel = lookup.keyToLabel.get(resolvedKey) || labelFromFieldKey(resolvedKey);
    const replacement = `[[${targetLabel}]]`;
    if (full !== replacement) {
      suggestions.set(full, {
        source: full,
        replacement,
        reason: `Normalize to saved field "${targetLabel}".`,
      });
    }
  }

  for (const match of content.matchAll(LEGACY_PLACEHOLDER_PATTERN)) {
    const full = match[0];
    const token = (match[1] || match[2] || "").trim();
    if (!token) {
      continue;
    }
    const resolvedKey = resolveFieldKey(token, lookup);
    if (!resolvedKey) {
      continue;
    }
    const targetLabel = lookup.keyToLabel.get(resolvedKey) || labelFromFieldKey(resolvedKey);
    const replacement = `[[${targetLabel}]]`;
    suggestions.set(full, {
      source: full,
      replacement,
      reason: `Convert legacy placeholder to field token "${targetLabel}".`,
    });
  }

  return Array.from(suggestions.values());
}

export function applyVariableNormalizationSuggestions(
  content: string,
  suggestions: VariableNormalizationSuggestion[]
): string {
  let next = content;
  for (const suggestion of suggestions) {
    if (!suggestion.source || suggestion.source === suggestion.replacement) {
      continue;
    }
    next = next.split(suggestion.source).join(suggestion.replacement);
  }
  return next;
}

export function suggestFieldsFromNarrative(
  content: string,
  fields: FieldDictionaryEntry[],
  usedKeys: string[]
): FieldDictionaryEntry[] {
  const used = new Set(usedKeys.map((key) => normalizeFieldKeyFromLabel(key)));
  const plainText = content.toLowerCase();
  const suggestions: FieldDictionaryEntry[] = [];

  for (const entry of fields) {
    const key = normalizeFieldKeyFromLabel(entry.key);
    if (!key || used.has(key)) {
      continue;
    }
    const phrases = [entry.label, ...(entry.aliases || [])]
      .map((value) => normalizePhrase(value))
      .filter((value) => value.length >= 4);
    if (!phrases.length) {
      continue;
    }
    const matched = phrases.some((phrase) => plainText.includes(phrase));
    if (matched) {
      suggestions.push(entry);
    }
  }

  return suggestions.slice(0, 8);
}
