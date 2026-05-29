import { api } from "./api";
import { parseTagInput } from "./templateTags";

export class TemplateSaveInputError extends Error {}

type ValidateTemplateSaveInput = {
  content: string;
  name: string;
  emptyContentMessage: string;
};

type SavePersonalTemplateInput = {
  content: string;
  name: string;
  type: string;
  tagsInput: string;
};

export function validateTemplateSaveInput({
  content,
  name,
  emptyContentMessage,
}: ValidateTemplateSaveInput): { cleanContent: string; cleanName: string } {
  const cleanContent = content.trim();
  if (!cleanContent) {
    throw new TemplateSaveInputError(emptyContentMessage);
  }

  const cleanName = name.trim();
  if (!cleanName) {
    throw new TemplateSaveInputError("Template name is required.");
  }

  return { cleanContent, cleanName };
}

export async function savePersonalTemplate({
  content,
  name,
  type,
  tagsInput,
}: SavePersonalTemplateInput): Promise<void> {
  await api.saveTemplate({
    name,
    type,
    content,
    visibility: "personal",
    tags: parseTagInput(tagsInput),
  });
}
