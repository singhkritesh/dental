export function parseTagInput(raw: string): string[] {
  const seen = new Set<string>();
  const tags: string[] = [];
  for (const value of raw.split(",")) {
    const tag = value.trim().toLowerCase();
    if (!tag || seen.has(tag)) {
      continue;
    }
    seen.add(tag);
    tags.push(tag);
  }
  return tags;
}

export function toTagInput(tags: string[] | undefined): string {
  if (!tags?.length) {
    return "";
  }
  return tags.join(", ");
}
