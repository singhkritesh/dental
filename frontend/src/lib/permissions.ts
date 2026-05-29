import type { AuthBootstrapResponse, TemplateItem, UserInfo } from "./types";

export function isAdminContext(
  user: UserInfo | null,
  bootstrap: AuthBootstrapResponse | null
) {
  return Boolean((bootstrap && !bootstrap.auth_enabled) || user?.role === "admin");
}

export function canManageTemplate(
  template: TemplateItem | null,
  user: UserInfo | null,
  bootstrap: AuthBootstrapResponse | null
) {
  if (!template) {
    return false;
  }
  if (isAdminContext(user, bootstrap)) {
    return true;
  }
  return template.visibility === "personal" && Boolean(user?.id) && template.owner_id === user?.id;
}

export function templateScopeLabel(template: TemplateItem) {
  return template.visibility === "personal" ? "Personal draft" : "Shared approved";
}
