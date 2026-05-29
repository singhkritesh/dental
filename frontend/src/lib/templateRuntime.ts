export type TemplateRenderResult = {
  rendered: string;
  placeholders: string[];
  missing: string[];
  used: Record<string, string>;
};

const PLACEHOLDER_TOKEN = "[A-Za-z][A-Za-z0-9_.-]{0,79}";
const PLACEHOLDER_PATTERN = new RegExp(
  `\\{\\{\\s*(${PLACEHOLDER_TOKEN})\\s*\\}\\}|(?<!\\{)\\{(${PLACEHOLDER_TOKEN})\\}(?!\\})`,
  "g"
);

export function extractTemplatePlaceholders(content: string): string[] {
  const found = new Set<string>();
  const matches = content.matchAll(PLACEHOLDER_PATTERN);
  for (const match of matches) {
    const token = (match[1] || match[2] || "").trim();
    if (token) {
      found.add(token);
    }
  }
  return Array.from(found).sort();
}

function normalizeRuntimeFields(raw: Record<string, unknown>): Record<string, string> {
  const normalized: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw)) {
    const token = key.trim();
    if (!token) {
      continue;
    }
    if (value === null || value === undefined) {
      normalized[token] = "";
    } else if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      normalized[token] = String(value).trim();
    } else {
      normalized[token] = JSON.stringify(value);
    }
  }
  return normalized;
}

export function parseRuntimeFieldsJson(rawJson: string): Record<string, string> {
  const raw = rawJson.trim();
  if (!raw) {
    return {};
  }
  const parsed = JSON.parse(raw) as unknown;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Runtime fields must be a JSON object.");
  }
  return normalizeRuntimeFields(parsed as Record<string, unknown>);
}

export function renderTemplateWithRuntimeFields(
  content: string,
  runtimeFields: Record<string, string>
): TemplateRenderResult {
  const placeholders = extractTemplatePlaceholders(content);
  if (!placeholders.length) {
    return { rendered: content, placeholders: [], missing: [], used: {} };
  }

  const lowerLookup = new Map<string, string>();
  for (const key of Object.keys(runtimeFields)) {
    lowerLookup.set(key.toLowerCase(), key);
  }

  const missing = new Set<string>();
  const used: Record<string, string> = {};
  const rendered = content.replace(PLACEHOLDER_PATTERN, (...args: string[]) => {
    const token = (args[1] || args[2] || "").trim();
    if (!token) {
      return args[0];
    }

    if (Object.prototype.hasOwnProperty.call(runtimeFields, token)) {
      used[token] = runtimeFields[token];
      return runtimeFields[token];
    }

    const resolvedKey = lowerLookup.get(token.toLowerCase());
    if (resolvedKey) {
      used[token] = runtimeFields[resolvedKey];
      return runtimeFields[resolvedKey];
    }

    missing.add(token);
    return args[0];
  });

  return {
    rendered,
    placeholders,
    missing: Array.from(missing).sort(),
    used,
  };
}
