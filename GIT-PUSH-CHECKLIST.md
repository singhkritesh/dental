# Git Push Checklist

Last updated: 2026-05-26

Use this checklist before any push to keep deployability and runtime behavior stable.

## 1) Validate the workspace

```bash
python3 -m compileall app.py api services
cd frontend && npm run build && cd ..
docker compose ps
```

Expected:
- Python compile succeeds with no errors
- Frontend typecheck + build succeed
- `api`, `frontend`, `db` containers are `Up` (if using Docker runtime)

## 2) Validate key runtime endpoints

```bash
curl -sS http://127.0.0.1:8000/
curl -sS http://127.0.0.1:8000/api/auth/bootstrap
curl -sS -I http://127.0.0.1:3000/
```

Expected:
- API root returns service status JSON
- auth bootstrap returns JSON payload
- frontend returns `HTTP/1.1 200 OK`

## 3) Confirm current email-thread scope

Before push, ensure docs and release notes reflect:
- Implemented: manual thread paste/upload analysis + draft generation
- Not implemented: mailbox-native sync, real-time inbox listeners, outbound send integration

## 4) Git readiness

If repository is already initialized:

```bash
git status
git add -A
git commit -m "docs: clarify email-thread scope and mailbox roadmap"
git push
```

If this directory is not currently a git repository:

```bash
git init
git remote add origin <your-repo-url>
git add -A
git commit -m "initial import: siligent dental ai"
git branch -M main
git push -u origin main
```
