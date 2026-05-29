# Implementation Plan — Siligent Dental AI Assistant

## Current Status Note (May 2026)

This plan reflects an earlier phase and is retained for history. Current implementation has moved beyond several assumptions in this file:

- Primary stack is FastAPI + React + PostgreSQL/pgvector (Docker Compose), with host Ollama.
- Multi-user authentication and audit logging are implemented.
- Canonical template model is enforced (one template per purpose type globally).
- Startup default template seeding is implemented.
- Smart Composer supports optional uploads (template/runtime-only generation is allowed).

Use `README.md`, `TRD-Siligent-Dental-AI.md`, and `RUNBOOK-Siligent-Dental-AI.md` snapshots for current operational truth.

## 1. Scope Baseline (From PRD/TRD)

This implementation plan covers v1 only:
- Local-only, offline-capable AI assistant (no outbound calls except `localhost:11434`)
- Three modules: Denial Letters, Insurance Verification, Email Drafting
- Template Library persisted in `data/templates.json` (file-based, no DB)
- Model via Ollama (`gemma:7b` primary, `gemma:2b` fallback)
- Single-machine deployment

Non-negotiables:
- `stream: false` for Ollama calls
- `timeout=60` for model inference
- Structured JSON error responses (`error`, `message`, `code`)
- No patient data logging
- Atomic writes for `templates.json`

## 2. Architecture Decisions (Gate in Week 1)

Make and lock these decisions before feature development:
1. UI path: `Streamlit` (faster delivery) or `React + Flask/FastAPI` (cleaner separation).
2. Model target: `gemma:7b` if latency targets pass; otherwise `gemma:2b`.
3. Binding mode: `localhost` only unless LAN access is explicitly required.

Decision criteria:
- Denial letter latency < 30s
- Verification latency < 20s
- Email latency < 15s
- 100% offline functionality

## 3. Phase Plan (5 Weeks)

## Week 1 — Foundation and Skeleton

Build:
- Project skeleton from TRD folder structure
- Environment loading (`.env`, `.env.example`)
- Core services: prompt loader, variable substitution, Ollama client, error mapper
- Data bootstrap (`data/payer_references/`, `data/templates.json`)
- Health check endpoint/page and startup checks

Deliverables:
- App starts cleanly
- Health endpoint confirms model reachability
- One test prompt works end-to-end

Exit criteria:
- Offline smoke test passes
- Guardrails implemented (timeout, stream false, no outbound URLs)

## Week 2 — Epic 2: Denial Letter Generator

Build:
- Denial code configuration (10 required CO codes)
- Denial form with client + server validation
- Template mapping: `/prompts/denial_letters/{code}.txt`
- Output panel with copy + download

Test:
- Generate 10/10 code scenarios
- Validate required field behavior
- Validate no hallucinated addresses/codes in scripted checks

Exit criteria:
- 100% structure adherence against expected format
- All 10 denial code paths generate successfully

## Week 3 — Epic 3: Insurance Verification

Build:
- Verification form (`payer_name`, `member_id`, `group_number`, `patient_dob`, `plan_type`)
- Payer reference resolver (`lowercase + spaces_to_underscores + .txt`)
- Structured verification output with all required fields:
  - covered procedures
  - estimated co-pay
  - prior authorization
  - annual maximum
  - waiting periods
  - exclusions/limitations

Test:
- Accuracy checks against 5 known reference scenarios
- Missing payer reference path returns 422
- No fabricated benefits in low-context tests

Exit criteria:
- All 6 structured fields present in every response
- No contradictions against payer source files in test set

## Week 4 — Epic 4: Email Drafting + Template Library

Build:
- 8 email scenario mappings under `/prompts/emails/`
- Editable draft output
- Template CRUD:
  - list
  - save (`name`, `type`, `content`, `created_at`)
  - load
  - delete by index
- Atomic read/write safeguards for `templates.json`

Test:
- 8/8 email scenarios generate
- Save/load/delete persistence across restart
- Corrupted/missing `templates.json` recovery behavior

Exit criteria:
- Persistence is stable across restarts
- CRUD operations return expected responses and errors

## Week 5 — Integration, Hardening, and Demo Readiness

Build:
- Unified navigation across all modules
- UX polish for non-technical users (clear errors, loading states, labels)
- Failure handling from runbook scenarios:
  - Ollama down
  - model missing
  - timeout
  - prompt file missing
  - disk/write failure
- Final setup and onboarding checks

Validation:
- 5-minute health check green
- Full offline walkthrough for all three modules
- Non-technical usability run with issue log and fixes
- NFR timing checks against targets

Exit criteria:
- End-to-end demo script passes without manual fallback
- Deployment checklist passes on a clean machine

## 4. Work Breakdown by Component

Backend core:
- Prompt file loader
- Variable validator
- Ollama adapter
- Error translation layer
- Templates storage service (atomic writes)

Feature modules:
- Denial letters
- Insurance verification
- Email drafting
- Template library

Operational assets:
- Prompt templates (10 denial + 8 email + verification)
- Payer reference seed files
- `.env.example`
- Health checks and failure playbook verification

## 5. Test Strategy

Required test sets:
- Unit tests for prompt composition, payer file resolution, template storage
- API tests for success + error contracts (React path) or service-layer tests (Streamlit path)
- Manual scenario tests from PRD acceptance criteria
- Offline validation test with network disconnected

Minimum quality gates before release:
- No uncaught exceptions in UI flows
- No tracebacks returned to users
- Zero external network calls during runtime validation

## 6. Delivery Order (Critical Path)

1. Decision gates (UI path + model benchmark)
2. Core inference and error handling
3. Denial letter module
4. Insurance verification module
5. Email + templates module
6. Integration + offline validation + handoff

Anything outside this path (RAG, audit log, Docker installer, expanded denial codes) stays in v2 backlog.
