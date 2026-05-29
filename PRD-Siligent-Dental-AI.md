---
version: "1.0"
last_updated: "2026-05-03"
status: "Draft"
theme: "Healthcare AI — Dental Office Efficiency"
---

# PRD — Siligent Dental AI Assistant

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Target Audience & Personas](#3-target-audience--personas)
4. [Jobs To Be Done](#4-jobs-to-be-done)
5. [Scope & Prioritization](#5-scope--prioritization)
6. [Functional Requirements](#6-functional-requirements)
7. [Authentication & Authorization](#7-authentication--authorization)
8. [AI System](#8-ai-system)
9. [System Architecture](#9-system-architecture)
10. [Data Model / Key Entities](#10-data-model--key-entities)
11. [API Design](#11-api-design)
12. [Security & Privacy](#12-security--privacy)
13. [Non-Functional Requirements](#13-non-functional-requirements)
14. [Error States & Edge Cases](#14-error-states--edge-cases)
15. [Out of Scope](#15-out-of-scope)
16. [Open Questions & Risks](#16-open-questions--risks)
17. [Glossary](#17-glossary)

---

## Current Implementation Snapshot (Authoritative)

This document includes legacy planning assumptions from early phases. The following reflects the implemented product state and supersedes conflicting legacy statements below:

- Backend/frontend/runtime:
  - FastAPI API + React frontend + Docker Compose deployment are implemented.
  - Streamlit remains legacy/local only and is not the primary production path.
- Data and persistence:
  - PostgreSQL + pgvector are primary persistence.
  - Local filesystem is still used for prompt files and uploaded file storage.
- Authentication:
  - Multi-user authentication is implemented (`admin` and `staff` roles).
  - Audit events are implemented.
- Template model:
  - Exactly one canonical template per purpose type is enforced globally.
  - Saving a template for a purpose type updates/replaces the existing canonical template.
  - Default shared templates are seeded automatically on API startup when missing.
- Prompt identity and drafting role:
  - Generation prompts enforce provider identity (Siligent provider perspective).
- Smart Composer UX behavior:
  - Uploads are optional for generation.
  - Users can generate from purpose/template + runtime fields without file uploads.

When this PRD conflicts with the above snapshot, follow the snapshot and the current codebase behavior.

---

## 1. Executive Summary

**Siligent Dental AI Assistant** is a locally-hosted, offline-capable AI tool that automates three high-frequency front desk workflows for dental practices: insurance verification, insurance denial letter generation, and email drafting with reusable templates. The tool targets non-technical front desk staff who currently perform these tasks manually using paper references, copy-paste templates, and phone calls.

The system runs Gemma (7B or 2B) via Ollama on a local server with no internet connection during use, satisfying HIPAA data-handling constraints by design. The UI is built with either Streamlit (Python) or React, chosen in Week 1 based on team skillset. Data persistence uses local JSON files — no external database. The project is a 5-week proof-of-concept engagement by a 3-person team for sponsor Tasha Dickinson, Founder & Chief Technologist at Siligent.

> **Assumed:** The final stack decision (Streamlit vs React, Gemma 7B vs 2B) is made during Week 1 based on hardware benchmarks and team capabilities. This PRD documents both paths where they diverge.

---

## 2. Problem Statement

Dental front desk staff at practices served by Siligent spend 15–30 minutes per insurance denial appeal, manually filling in letter templates with patient data, denial codes, and payer-specific language. Insurance verification requires cross-referencing printed payer coverage summaries or calling payer hotlines — a process that takes 10–20 minutes per patient and is error-prone when staff misread coverage terms. Routine email communications (appointment reminders, balance due notices, referral letters) are drafted from scratch or copy-pasted from old emails, leading to inconsistent tone, missing details, and 5–10 minutes per email.

These tasks are repetitive, high-volume (a busy practice handles 20–40 patient interactions per day), and critically error-sensitive — a wrong denial code or misquoted coverage term can delay reimbursement by weeks or result in denied appeals. Staff performing these tasks have no technical background and cannot use tools that require command-line interaction, API knowledge, or complex multi-step interfaces.

Existing solutions fail this audience in specific ways. General-purpose LLM tools (ChatGPT, Copilot) require internet connectivity, which violates HIPAA data-handling constraints when patient-identifiable information is entered. Practice management software (Dentrix, Eaglesoft) handles scheduling and billing but offers no AI-assisted document generation. Manual template systems (Word docs, printed binders) work but are slow, error-prone, and cannot adapt to payer-specific language requirements.

**The opportunity:** A locally-hosted AI assistant that understands dental terminology, payer-specific coverage language, and denial code semantics can reduce denial letter generation from 15–30 minutes to under 2 minutes, insurance verification from 10–20 minutes to under 1 minute, and email drafting from 5–10 minutes to under 30 seconds — while eliminating the HIPAA exposure risk of cloud-based tools entirely.

---

## 3. Target Audience & Personas

### The Veteran Front Desk Coordinator — Maria

- 15 years at a mid-size dental practice, handles all insurance correspondence and patient communications. Uses Dentrix for scheduling, Word for letters, Outlook for email. No comfort with command lines or developer tools.
- **Primary journey:** Patient's insurance claim denied with code CO-45 → Maria opens the AI tool → selects "Denial Letter" → picks CO-45 from dropdown → enters patient name, DOS, procedure, payer → clicks Generate → reviews the letter → clicks Download → prints and mails.
- **Pain point:** Currently spends 20 minutes per denial letter finding the right template, filling in 8–12 fields manually, and rewording payer-specific language. Makes 1–2 errors per week that require re-drafting.
- **Success state:** Maria generates a complete, print-ready denial appeal letter in under 2 minutes without leaving the AI tool, with zero manual field lookups.

### The New Hire — Jordan

- 3 months into the job, still learning denial codes and payer terminology. Frequently asks Maria for help with letter wording and coverage verification. Comfortable with web apps but not technical tools.
- **Primary journey:** Needs to verify a patient's coverage with Delta Dental → opens the AI tool → selects "Insurance Verification" → enters payer name, member ID, patient DOB → clicks Verify → reads the structured summary showing covered procedures, co-pay estimates, and prior auth requirements.
- **Pain point:** Doesn't know which payer documents to reference or how to interpret coverage tables. Currently takes 15–20 minutes to answer a coverage question, often needing Maria's help.
- **Success state:** Jordan gets a structured, plain-English coverage summary in under 1 minute without asking anyone for help.

### The Practice Manager — Dr. Patel

- Owns the practice, reviews all outgoing insurance correspondence before mailing. Wants consistent, professional communication. Does not use the tool directly but evaluates its output.
- **Primary journey:** Reviews a stack of denial letters at end of day → checks that each letter correctly cites the denial code, procedure, and payer-specific appeal language → approves or flags for revision.
- **Pain point:** Inconsistent letter quality from different staff members. Letters sometimes cite wrong denial codes or use outdated appeal language.
- **Success state:** Every letter generated by the AI tool follows the same template structure, correctly cites the denial code definition, and uses current payer-specific language — reducing Dr. Patel's review time from 5 minutes per letter to 30 seconds.

### The IT Admin / Siligent Technician — Tasha

- Deploys and maintains the tool on the practice's local server. Technical background but needs the deployment to be simple enough to hand off to junior staff.
- **Primary journey:** Sets up a new practice → installs Ollama → pulls Gemma model → launches the app → verifies all three features work offline → hands off to front desk staff.
- **Pain point:** Complex deployment procedures that require developer-level troubleshooting when something breaks.
- **Success state:** Tasha deploys the tool on a new machine in under 30 minutes using a documented setup guide, with a single verification command confirming everything works.

---

## 4. Jobs To Be Done

| Job | User | Statement |
|-----|------|-----------|
| Generate denial appeal | Maria, Jordan | When I receive an insurance denial with a specific code, I select the code and enter patient details — and get a print-ready appeal letter in under 2 minutes without looking up template language. |
| Verify insurance coverage | Jordan, Maria | When a patient calls about coverage for a procedure, I enter their payer and plan info — and get a structured summary telling me what's covered, estimated co-pay, and whether prior auth is needed, in under 1 minute. |
| Draft routine email | Maria, Jordan | When I need to send an appointment reminder or balance notice, I pick the scenario and add patient details — and get a professional, editable email draft in under 30 seconds. |
| Save and reuse templates | Maria | When I generate a good email or letter, I save it as a named template — and can reload and adapt it for similar situations without regenerating from scratch. |
| Deploy on new machine | Tasha | When I set up a new practice, I follow the setup guide — and have the tool running offline in under 30 minutes with all three features verified. |
| Review generated output | Dr. Patel | When I review denial letters at end of day, every letter follows the same structure and correctly cites denial code definitions — reducing my review time to under 30 seconds per letter. |

---

## 5. Scope & Prioritization

### Must Have (v1)

- Local LLM (Gemma via Ollama) running offline with no internet dependency — **Planned**
- Backend wrapper accepting prompt template name + variable dict, returning generated text — **Planned**
- Denial Letter Generator: dropdown of 10 denial codes (CO-4, CO-6, CO-16, CO-22, CO-29, CO-45, CO-50, CO-97, CO-109, CO-119), patient fields, template-based generation — **Planned**
- Insurance Verification: payer name, member ID, group number, patient DOB, plan type inputs → structured coverage summary using payer reference text as context — **Planned**
- Email Drafting: 8 scenario types (appointment reminder, cancellation confirmation, balance due, insurance update request, referral letter, new patient welcome, post-treatment follow-up, general inquiry response) — **Planned**
- Template Library: save, load, list, edit generated outputs as reusable named templates, persisted in local JSON — **Planned**
- Single integrated app with navigation across all three modules — **Planned**
- Copy-to-clipboard and download-as-text for all generated outputs — **Planned**
- Offline validation: all features verified with zero external API calls — **Planned**

### Should Have (v1)

- Usability testing by a non-technical user before demo — **Planned**
- Setup guide for deploying on a new machine, written for non-developer audience — **Planned**
- Demo script with 3 realistic walkthroughs and backup screen recording — **Planned**

### Could Have (v2)

- RAG with ChromaDB for insurance verification (replacing prompt-stuffing for better accuracy at scale)
- Session audit log (timestamp, feature used, input summary — no patient data) for HIPAA documentation
- One-command installer (Docker or shell script) for zero-setup deployment
- Expanded denial letter support beyond initial 10 codes to cover Tasha's full template set

### Won't Have (v1)

- Production deployment to real dental practices
- Real patient data ingestion or processing
- EHR/practice management software integration (Dentrix, Eaglesoft)
- HIPAA certification or formal compliance audit
- Post-engagement support or maintenance
- Multi-user authentication or role-based access
- Cloud hosting or remote access
- Automated payer reference data updates
- Voice input or speech-to-text capabilities

---

## 6. Functional Requirements

### Epic 1: AI Backend & Model Infrastructure

**Local LLM Provisioning**
Ollama runs on the local server hosting Gemma (7B preferred, 2B fallback). The model is pre-pulled during setup — no internet connection required during use. The backend wrapper accepts a POST request with a prompt template name and a dictionary of variable values, injects variables into the prompt template, calls the Ollama API at `http://localhost:11434/api/generate`, and returns the generated text as plain text. On Ollama API timeout (>60s), the backend returns HTTP 504 with message "Model response timed out. Please try again." On Ollama API connection refused, the backend returns HTTP 503 with message "AI model is not running. Please contact your administrator."

**Prompt Template System**
Prompts are stored as text files in `/prompts/{feature}/` directories. Each prompt file contains a system prompt with `{variable_name}` placeholders. The backend reads the template file, substitutes variables using Python string formatting, and sends the composed prompt to Ollama. If a required variable is missing from the input dict, the backend returns HTTP 400 with a message listing the missing fields. Prompt files are version-controlled in the repo.

**Acceptance Criteria — Epic 1**

| Requirement | Evaluation Method | Metric | Criteria | Justification |
|-------------|-------------------|--------|----------|---------------|
| LLM responds offline | Disconnect network, submit prompt | Response received | Yes/No, must succeed | Core HIPAA constraint — any external call is a violation |
| Response time | Stopwatch from submit to full response displayed | Latency | < 30s for denial letter, < 20s for verification, < 15s for email | Longer than 30s breaks the workflow efficiency value proposition |
| Variable injection accuracy | Submit 5 prompts with known variables, check output | Correct substitution rate | 100% | A missed variable produces an unusable letter with blank fields |

### Epic 2: Insurance Denial Letter Generator

**Denial Code Selection**
A dropdown presents 10 pre-loaded denial codes: CO-4, CO-6, CO-16, CO-22, CO-29, CO-45, CO-50, CO-97, CO-109, CO-119. Each code is displayed with its short description (e.g., "CO-45: Charge exceeds fee schedule/maximum allowable"). The dropdown is populated from a static config file, not dynamically generated.

**Patient Input Form**
Text fields for: patient full name, date of service (date picker), procedure description (free text), procedure code (optional), payer name, payer address (optional), provider name, provider NPI (optional). Required fields: patient name, date of service, procedure description, payer name. On submit with missing required fields, the form highlights missing fields in red and displays "Please fill in all required fields" without calling the backend.

**Letter Generation**
On submit, the backend receives the denial code + patient input, loads the corresponding prompt template from `/prompts/denial_letters/{code}.txt`, injects all variables, calls Gemma, and returns the generated letter. The letter follows Tasha's template structure: header with practice info, date, payer address, RE line with patient and claim info, body citing the denial code definition and appeal rationale, closing with provider signature block. The generated letter is displayed in a read-only text area with Copy to Clipboard and Download as .txt buttons.

**Output Validation**
Gemma is instructed via the system prompt to never invent payer addresses, procedure codes, or coverage details not provided in the input. If the model hallucinates content not present in the input, it should be caught during the 5-scenario testing in Week 2 and addressed through prompt refinement. The system does not perform automated hallucination detection.

**Acceptance Criteria — Epic 2**

| Requirement | Evaluation Method | Metric | Criteria | Justification |
|-------------|-------------------|--------|----------|---------------|
| Template adherence | Generate 10 letters (one per code), compare structure to Tasha's originals | Structure match rate | 100% header/footer structure match | Letters that don't match the practice's format will be rejected by Dr. Patel |
| No hallucinated data | Generate 5 letters, check for addresses/codes not in input | Hallucination count | 0 hallucinated fields per letter | Invented payer addresses or procedure codes invalidate the appeal |
| All 10 codes functional | Generate one letter per denial code | Success rate | 10/10 generate without error | Missing a code means manual fallback for that denial type |

### Epic 3: Insurance Verification

**Input Fields**
Form fields for: payer name (dropdown of 3+ pre-loaded payers, or free text), member ID, group number (optional), patient DOB (date picker), plan type (dropdown: PPO, HMO, DHMO, Indemnity, Other). Required fields: payer name, member ID, patient DOB.

**Payer Reference Context**
Plain-text payer reference documents are stored in `/data/payer_references/` (one file per payer, e.g., `delta_dental.txt`). On submit, the backend loads the reference file matching the selected payer name and injects it into the prompt as context. If no reference file exists for the entered payer, the backend returns HTTP 422 with message "No reference data available for this payer. Please contact your administrator to add it."

**Structured Summary Output**
The prompt instructs Gemma to return a structured summary with these fields: Covered Procedures (list), Estimated Co-Pay (percentage or dollar amount if available, "Not available" otherwise), Prior Authorization Required (Yes/No per procedure category), Annual Maximum (dollar amount if available), Waiting Periods (if applicable), Notable Exclusions/Limitations. The summary is displayed in a formatted card layout, not raw text.

**Acceptance Criteria — Epic 3**

| Requirement | Evaluation Method | Metric | Criteria | Justification |
|-------------|-------------------|--------|----------|---------------|
| Coverage accuracy | Test 5 scenarios against known payer docs, check each field | Field accuracy | No fields contradict the reference document | A wrong coverage answer costs the practice money or delays patient care |
| No hallucinated coverage | Test 3 scenarios with payers that have limited reference data | Fabricated coverage count | 0 fabricated benefits | Staff will trust the output — false coverage info creates liability |
| Response structure | Test 10 queries, check all 6 summary fields present | Field completeness | 100% — all 6 fields present in every response | Missing fields force staff to call the payer anyway, defeating the purpose |

### Epic 4: Email Drafting & Template Library

**Scenario Selection**
Dropdown with 8 scenarios: Appointment Reminder, Cancellation Confirmation, Balance Due Notice, Insurance Update Request, Referral Letter, New Patient Welcome, Post-Treatment Follow-Up, General Inquiry Response. Each scenario loads a dedicated prompt template from `/prompts/emails/{scenario}.txt`.

**Context Input**
An optional free-text field for additional context (patient name, appointment date, balance amount, etc.). The prompt template incorporates this context. If context is left blank, the model generates a generic version of the email.

**Editable Output**
The generated email appears in an editable text area. Staff can modify the draft before copying or downloading. The editing does not re-trigger the model — it is pure client-side text editing.

**Template Library**
Any generated output (email or denial letter) can be saved with a user-defined name. Saved templates are stored in `/data/templates.json` as an array of objects: `{name, type, content, created_at}`. The template list view shows all saved templates sorted by creation date. Clicking a template loads it into the editable output area. Templates persist across app restarts (file-based persistence). Duplicate names are allowed — no unique constraint. Delete removes the entry from the JSON array and rewrites the file.

**Acceptance Criteria — Epic 4**

| Requirement | Evaluation Method | Metric | Criteria | Justification |
|-------------|-------------------|--------|----------|---------------|
| All 8 scenarios generate | Generate one email per scenario | Success rate | 8/8 | Missing scenarios force manual drafting |
| Template persistence | Save 3 templates, restart app, verify all 3 present | Persistence rate | 100% | Lost templates erode trust in the tool |
| Template load/edit | Load a saved template, edit, copy to clipboard | Workflow completion | Completes without error | This is the daily workflow — any friction means staff won't use it |

### Epic 5: Integration & Offline Validation

**Unified Navigation**
All three modules (Verification, Denial Letters, Emails & Templates) are accessible from a single app with consistent navigation (sidebar or tab bar). Clicking a module loads it without a full page refresh (SPA behavior in React/Svelte; Streamlit uses its native multipage approach). No broken links or navigation dead-ends.

**Offline Validation**
With the machine disconnected from the internet, all three features must complete end-to-end: form submission, model inference, output display, copy/download, template save/load. Zero HTTP requests leave the local machine. This is verified by running all features while monitoring network traffic.

**Usability Validation**
One team member role-plays a non-technical front desk user and attempts all three features without assistance. Any step that causes confusion (>10 seconds of hesitation, wrong button clicked, unclear feedback) is logged and addressed before demo.

---

## 7. Authentication & Authorization

> **Assumed:** v1 has no authentication. The tool runs on a single local machine accessible only by staff in the dental office. Physical access to the machine is the only access control. This is appropriate for a PoC but must be addressed before any production deployment.

| Role | Capabilities |
|------|-------------|
| Front Desk Staff (default) | Full access to all three modules, template library CRUD |
| Administrator (Tasha / IT) | All staff capabilities + access to prompt template files, payer reference data, and system configuration |

Role enforcement is physical — administrators have filesystem access, staff interact only through the UI. No software-enforced role separation in v1.

---

## 8. AI System

**Model**
Gemma via Ollama, running locally. Model size (7B vs 2B) is determined by hardware benchmarks in Week 1. The 7B model is preferred for output quality; the 2B model is the fallback if 7B inference exceeds 60 seconds on the target hardware.

**Provider Abstraction**
There is no provider abstraction in v1. The backend calls the Ollama local API directly at `http://localhost:11434/api/generate`. Switching to a different model requires changing the model name in the API call and updating prompt templates if the new model has different instruction formatting.

**Retrieval Strategy**
v1 uses prompt-stuffing: payer reference text is loaded from a local file and injected directly into the prompt as context. This approach is simpler and sufficient for 3–5 payer reference documents of moderate length (< 10 pages each). If reference documents exceed the model's context window or verification accuracy degrades, RAG with ChromaDB is available as a stretch goal.

**Response Delivery**
Responses are delivered synchronously — the backend waits for the full Ollama response and returns it in a single HTTP response. No streaming (SSE/WebSocket) in v1. The UI shows a loading spinner during generation.

**Guardrails**
The system prompt for each feature includes explicit instructions:
- Never invent information not provided in the input or reference context
- Never fabricate payer addresses, phone numbers, or procedure codes
- Always use the patient name, dates, and codes exactly as provided
- If insufficient context is available, state "Insufficient information to generate this field" rather than guessing

No automated hallucination detection. Output quality is validated through manual testing during Weeks 2–4.

**Retry & Fallback**
If Ollama returns an error or times out, the backend returns an appropriate HTTP error code. The UI displays the error message and a "Try Again" button. No automatic retry — the user decides whether to retry. If the primary model (7B) consistently fails on specific prompt types, the fallback is to switch to 2B for those prompts by updating the backend config.

---

## 9. System Architecture

The system is a two-tier local application. The frontend (Streamlit app or React SPA) runs in the user's browser on the same machine or local network as the backend. The backend is a Python process (Flask or FastAPI if React is chosen; built into Streamlit if Streamlit is chosen) that receives prompt requests, loads template files from the local filesystem, composes the full prompt, calls the Ollama HTTP API on localhost:11434, and returns the generated text to the frontend.

Ollama runs as a separate system process, serving the Gemma model on port 11434. It is started before the application and remains running. The backend never calls any external URL — all communication is localhost-only.

Data persistence is file-based: prompt templates in `/prompts/`, payer reference documents in `/data/payer_references/`, saved user templates in `/data/templates.json`. No database. No background workers. No async job queue. Every request is synchronous: submit → generate → display.

Deployment is a single machine. The application, Ollama, and all data files reside on the same local server. There is no container orchestration, no load balancer, no reverse proxy. In the stretch goal, Docker may be used for packaging, but the runtime architecture remains single-machine.

---

## 10. Data Model / Key Entities

- **Prompt Template** — A text file containing a system prompt with `{variable}` placeholders. Organized by feature in `/prompts/{feature}/`. Key relationship: each denial code maps to one prompt template file. No database representation.
- **Payer Reference** — A plain-text file containing coverage summary information for one dental insurance payer. Stored in `/data/payer_references/`. Key constraint: filename must match the payer name used in the verification form dropdown. No structured schema — raw text injected into prompts.
- **User Template** — A saved output with a user-defined name. Stored as a JSON array in `/data/templates.json`. Fields: `name` (string), `type` (string: "email" | "denial_letter"), `content` (string), `created_at` (ISO timestamp). No unique constraint on name. Soft delete not implemented — delete removes the entry permanently.
- **Denial Code** — A static configuration entry (code string + description). Stored in application config (hardcoded list or config file). The initial set: CO-4, CO-6, CO-16, CO-22, CO-29, CO-45, CO-50, CO-97, CO-109, CO-119.

Full entity details are file-based, not database-backed. See TRD §3 for file format specifications.

---

## 11. API Design

> **Assumed:** If Streamlit is chosen, there is no separate API — Streamlit handles UI and backend logic in a single Python process. The API design below applies only if React (or SvelteKit) is chosen as the UI framework, requiring a separate backend API.

**Base path:** `http://localhost:8000/api`
**Auth:** None (v1)
**Content type:** `application/json`
**No streaming endpoints in v1** — all responses are synchronous JSON.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/generate` | POST | Accepts `{template: string, variables: dict}`, returns `{text: string}` |
| `/api/templates` | GET | Returns array of saved user templates |
| `/api/templates` | POST | Saves a new user template `{name, type, content}` |
| `/api/templates/{index}` | DELETE | Deletes a template by array index |
| `/api/health` | GET | Returns `{status: "ok", model: "gemma:7b"}` if Ollama is reachable |

Full route specifications in TRD §5.

---

## 12. Security & Privacy

**HIPAA Compliance by Architecture**
The primary security control is architectural: the system never connects to the internet during use. No patient data leaves the local machine. This is enforced by design (no outbound HTTP calls in the codebase) and verified by the offline validation test in Week 4.

**Data at Rest**
Patient data entered into forms is ephemeral — it exists only in the browser session and the prompt sent to the local Ollama instance. Generated outputs are displayed to the user but not persisted unless the user explicitly saves them as a template. Saved templates may contain patient-identifiable information if the user saves a generated letter with real patient data — this is a known risk documented in §16.

**No Encryption in v1**
Data files (`templates.json`, payer references) are stored as plain text on the local filesystem. Encryption at rest is not implemented in the PoC. The security assumption is that physical access to the server is restricted to authorized staff.

**Input Sanitization**
User input is passed through Python string formatting into prompt templates. The backend validates that required fields are present and non-empty. No HTML sanitization is needed (outputs are plain text, not rendered as HTML). No SQL injection vector exists (no database).

**Audit Trail (Stretch)**
The stretch-goal audit log records timestamp, feature used, and a summary of the input — but explicitly excludes patient-identifiable data (names, DOB, member IDs). If implemented, the log file is written to `/data/audit.log` and is accessible only via filesystem access.

---

## 13. Non-Functional Requirements

| Requirement | Target | Notes |
|-------------|--------|-------|
| Denial letter generation latency | < 30 seconds from submit to full letter displayed | Measured from button click to rendered text. Degraded = > 45s. Failing = > 60s. Hardware-dependent; benchmark in Week 1 determines if 7B or 2B model is used. |
| Insurance verification latency | < 20 seconds from submit to structured summary | Measured from button click to rendered summary card. Longer prompts (large payer reference files) may increase latency. |
| Email draft latency | < 15 seconds from submit to editable draft | Emails are shorter outputs; should be fastest of the three features. |
| Offline operation | 100% — zero external network calls | Verified by disconnecting network and running all features. Any external call is a critical failure. |
| Uptime / availability | During office hours (8am–6pm), server must be running | Single-machine deployment; no redundancy. If the server is off, the tool is unavailable. |
| Browser support | Chrome 90+, Edge 90+ | Streamlit and React both support these. Safari and Firefox are not tested but likely work. |
| Mobile support | Not required | Front desk staff use desktop workstations. |
| Accessibility | Basic — all form fields labeled, tab navigation works | WCAG AA is a stretch goal, not a v1 requirement. |
| Template library capacity | Supports 100+ saved templates without degradation | JSON file-based storage; performance tested with 100 entries. |
| Concurrent users | 1 (single-user tool) | Ollama handles one inference at a time. Concurrent requests queue. |

---

## 14. Error States & Edge Cases

| Scenario | Behaviour |
|----------|-----------|
| Ollama process not running | Backend returns HTTP 503 "AI model is not running. Please contact your administrator." UI displays error with retry button. |
| Ollama model not pulled | Backend returns HTTP 503 "Model not found. Run `ollama pull gemma:7b` to install." |
| Ollama request timeout (> 60s) | Backend returns HTTP 504 "Model response timed out. Please try again." UI shows timeout message with retry button. |
| Required form fields empty | Client-side validation prevents submission. Missing fields highlighted in red. "Please fill in all required fields." |
| Payer not found in reference data | Backend returns HTTP 422 "No reference data available for this payer." UI suggests contacting administrator to add the payer. |
| Generated letter contains hallucinated data | No automated detection. Relies on staff review. Prompt engineering minimizes risk. Documented as a known limitation. |
| templates.json corrupted or missing | On read failure, backend returns empty template list and logs warning. On write failure, returns HTTP 500 "Could not save template. Check disk space." |
| templates.json exceeds reasonable size (> 1MB) | No automated cleanup. Performance may degrade. Manual file management required. |
| Prompt template file missing | Backend returns HTTP 500 "Template file not found: {path}." Indicates a deployment issue — prompt files not copied to the correct directory. |
| Gemma returns empty or malformed response | Backend returns HTTP 502 "Model returned an unusable response. Please try again." This can occur with very short or ambiguous inputs. |
| Disk full | template save fails with HTTP 500. Ollama may also fail to generate. No automated disk space monitoring. |
| Browser session lost (page refresh) | Current form inputs are lost. Generated output is lost unless saved as a template. No session persistence in v1. |
| Two users submit simultaneously | Ollama queues requests. Second user waits for first inference to complete. No explicit queuing UI — second user sees a long spinner. |

---

## 15. Out of Scope

- Integration with any practice management system (Dentrix, Eaglesoft, Open Dental)
- Integration with any EHR system
- Real patient data — all testing uses synthetic/sample data
- HIPAA certification or formal compliance audit (the architecture satisfies HIPAA data-handling by design, but no formal certification is pursued)
- Multi-practice deployment or multi-tenant architecture
- User accounts, login, or session management
- Cloud hosting, remote access, or VPN-based access
- Automated updates to payer reference data
- OCR or PDF parsing of payer documents (reference text is manually extracted)
- Voice input, speech-to-text, or accessibility beyond basic form labeling
- Billing, payment processing, or claims submission
- Appointment scheduling or calendar integration
- Automated follow-up or notification systems
- Fine-tuning or training the Gemma model on dental-specific data
- Support for languages other than English
- Printing directly from the app (staff use browser print or downloaded files)
- Analytics, reporting, or usage dashboards

---

## 16. Open Questions & Risks

| # | Risk / Question | Severity | Notes |
|---|-----------------|----------|-------|
| 1 | LLM hallucination in denial letters — model invents payer addresses, procedure codes, or coverage terms not in the input | High | Mitigation: system prompt explicitly prohibits fabrication. 5-scenario test suite per feature validates output. Staff are instructed to review all output before use. No automated detection — relies on human review. |
| 2 | Hardware performance — team hardware may not run Gemma 7B at usable speeds (< 30s per response) | High | Mitigation: benchmark in Week 1 before committing. Fallback to Gemma 2B. If neither performs acceptably, project scope is at risk — escalate to sponsor immediately. |
| 3 | Sponsor templates arrive late — Tasha's denial letter templates are needed in Week 1 for prompt engineering | High | Mitigation: escalated at kickoff call. Use placeholder templates to unblock prompt work. If templates are not received by end of Week 1, denial letter feature is delayed by one week. |
| 4 | Patient data in saved templates — users may save generated letters containing real patient names, DOBs, and member IDs to templates.json | Medium | Mitigation: documented as a known risk. Stretch-goal audit log excludes patient data. Production deployment should add encryption at rest and access controls. |
| 5 | Payer reference data accuracy — manually extracted coverage summaries may be outdated or incomplete | Medium | Mitigation: reference data sourced from current payer portal documents. Include "last updated" metadata in each reference file. Staff are trained to verify critical coverage decisions by phone. |
| 6 | Prompt-stuffing context window limits — large payer reference documents may exceed Gemma's context window (8K tokens for 7B) | Medium | Mitigation: keep reference documents under 5 pages of plain text. RAG stretch goal addresses this for larger document sets. |
| 7 | Scope creep — sponsor requests additional features beyond the three agreed modules | Medium | Mitigation: scope locked after Week 1. New requests added to backlog for post-engagement development. Weekly check-ins include explicit scope review. |
| 8 | JSON template storage durability — no backup, no transactions, file corruption loses all saved templates | Low | Mitigation: low risk for PoC with small data volumes. Production deployment should use a proper database. Manual backup procedure documented in runbook. |

---

## 17. Glossary

| Term | Definition |
|------|-----------|
| CO Code | Claim Adjustment Reason Code prefixed with "CO" (Contractual Obligation). Standardized codes used by insurance payers to explain why a claim was denied or adjusted. Examples: CO-45 (exceeds fee schedule), CO-97 (benefit included in another service). |
| Denial Letter | A formal appeal letter sent to an insurance payer contesting a denied claim. Contains patient information, the denial code, the procedure performed, and the appeal rationale. |
| Gemma | Google's open-source large language model, available in 2B and 7B parameter sizes. Runs locally via Ollama. |
| HIPAA | Health Insurance Portability and Accountability Act. Federal law governing the privacy and security of patient health information. Relevant here because patient data entered into the tool must never leave the local machine. |
| Ollama | An open-source tool for running LLMs locally. Provides an HTTP API at localhost:11434 for model inference. |
| Payer | An insurance company that provides dental coverage. Examples: Delta Dental, Cigna, Aetna. |
| Payer Reference | A plain-text document summarizing a payer's coverage terms, benefit structures, and limitations. Used as context for insurance verification prompts. |
| Prior Authorization | Approval required from the insurance payer before a procedure can be performed and covered. Some procedures require prior auth; others do not. |
| Prompt-Stuffing | A technique where reference text is injected directly into the LLM prompt as context, rather than using a vector database for retrieval. Simpler than RAG but limited by the model's context window size. |
| RAG | Retrieval-Augmented Generation. A technique that embeds documents into a vector database (e.g., ChromaDB) and retrieves relevant chunks per query before sending them to the LLM. More scalable than prompt-stuffing for large document sets. |
| Streamlit | A Python framework for building data apps with minimal frontend code. Runs as a single Python process serving a web UI. |
| Template Library | A feature allowing users to save, name, and reload generated outputs (emails or letters) for reuse. Stored as JSON on the local filesystem. |
