# Siligent Dental AI Assistant

## 1. Project Overview

Locally-hosted AI tool for dental front desk staff. Three features: insurance denial letter generation, insurance verification, and email drafting with a reusable template library. Runs Gemma via Ollama offline — zero internet dependency (HIPAA constraint). UI is Streamlit or React. Data persistence is file-based JSON — no database. Single-machine deployment.

When in doubt: `/docs/PRD.md` for product intent, `/docs/TRD.md` for implementation detail, `/docs/RUNBOOK.md` for ops.

## 2. Where Things Live

```
siligent-dental-ai/
├── CLAUDE.md              ← this file
├── app.py                 ← main application entry point
├── requirements.txt       ← Python dependencies
├── .env                   ← environment config (gitignored)
├── .env.example           ← template for .env
├── prompts/               ← prompt templates — hand-crafted, version-controlled
│   ├── denial_letters/    ← one .txt per denial code (CO-4.txt, CO-45.txt, etc.)
│   ├── emails/            ← one .txt per email scenario
│   └── insurance_verification.txt
├── data/                  ← runtime data — NOT version-controlled (except payer refs)
│   ├── payer_references/  ← plain text coverage docs, one per payer
│   └── templates.json     ← user-saved templates (created at runtime)
├── frontend/              ← React only — omit for Streamlit
│   ├── src/pages/         ← one component per feature
│   └── src/components/    ← shared UI components
├── docs/
│   ├── PRD.md
│   ├── TRD.md
│   ├── RUNBOOK.md
│   └── decisions/         ← architecture decision records from Week 1
└── tests/                 ← manual test logs
```

⚠️ **Do not modify files in `prompts/` programmatically.** Prompt templates are hand-crafted and version-controlled. Edit manually, test, commit.

## 3. Stack & Key Packages

**Runtimes:**
- Python 3.11+ — backend and Streamlit
- Ollama — local LLM server on port 11434
- Node 18+ — React frontend only

**Key packages:**
- `requests` — HTTP client for Ollama API calls. Always set `timeout=60`.
- `streamlit` — UI framework (Streamlit path). Handles rendering, state, and routing.
- `flask` or `fastapi` — Backend API (React path). Serves JSON endpoints.
- `python-dotenv` — Loads `.env` file. Used in `app.py` startup.

> ⚠️ No database packages. No ORM. No SQLAlchemy, no SQLite, no Drizzle. Data is file-based JSON. This is intentional — see TRD §9 rule 10.

## 4. Data Model Quick Reference

No database tables. All data is file-based:

| Entity | Location | Format | Key fields |
|--------|----------|--------|------------|
| Prompt Template | `prompts/{feature}/{name}.txt` | Plain text with `{variable}` placeholders | N/A — raw text file |
| Payer Reference | `data/payer_references/{payer}.txt` | Unstructured plain text | N/A — raw text file |
| User Template | `data/templates.json` | JSON array of objects | `name`, `type`, `content`, `created_at` |
| Denial Codes | Hardcoded in app | Python list of dicts | `code`, `description` |

⚠️ **Payer filename mapping:** `"Delta Dental"` → `delta_dental.txt`. Lowercase, spaces to underscores. A mismatch means file-not-found at runtime.

⚠️ **`templates.json` must exist before first read.** Initialize as `[]` if missing. Never let `FileNotFoundError` reach the user.

## 5. API Patterns

> Streamlit path: no HTTP API — use direct Python function calls. Skip this section.

**React/Flask path:**

- Base path: `http://localhost:8000/api`
- Auth: None
- Content type: `application/json`
- No streaming — all responses are synchronous

**Standard success response:**
```json
{"text": "generated content here"}
```

**Standard error response:**
```json
{"error": true, "message": "Human-readable message", "code": "ERROR_CODE"}
```

Error codes: `MISSING_VARIABLES` (400), `TEMPLATE_NOT_FOUND` (500), `OLLAMA_UNREACHABLE` (503), `OLLAMA_TIMEOUT` (504), `GENERATION_FAILED` (502), `SAVE_FAILED` (500), `INDEX_OUT_OF_RANGE` (404).

## 6. Authentication & Authorization

**None.** No login, no tokens, no middleware. Physical access = full access. This is a single-user, single-machine PoC.

If you're adding a new endpoint: no auth header check needed. Just handle the request.

## 7. Critical Rules

1. **Always set `stream: False` in Ollama API calls.** Ollama defaults to streaming (newline-delimited JSON chunks). Without `stream: False`, `response.json()` throws `JSONDecodeError` — it looks like a corrupt response, not a config issue. Silent, confusing failure.
   ```python
   requests.post(url, json={"model": model, "prompt": prompt, "stream": False, ...})
   ```

2. **Use `str.format(**variables)` for prompt substitution.** Templates are `.txt` files with `{variable_name}` placeholders. F-strings don't work on file-loaded strings. `.format(**dict)` raises `KeyError` on missing variables — this is the correct behavior. A missing variable should crash loudly, not produce a letter with `{patient_name}` in it.

3. **Never make outbound HTTP requests except to `localhost:11434`.** HIPAA constraint. No CDN calls, no telemetry, no pip install at runtime, no external API. Any external request is a compliance violation. The Week 4 offline test will catch this.

4. **Set `timeout=60` on every `requests.post()` to Ollama.** Without a timeout, a hung Ollama process blocks the backend forever. The user sees an infinite spinner with no error. The timeout produces `requests.exceptions.Timeout` which you catch and return as HTTP 504.

5. **Initialize `templates.json` as `[]` on missing file.** Check before every read, not just at startup — the file could be deleted while the app is running. Never propagate `FileNotFoundError` to the UI.

6. **Atomic writes to `templates.json`.** Write to a temp file, then `os.replace()`. Never write directly to the live file — an interrupted write (Ctrl+C, power loss) corrupts the JSON and loses all saved templates.
   ```python
   fd, tmp = tempfile.mkstemp(dir=data_dir, suffix=".json")
   with os.fdopen(fd, "w") as f:
       json.dump(templates, f, indent=2)
   os.replace(tmp, templates_path)
   ```

7. **Return structured JSON errors, never Python tracebacks.** Front desk staff cannot interpret a Python stack trace. Every exception in a route handler must be caught and mapped to `{"error": true, "message": "...", "code": "..."}`.

8. **Never log patient data.** No names, DOBs, member IDs, or form field values in logs or print statements. Log template names, error codes, timing — not content.

9. **Match payer reference filenames to dropdown values.** Transform: lowercase, replace spaces with underscores. `"Delta Dental"` → `delta_dental.txt`. If they don't match, verification silently fails with file-not-found.

10. **Don't add a database.** File-based storage is deliberate. No SQLite, no PostgreSQL, no Redis. The simplicity of `echo '[]' > templates.json` is a feature for dental IT admins.

11. **Never modify files outside the current working directory.** All read/write/create/delete operations must stay within the active project directory. If work outside the current directory is required, stop and request an explicit absolute path from the user before making any change.

## 8. Common Patterns with Examples

### Calling Ollama

```python
import requests

def generate(prompt: str) -> str:
    resp = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": MODEL_NAME, "prompt": prompt, "stream": False,
              "options": {"temperature": 0.3, "num_predict": 2048}},
        timeout=60
    )
    resp.raise_for_status()
    return resp.json()["response"]
```

### Loading and substituting a prompt template

```python
def load_prompt(template_path: str, variables: dict) -> str:
    with open(template_path) as f:
        template = f.read()
    return template.format(**variables)  # KeyError on missing vars = correct
```

### Reading/writing templates.json

```python
import json, os, tempfile

TEMPLATES_PATH = os.path.join(DATA_DIR, "templates.json")

def read_templates() -> list:
    if not os.path.exists(TEMPLATES_PATH):
        return []
    with open(TEMPLATES_PATH) as f:
        return json.load(f)

def save_templates(templates: list):
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".json")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(templates, f, indent=2)
        os.replace(tmp, TEMPLATES_PATH)
    except:
        os.unlink(tmp)
        raise
```

### Resolving a payer reference file

```python
def get_payer_reference(payer_name: str) -> str:
    filename = payer_name.lower().replace(" ", "_") + ".txt"
    path = os.path.join(DATA_DIR, "payer_references", filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No reference data for payer: {payer_name}")
    with open(path) as f:
        return f.read()
```

## 9. Anti-Patterns — What Not To Do

- **Don't omit `stream: False`** → Ollama streams by default, breaking `response.json()` silently
- **Don't use f-strings for prompt templates** → templates are loaded from files, f-strings only work on in-code strings
- **Don't use `.format_map(defaultdict)`** → silently swallows missing variables instead of raising `KeyError`
- **Don't make any HTTP call to a non-localhost URL** → HIPAA violation, caught by offline test
- **Don't add a database** → file-based persistence is a deliberate design choice (TRD §9 rule 10)
- **Don't log form field values** → patient data must never appear in logs
- **Don't write directly to `templates.json`** → use atomic temp file + `os.replace()` pattern
- **Don't generate prompt files at runtime** → prompt templates are hand-crafted and version-controlled
- **Don't hard-code payer names in the backend** → derive available payers from filenames in `data/payer_references/`

## 10. Verifying Your Work

**Test Ollama directly:**
```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"gemma:7b","prompt":"Say hello","stream":false}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['response'][:100])"
```

**Test the backend (React path):**
```bash
curl -s http://localhost:8000/api/health
# Expected: {"status": "ok", "model": "gemma:7b"}

curl -s -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"template":"denial_letters/CO-45","variables":{"patient_name":"Test","date_of_service":"2026-04-22","procedure_description":"Crown","procedure_code":"D2740","payer_name":"Delta Dental","payer_address":"N/A","provider_name":"Dr Smith","provider_npi":"1234567890"}}'
# Expected: {"text": "Dear Claims Department..."}
```

**Verify templates persistence:**
```bash
cat data/templates.json | python3 -m json.tool
# Should be valid JSON array
```

**Verify offline operation:**
```bash
# Disconnect network, then run all three features through the UI
# Any error = external dependency was introduced
```

**Key log lines indicating correct behavior:**
- Ollama: "model loaded" after first request
- Backend: no Python tracebacks in terminal output
- templates.json: valid JSON after every save operation
