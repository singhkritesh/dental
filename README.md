# Siligent Dental AI Assistant

Production-oriented local AI platform for dental front desk workflows:
- Insurance denial letter generation
- Insurance verification from payer references
- Email drafting with template library
- Conversation-aware email thread replies
- Multi-document smart template composer (up to 3 files, including image/PDF/DOCX/text)
- Local model routing (global or per use-case)
- Multi-user authentication and audit events
- Centralized prompt registry for all generation paths (`services/prompt_registry.py`)
- Server-side draft quality gating + auto-repair for weak/non-professional outputs
- Server-side factual grounding guardrails for high-risk values (dates/times/IDs/phones/currency/email)

Current scope note:
- Mailbox-native thread sync (Gmail/Outlook/Exchange), real-time inbox monitoring, and live suggestion push are not implemented yet. Current email-thread workflow is manual input/upload based.

## Email Exchange Capability Matrix (Current vs Planned)

Current (implemented):
- Analyze pasted/uploaded email thread content
- Detect intent/urgency/tone from thread context
- Recommend matching templates
- Generate role-aligned reply drafts with runtime field support

Not yet implemented:
- Direct mailbox connection (Microsoft 365, Gmail, Exchange/IMAP)
- Real-time inbound sync/webhook processing
- In-app live suggestion stream for newly received emails
- Send-assist or outbound dispatch integration

Implementation path:
- Continue using `/api/email-thread/generate` as the generation engine.
- Add mailbox connectors as ingestion/orchestration layer in a later phase.

## Current Behavior (May 2026)

- Provider-role identity enforced in prompts:
  - Drafts are generated from Siligent provider perspective (not AI narrator perspective).
- Smart Composer generation supports template-only mode:
  - Uploads are optional; users can generate from template type + runtime fields without files.
- Canonical template model:
  - Exactly one template per purpose type is enforced globally.
  - Saving a template for an existing purpose type updates/replaces the canonical template.
- Default template seeding:
  - On API startup, shared default templates are auto-seeded for purpose types that are missing.
- Storage/auth reality:
  - PostgreSQL + pgvector is primary runtime persistence.
  - Multi-user auth is enabled by default (`admin` and `staff` roles).

## Recommended Production Stack

- API backend: FastAPI (`api/main.py`)
- Inference: Ollama local API (`localhost:11434`)
- Persistence: PostgreSQL + pgvector (primary), local filesystem for uploaded binary files
- Frontend: React + TypeScript + Vite SPA (`frontend/`)

Legacy local UI:
- Streamlit app remains available in `app.py` for internal/local use.

## Quick Start (FastAPI)

1. Create and activate virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Configure environment:
   - `cp .env.example .env`
   - Optional tuning:
     - `OLLAMA_GENERATE_TIMEOUT_SEC` (default `180`)
     - `OLLAMA_NUM_PREDICT` (default `1024`)
     - `OLLAMA_THINK` (default `false` for faster/stable structured output on reasoning models)
     - `OLLAMA_KEEP_ALIVE` (default `0` to unload model immediately after each request)
     - `AUTH_ENABLED` (default `true`)
     - `AUTH_SESSION_HOURS` (default `12`)
     - `ALLOW_SELF_REGISTER` (default `false`)
     - `DATABASE_URL` (default `postgresql://siligent:siligent@localhost:5434/siligent`)
     - `DB_POOL_MIN_SIZE` / `DB_POOL_MAX_SIZE` for API connection pool sizing
4. Start Ollama and model:
   - `ollama serve`
   - `ollama pull qwen3.5:4b`
5. Start API:
   - `uvicorn api.main:app --host 0.0.0.0 --port 8000`
6. Open API docs:
   - `http://localhost:8000/docs`

## Quick Start (Frontend)

1. In a new terminal:
   - `cd frontend`
2. Copy env:
   - `cp .env.example .env`
3. Install dependencies:
   - `npm install`
4. Start dev server:
   - `npm run dev`
5. Open app:
   - `http://localhost:3000`

## Docker Deployment (API + Frontend, Host Ollama)

- Prerequisite on host:
  - `ollama serve`
  - `ollama pull qwen3.5:4b`
- Build and start containers:
  - `docker compose up --build`
- Stack services:
  - `db` (pgvector/Postgres 16) on `localhost:5434`
  - `api` on `localhost:8000`
  - `frontend` on `localhost:3000`
- Frontend:
  - `http://localhost:3000`
- API:
  - `http://localhost:8000/docs`
- Ollama (host process):
  - `http://localhost:11434`

## Local Process Control Scripts

- Start Docker stack (API + frontend; uses host Ollama):
  - `./start.sh`
- Stop Docker stack:
  - `./stop.sh`

Notes:
- Scripts are Docker Compose wrappers and control `frontend` + `api` + `db` containers in `docker-compose.yml`.
- Extra arguments are passed through to compose commands (example: `./start.sh --no-build`).

## One-Time Data Migration (File Store -> Postgres)

When upgrading from file-based runtime storage, migrate existing data (`users/sessions/templates/template_types/model_preferences/uploads/audit`) into Postgres:

- Preferred (containerized runtime):
  - `docker compose exec -T api python scripts/migrate_file_store_to_postgres.py`
- Alternate (local Python runtime with dependencies installed):
  - `python3 scripts/migrate_file_store_to_postgres.py`

The migration is idempotent and safe to re-run.

## API Endpoints

- `GET /api/auth/bootstrap`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/health`
- `GET /api/models`
- `GET /api/email-scenarios`
- `GET /api/model-preferences`
- `PUT /api/model-preferences`
- `GET /api/template-types`
- `POST /api/template-types`
- `GET /api/field-dictionary`
- `PUT /api/field-dictionary/{field_key}`
- `DELETE /api/field-dictionary/{field_key}`
- `GET /api/denial-codes`
- `GET /api/payers`
- `POST /api/denial-letters/generate`
- `POST /api/emails/generate`
- `POST /api/email-thread/generate`
- `POST /api/insurance-verification/generate`
- `POST /api/document-pipeline/generate`
- `GET /api/templates`
- `POST /api/templates`
- `DELETE /api/templates/{index}`
- `GET /api/audit-events` (admin)

## Prompt Architecture (Single Source of Truth)

All prompt path selection is centralized in:
- `services/prompt_registry.py`

This registry defines:
- Email scenario label -> prompt file mapping
- Document pipeline prompt keys (`detect_template_type`, `structured_output`, `repair_final_draft`)
- Email thread prompt keys (`analyze_thread`, `generate_reply`)
- Insurance verification prompt key
- Denial prompt path resolver by denial code

Rule:
- Add or change prompt mappings in `services/prompt_registry.py` first.
- Keep prompt text files in `prompts/**/*.txt`.
- Runtime code should resolve prompt names from the registry only.

## Draft Quality Enforcement

For document pipeline generation (`POST /api/document-pipeline/generate`):
- Output is normalized and stabilized.
- Final draft is structurally validated by template type.
- Weak outputs (for example bullet-only summaries) are rejected.
- A repair rewrite pass (`prompts/document_pipeline/repair_final_draft.txt`) runs automatically when needed.

This ensures users receive professional, production-ready communication drafts rather than summary fragments.

## Factual Grounding Policy

The backend enforces a strict trust boundary for high-risk factual values:
- Dates, times, IDs, phone numbers, currency values, and email addresses in generated drafts must be grounded in trusted input sources (uploaded docs, runtime fields, or user-provided request context).
- If ungrounded values are detected, the API returns:
  - `code: "UNGROUNDED_FACTS"`
  - HTTP `422`
- Resolution path:
  - Provide missing facts via runtime fields or uploaded source documents, then regenerate.

Insurance verification has additional grounding:
- `covered_procedures` and other summary fields are filtered against payer reference text.
- Non-grounded values are replaced with `"Not available"` rather than guessed.

## Security and Operational Guardrails

- Only localhost Ollama URLs are allowed by backend config.
- Payer reference loads are path-bound to `data/payer_references`.
- Uploaded documents are stored locally under `data/uploads/`.
- Authentication is token-based; first user bootstrap creates admin account.
- Audit events are stored locally in `data/audit_events.jsonl`.
- Structured error responses are returned for all known failures.
- Optional API key auth via `API_KEY` and `X-API-Key` header.
- CORS allowlist configurable via `CORS_ORIGINS`.
- Frontend sends API key via `VITE_API_KEY` (if configured).

## Planned (Not Yet Implemented)

- Mailbox connector integrations:
  - Microsoft 365 / Outlook (Graph)
  - Gmail (watch/history)
  - Exchange/IMAP paths where required
- Real-time thread sync and suggestion delivery:
  - new inbound email events
  - auto-analysis and draft suggestion queue
  - live UI updates via SSE/WebSocket
- Guarded send-assist workflow:
  - human review and approve/reject before any outbound action

## Legacy Streamlit Run

- `streamlit run app.py --server.port 8501`
