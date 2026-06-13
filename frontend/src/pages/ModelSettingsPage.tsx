import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { Notice } from "../components/Notice";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { resolveErrorMessage } from "../lib/errorMessages";
import { isAdminContext } from "../lib/permissions";
import type { AuditEventItem, ModelPreferences } from "../lib/types";

const USE_CASE_LABELS: Record<string, string> = {
  denial_letters: "Denial Letters",
  insurance_verification: "Insurance Verification",
  email_thread: "Email Exchange",
  email_drafting: "Standalone Email Drafts",
  document_ingestion: "Document-Based Drafts"
};

export function ModelSettingsPage() {
  const { user, bootstrap } = useAuth();
  const isAdmin = isAdminContext(user, bootstrap);
  const [models, setModels] = useState<string[]>([]);
  const [templateTypes, setTemplateTypes] = useState<string[]>([]);
  const [preferences, setPreferences] = useState<ModelPreferences>({
    use_global_model_for_all: true,
    global_model: "",
    per_use_case: {}
  });
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newUserName, setNewUserName] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<"admin" | "staff">("staff");
  const [creatingUser, setCreatingUser] = useState(false);
  const [notice, setNotice] = useState<{ type: "error" | "success" | "info"; message: string } | null>(
    null
  );
  const canCreateUser = Boolean(
    isAdmin && newUserName.trim().length >= 3 && newUserPassword.length >= 8 && !creatingUser
  );
  const hasModels = models.length > 0;

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const [modelsData, prefData, templateTypeData] = await Promise.all([
          api.getModels(),
          api.getModelPreferences(),
          api.getTemplateTypes()
        ]);
        if (!active) {
          return;
        }
        setModels(modelsData);
        setPreferences(prefData);
        setTemplateTypes(templateTypeData.template_types);
        if (isAdmin) {
          const audit = await api.getAuditEvents(80);
          if (active) {
            setAuditEvents(audit.events.reverse());
          }
        }
      } catch (error) {
        const message = resolveErrorMessage(error, "Failed to load model settings.");
        if (active) {
          setNotice({ type: "error", message });
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [isAdmin]);

  function setUseCaseModel(useCase: string, modelName: string) {
    setPreferences((current) => ({
      ...current,
      per_use_case: {
        ...current.per_use_case,
        [useCase]: modelName
      }
    }));
  }

  async function onSavePreferences() {
    setNotice(null);
    setSaving(true);
    try {
      const saved = await api.saveModelPreferences(preferences);
      setPreferences(saved);
      setNotice({ type: "success", message: "Model preferences saved." });
    } catch (error) {
      const message = resolveErrorMessage(error, "Could not save model preferences.");
      setNotice({ type: "error", message });
    } finally {
      setSaving(false);
    }
  }

  async function onCreateUser() {
    if (!newUserName.trim() || newUserPassword.length < 8) {
      setNotice({ type: "error", message: "Provide a username and password (min 8 chars)." });
      return;
    }
    setCreatingUser(true);
    try {
      await api.register({
        username: newUserName.trim(),
        password: newUserPassword,
        role: newUserRole
      });
      setNewUserName("");
      setNewUserPassword("");
      setNotice({ type: "success", message: "User account created." });
    } catch (error) {
      const message = resolveErrorMessage(error, "Could not create user account.");
      setNotice({ type: "error", message });
    } finally {
      setCreatingUser(false);
    }
  }

  if (!isAdmin) {
    return (
      <section className="page">
        <header className="page-header">
          <h1>Admin Console</h1>
          <p>Model routing, template taxonomy, user management, and audit trail.</p>
        </header>
        <Notice
          type="error"
          message="Admin access required. You can continue using insurance verification, denial letters, and email exchange."
        />
      </section>
    );
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>Admin Console</h1>
        <p>Model routing, template taxonomy, user management, and audit trail.</p>
      </header>

      {notice && <Notice type={notice.type} message={notice.message} />}

      <div className="panel-grid two-col">
        <div className="panel">
          <h2>Model Routing</h2>
          {loading ? <p className="placeholder">Loading settings...</p> : null}
          {!loading ? (
            <>
              {!hasModels ? (
                <Notice
                  type="error"
                  message="No local Ollama models found. Pull or load a model before changing routing."
                />
              ) : null}
              <label className="checkbox-inline">
                <input
                  type="checkbox"
                  checked={preferences.use_global_model_for_all}
                  disabled={!isAdmin}
                  onChange={(event) =>
                    setPreferences((current) => ({
                      ...current,
                      use_global_model_for_all: event.target.checked
                    }))
                  }
                />
                Use one global model for all use cases
              </label>

              <label>
                Global Model
                <select
                  value={preferences.global_model}
                  disabled={!isAdmin || !hasModels}
                  onChange={(event) =>
                    setPreferences((current) => ({
                      ...current,
                      global_model: event.target.value
                    }))
                  }
                >
                  {models.map((modelName) => (
                    <option key={modelName} value={modelName}>
                      {modelName}
                    </option>
                  ))}
                </select>
              </label>

              {Object.keys(USE_CASE_LABELS).map((useCase) => (
                <label key={useCase}>
                  {USE_CASE_LABELS[useCase]}
                  <select
                    disabled={!isAdmin || preferences.use_global_model_for_all || !hasModels}
                    value={preferences.per_use_case[useCase] ?? preferences.global_model}
                    onChange={(event) => setUseCaseModel(useCase, event.target.value)}
                  >
                    {models.map((modelName) => (
                      <option key={modelName} value={modelName}>
                        {modelName}
                      </option>
                    ))}
                  </select>
                </label>
              ))}

              <button
                className="primary-btn"
                type="button"
                onClick={onSavePreferences}
                disabled={saving || !isAdmin || !hasModels}
              >
                {saving ? "Saving..." : "Save Model Settings"}
              </button>
              <p className="helper">
                Workflow pages may show an admin model override for a single run. These settings control the default
                routing used across the app.
              </p>
              {!isAdmin ? <p className="helper">Only admins can update model routing.</p> : null}
            </>
          ) : null}
        </div>

        <div className="panel">
          <h2>Purpose Types</h2>
          <p className="helper">
            Purpose types are created and edited from Template Library so each type remains tied to its canonical
            template and fields.
          </p>

          <div className="chips-wrap">
            {templateTypes.map((typeName) => (
              <span className="chip" key={typeName}>
                {typeName}
              </span>
            ))}
          </div>
          <Link className="secondary-btn" to="/template-library">
            Manage templates and purpose types
          </Link>

          {isAdmin ? (
            <>
              <h3>User Access</h3>
              <div className="inline-actions">
                <input
                  placeholder="username"
                  value={newUserName}
                  onChange={(event) => setNewUserName(event.target.value)}
                />
                <input
                  placeholder="password (min 8)"
                  type="password"
                  value={newUserPassword}
                  onChange={(event) => setNewUserPassword(event.target.value)}
                />
                <select value={newUserRole} onChange={(event) => setNewUserRole(event.target.value as "admin" | "staff")}>
                  <option value="staff">staff</option>
                  <option value="admin">admin</option>
                </select>
                <button className="secondary-btn" type="button" onClick={onCreateUser} disabled={!canCreateUser}>
                  {creatingUser ? "Creating..." : "Create User"}
                </button>
              </div>

              <h3>Audit Trail</h3>
              <div className="audit-list">
                {auditEvents.slice(0, 20).map((event) => (
                  <div className="audit-item" key={`${event.at}-${event.action}`}>
                    <p>
                      <strong>{event.action}</strong> ({event.outcome})
                    </p>
                    <p className="helper">{new Date(event.at).toLocaleString()}</p>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
