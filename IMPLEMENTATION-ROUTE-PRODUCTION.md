# Production Implementation Route (v2)

Last updated: 2026-05-26
Status: Ready for execution after client discovery sign-off

## Technical Direction

1. Keep `FastAPI` backend and `React + TypeScript` frontend.
2. Replace file-only persistence with production storage:
   - PostgreSQL for app data
   - Object storage for uploaded documents
3. Keep Ollama local inference; add model management layer and per-use-case model selection.
4. Add authenticated multi-user RBAC and full audit logging.
5. Use bounded agentic architecture (workflow-constrained), not autonomous open-ended agents.

## Phase 1 — Foundation (Security, Auth, Data)

1. Add authentication (JWT/session), RBAC, and tenant-aware data model.
2. Introduce PostgreSQL schema:
   - users, roles, organizations
   - templates, template_types, template_versions
   - uploads, extracted_documents, generations
   - audit_events
3. Add object/document storage abstraction with checksum + metadata.
4. Add compliance controls:
   - PHI-safe logging
   - retention policies
   - auditable events for all critical actions

Exit criteria:
- Multi-user login works.
- Data is isolated by org/tenant.
- All critical events are auditable.

## Phase 2 — Ingestion Pipeline (Upload, OCR, Extraction)

1. Add multi-file upload (max 3 files per generation).
2. Support file types:
   - text docs: `txt`, `pdf`, `docx`
   - images/scans: `png`, `jpg`, `jpeg`, `tiff` (+ OCR path)
3. Build ingestion service:
   - parse text-native files
   - OCR scanned files/images
   - normalize and chunk extracted text
   - persist extraction artifacts
4. Add upload UI with preview/remove/retry states.

Exit criteria:
- Users can upload up to 3 mixed files reliably.
- Extracted text is persisted and queryable.

## Phase 3 — Scenario Detection + Template Recommendations

1. Add scenario classifier returning:
   - predicted scenario type
   - confidence score
   - rationale/labels
2. Add recommendation engine ranking templates descending by score.
3. Add manual override UI for scenario and template selection.
4. Add user-defined template types in UI.

Exit criteria:
- System returns ranked template recommendations.
- User can override classifier decisions at any step.

## Phase 4 — Structured Generation Engine

1. Introduce schema-driven generation per template type.
2. Enforce structured JSON output contract server-side.
3. Render human-friendly formatted letter/email from structured JSON.
4. Add validation and failure recovery for malformed model output.
5. Enforce final-draft quality gates (role/purpose/type structure) with auto-repair rewrite step.

Exit criteria:
- Outputs are structurally valid and consistent across runs.
- Template-specific required sections are enforced.
- Weak summary-like drafts are automatically repaired before UI display.

## Agentic Pattern (Bounded)

Implement specialized, contract-bound stages:
1. Intent/Type stage
2. Template retrieval/ranking stage
3. Draft generation stage
4. Quality/compliance gate stage

Guardrails:
- Deterministic routing and fallback path per stage
- Strict input/output schema per stage
- Full observability (prompt version, model, timing, gate outcomes)
- Human-in-the-loop remains mandatory for outbound usage

## Phase 5 — Model Management

1. Query local models from Ollama `/api/tags`.
2. Add model picker modes:
   - per-generation
   - default per use-case
   - global “use this for all”
3. Add model policy controls:
   - allowlist
   - fallback on timeout/failure
4. Persist model selection and include in audit log.

Exit criteria:
- Users can choose model flexibly.
- System supports safe fallback when selected model fails.

## Phase 6 — UX Overhaul

1. Replace current forms with guided stepper flow:
   - Upload
   - Auto-classify
   - Choose template/model
   - Generate
   - Review + save
2. Improve information hierarchy and feedback states.
3. Add empty states, progressive disclosure, and inline help.
4. Add accessibility pass (keyboard and screen-reader basics).

Exit criteria:
- Non-technical user can complete each workflow without assistance.
- UX matches production usability expectations.

## Phase 7 — Hardening and Deployment

1. Add e2e tests for critical flows.
2. Add performance/load tests for target concurrency.
3. Add backup/restore scripts and operational runbook updates.
4. Finalize Docker deployment profile and environment templates.

Exit criteria:
- Stable production deploy process.
- Signed UAT for pilot clinic workflows.

## Phase 8 — Mailbox Sync and Real-Time Suggestions (Planned)

Current baseline before this phase:
- Manual email-thread draft generation already exists via Smart Composer + `/api/email-thread/generate`.
- This phase adds mailbox ingestion and real-time suggestion delivery on top of that baseline.

1. Add mailbox connectors (tenant-configurable):
   - Microsoft Graph (Outlook/M365)
   - Gmail watch/history
   - Exchange/IMAP fallback where needed
2. Add inbound event ingestion:
   - webhook/event receiver
   - incremental thread fetch + dedupe
   - secure token/secret handling and rotation
3. Reuse existing email-thread analysis/generation for event-driven suggestions.
4. Add real-time suggestion delivery to UI:
   - SSE/WebSocket channel
   - inbox suggestion queue by user/role
5. Enforce human-in-the-loop review (no automatic sending).
6. Expand audit trail for mailbox events and suggestion lifecycle.

Exit criteria:
- New inbound mailbox messages create draft suggestions automatically.
- Staff can review suggestions in near real time from the app UI.
- Full mailbox event and suggestion lifecycle is auditable.

## Delivery Sequence (Recommended)

1. Phase 1 + Phase 2
2. Phase 3 + Phase 4
3. Phase 5 + Phase 6
4. Phase 7 + UAT

## Immediate Next Step

Use `CLIENT-DISCOVERY-QUESTIONNAIRE.md` with client stakeholders first.  
Once answered, lock schemas and start Phase 1 implementation.
