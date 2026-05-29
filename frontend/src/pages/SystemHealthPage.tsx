import { useState } from "react";

import { Notice } from "../components/Notice";
import { api } from "../lib/api";
import { resolveErrorMessage } from "../lib/errorMessages";
import type { DenialCode, HealthResponse } from "../lib/types";

type HealthSnapshot = {
  health: HealthResponse;
  payers: string[];
  denialCodes: DenialCode[];
};

export function SystemHealthPage() {
  const [snapshot, setSnapshot] = useState<HealthSnapshot | null>(null);
  const [notice, setNotice] = useState<{ type: "error" | "success" | "info"; message: string } | null>(
    null
  );
  const [loading, setLoading] = useState(false);

  async function runChecks() {
    setLoading(true);
    setNotice(null);
    try {
      const [health, payers, denialCodes] = await Promise.all([
        api.getHealth(),
        api.getPayers(),
        api.getDenialCodes()
      ]);
      setSnapshot({ health, payers, denialCodes });
      setNotice({ type: "success", message: "Health checks passed." });
    } catch (error) {
      const message = resolveErrorMessage(error, "Failed to run health checks.");
      setNotice({ type: "error", message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>System Health</h1>
        <p>Validate API/model reachability and required runtime configuration.</p>
      </header>

      {notice && <Notice type={notice.type} message={notice.message} />}

      <div className="panel">
        <button className="primary-btn" type="button" onClick={runChecks} disabled={loading}>
          {loading ? "Running checks..." : "Run Health Check"}
        </button>
      </div>

      {snapshot ? (
        <div className="panel-grid three-col">
          <div className="panel stat-card">
            <h2>Model</h2>
            <p>
              <strong>Configured:</strong> {snapshot.health.model_configured}
            </p>
            <p>
              <strong>Available:</strong> {snapshot.health.model_available ? "Yes" : "No"}
            </p>
            <p>
              <strong>Models on host:</strong> {snapshot.health.available_models.length}
            </p>
          </div>
          <div className="panel stat-card">
            <h2>Payer References</h2>
            <p>
              <strong>Loaded:</strong> {snapshot.payers.length}
            </p>
            <ul>
              {snapshot.payers.slice(0, 5).map((payer) => (
                <li key={payer}>{payer}</li>
              ))}
            </ul>
          </div>
          <div className="panel stat-card">
            <h2>Denial Codes</h2>
            <p>
              <strong>Loaded:</strong> {snapshot.denialCodes.length}
            </p>
            <ul>
              {snapshot.denialCodes.slice(0, 5).map((code) => (
                <li key={code.code}>{code.code}</li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}
