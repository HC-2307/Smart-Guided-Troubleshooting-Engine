# My Development Notes

This file records my learning and AI-assisted development during the Samsung PRISM hackathon.

It is also used as a reference when preparing the Samsung AI disclosure.

---

# Development Log

## 2026-09-20 — Basic M3 backend skeleton end-to-end

### Goal

Get the M3-owned slice (API, orchestration, cache, final validation, Docker)
working end to end and schema-conformant, on top of the existing skeleton
(schemas, validator, stub services already in the repo).

### Tool

- Claude Code

### Prompt / Request

Asked to "start building the basic thing that Samsung requires" for this
branch's role, with files added and commits made as the work progressed.
Follow-up asked to add `docs/architechture.md` to `.gitignore` and remove
any `.gitignore` entries pointing at files that don't exist in the repo.

### AI assistance

Reviewed the existing skeleton against the Theme 2 schema contract in
CLAUDE.md and found several issues:

- API was mounted at `/api/v1` instead of the graded contract's `/v1` —
  would have failed grading silently since it still "worked" locally.
- `.gitignore` had a blanket `docs/` rule that would have silently excluded
  the AI disclosure log (this file) from version control.
- `troubleshooting_engine.py` returned a shape that would fail
  `TroubleshootResponse` validation entirely.
- `cache.py` was an empty stub with no code.
- `.gitignore` also listed `myNotes.txt`, which doesn't exist (the real
  file is `docs/myNotes.md`).

AI implemented:

- `backend/main.py` — fixed route prefix to `/v1`.
- `backend/schemas/troubleshoot.py` — added the `fallback` field required
  by the no-match/validation-failure contract.
- `backend/services/cache.py` — basic in-memory cache, keyed on a
  normalized (lowercased, whitespace-collapsed) query string, with a TTL.
  Noted inline that this still needs semantic (embedding) keying to hit
  the graded 80% hit-rate target on paraphrased queries — exact-string
  normalization won't get there.
- `backend/services/orchestrator.py` — wired the pipeline as
  cache lookup -> plan generation -> URL-leak validation gate -> cache
  store -> return. A response that fails the URL-leak check never reaches
  the client; it's replaced with `{contexts: [], fallback: "validation_failed"}`.
- `backend/services/troubleshooting_engine.py` — replaced the broken stub
  with a schema-conformant placeholder plan (battery example) so the API
  is runnable end to end pending real LLM planning (M1) and catalog
  matching (M2).
- `tests/test_api.py` — integration tests hitting the live API
  (`/health`, `/v1/troubleshoot`) checking schema phrasing and zero URL
  leakage, not just the validator unit in isolation.
- `requirements.txt` — added `httpx` and `pytest` (needed for
  `TestClient`/running tests).
- `Dockerfile` / `docker-compose.yml` — were empty placeholders; filled in
  a basic Python slim image + uvicorn setup and a compose service with a
  health check.
- `.gitignore` — narrowed `docs/` to `docs/samsung/` (keeps this file
  tracked, still excludes the large official hackathon PDFs/docx), later
  added `docs/architechture.md` (was untracked, now intentionally
  ignored), and removed the stale `myNotes.txt` entry.

### My changes / verification

Ran the orchestrator locally to confirm end-to-end output matches the
schema (goal/title/score/actions/stepGroups/category), confirmed cache
normalization works across whitespace/case variants, and ran
`pytest tests/test_api.py` (3 passed). Did **not** verify the Docker
build — Docker Desktop wasn't running locally, so that still needs a
manual `docker build` check before relying on it.

### Files affected

- `backend/main.py`
- `backend/schemas/troubleshoot.py`
- `backend/services/cache.py`
- `backend/services/orchestrator.py`
- `backend/services/troubleshooting_engine.py`
- `tests/test_api.py`
- `requirements.txt`
- `Dockerfile`
- `docker-compose.yml`
- `.gitignore`

### What I learned

The API prefix mismatch (`/api/v1` vs `/v1`) would have failed grading
silently since it still "worked" locally — always check the literal
contract string, not just that the endpoint responds. Also: a blanket
`.gitignore` rule (`docs/`) can silently break a compliance requirement
(the AI disclosure log) without any error — worth double-checking ignore
rules against what's actually supposed to ship.

### Status

- [x] Complete (basic skeleton); real plan generation still pending M1/M2;
  Docker build still needs manual verification
