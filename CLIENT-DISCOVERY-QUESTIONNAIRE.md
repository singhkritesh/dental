# Client Discovery Questionnaire — Production Build

Last updated: 2026-04-23
Owner: Product + Engineering

## 1) Current Decisions From Sponsor (Already Confirmed)

These are inputs already provided and should be treated as current defaults:

1. Document upload types: support all major types, including vision-capable paths.
2. Max uploads per generation: 3 files.
3. Template types: user should be able to add template/use-case types in UI.
4. Scenario detection: auto-detect scenario, with user control.
5. Recommendations: show best matches in descending order.
6. Model selection: allow per-use-case model selection and “use one model for all”.
7. Local model source: list installed local models from Ollama.
8. Output format: structured outputs.
9. Document persistence: store uploaded documents.
10. Compliance: include compliance controls.
11. User model: authenticated multi-user system.

## 2) Business & Product Alignment Questions

1. What are the top 3 business outcomes for phase 1 production rollout?
2. What does success look like in 30/60/90 days (time saved, denial turnaround, error reduction)?
3. Which workflows are mandatory for go-live vs acceptable for phase 2?
4. Which clinics/practices are pilot users, and how many staff will use the app initially?
5. Which geographies/jurisdictions apply (US only, state-specific rules)?

## 3) User Roles, Auth, and Access Control

1. Required roles at launch (Front Desk, Manager, Billing Specialist, Admin, Compliance Officer)?
2. Should role permissions differ by feature (view/generate/delete/export/manage models)?
3. Authentication source:
   - Local accounts
   - SSO (Google/Microsoft/Okta)
   - Existing internal IdP
4. Password policy + MFA requirements?
5. Session timeout/inactivity timeout requirements?
6. Need IP restrictions or allowlist?
7. Need per-tenant isolation (multi-practice separation) now or later?

## 4) Compliance, Privacy, and Legal

1. Confirm regulatory baseline: HIPAA only, or HIPAA + SOC2 controls + state privacy laws?
2. Do we need Business Associate Agreement workflows or templates?
3. PHI handling policy:
   - Can raw uploaded documents contain PHI? (assume yes)
   - Should PHI be masked in UI previews/logs by default?
4. Encryption requirements:
   - At rest
   - In transit
   - Key management expectations
5. Audit log scope:
   - Login events
   - Document upload/download/delete
   - Generation request/response metadata
   - Template CRUD
   - Model selection changes
6. Audit log retention period and export format requirements?
7. Data retention policy for uploaded documents and generated outputs?
8. Data deletion policy (soft delete, hard delete, legal hold)?
9. Need tamper-evident audit logs?

## 5) Document Ingestion & Extraction

1. Confirm supported formats for day 1:
   - `pdf`, `docx`, `txt`, `rtf`, `png`, `jpg`, `jpeg`, `tiff`, `heic`?
2. For PDFs, should both text PDFs and scanned PDFs be supported? (recommended: yes)
3. OCR engine preference:
   - Vision LLM only
   - Traditional OCR + LLM refinement
   - Hybrid fallback chain
4. Language support beyond English?
5. File limits to confirm:
   - Max file size per file
   - Max total request size
   - Max pages per PDF
6. Need drag-and-drop and bulk upload UX?
7. Need per-file preview before generation?
8. Should users be able to remove/reorder files before generation?

## 6) Scenario Classification & Recommendation Engine

1. Required scenario classes at launch (exact list)?
2. Should classification return confidence scores?
3. If confidence is low, should UI force user confirmation?
4. Recommendation strategy preference:
   - Semantic similarity to historical templates
   - Metadata/tag matching
   - Hybrid scoring
5. Should recommendations include “why recommended” explanations?
6. Should users be allowed to pin/favorite templates?
7. Do we need tenant-specific recommendation isolation?

## 7) Template System & Structured Output Requirements

1. Template type schema:
   - User-defined name only
   - Name + required fields + output section schema
2. Structured output format:
   - JSON schema enforced on backend
   - Rendered formatted text sections on frontend
3. For each template type, what sections are mandatory?
4. Need versioning for templates (draft/published)?
5. Need approval workflow before template can be used org-wide?
6. Should templates be private, team-shared, or org-shared?
7. Need import/export for templates?

## 8) Model Management

1. Model eligibility rules:
   - Any local Ollama model
   - Allowlisted models only
2. Need model capability tags in UI (vision, text-only, latency class)?
3. Should model defaults be configurable by:
   - Global
   - Template type
   - User
4. Need automatic fallback model on failure/timeout?
5. Need model benchmark panel (quality/latency/cost proxy)?
6. Need to track model used per generation in audit logs?

## 9) UX & Interaction Design

1. Preferred UX direction: enterprise dashboard vs guided wizard?
2. Need onboarding flow for first-time users?
3. Should generation be:
   - Single-page form
   - Stepper (Upload → Classify → Choose template/model → Generate)
4. Need side-by-side comparison of recommended templates?
5. Need editable output with section-level locking?
6. Need autosave for drafts?
7. Accessibility targets (WCAG 2.1 AA)?

## 10) Data Persistence & Storage

1. Storage backend for production:
   - Continue file-based storage
   - Move to database + object storage
2. If DB, preference (PostgreSQL/MySQL/SQLite for pilot)?
3. If object storage, local disk vs S3-compatible store?
4. Need checksum/deduplication for uploaded files?
5. Need retention jobs and archival policies?

## 11) Deployment, Infra, and Operations

1. Target environment:
   - Single on-prem server
   - Multi-node on-prem
   - Cloud VPC
2. Container orchestration:
   - Docker Compose
   - Kubernetes
3. Backup and restore requirements?
4. Monitoring and alerting requirements (logs/metrics/traces)?
5. Incident response expectations and escalation paths?
6. Uptime target and maintenance windows?

## 12) Performance & Reliability Targets

1. Max acceptable latency by use case:
   - Classification
   - Recommendation
   - Final generation
2. Expected concurrent users at pilot and 12 months?
3. Expected daily generation volume?
4. Timeout policy per endpoint?
5. Retry behavior policy for model errors?

## 13) Reporting & Analytics

1. Required operational dashboards?
2. Required business reports (usage by workflow, model success rate)?
3. Need per-user productivity metrics?
4. Need export to CSV/PDF?

## 14) Go-Live, UAT, and Change Management

1. UAT sign-off criteria by stakeholder?
2. Required training materials (videos, SOP docs, in-app guides)?
3. Rollout strategy:
   - Pilot only
   - Phased rollout
   - Big bang
4. Support model after launch (SLA, helpdesk, escalation)?

## 15) Risks To Resolve Early

1. OCR quality variance across scanned documents.
2. Hallucination risk in legal/insurance correspondence.
3. PHI retention and audit completeness.
4. Model performance variability across local hardware.
5. Role/tenant access leaks if auth and isolation are under-scoped.

## 16) Proposed Default Assumptions (If Client Does Not Answer)

1. Enforce model allowlist (`qwen3.5:4b`, `qwen3.5:9b`, `gemma4:*`) with admin override.
2. Use stepper UX flow with manual override at classification and recommendations.
3. Use structured JSON schemas per template type + human-readable rendered output.
4. Persist uploads and outputs with encrypted-at-rest storage and full audit trails.
5. Introduce RBAC with Admin/Manager/Staff roles and tenant-aware data partitioning.

## 17) Mailbox Integration (Planned Phase; Not in Current Build)

1. Which mailbox platforms are in scope for phase 1 mailbox sync?
   - Microsoft 365 / Outlook
   - Gmail (Google Workspace)
   - Exchange / IMAP
2. Should the system ingest:
   - all inbound messages
   - selected folders/labels only
   - selected shared mailboxes only
3. Real-time expectation:
   - near real time (webhook/watch)
   - periodic polling
4. Is auto-sending allowed, or must all suggestions remain human-reviewed only?
5. Required assignment model for suggestions:
   - by mailbox
   - by location/clinic
   - by user role/team
6. Required retention policy for synced email content and generated suggestions?
7. Any legal/compliance constraints on mailbox data storage in the app database?
