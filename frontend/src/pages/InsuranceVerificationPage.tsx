import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Notice } from "../components/Notice";
import { OutputActions } from "../components/OutputActions";
import { api } from "../lib/api";
import { resolveErrorMessage } from "../lib/errorMessages";
import { verificationSummaryToText } from "../lib/formatters";
import { useGenerationTasks } from "../lib/generationTasks";
import type { InsuranceVerificationSummary } from "../lib/types";

const PLAN_TYPES = ["PPO", "HMO", "DHMO", "Indemnity", "Other"];

type VerificationFormState = {
  payer_name: string;
  member_id: string;
  group_number: string;
  patient_dob: string;
  plan_type: string;
};

type VerificationPersistedState = {
  form: VerificationFormState;
  modelName: string;
  manualPayer: boolean;
};

function defaultDob(): string {
  return "1990-01-01";
}

const INSURANCE_STATE_STORAGE_KEY = "siligent_insurance_state_v1";

export function InsuranceVerificationPage() {
  const { tasks, runTask, getInFlight, clearTask } = useGenerationTasks();
  const [payers, setPayers] = useState<string[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [modelName, setModelName] = useState("");
  const [summary, setSummary] = useState<InsuranceVerificationSummary | null>(null);
  const [rawText, setRawText] = useState("");
  const [notice, setNotice] = useState<{ type: "error" | "success" | "info"; message: string } | null>(
    null
  );
  const [manualPayer, setManualPayer] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [form, setForm] = useState<VerificationFormState>({
    payer_name: "",
    member_id: "",
    group_number: "",
    patient_dob: defaultDob(),
    plan_type: PLAN_TYPES[0]
  });
  const hasPayerOptions = payers.length > 0;

  useEffect(() => {
    clearTask("insurance_verification_generate");
    setSummary(null);
    setRawText("");
  }, [clearTask]);

  useEffect(() => {
    const raw = window.sessionStorage.getItem(INSURANCE_STATE_STORAGE_KEY);
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as Partial<VerificationPersistedState>;
      if (parsed.form) {
        setForm((current) => ({
          ...current,
          ...parsed.form
        }));
      }
      if (typeof parsed.modelName === "string") {
        setModelName(parsed.modelName);
      }
      if (typeof parsed.manualPayer === "boolean") {
        setManualPayer(parsed.manualPayer);
      }
    } catch {
      window.sessionStorage.removeItem(INSURANCE_STATE_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    const payload: VerificationPersistedState = {
      form,
      modelName,
      manualPayer
    };
    window.sessionStorage.setItem(INSURANCE_STATE_STORAGE_KEY, JSON.stringify(payload));
  }, [form, modelName, manualPayer]);

  useEffect(() => {
    let active = true;
    async function loadPayers() {
      try {
        const [data, modelList, prefs] = await Promise.all([
          api.getPayers(),
          api.getModels(),
          api.getModelPreferences()
        ]);
        if (!active) {
          return;
        }
        setPayers(data);
        setModels(modelList);
        setModelName((current) =>
          current || (prefs.per_use_case.insurance_verification ?? prefs.global_model ?? modelList[0] ?? "")
        );
        setForm((current) => ({
          ...current,
          payer_name: current.payer_name || data[0] || ""
        }));
      } catch (error) {
        const message = resolveErrorMessage(error, "Failed to load payers.");
        if (active) {
          setNotice({ type: "error", message });
        }
      }
    }
    void loadPayers();
    return () => {
      active = false;
    };
  }, []);

  function updateField<K extends keyof VerificationFormState>(key: K, value: VerificationFormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  const summaryText = useMemo(() => {
    if (!summary) {
      return "";
    }
    return verificationSummaryToText(summary);
  }, [summary]);
  const taskState = tasks["insurance_verification_generate"];

  useEffect(() => {
    if (!taskState) {
      return;
    }
    if (taskState.status === "running") {
      setIsLoading(true);
      const pending = getInFlight<{ summary: InsuranceVerificationSummary; raw_text: string }>(
        "insurance_verification_generate"
      );
      if (!pending) {
        return;
      }
      void pending
        .then((response) => {
          setSummary(response.summary);
          setRawText(response.raw_text);
          setNotice({ type: "success", message: "Insurance verification generated." });
        })
        .catch((error) => {
          const message = resolveErrorMessage(error, "Unable to complete verification at this time.");
          setNotice({ type: "error", message });
        })
        .finally(() => {
          setIsLoading(false);
        });
      return;
    }
    if (taskState.status === "success" && taskState.result) {
      const response = taskState.result as { summary: InsuranceVerificationSummary; raw_text: string };
      setSummary(response.summary);
      setRawText(response.raw_text);
      setIsLoading(false);
      return;
    }
    if (taskState.status === "error") {
      setIsLoading(false);
    }
  }, [getInFlight, taskState]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setSummary(null);
    setRawText("");

    if (!form.payer_name.trim() || !form.member_id.trim() || !form.patient_dob.trim()) {
      setNotice({ type: "error", message: "Payer name, member ID, and patient DOB are required." });
      return;
    }

    setIsLoading(true);
    try {
      const response = await runTask("insurance_verification_generate", () =>
        api.generateInsuranceVerification({
          ...form,
          model_name: modelName || undefined
        })
      );
      setSummary(response.summary);
      setRawText(response.raw_text);
      setNotice({ type: "success", message: "Insurance verification generated." });
    } catch (error) {
      const message = resolveErrorMessage(error, "Unable to complete verification at this time.");
      setNotice({ type: "error", message });
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>Insurance Verification</h1>
        <p>Check coverage details from payer references. For upload-based scenario drafting, use Compose.</p>
      </header>

      {notice && <Notice type={notice.type} message={notice.message} />}

      <div className="panel-grid two-col">
        <form className="panel" onSubmit={onSubmit}>
          <h2>Verification details</h2>
          <div className="switch-row">
            <label>
              <input
                type="radio"
                name="payer-source"
                checked={!manualPayer}
                onChange={() => {
                  setManualPayer(false);
                  if (payers[0]) {
                    updateField("payer_name", payers[0]);
                  }
                }}
              />
              Choose from saved payer references
            </label>
            <label>
              <input
                type="radio"
                name="payer-source"
                checked={manualPayer}
                onChange={() => {
                  setManualPayer(true);
                  updateField("payer_name", "");
                }}
              />
              Enter payer manually
            </label>
          </div>

          {manualPayer ? (
            <label>
              Payer Name *
              <input value={form.payer_name} onChange={(event) => updateField("payer_name", event.target.value)} />
            </label>
          ) : hasPayerOptions ? (
            <label>
              Payer Name *
              <select value={form.payer_name} onChange={(event) => updateField("payer_name", event.target.value)}>
                {payers.map((payer) => (
                  <option key={payer} value={payer}>
                    {payer}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <p className="helper">
              No payer references found. Add payer files first, or switch to manual payer entry.
            </p>
          )}

          <details>
            <summary>Model options</summary>
            <label>
              Model
              <select
                value={modelName}
                onChange={(event) => setModelName(event.target.value)}
                disabled={models.length === 0}
              >
                {models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
              {models.length === 0 ? <p className="helper">No local models detected.</p> : null}
            </label>
          </details>

          <label>
            Member ID *
            <input value={form.member_id} onChange={(event) => updateField("member_id", event.target.value)} />
          </label>
          <label>
            Group Number
            <input value={form.group_number} onChange={(event) => updateField("group_number", event.target.value)} />
          </label>
          <label>
            Patient DOB *
            <input type="date" value={form.patient_dob} onChange={(event) => updateField("patient_dob", event.target.value)} />
          </label>
          <label>
            Plan Type
            <select value={form.plan_type} onChange={(event) => updateField("plan_type", event.target.value)}>
              {PLAN_TYPES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <button className="primary-btn" type="submit" disabled={isLoading}>
            {isLoading ? "Generating..." : "Generate verification"}
          </button>
          <button
            className="secondary-btn"
            type="button"
            onClick={() => {
              setSummary(null);
              setRawText("");
              setNotice(null);
              setManualPayer(false);
              setForm({
                payer_name: payers[0] ?? "",
                member_id: "",
                group_number: "",
                patient_dob: defaultDob(),
                plan_type: PLAN_TYPES[0],
              });
            }}
            disabled={isLoading}
          >
            Reset form
          </button>
          {isLoading ? (
            <p className="helper">Verification is running. You can switch tabs and return safely.</p>
          ) : null}
        </form>

        <div className="panel">
          <h2>Verification summary</h2>
          {!summary ? (
            <p className="placeholder">Summary appears here after generation.</p>
          ) : (
            <div className="summary">
              <h3>Covered Procedures</h3>
              {summary.covered_procedures.length > 0 ? (
                <ul>
                  {summary.covered_procedures.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="helper">No grounded covered procedures were found in payer references.</p>
              )}
              <p>
                <strong>Estimated Co-Pay:</strong> {summary.estimated_copay}
              </p>
              <p>
                <strong>Prior Authorization Required:</strong> {summary.prior_authorization_required}
              </p>
              <p>
                <strong>Annual Maximum:</strong> {summary.annual_maximum}
              </p>
              <p>
                <strong>Waiting Periods:</strong> {summary.waiting_periods}
              </p>
              <p>
                <strong>Notable Exclusions/Limitations:</strong> {summary.notable_exclusions_limitations}
              </p>
            </div>
          )}
          <OutputActions text={summaryText} filenamePrefix="insurance_verification" mode="document" />
          {rawText && (
            <details className="raw-response">
              <summary>Raw model response</summary>
              <textarea className="output compact" value={rawText} readOnly />
            </details>
          )}
        </div>
      </div>
    </section>
  );
}
