import { ApiError } from "./api";

export function resolveErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.message} (${error.code})`;
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return fallback;
}
