import { type FormEvent, useState } from "react";

import { Notice } from "../components/Notice";
import { useAuth } from "../lib/auth";
import { resolveErrorMessage } from "../lib/errorMessages";

export function LoginPage() {
  const { bootstrap, login, register } = useAuth();
  const bootstrapRequired = bootstrap?.bootstrap_required ?? false;

  const mode = bootstrapRequired ? "register" : "login";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"admin" | "staff">("staff");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<{ type: "error" | "success" | "info"; message: string } | null>(
    null
  );

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    setLoading(true);
    try {
      if (mode === "register") {
        await register(username.trim(), password, bootstrapRequired ? "admin" : role);
      } else {
        await login(username.trim(), password);
      }
      setNotice({
        type: "success",
        message: mode === "register" ? "Account created." : "Signed in successfully."
      });
    } catch (error) {
      const message = resolveErrorMessage(error, "Authentication request failed.");
      setNotice({ type: "error", message });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-wrap">
      <section className="auth-card">
        <header>
          <h1>Siligent Dental AI</h1>
          <p>{bootstrapRequired ? "Create the first admin account to initialize this workspace." : "Sign in to continue."}</p>
        </header>

        {notice && <Notice type={notice.type} message={notice.message} />}

        <form className="auth-form" onSubmit={onSubmit}>
          <label>
            Username
            <input value={username} onChange={(event) => setUsername(event.target.value)} required minLength={3} />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
            />
          </label>

          {mode === "register" && !bootstrapRequired ? (
            <label>
              Role
              <select value={role} onChange={(event) => setRole(event.target.value as "admin" | "staff")}>
                <option value="staff">Staff</option>
                <option value="admin">Admin</option>
              </select>
            </label>
          ) : null}

          <button className="primary-btn" type="submit" disabled={loading}>
            {loading ? "Please wait..." : mode === "register" ? "Create Account" : "Sign In"}
          </button>
        </form>

      </section>
    </div>
  );
}
