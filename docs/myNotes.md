# My Development Notes

This file records my learning and AI-assisted development during the Samsung PRISM hackathon.

It is also used as a reference when preparing the Samsung AI disclosure.

---

# How to use this file

For every meaningful development task, record:

- Date
- Task
- Tool used
- What I asked
- What the AI produced or helped with
- What I personally changed or verified
- Files affected
- What I learned

Do not fabricate or minimize AI involvement.

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

### AI assistance

Reviewed the existing skeleton against the Theme 2 schema contract in
CLAUDE.md and found: API mounted at `/api/v1` instead of the required
`/v1`; `.gitignore` had a blanket `docs/` rule that would have silently
excluded this disclosure log from version control; `troubleshooting_engine.py`
returned a shape that would fail `TroubleshootResponse` validation; `cache.py`
was an empty stub with no code. AI implemented: `main.py` route prefix fix,
`fallback` field on `TroubleshootResponse`, an in-memory normalized-string
cache (`cache.py`) with a note that semantic keying is still needed for the
80% hit-rate target, `orchestrator.py` wiring cache -> plan generation ->
URL-leak validation gate, a schema-conformant placeholder in
`troubleshooting_engine.py`, integration tests (`tests/test_api.py`), and
`Dockerfile`/`docker-compose.yml`.

### My changes / verification

Ran the orchestrator locally to confirm end-to-end output matches the schema
(goal/title/score/actions/stepGroups/category), confirmed cache normalization
works across whitespace/case variants, and ran `pytest tests/test_api.py`
(3 passed). Did not verify the Docker build — Docker Desktop wasn't running
locally, so that still needs a manual `docker build` check.

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
contract string, not just that the endpoint responds.

### Status

- [x] Complete (basic skeleton); real plan generation still pending M1/M2

---

## YYYY-MM-DD — Task name

### Goal

What were we trying to build?

### Tool

Example:

- Claude Code
- ChatGPT
- Other

### Prompt / Request

What did I ask the AI?

### AI assistance

What did the AI explain, generate, debug or suggest?

### My changes / verification

What did I personally change, test, verify or decide?

### Files affected

- `path/to/file.py`

### What I learned

Write this in simple language.

### Status

- [ ] Not started
- [ ] In progress
- [ ] Tested
- [ ] Complete

---

# Concepts I Have Learned

## FastAPI

### What it is

...

### How we use it

...

### What I understand

...

---

## Pydantic

### What it is

...

### How we use it

...

### What I understand

...

---

## REST API

### What it is

...

### How we use it

...

### What I understand

...

---

## Orchestration

### What it is

...

### How we use it

...

### What I understand

...

---

## Validation

### What it is

...

### How we use it

...

### What I understand

...

---

## Caching

### What it is

...

### How we use it

...

### What I understand

...

---

## Testing

### What it is

...

### How we use it

...

### What I understand

...

---

# Questions I Still Have

- 
- 
- 