# Development Learnings — Siligent Dental AI Assistant

**Date:** 2026-05-03  
**Perspective:** Product Management + Engineering

## 1) Product Learnings

1. The biggest UX failure mode was not model quality, it was workflow friction.
2. Users needed one clear drafting flow more than multiple overlapping tools.
3. Upload-first gating created unnecessary drop-off; template-first drafting had to be supported.
4. Non-technical users do better with explicit step labels and visible progress, not dense forms.
5. Canonical templates by purpose type reduced confusion and configuration drift.
6. Role clarity in outputs is mandatory: provider voice had to be enforced, not implied.
7. “Smart” features must still explain intent in plain language to build trust.
8. Real-world usage is iterative editing, not one-shot generation; editable outputs are essential.
9. “Open in workspace” from template library is a critical bridge for adoption.
10. Operational transparency (model in use, running status, recoverable tasks) matters as much as draft quality.

## 2) UX Learnings

1. Tab switching and route switching cannot reset in-progress work.
2. Background generation must survive navigation and visibly rehydrate when users return.
3. Library browsing needed card/list selection and filtering, not only dropdown selection.
4. “Save edited copy” language conflicted with canonical-template behavior and caused mental mismatch.
5. Non-admin users needed clear read-only boundaries to prevent accidental destructive edits.
6. Explicit “unsaved changes” indicators and “revert” controls prevent silent data loss.
7. Prompting users with “what this upload is used for” improved confidence and reduced confusion.

## 3) AI/Prompt Learnings

1. Prompt quality alone is insufficient; output guardrails and structural validation are required.
2. Role drift happens frequently unless identity is explicitly locked in prompts and rewrite passes.
3. Missing-field hallucination is common in appointment-style outputs unless forced fallback rules exist.
4. “Use Not provided” must be enforced both in prompt policy and post-processing logic.
5. Prompt registry centralization significantly reduced maintenance overhead and inconsistency risk.
6. Purpose-specific templates outperform generic prompts for reliability in dental admin workflows.

## 4) Architecture Learnings

1. FastAPI + React + Docker + Postgres/pgvector was the right production-leaning baseline.
2. Host Ollama (not containerized Ollama) simplified local model ownership and reduced duplication.
3. Model keep-alive/offload behavior is an operational requirement, not an optimization detail.
4. Postgres schema + pgvector reranking improved relevance and future-proofed retrieval/ranking paths.
5. File-backed fallback stores were useful for resilience and migration safety.
6. Startup seeding for defaults is essential for first-run usability and admin onboarding.

## 5) Data and Template Model Learnings

1. One-template-per-purpose globally is easier for operations than many near-duplicates.
2. Enforcing canonical upsert semantics at storage layer avoids UI-only policy drift.
3. Startup normalization/dedup is required to clean historic data inconsistencies.
4. Template type governance must be explicit (admin control, scoped additions, clear naming).

## 6) Operational Learnings

1. Rebuild discipline matters: code changes without container rebuilds caused stale behavior confusion.
2. Port ownership must be explicit and documented; implicit defaults created avoidable conflicts.
3. Health checks should include auth/bootstrap-aware probes, not only legacy unauthenticated routes.
4. “Working but not visible” failures need clear UI indicators and status banners.
5. Scripted start/stop controls (`start.sh` / `stop.sh`) are mandatory for repeatable operator workflows.

## 7) Reliability Learnings

1. Background task state should be global and recoverable across pages.
2. Session persistence should store non-file inputs to minimize lost work.
3. API validation should allow valid low-friction flows (template/runtime-only) and block only empty intent.
4. Guardrails need deterministic fallback outputs for safety-critical cases (e.g., appointment confirmations).

## 8) What Worked Well

1. Moving prompts into dedicated files with explicit usage mapping.
2. Adding structured output stabilization + repair pass for weak drafts.
3. Implementing canonical template policy in storage layer (not just UI policy).
4. Adopting Docker-based deployment with host Ollama integration.
5. Continuous UX tightening based on observed failure points.

## 9) What We Would Do Earlier Next Time

1. Define canonical data/template rules before building library UI.
2. Lock role identity and anti-hallucination policies in week 1 prompts.
3. Build navigation-safe task persistence before feature expansion.
4. Introduce a “single source of truth” operations doc from day 1.
5. Add automated regression tests around template policy and draft safety outputs earlier.

## 10) Next-Phase Recommendations

1. Add mailbox connectors (Gmail/Outlook/Exchange) with human-in-the-loop reply workflows.
2. Add stronger evaluation harness:
   - Role compliance checks
   - Hallucination checks for key fields
   - Template conformance scoring
3. Add admin analytics:
   - Draft acceptance rate
   - Edit distance after generation
   - Purpose-type usage and turnaround time
4. Add structured policy packs by use case (billing, insurance, scheduling).
5. Add onboarding mode with guided examples for non-technical administrative users.

## 11) Bottom Line

The most important lesson: **production readiness for this product is mostly about workflow reliability, role-consistent communication, and operational predictability**. Better prompts help, but adoption depended on reducing UI friction, enforcing canonical template behavior, and hardening state/validation/guardrails end to end.

