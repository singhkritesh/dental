export function compactRuntimeFields(values: Record<string, string>): Record<string, string> {
  const compact: Record<string, string> = {};
  for (const [rawKey, rawValue] of Object.entries(values)) {
    const key = rawKey.trim();
    const value = rawValue.trim();
    if (!key || !value) {
      continue;
    }
    compact[key] = value;
  }
  return compact;
}

export function hasRuntimeFields(values: Record<string, string>): boolean {
  return Object.keys(compactRuntimeFields(values)).length > 0;
}
