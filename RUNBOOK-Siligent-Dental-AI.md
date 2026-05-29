---
last_updated: "2026-05-26"
stack: "Python 3.11+ · Ollama (local) · FastAPI · React · PostgreSQL/pgvector + local uploads"
status: "Draft"
---

# RUNBOOK — Siligent Dental AI Assistant

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Local Development Setup](#2-local-development-setup)
3. [Environment Configuration](#3-environment-configuration)
4. [Running the Stack](#4-running-the-stack)
5. [Deployment](#5-deployment)
6. [Health Checks & Monitoring](#6-health-checks--monitoring)
7. [Failure Playbook](#7-failure-playbook)
8. [Backup & Recovery](#8-backup--recovery)
9. [Common Tasks](#9-common-tasks)
10. [Onboarding Checklist](#10-onboarding-checklist)

---

## Current Operations Snapshot (Authoritative)

Use this snapshot as the source of truth for current operations:

- Primary runtime mode is Docker Compose:
  - `frontend` on `:3000`
  - `api` on `:8000`
  - `db` (PostgreSQL/pgvector) on `:5434`
- Ollama runs on host machine (not in Docker) and is accessed from API via `host.docker.internal:11434`.
- Default model is `qwen3.5:4b` unless overridden in `.env`.
- Some legacy command examples below still reference `gemma:*`; treat those as historical and substitute your active model (default `qwen3.5:4b`).
- Canonical template model is enforced: one template per purpose type globally.
- API startup auto-seeds missing default shared templates per purpose type.
- Smart Composer supports optional uploads; template/runtime-only generation is valid.
- Email thread workflow is manual-only (paste/upload thread content). Mailbox-native sync and real-time inbox listeners are not active in current runtime.

When this runbook contains legacy Streamlit/file-only instructions, prefer this snapshot and current repository scripts.

---

## 1. Prerequisites

| Tool | Version | Purpose | Install | Verify |
|------|---------|---------|---------|--------|
| Python | ≥ 3.11 | Backend runtime | https://python.org/downloads/ or `sudo apt install python3.11` | `python3 --version` → `Python 3.11.x` |
| pip | ≥ 23.0 | Python package manager | Bundled with Python | `pip --version` → `pip 23.x` |
| Ollama | Latest | Local LLM server | https://ollama.com/download | `ollama --version` → `ollama version 0.x.x` |
| Git | ≥ 2.30 | Version control | `sudo apt install git` | `git --version` → `git version 2.x` |
| Node.js | ≥ 18 | React frontend (React path only) | https://nodejs.org/ | `node --version` → `v18.x` or higher |
| npm | ≥ 9 | JS package manager (React path only) | Bundled with Node.js | `npm --version` → `9.x` |

**Hardware requirements:**
- RAM: 8 GB minimum (16 GB recommended for Gemma 7B)
- Disk: 10 GB free (Gemma 7B model is ~4.5 GB)
- GPU: Optional but dramatically improves inference speed. NVIDIA GPU with CUDA support preferred.

Verify GPU access for Ollama:
```bash
ollama run gemma:2b "Say hello" 
# Should respond in < 10 seconds on GPU, < 30 seconds on CPU
```

---

## 2. Local Development Setup

### Step 1: Clone the repository

```bash
git clone https://github.com/siligent/dental-ai-assistant.git
cd dental-ai-assistant
```

### Step 2: Install Ollama and pull the model

```bash
# Install Ollama (Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama (runs in background)
ollama serve &

# Pull the Gemma model (this downloads ~4.5 GB for 7B)
ollama pull qwen3.5:4b

# Verify the model is available
ollama list
# Should show: qwen3.5:4b    <hash>    <size>
```

### Step 3: Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Set up environment

```bash
cp .env.example .env
# Edit .env — the defaults should work for local development:
#   OLLAMA_URL=http://localhost:11434
#   MODEL_NAME=gemma:7b
#   PROMPTS_DIR=./prompts
#   DATA_DIR=./data
```

### Step 5: Initialize data directory

```bash
# Ensure data directories exist
mkdir -p data/payer_references

# Create empty templates file if it doesn't exist
[ -f data/templates.json ] || echo '[]' > data/templates.json
```

### Step 6: Add payer reference data

Copy payer reference text files to `data/payer_references/`. Each file should be named to match the payer dropdown value (lowercased, spaces to underscores):
- `delta_dental.txt`
- `cigna.txt`
- `aetna.txt`

### Step 7: Verify prompt templates exist

```bash
ls prompts/denial_letters/
# Should show: CO-4.txt CO-6.txt CO-16.txt CO-22.txt CO-29.txt
#              CO-45.txt CO-50.txt CO-97.txt CO-109.txt CO-119.txt

ls prompts/emails/
# Should show: 8 .txt files (one per email scenario)

ls prompts/insurance_verification.txt
# Should show the file exists

ls prompts/document_pipeline/repair_final_draft.txt
# Should show the file exists (used by final-draft auto-repair)

python3 - <<'PY'
from pathlib import Path
from services.prompt_registry import (
    EMAIL_SCENARIO_PROMPTS,
    DOCUMENT_PIPELINE_PROMPTS,
    EMAIL_THREAD_PROMPTS,
    INSURANCE_VERIFICATION_PROMPT,
)
base = Path("prompts")
missing = []
for rel in EMAIL_SCENARIO_PROMPTS.values():
    if not (base / f"{rel}.txt").exists():
        missing.append(rel)
for rel in DOCUMENT_PIPELINE_PROMPTS.values():
    if not (base / f"{rel}.txt").exists():
        missing.append(rel)
for rel in EMAIL_THREAD_PROMPTS.values():
    if not (base / f"{rel}.txt").exists():
        missing.append(rel)
if not (base / f"{INSURANCE_VERIFICATION_PROMPT}.txt").exists():
    missing.append(INSURANCE_VERIFICATION_PROMPT)
print("OK: prompt registry mappings resolve to files" if not missing else f"MISSING: {missing}")
PY
```

### Step 8: Start the application

Preferred (current):
```bash
./start.sh
```

Stop:
```bash
./stop.sh
```

Direct compose alternative:
```bash
docker compose up -d --build
docker compose ps
```

Legacy direct Python/React dev mode (optional):

**React path:**
```bash
# Terminal 1: Backend
uvicorn api.main:app --host 0.0.0.0 --port 8000
# Should print: Running on http://localhost:8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev
# Should print: Local: http://localhost:3000
```

### Step 9: Verify it works

1. Open `http://localhost:3000` in Chrome
2. Navigate to "Denial Letters"
3. Select CO-45 from the dropdown
4. Enter: Patient Name = "Test Patient", DOS = today's date, Procedure = "Crown D2740", Payer = "Delta Dental"
5. Click Generate
6. **You know it worked when:** A formatted denial appeal letter appears in the output area within 30 seconds, containing the patient name and denial code you entered.

---

## 3. Environment Configuration

### Backend / Streamlit

| Variable | Required | Description | Example | Notes |
|----------|----------|-------------|---------|-------|
| `OLLAMA_URL` | Yes | Ollama API base URL | `http://localhost:11434` | Do not include trailing slash |
| `MODEL_NAME` | Yes | Ollama model to use | `qwen3.5:4b` | Can be set to any local model available in Ollama |
| `PROMPTS_DIR` | Yes | Path to prompt templates | `./prompts` | Relative to app.py or absolute path |
| `DATA_DIR` | Yes | Path to data directory | `./data` | Contains payer_references/ and templates.json |

### React Frontend (React path only)

| Variable | Required | Description | Example | Notes |
|----------|----------|-------------|---------|-------|
| `VITE_API_URL` | Yes | Backend API base URL | `http://localhost:8000/api` | Must include `/api` suffix. Set in `.env` in `/frontend/` directory. |

### Ollama

| Variable | Required | Description | Example | Notes |
|----------|----------|-------------|---------|-------|
| `OLLAMA_HOST` | No | Bind address | `0.0.0.0` | Default is `127.0.0.1`. Only change if other machines on LAN need direct Ollama access. |
| `OLLAMA_MODELS` | No | Custom model storage path | `/opt/ollama/models` | Default is `~/.ollama/models`. Change if disk space is limited on home partition. |

---

## 4. Running the Stack

### Local Development

**Start (React):**
```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: Backend
source venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000

# Terminal 3: Frontend
cd frontend && npm run dev
```

**Stop:**
```bash
# Stop backend/frontend dev processes: Ctrl+C in terminal
# Stop Ollama:
pkill ollama
# Or if running as systemd service:
sudo systemctl stop ollama
```

**Verify it started:**
- Ollama: `curl http://localhost:11434/api/tags` → returns JSON with model list
- Backend: `curl http://localhost:8000/api/health` (authenticated route behavior depends on auth mode; use `/api/auth/bootstrap` for unauthenticated check)
- React: Open `http://localhost:3000` → page loads

**Tail logs:**
```bash
# Ollama logs (systemd)
journalctl -u ollama -f

# Ollama logs (manual start)
# Ollama logs to stdout — check the terminal where you ran `ollama serve`

# Python backend/Streamlit
# Logs to stdout — check the terminal where you started the app
```

**Restart one service:**
```bash
# Restart just Ollama (without touching the app)
pkill ollama && sleep 2 && ollama serve &

# Restart just the backend (without touching Ollama)
# Ctrl+C the Python process, then re-run:
python app.py
```

---

## 5. Deployment

### First Deploy (New Machine)

1. Install prerequisites (see §1).
2. Clone the repo:
   ```bash
   git clone https://github.com/siligent/dental-ai-assistant.git
   cd dental-ai-assistant
   ```
3. Install and start Ollama:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ollama serve &
   ollama pull gemma:7b
   ```
4. Install Python deps:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
5. Copy `.env.example` to `.env`, edit if needed.
6. Create data directories and `templates.json`:
   ```bash
   mkdir -p data/payer_references
   echo '[]' > data/templates.json
   ```
7. Copy payer reference files to `data/payer_references/`.
8. Start the app (see §4).
9. Run the 5-minute health check (see §6).

### Subsequent Updates

```bash
cd dental-ai-assistant
git pull origin main
source venv/bin/activate
pip install -r requirements.txt  # In case deps changed
# Restart the app (Ctrl+C, re-run start command)
```

⚠️ `git pull` does not modify `data/templates.json` or `data/payer_references/` — user data is preserved. But always verify after pulling.

### Rollback

```bash
git log --oneline -5          # Find the previous good commit
git checkout <commit-hash>    # Roll back
# Restart the app
```

### Post-Deploy Verification

1. Open the app in browser
2. Generate one denial letter (CO-45, test data)
3. Generate one insurance verification (any payer with reference data)
4. Generate one email (appointment reminder)
5. Save a template, refresh, verify it persists
6. Confirm all three features complete without errors

---

## 6. Health Checks & Monitoring

Prompt routing health check:
```bash
curl -s http://localhost:8000/api/email-scenarios
# Expected: JSON array of scenario labels served from prompt registry mapping.
```

### 5-Minute Health Check

Run this when something first seems wrong, before diving into the failure playbook:

1. **Is Ollama running?**
   ```bash
   curl -s http://localhost:11434/api/tags | python3 -m json.tool
   ```
   Expected: JSON with `"models"` array containing `gemma:7b`. If connection refused → Ollama is not running.

2. **Is the model loaded?**
   ```bash
   curl -s http://localhost:11434/api/tags | grep -o '"name":"[^"]*"'
   ```
   Expected: `"name":"gemma:7b"`. If empty → model not pulled.

3. **Does the model respond?**
   ```bash
   curl -s http://localhost:11434/api/generate \
     -d '{"model":"gemma:7b","prompt":"Say hello","stream":false}' \
     | python3 -c "import sys,json; print(json.load(sys.stdin)['response'][:100])"
   ```
   Expected: A greeting response within 30 seconds. If timeout → model loading issue or resource starvation.

4. **Is the backend/app running?**
   - Streamlit: `curl -s http://localhost:8501` → HTML response
   - React backend: `curl -s http://localhost:8000/api/health` → `{"status": "ok"}`

5. **Are data files accessible?**
   ```bash
   ls -la data/templates.json
   ls data/payer_references/
   ls prompts/denial_letters/
   ```
   Expected: Files exist and are readable.

### NFR Monitoring

| What to Check | Healthy | Degraded | Failing |
|----------------|---------|----------|---------|
| Denial letter generation time | < 30s | 30–45s | > 60s or timeout |
| Verification generation time | < 20s | 20–40s | > 60s or timeout |
| Email generation time | < 15s | 15–30s | > 60s or timeout |
| Ollama API response | < 1s for `/api/tags` | 1–5s | > 5s or unreachable |
| templates.json file size | < 500KB | 500KB–1MB | > 1MB (manual cleanup needed) |
| Disk free space | > 5GB | 1–5GB | < 1GB (Ollama may fail) |

Check disk space:
```bash
df -h /home
df -h $(dirname $(ollama list 2>/dev/null | tail -1 | awk '{print $NF}') 2>/dev/null || echo ~/.ollama)
```

---

## 7. Failure Playbook

### Ollama process not running

**Symptoms:** UI shows "AI model is not running." Backend returns HTTP 503. `curl localhost:11434` returns "Connection refused."

**Likely cause:** Ollama was never started, or it crashed (OOM, signal, system restart).

**Diagnosis:**
```bash
curl -s http://localhost:11434/api/tags
# Connection refused = not running

pgrep -a ollama
# Empty = not running

journalctl -u ollama --no-pager -n 20
# Check for crash logs if running as systemd service
```

**Fix:**
1. Start Ollama: `ollama serve &` (or `sudo systemctl start ollama`)
2. Verify: `curl http://localhost:11434/api/tags`
3. If it crashes immediately, check system memory: `free -h`
4. If OOM: close other applications, or switch to `gemma:2b`

**Prevention:** Run Ollama as a systemd service so it restarts automatically:
```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

---

### Ollama model not pulled

**Symptoms:** Backend returns HTTP 503 "Model not found." Ollama is running but `/api/generate` returns error about missing model.

**Likely cause:** First deployment, model was never downloaded. Or model was deleted.

**Diagnosis:**
```bash
ollama list
# Should show gemma:7b. If empty or missing, model not pulled.
```

**Fix:**
1. Pull the model: `ollama pull gemma:7b`
2. Wait for download (~4.5 GB for 7B)
3. Verify: `ollama list` shows `gemma:7b`
4. Restart the app

---

### Ollama request timeout

**Symptoms:** UI shows "Model response timed out. Please try again." Backend returns HTTP 504. The spinner runs for 60+ seconds.

**Likely cause:** Model loading into memory on first request (cold start). Very long prompt (large payer reference file). CPU-only inference on a slow machine. System under heavy load.

**Diagnosis:**
```bash
# Check system resources
top -bn1 | head -20
free -h
nvidia-smi  # If GPU is available

# Test with a minimal prompt
time curl -s http://localhost:11434/api/generate \
  -d '{"model":"gemma:7b","prompt":"Hello","stream":false}' > /dev/null
# First call may be slow (model loading). Second call should be faster.
```

**Fix:**
1. If first request after boot: wait — model is loading into memory. Retry after 30 seconds.
2. If consistently slow: switch to `gemma:2b` (update `MODEL_NAME` in `.env`, restart app).
3. If system memory is low: close other applications, check with `free -h`.
4. If payer reference file is very large: trim the reference text to essential coverage information only.

---

### Required form fields empty (client-side)

**Symptoms:** Form won't submit. Required fields highlighted in red. Message: "Please fill in all required fields."

**Likely cause:** User forgot to fill in a required field. Normal behavior, not an error.

**Diagnosis:** Visual — check which fields are highlighted.

**Fix:** Fill in the highlighted fields and resubmit.

---

### Payer not found in reference data

**Symptoms:** Insurance verification returns "No reference data available for this payer."

**Likely cause:** No reference file exists for the selected payer in `data/payer_references/`.

**Diagnosis:**
```bash
ls data/payer_references/
# Check if a file exists for the payer
# Remember: "Delta Dental" → delta_dental.txt
```

**Fix:**
1. Obtain the payer's coverage summary document
2. Extract text content
3. Save to `data/payer_references/{payer_name_lowercase}.txt` (spaces → underscores)
4. Restart the app (Streamlit) or the payer should appear on next request (React)

---

### templates.json corrupted or missing

**Symptoms:** Template list is empty when it shouldn't be, or template save fails with HTTP 500.

**Likely cause:** File was deleted, or a previous write was interrupted (power loss, force-kill during save).

**Diagnosis:**
```bash
cat data/templates.json
# Should be valid JSON. If it shows garbage, truncation, or is missing:

python3 -c "import json; json.load(open('data/templates.json'))"
# JSONDecodeError = corrupted
```

**Fix (corrupted):**
1. Check if a `.json.tmp` file exists (from atomic write): `ls data/*.tmp`
2. If temp file exists and is valid JSON: `mv data/templates.json.tmp data/templates.json`
3. If no backup: `echo '[]' > data/templates.json` (starts fresh — saved templates are lost)

**Fix (missing):**
```bash
echo '[]' > data/templates.json
```

---

### Prompt template file missing

**Symptoms:** Backend returns HTTP 500 "Template file not found: {path}."

**Likely cause:** Incomplete deployment — prompt files not copied to the correct directory. Or a new denial code was added to the frontend dropdown without creating its prompt file.

**Diagnosis:**
```bash
# Check if the specific file exists
ls -la prompts/denial_letters/CO-45.txt

# Check all expected files
for code in CO-4 CO-6 CO-16 CO-22 CO-29 CO-45 CO-50 CO-97 CO-109 CO-119; do
  [ -f "prompts/denial_letters/${code}.txt" ] && echo "OK: ${code}" || echo "MISSING: ${code}"
done
```

**Fix:**
1. Check git status: `git status prompts/`
2. If files are in the repo but not on disk: `git checkout -- prompts/`
3. If files were never created: write the prompt template (see TRD §3 for template format)

### Draft output is summary-like or not a professional letter/email

**Symptoms:** Generated draft contains bullets only, generic summary text, or lacks required letter/email structure.

**Likely cause:** Model output quality drift or prompt mismatch.

**Checks:**
1. Confirm repair prompt exists:
   ```bash
   ls -la prompts/document_pipeline/repair_final_draft.txt
   ```
2. Confirm registry mapping includes repair key:
   ```bash
   rg -n "repair_final_draft" services/prompt_registry.py
   ```
3. Re-run mapping verification script from §2 Step 7.

**Resolution:**
1. Ensure `services/prompt_registry.py` points to the correct prompt path.
2. Refine the relevant prompt text file in `prompts/document_pipeline/`.
3. Restart API service and retest.

---

### Gemma returns empty or malformed response

**Symptoms:** Backend returns HTTP 502 "Model returned an unusable response."

**Likely cause:** Very short or ambiguous input. Model context window exceeded. Model loaded but not warmed up.

**Diagnosis:**
```bash
# Test directly with Ollama
curl -s http://localhost:11434/api/generate \
  -d '{"model":"gemma:7b","prompt":"Write a short greeting","stream":false}' \
  | python3 -m json.tool
# Check if "response" field is empty or contains error
```

**Fix:**
1. Retry — the issue may be transient (model not fully loaded).
2. If consistent: check the prompt template for issues (see §9 Common Tasks: debugging prompts).
3. If the response field is empty: the model may be corrupted. Re-pull: `ollama rm gemma:7b && ollama pull gemma:7b`

---

### Disk full

**Symptoms:** Template save fails. Ollama may also fail silently or crash. System becomes sluggish.

**Likely cause:** Ollama model files, log files, or system data consuming available space.

**Diagnosis:**
```bash
df -h /
du -sh ~/.ollama/models
du -sh data/
```

**Fix:**
1. Clear old Ollama models: `ollama rm <unused-model-name>`
2. Clear system temp files: `sudo apt clean` (Ubuntu)
3. If templates.json is unexpectedly large: inspect and prune old templates
4. Move Ollama model storage to a larger partition: set `OLLAMA_MODELS=/path/to/larger/disk`

---

### Service won't start — port conflict

**Symptoms:** "Address already in use" error on startup.

**Diagnosis:**
```bash
# Check what's using the port
lsof -i :8501   # Streamlit
lsof -i :8000   # Backend
lsof -i :11434  # Ollama
```

**Fix:**
1. Kill the conflicting process: `kill <PID>` (get PID from `lsof` output)
2. Or change the port: `streamlit run app.py --server.port 8502`

---

### Two users submit simultaneously

**Symptoms:** Second user sees a very long spinner (waiting for first inference to finish). No error — just slow.

**Likely cause:** Ollama processes one request at a time. The second request is queued.

**Diagnosis:** Expected behavior in v1 (single-user tool). Not a bug.

**Fix:** Wait. The second request will complete after the first finishes. If this becomes frequent, it indicates the tool needs multi-instance Ollama or a request queue — out of scope for v1.

---

## 8. Backup & Recovery

### Current State: No Automated Backup

There is no automated backup strategy for this PoC. This is a known risk (see PRD §16 risk #8).

### What Data Exists and Where

| Data | Location | Criticality | Changes? |
|------|----------|-------------|----------|
| User-saved templates | `data/templates.json` | Medium — user-created, hard to recreate | Yes, every time a user saves/deletes |
| Payer reference docs | `data/payer_references/*.txt` | High — manually curated | Rarely |
| Prompt templates | `prompts/**/*.txt` | High — engineering effort to create | Version-controlled in git |
| Application code | Repo root | High | Version-controlled in git |
| Ollama model weights | `~/.ollama/models/` | Low — can be re-downloaded | Never (after pull) |

### Manual Backup Procedure

```bash
# Create a timestamped backup of user data
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp data/templates.json "$BACKUP_DIR/"
cp -r data/payer_references/ "$BACKUP_DIR/"
echo "Backup created at $BACKUP_DIR"
```

Run this weekly or before any deployment update.

### Restore Procedure

```bash
# List available backups
ls -lt backups/

# Restore from a specific backup
cp backups/20260422_100000/templates.json data/templates.json
cp -r backups/20260422_100000/payer_references/ data/payer_references/

# Restart the app to pick up restored data
```

### RTO / RPO

Not formally defined. For a PoC with < 100 templates and 3 payer reference files, a full manual restore takes under 5 minutes if a backup exists. If no backup exists, templates are permanently lost; payer references can be re-created from source documents in 30–60 minutes.

---

## 9. Common Tasks

### Add a new payer for insurance verification

1. Obtain the payer's coverage summary document (PDF or web page).
2. Extract the relevant text — covered procedures, co-pay schedules, prior auth requirements, exclusions.
3. Save as a plain text file:
   ```bash
   # Payer name: "United Healthcare" → filename: united_healthcare.txt
   nano data/payer_references/united_healthcare.txt
   # Paste the extracted text, save
   ```
4. If using a dropdown (React path), add the payer name to the dropdown options in the frontend code.
5. Restart the app (Streamlit) or refresh the page (React).
6. Test: run a verification query for the new payer and confirm the summary references the correct document.

### Add a new denial code

1. Write a prompt template for the new code:
   ```bash
   cp prompts/denial_letters/CO-45.txt prompts/denial_letters/CO-NEW.txt
   nano prompts/denial_letters/CO-NEW.txt
   # Update the denial code description and appeal rationale
   ```
2. Add the code to the `DENIAL_CODES` list in the backend/frontend code.
3. Restart the app.
4. Test: generate a letter with the new code and verify output quality.

### Debug a prompt that produces poor output

1. Test the prompt directly with Ollama (bypass the app):
   ```bash
   curl -s http://localhost:11434/api/generate \
     -d '{
       "model": "gemma:7b",
       "prompt": "'"$(cat prompts/denial_letters/CO-45.txt | sed 's/{patient_name}/Test Patient/g; s/{date_of_service}/2026-04-22/g; s/{procedure_description}/Crown D2740/g; s/{procedure_code}/D2740/g; s/{payer_name}/Delta Dental/g; s/{payer_address}/123 Main St/g; s/{provider_name}/Dr Smith/g; s/{provider_npi}/1234567890/g')"'",
       "stream": false,
       "options": {"temperature": 0.3}
     }' | python3 -c "import sys,json; print(json.load(sys.stdin)['response'])"
   ```
2. Read the output. Identify where the model deviates from the expected template.
3. Edit the prompt file to add stronger constraints where needed.
4. Re-test until output is acceptable.
5. Commit the updated prompt: `git add prompts/ && git commit -m "Refine CO-45 prompt"`

### Clear a corrupted templates.json

```bash
# Back up the corrupted file first
cp data/templates.json data/templates.json.corrupted

# Reset to empty
echo '[]' > data/templates.json

# If the corrupted file has some valid JSON at the start, try to salvage:
python3 -c "
import json
with open('data/templates.json.corrupted') as f:
    content = f.read()
# Try parsing progressively shorter substrings
for i in range(len(content), 0, -1):
    try:
        data = json.loads(content[:i])
        if isinstance(data, list):
            with open('data/templates.json', 'w') as out:
                json.dump(data, out, indent=2)
            print(f'Salvaged {len(data)} templates')
            break
    except:
        pass
"
```

### Switch from Gemma 7B to 2B (or vice versa)

1. Pull the target model: `ollama pull gemma:2b`
2. Update `.env`: set `MODEL_NAME=gemma:2b`
3. Restart the app.
4. Test all three features to verify output quality is acceptable.
5. (Optional) Remove the old model to free disk space: `ollama rm gemma:7b`

---

## 10. Onboarding Checklist

A new developer completing this checklist should have a running local environment and enough context to make their first contribution.

- [ ] All prerequisites installed and verified (§1 — run all verify commands)
- [ ] Repo cloned: `git clone https://github.com/siligent/dental-ai-assistant.git`
- [ ] Python venv created and dependencies installed: `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- [ ] Ollama installed, running, and Gemma model pulled: `ollama list` shows `gemma:7b`
- [ ] `.env` configured from `.env.example`
- [ ] Data directories exist: `data/payer_references/` has at least one payer file, `data/templates.json` exists
- [ ] Prompt templates exist: all 10 denial code files + verification prompt + 8 email prompts
- [ ] App starts without errors (Streamlit on :8501 or Backend on :8000 + React on :3000)
- [ ] Can generate a denial letter (CO-45 with test data) — letter appears within 30 seconds
- [ ] Can run insurance verification (any payer with reference data) — summary appears
- [ ] Can generate an email (appointment reminder) — draft appears
- [ ] Can save a template, refresh the page, and see it in the template list
- [ ] Read PRD §1–6 (problem, personas, scope, functional requirements)
- [ ] Read TRD §9 (AI coding guardrails) — **before writing any code**
- [ ] Ran the 5-minute health check (§6) — all checks pass
- [ ] Made a small change (e.g., edited a prompt file, restarted, verified the change appears in output)
