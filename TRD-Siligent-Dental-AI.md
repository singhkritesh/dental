---
stack: "Python 3.11+ · Ollama (host) · FastAPI · React · PostgreSQL/pgvector + local uploads"
last_updated: "2026-05-03"
status: "Draft"
---

# TRD — Siligent Dental AI Assistant

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Infrastructure & Deployment](#2-infrastructure--deployment)
3. [Data Models](#3-data-models)
4. [LLM & Inference Configuration](#4-llm--inference-configuration)
5. [API Routes](#5-api-routes)
6. [Authentication & Security](#6-authentication--security)
7. [Frontend Architecture](#7-frontend-architecture)
8. [Background Workers & Jobs](#8-background-workers--jobs)
9. [AI Coding Guardrails](#9-ai-coding-guardrails)

---

## Current Implementation Snapshot (Authoritative)

This TRD contains legacy optioning language from early design (e.g., Streamlit-vs-React and file-only persistence). The implemented system is:

- Primary app architecture:
  - FastAPI backend (`api/main.py`)
  - React frontend (`frontend/`)
  - Docker Compose services: `api`, `frontend`, `db` (PostgreSQL + pgvector)
- LLM runtime:
  - Ollama on host (`host.docker.internal:11434` from API container).
  - Default model is currently `qwen3.5:4b` (configurable).
- Persistence model:
  - PostgreSQL is primary for auth, templates, template types, model preferences, uploads metadata, and audit events.
  - File-system fallback stores still exist for non-DB mode.
- Template model:
  - Exactly one canonical template per purpose type globally.
  - Save operation is effectively upsert-by-type.
  - Startup seeding creates missing shared defaults by template type.
- Compose behavior:
  - Document pipeline supports optional upload; generation can run from template type + runtime fields without files.
- Prompt role behavior:
  - Prompts enforce Siligent provider-role perspective.

When this TRD conflicts with the snapshot above, follow the snapshot and current code.

---

## 1. System Architecture

The Siligent Dental AI Assistant is a two-tier local application with no external dependencies at runtime. The frontend — either a Streamlit app (single Python process) or a React SPA served by a static file server — renders in the user's browser on the same machine or local network. If Streamlit is chosen, the frontend and backend are a single process: Streamlit handles UI rendering and makes direct Python function calls to the backend logic. If React is chosen, the frontend makes HTTP requests to a Python backend (Flask or FastAPI) running on `localhost:8000`.

The backend logic is identical regardless of UI choice: it reads prompt template files from disk, accepts a template name and variable dictionary, performs string substitution, and sends the composed prompt to the Ollama HTTP API at `http://localhost:11434/api/generate`. Ollama runs as a separate system process, serving the Gemma model. The backend waits synchronously for the full Ollama response (no streaming in v1) and returns the generated text to the frontend.

Data persistence is entirely file-based. Prompt templates live in `/prompts/{feature}/` as `.txt` files. Payer reference documents live in `/data/payer_references/` as `.txt` files. User-saved templates are stored in `/data/templates.json`. No database, no object storage, no message queue. Every operation is a synchronous read/write to the local filesystem.

Deployment is a single machine. All components — Ollama, the Python backend/Streamlit app, all data files — run on one physical or virtual server. There is no container orchestration, no reverse proxy, no load balancer. The stretch-goal Docker packaging wraps everything into a single container or compose file for easier setup, but the runtime architecture remains unchanged.

```
┌──────────────────────────────────────────────────────┐
│                   Local Machine                       │
│                                                       │
│  ┌─────────────┐     HTTP POST      ┌──────────────┐ │
│  │  Browser     │ ──────────────────▶│  Backend     │ │
│  │  (Streamlit  │ ◀──────────────────│  Python      │ │
│  │   or React)  │     JSON response  │  :8000       │ │
│  └─────────────┘                     └──────┬───────┘ │
│                                             │         │
│                                     HTTP POST to      │
│                                     /api/generate     │
│                                             │         │
│                                      ┌──────▼───────┐ │
│                                      │  Ollama      │ │
│                                      │  Gemma 7B/2B │ │
│                                      │  :11434      │ │
│                                      └──────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │  Local Filesystem                                │  │
│  │  /prompts/   /data/payer_references/             │  │
│  │  /data/templates.json                            │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## 2. Infrastructure & Deployment

### Services

```
ollama          → system process, port 11434, serves Gemma model
                  Env: OLLAMA_HOST=0.0.0.0 (default localhost)
                  Start: ollama serve
                  Model: ollama pull gemma:7b (or gemma:2b)

backend         → Python 3.11+, port 8000 (React path only)
                  Runtime: Flask or FastAPI
                  Env: OLLAMA_URL=http://localhost:11434
                       MODEL_NAME=gemma:7b
                       PROMPTS_DIR=./prompts
                       DATA_DIR=./data
                  Start: python app.py (Flask) or uvicorn app:app --port 8000 (FastAPI)

streamlit_app   → Python 3.11+, port 8501 (Streamlit path only)
                  Runtime: Streamlit
                  Env: OLLAMA_URL=http://localhost:11434
                       MODEL_NAME=gemma:7b
                       PROMPTS_DIR=./prompts
                       DATA_DIR=./data
                  Start: streamlit run app.py --server.port 8501

react_frontend  → Node 18+ (dev only), port 3000 (React path only)
                  Runtime: Vite + React
                  Env: VITE_API_URL=http://localhost:8000/api
                  Start: npm run dev
                  Build: npm run build (static files served by backend)
```

### Startup Order

1. **Ollama** — must be running and model pulled before backend starts
2. **Backend / Streamlit** — requires Ollama to be reachable at `OLLAMA_URL`
3. **React frontend** (if applicable) — requires backend to be reachable at `VITE_API_URL`

### Environment Variables

| Variable | Service | Required | Description | Example |
|----------|---------|----------|-------------|---------|
| `OLLAMA_URL` | backend / streamlit | Yes | Ollama API base URL | `http://localhost:11434` |
| `MODEL_NAME` | backend / streamlit | Yes | Ollama model identifier | `gemma:7b` |
| `PROMPTS_DIR` | backend / streamlit | Yes | Path to prompt template directory | `./prompts` |
| `DATA_DIR` | backend / streamlit | Yes | Path to data directory (payer refs, templates.json) | `./data` |
| `VITE_API_URL` | react frontend | Yes (React only) | Backend API base URL | `http://localhost:8000/api` |
| `OLLAMA_HOST` | ollama | No | Bind address for Ollama server | `0.0.0.0` |

### Folder Structure

```
siligent-dental-ai/
├── README.md
├── app.py                          # Main application (Streamlit or Flask/FastAPI)
├── requirements.txt                # Python dependencies
├── .env.example                    # Template environment file
├── prompts/
│   ├── denial_letters/
│   │   ├── CO-4.txt
│   │   ├── CO-6.txt
│   │   ├── CO-16.txt
│   │   ├── CO-22.txt
│   │   ├── CO-29.txt
│   │   ├── CO-45.txt
│   │   ├── CO-50.txt
│   │   ├── CO-97.txt
│   │   ├── CO-109.txt
│   │   └── CO-119.txt
│   ├── insurance_verification.txt
│   └── emails/
│       ├── appointment_reminder.txt
│       ├── cancellation_confirmation.txt
│       ├── balance_due.txt
│       ├── insurance_update_request.txt
│       ├── referral_letter.txt
│       ├── new_patient_welcome.txt
│       ├── post_treatment_followup.txt
│       └── general_inquiry.txt
├── data/
│   ├── payer_references/
│   │   ├── delta_dental.txt
│   │   ├── cigna.txt
│   │   └── aetna.txt
│   └── templates.json              # User-saved templates (created at runtime)
├── docs/
│   ├── decisions/
│   │   ├── backend.md
│   │   └── ui.md
│   ├── verification_inputs.md
│   ├── demo_script.md
│   └── SETUP.md
├── frontend/                       # React only — omit for Streamlit
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── pages/
│       │   ├── DenialLetters.jsx
│       │   ├── InsuranceVerification.jsx
│       │   └── EmailDrafting.jsx
│       └── components/
│           ├── TemplateLibrary.jsx
│           └── OutputArea.jsx
└── tests/
    ├── test_denial_letters.md       # Manual test log
    ├── test_verification.md
    └── test_offline.md
```

---

## 3. Data Models

There is no relational database. All data is stored on the local filesystem. The data model describes file formats and in-memory structures.

### Prompt Template (file-based)

**Location:** `/prompts/{feature}/{template_name}.txt`

**Format:** Plain text with `{variable_name}` placeholders for Python `str.format()` substitution.

Example denial letter template (`/prompts/denial_letters/CO-45.txt`):
```
You are a dental office assistant writing a formal insurance denial appeal letter.

The patient's claim was denied with code CO-45: Charge exceeds fee schedule/maximum allowable or contracted/legislated fee arrangement.

Use the following information to write a professional appeal letter:
- Patient Name: {patient_name}
- Date of Service: {date_of_service}
- Procedure: {procedure_description}
- Procedure Code: {procedure_code}
- Payer: {payer_name}
- Payer Address: {payer_address}
- Provider: {provider_name}
- Provider NPI: {provider_npi}

Write the letter with:
1. Practice letterhead placeholder at the top
2. Today's date
3. Payer address block
4. RE: line with patient name and claim reference
5. Body explaining why the charge is appropriate and the denial should be overturned
6. Professional closing with provider signature block

CRITICAL: Only use information provided above. Do not invent any addresses, phone numbers, procedure codes, or coverage details.
```

⚠️ **Variable names must match exactly between the prompt file and the backend's variable dictionary.** A mismatch (e.g., `{patientName}` vs `{patient_name}`) produces a `KeyError` at runtime. Use snake_case consistently.

### Payer Reference (file-based)

**Location:** `/data/payer_references/{payer_name_lowercase}.txt`

**Format:** Unstructured plain text — coverage summaries extracted from payer portal documents. No schema enforced. The entire file content is injected into the insurance verification prompt as context.

⚠️ **Filename must match the payer name used in the frontend dropdown, lowercased and with spaces replaced by underscores.** If the dropdown shows "Delta Dental" but the file is named `deltadental.txt`, the backend will fail with a file-not-found error.

### User Template (JSON file)

**Location:** `/data/templates.json`

**Format:**
```json
[
  {
    "name": "Dr Smith CO-45 Appeal",
    "type": "denial_letter",
    "content": "Dear Claims Department...",
    "created_at": "2026-04-15T10:30:00Z"
  },
  {
    "name": "Appointment Reminder - Generic",
    "type": "email",
    "content": "Dear Patient, this is a reminder...",
    "created_at": "2026-04-16T14:00:00Z"
  }
]
```

**Fields:**

| Field | Type | Constraints |
|-------|------|-------------|
| `name` | string | User-defined. No unique constraint. Max display length in UI: 100 chars. |
| `type` | string | One of: `"email"`, `"denial_letter"` |
| `content` | string | The full generated text. No size limit enforced. |
| `created_at` | string | ISO 8601 timestamp. Set by the backend at save time. |

**Read/write pattern:**
- **Read:** Load entire file, parse JSON array, return to frontend.
- **Write (save):** Load existing array, append new entry, write entire file back.
- **Write (delete):** Load existing array, remove entry by index, write entire file back.

⚠️ **No file locking.** Concurrent writes (two users saving templates at the same time) can cause data loss — the last write wins. Acceptable for a single-user PoC. Production deployment must add file locking or move to a database.

⚠️ **If `templates.json` does not exist on first read, create it with an empty array `[]`.** Do not crash on missing file.

### Denial Code Configuration (in-memory)

Hardcoded list in the backend/frontend. Not stored in a separate config file in v1.

```python
DENIAL_CODES = [
    {"code": "CO-4",   "description": "The procedure code is inconsistent with the modifier used"},
    {"code": "CO-6",   "description": "The procedure/revenue code is inconsistent with the patient's age"},
    {"code": "CO-16",  "description": "Claim/service lacks information or has submission errors"},
    {"code": "CO-22",  "description": "This care may be covered by another payer per coordination of benefits"},
    {"code": "CO-29",  "description": "The time limit for filing has expired"},
    {"code": "CO-45",  "description": "Charge exceeds fee schedule/maximum allowable"},
    {"code": "CO-50",  "description": "These are non-covered services because this is not deemed a medical necessity"},
    {"code": "CO-97",  "description": "The benefit for this service is included in another service/procedure"},
    {"code": "CO-109", "description": "Claim/service not covered by this payer/contractor"},
    {"code": "CO-119", "description": "Benefit maximum for this time period or occurrence has been reached"},
]
```

---

## 4. LLM & Inference Configuration

### Model Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| Provider | Ollama (local) | No cloud fallback |
| Model (primary) | `gemma:7b` | Preferred for output quality |
| Model (fallback) | `gemma:2b` | Use if 7B exceeds 60s inference on target hardware |
| API endpoint | `http://localhost:11434/api/generate` | POST request |
| Context window | ~8192 tokens (7B) | Payer reference docs must fit within this limit |
| Temperature | 0.3 | Low temperature for consistent, factual output |
| Max output tokens | 2048 | Sufficient for longest denial letter |
| Timeout | 60 seconds | Backend aborts and returns 504 after this |

### Ollama API Call Pattern

```python
import requests

def call_ollama(prompt: str, model: str = "gemma:7b") -> str:
    """Call local Ollama API. Returns generated text or raises."""
    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,          # Synchronous — wait for full response
            "options": {
                "temperature": 0.3,
                "num_predict": 2048,
            }
        },
        timeout=60
    )
    response.raise_for_status()
    return response.json()["response"]
```

⚠️ **`stream: False` is critical.** If set to `True` (or omitted — Ollama defaults to streaming), the response is a stream of JSON lines, not a single JSON object. The `response.json()` call will fail with a parse error. Always explicitly set `stream: False`.

### Prompt Composition Pattern

```python
import os

def compose_prompt(template_name: str, variables: dict) -> str:
    """Load a prompt template and substitute variables."""
    template_path = os.path.join(PROMPTS_DIR, f"{template_name}.txt")
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Prompt template not found: {template_path}")

    with open(template_path, "r") as f:
        template = f.read()

    try:
        return template.format(**variables)
    except KeyError as e:
        raise ValueError(f"Missing required variable: {e}")
```

⚠️ **Use `str.format(**variables)` not f-strings or `%` formatting.** The template files contain literal `{variable_name}` placeholders. `str.format()` is the only safe substitution method that maps variable names to their values. Using `.format_map()` with a `defaultdict` would silently swallow missing variables — use `.format(**dict)` to get explicit `KeyError` on missing keys.

---

## 5. API Routes

> This section applies only to the React/Flask/FastAPI path. If Streamlit is chosen, these endpoints are replaced by direct Python function calls within the Streamlit app.

### Backend API (Flask / FastAPI)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/generate` | Accepts `{"template": "denial_letters/CO-45", "variables": {"patient_name": "...", ...}}`. Loads prompt template, substitutes variables, calls Ollama, returns `{"text": "generated content"}`. Returns 400 if variables missing, 503 if Ollama unreachable, 504 on timeout, 500 if template file missing. |
| GET | `/api/templates` | Returns the full array from `templates.json`. Returns empty array `[]` if file doesn't exist. |
| POST | `/api/templates` | Accepts `{"name": "...", "type": "email|denial_letter", "content": "..."}`. Appends to `templates.json` with server-generated `created_at`. Returns `{"status": "saved", "index": N}`. Returns 400 if name or content is empty. |
| DELETE | `/api/templates/{index}` | Deletes the template at the given array index. Returns `{"status": "deleted"}`. Returns 404 if index out of range. |
| GET | `/api/health` | Returns `{"status": "ok", "model": "gemma:7b"}` if Ollama responds to a lightweight request. Returns `{"status": "error", "message": "..."}` with HTTP 503 if Ollama is unreachable. |
| GET | `/api/denial-codes` | Returns the hardcoded array of denial code objects. Used by the frontend to populate the dropdown. |
| GET | `/api/payers` | Returns list of available payer names (derived from filenames in `/data/payer_references/`). Used by the frontend to populate the payer dropdown. |

### Error Response Shape

All error responses follow:
```json
{
  "error": true,
  "message": "Human-readable error description",
  "code": "OLLAMA_UNREACHABLE"
}
```

Error codes:
- `MISSING_VARIABLES` — 400
- `TEMPLATE_NOT_FOUND` — 500
- `OLLAMA_UNREACHABLE` — 503
- `OLLAMA_TIMEOUT` — 504
- `GENERATION_FAILED` — 502
- `SAVE_FAILED` — 500
- `INDEX_OUT_OF_RANGE` — 404

---

## 6. Authentication & Security

### Authentication

**None in v1.** No login, no tokens, no session management. The application is accessible to anyone who can reach the server on the local network. Physical access control is the only security boundary.

> Per PRD §7: Role enforcement is physical — administrators have filesystem access, staff interact only through the UI.

### Network Security

The primary security mechanism is architectural isolation:
- Ollama binds to `localhost:11434` by default — not accessible from the network unless `OLLAMA_HOST` is changed.
- The backend binds to `localhost:8000` (or `0.0.0.0:8000` if other machines on the LAN need access).
- **No outbound HTTP calls.** The backend makes requests only to `localhost:11434`. No telemetry, no update checks, no external APIs.
- The React frontend (if used) makes requests only to the backend at `VITE_API_URL`.

⚠️ **If deploying on a shared LAN, bind the backend to `127.0.0.1`, not `0.0.0.0`.** Binding to `0.0.0.0` exposes the unprotected API to every device on the network. If LAN access is needed, add IP allowlisting or a simple shared-secret header before production use.

### Input Handling

- User input is passed through `str.format()` into prompt templates. This is not an injection vector for the filesystem or OS, but it is a prompt injection vector — a user could enter text in the "procedure description" field that alters the model's behavior. This is acceptable for v1 (the user is the dental office staff, not an adversary).
- No HTML sanitization needed — all output is rendered as plain text.
- No SQL injection surface — no database.

### Secrets

- No API keys, tokens, or credentials in v1.
- The `.env` file contains only configuration values (URLs, paths, model name). None are secret.
- `.env` should still be gitignored as a habit — it contains environment-specific values.

---

## 7. Frontend Architecture

### Path A: Streamlit

- **Rendering model:** Server-rendered. Streamlit runs a Python process that serves a web UI. The browser communicates with the Streamlit server via WebSocket.
- **State management:** Streamlit `st.session_state` for form inputs and generated output. State persists within a browser session but is lost on page refresh (Streamlit re-runs the script on every interaction).
- **Pages:** Streamlit multipage app using `st.sidebar` navigation or `st.navigation()` (Streamlit ≥ 1.30). One `.py` file per page in a `/pages/` directory.
- **Template library:** Displayed as a `st.selectbox` or `st.dataframe`. Load/save operations call Python functions directly.
- **Theme:** Streamlit's built-in theming via `.streamlit/config.toml`. Custom CSS possible via `st.markdown(unsafe_allow_html=True)` but not recommended for v1.

### Path B: React

- **Rendering model:** SPA (Single Page Application). Built with Vite + React. Served as static files.
- **State management:** React `useState` and `useContext` for form state and generated output. No external state library (Redux, Zustand) needed for this scale.
- **Routing:** React Router v6. Three routes: `/verification`, `/denial-letters`, `/emails`.
- **API communication:** `fetch()` to backend at `VITE_API_URL`. All requests are `Content-Type: application/json`. No auth headers.
- **Template library:** Component that fetches `GET /api/templates`, renders as a scrollable list, and loads selected template content into the output text area.
- **Theme:** CSS variables for colors and spacing. No dark mode in v1. Basic professional styling — clean forms, readable output areas.
- **Loading state:** A spinner component displayed while waiting for Ollama response. Spinner replaces the output area during generation.

### Shared UI Requirements (both paths)

- **Output area:** Read-only text area displaying generated content. Minimum height: 300px. Monospace or sans-serif font at readable size (14–16px).
- **Copy to Clipboard:** Button that copies the output area content to the system clipboard. Shows "Copied!" confirmation for 2 seconds.
- **Download as .txt:** Button that triggers a browser download of the output content as a `.txt` file. Filename: `{feature}_{timestamp}.txt` (e.g., `denial_letter_2026-04-22_143000.txt`).
- **Form validation:** Required fields marked with asterisk. Client-side validation prevents submission with empty required fields. Error messages appear below the field, not in an alert dialog.

---

## 8. Background Workers & Jobs

**None.** All operations in v1 are synchronous request-response. No background workers, no job queue, no async processing. Ollama inference is blocking — the backend waits for the full response before returning to the frontend.

If the RAG stretch goal is implemented, document embedding (converting payer PDFs to vectors in ChromaDB) would be a one-time batch operation run manually from the command line, not a background worker.

---

## 9. AI Coding Guardrails

These rules are written for an AI coding agent implementing features in this codebase. Follow them exactly.

1. **Always set `stream: False` in Ollama API calls.** Ollama defaults to streaming mode, which returns newline-delimited JSON chunks instead of a single JSON object. If you omit `stream: False`, `response.json()` will throw a `JSONDecodeError` with no useful error message — it looks like a malformed response, not a configuration issue. Always pass `"stream": False` in the request body.

2. **Use `str.format(**variables)`, never f-strings, for prompt template substitution.** Prompt templates are loaded from `.txt` files containing `{variable_name}` placeholders. F-strings would require `eval()` (security nightmare) or wouldn't work at all on file-loaded strings. `.format(**dict)` is the correct pattern and raises `KeyError` on missing variables, which is the behavior we want — silent missing variables produce letters with blank fields that staff won't catch.

3. **Match payer reference filenames to dropdown values exactly.** The backend resolves payer reference files by lowercasing the payer name and replacing spaces with underscores: `"Delta Dental"` → `delta_dental.txt`. If the frontend dropdown value and the filename don't match through this transform, the backend will return a file-not-found error. When adding a new payer, update both the dropdown options and the reference file name.

4. **Initialize `templates.json` as `[]` on first access.** If the file doesn't exist, create it with an empty JSON array. Never let a `FileNotFoundError` propagate to the user — an empty template list is the correct first-run state. Check for file existence before every read, not just at startup, because the file could be deleted while the app is running.

5. **Never make outbound HTTP requests to any URL except `localhost:11434`.** This is a HIPAA constraint. Any HTTP call to an external URL — even a CDN, a package registry, or a telemetry endpoint — is a compliance violation. If you add a new dependency, verify it doesn't phone home at runtime. The offline validation test in Week 4 will catch this, but the earlier you prevent it, the better.

6. **Set an explicit timeout on every Ollama API call.** Use `timeout=60` in the `requests.post()` call. Without a timeout, a hung Ollama process (model loading, GPU memory issue) will block the backend indefinitely, and the user sees an infinite spinner with no error message. The timeout produces a `requests.exceptions.Timeout` that the backend catches and returns as HTTP 504.

7. **Return structured error responses, not raw exceptions.** Every error returned to the frontend must be a JSON object with `error`, `message`, and `code` fields. Never let a Python traceback reach the frontend — it's useless to front desk staff and may expose file paths. Catch exceptions at the route handler level and map them to the error codes defined in TRD §5.

8. **Keep prompt templates in version control, not generated at runtime.** Prompt files in `/prompts/` are hand-crafted and tested. Never generate prompt files dynamically or modify them from the application. If a prompt needs updating, edit the file, commit, and redeploy. This keeps prompt engineering changes auditable and reversible.

9. **Write the entire `templates.json` file on every save/delete.** The file is small (100 templates ≈ 200KB). Read the full array, modify it in memory, and write it back atomically (write to a temp file, then rename). Don't append to the file — that risks corruption if the process is interrupted mid-write. The atomic write pattern:
   ```python
   import json, os, tempfile

   def save_templates(templates: list, path: str):
       dir_name = os.path.dirname(path)
       fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".json")
       try:
           with os.fdopen(fd, "w") as f:
               json.dump(templates, f, indent=2)
           os.replace(tmp_path, path)  # Atomic on POSIX
       except:
           os.unlink(tmp_path)
           raise
   ```

10. **Don't add a database.** The temptation to add SQLite or PostgreSQL "for reliability" is strong. Resist it. File-based storage is a deliberate design choice for this PoC — it eliminates an entire class of setup complexity (migrations, connection strings, drivers) for a tool that stores < 1MB of data. The simplicity of "edit a JSON file" is a feature when the audience is a dental IT admin, not a DBA.

11. **Validate required form fields client-side AND server-side.** Client-side validation prevents unnecessary Ollama calls. Server-side validation (in the route handler) catches direct API calls or form bypass. Both checks compare against the same required field list. A field is "present" if it's a non-empty string after `.strip()`.

12. **Never log patient-identifiable information.** If you add logging (print statements, logging module, etc.), never include patient names, DOBs, member IDs, or any input field values. Log template names, error codes, and timing — not content. The stretch-goal audit log follows this same rule by design.

---
