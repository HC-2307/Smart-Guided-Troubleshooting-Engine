# Smart Guided Troubleshooting Engine

Samsung PRISM Y2026 GenAI Hackathon, Theme 2.

The engine takes a free-text Galaxy device complaint (for example *"my wifi keeps
disconnecting"*) and returns a structured, step-by-step troubleshooting plan as pure JSON.
Each step is a Settings interaction, and each action carries a Settings deeplink matched
from the official catalog. The plan follows the Theme 2 response schema.

## How it works

```
query ──► semantic cache ──hit──────────────────────────────────────────► response
              │ miss
              ▼
        M1  query enrichment        domain, issue, technical query, 8–10 paraphrases
              ▼
        M1  plan structuring        goal, title, actions, steps, category
              ▼
        M2  deeplink matching       catalog deeplink per action (metadata match only)
              ▼
        M3  contract validation     repair or quarantine anything off-spec
              ▼
        M3  URL-leak check ──► cache store ──► response
```

| Stage | Where | What it guarantees |
|---|---|---|
| Query enrichment | `backend/services/query_enrichment.py` | Normalised query and paraphrases. Uses an LLM if a key is set, otherwise a deterministic fallback. |
| Plan structuring | `backend/services/troubleshooting_engine.py` | Steps derived from reference text only. Critical actions ordered last. |
| Deeplink matching | `backend/services/m2_engine.py`, `action_matcher.py`, `deeplink_resolver.py` | Deeplinks come only from `data/deeplinks.json`, matched on `description` / `message` / `qna_description`, never on the URI string. |
| Semantic cache | `backend/services/cache.py`, `text_similarity.py` | Paraphrased queries hit the cache. Guards stop wrong reuse, for example front vs rear camera or Wi-Fi vs mobile data. |
| Contract validation | `backend/services/contract_validator.py` | Enforces the graded schema: description of 5–7 words starting "It will", Title Case action names, `auto` / `manual` / `critical` categories, no deeplink on manual actions, toggle polarity, 8–10 variations. |
| Telemetry | `backend/services/telemetry.py` | Request ID, per-stage timings, cache tier, LLM calls and estimated cost for every request. |

## Quick start

### Local (Python 3.11+)

```bash
pip install -r requirements.txt
uvicorn backend.main:app --port 8000
```

### Docker

```bash
docker compose up --build
```

This starts both the API and the frontend. Open `http://localhost:5500` for the UI.
`OPENAI_API_KEY` / `GEMINI_API_KEY` are passed through from your shell if set.

In both cases the API is at `http://localhost:8000`. It works without any API key: the
deterministic fallback handles enrichment and structuring.

### Enabling the LLM path (optional)

Copy [`.env.example`](.env.example) to `.env` and fill in a key. The app loads `.env` on
startup, and Docker Compose reads it too:

```bash
cp .env.example .env    # then set OPENAI_API_KEY=...
uvicorn backend.main:app --port 8000
```

Variables already set in your shell take priority over `.env`. Any OpenAI-compatible provider
works by setting `OPENAI_BASE_URL` and `LLM_MODEL` (for example Gemini or NVIDIA).

Every setting and its default is listed in [`.env.example`](.env.example). Never commit a
real key.

## API

### `POST /v1/troubleshoot`

Request:

```json
{ "query": "my wifi keeps disconnecting", "siis_response": null }
```

`siis_response` is optional. When it is provided, the plan is built from that reference
text and the cache is bypassed.

Response (shortened):

```json
{
  "contexts": [
    {
      "goal": "Follow these steps to perform this Network Troubleshooting",
      "title": "Network connection issue",
      "score": 0.95,
      "actions": [
        {
          "actionName": "View WiFi Settings",
          "description": "It will reconnect your phone to Wi-Fi.",
          "category": "auto",
          "stepGroups": [
            {
              "steps": ["Navigate to and open Settings.", "Tap Connections.", "Tap Wi-Fi."],
              "actionableDeeplink": { "deeplink": "bixby://masked/act/c564686e0d", "...": "..." },
              "validationDeeplink": null
            }
          ]
        }
      ]
    }
  ],
  "query_variations": ["My Galaxy phone keeps disconnecting from Wi-Fi.", "..."],
  "fallback": null
}
```

If nothing viable matches, the response is `{"contexts": [], "fallback": "no_match"}`. The
engine never invents a plan or a deeplink.

Queries that are not about a Galaxy device (for example *"what is the capital of france"* or
*"my laptop battery drains fast"*) are also rejected with `no_match`
(`backend/services/relevance.py`, prompt in `prompts/relevance_prompt.txt`):

- If an LLM key is set, the LLM decides. Verdicts are memoized per query, and the call fails
  fast (no retries, `RELEVANCE_LLM_TIMEOUT_SECONDS`).
- If no key is set, or the LLM call fails or returns an unusable verdict, a keyword check
  decides instead.
- A cache hit that passes the keyword check is served without an LLM call, to keep cache-hit
  latency low. Set `RELEVANCE_LLM_ON_CACHE_HIT=true` to have the LLM check cache hits too.
- A request with `siis_response` skips the check.

The `X-Relevance` response header shows which check decided: `llm`, `keywords` or `skipped`.

Response headers:

| Header | Meaning |
|---|---|
| `X-Request-ID` | Trace ID. Send your own to correlate logs. |
| `X-Cache` | `exact`, `semantic`, `variation`, or `miss` |
| `X-Pipeline-Ms` | Server-side processing time |
| `X-LLM-Calls`, `X-Est-Cost-USD` | Per-request LLM usage and estimated cost |
| `X-Relevance` | Which check accepted or rejected the query: `llm`, `keywords` or `skipped` |

Errors: a blank or oversized query returns `422`. An unexpected failure returns `500` with
`{"contexts": [], "fallback": "internal_error"}` and is logged with its request ID.

### `GET /health`

Returns `{"status": "ok"}` once the catalog and similarity indexes are loaded, or `503` if
warm-up fails.

### `GET /v1/metrics`

Returns the cache hit rate, hits by tier, p50/p95 latency for hit and cold requests,
validation repair codes and total estimated cost.

## Tests and evaluation

```bash
python -m pytest -q                  # full suite, 165 tests
python evaluation/benchmark.py       # M1: schema checks on the official queries
python evaluation/benchmark_m2.py    # M2: deeplink matching scenarios
python evaluation/benchmark_m3.py    # M3: paraphrase cache hit rate, latency, contract audit
```

The test suite strips LLM keys, so it is deterministic and never makes billed calls. Set
`M3_TESTS_ALLOW_LLM=1` to allow them.

Latest M3 benchmark results (`evaluation/benchmark_m3_results.json`, no LLM):

| Metric | Result | Target |
|---|---|---|
| Paraphrase cache hit rate, held-out split | **80.4%** (45/56), 0 wrong hits | ≥80% |
| Cache-hit latency, server p95 | under 10 ms | ≤300 ms |
| Cold-path latency, server p95 | under 30 ms | ≤8 s |
| 20 official queries through the contract validator | 20/20 delivered, 0 repairs | — |

The paraphrase benchmark is small and was written by the team. Method, ablations and
limitations are in [`docs/M3_RESEARCH_UPGRADE.md`](docs/M3_RESEARCH_UPGRADE.md).

## Repository layout

```
backend/
  main.py              FastAPI app, request tracing, /health, /v1/metrics
  config.py            environment-driven settings
  api/                 /v1/troubleshoot route
  schemas/             request / response models
  services/            pipeline stages (see "How it works")
data/                  catalog (deeplinks.json), official queries (input.txt), SIIS references
prompts/               LLM prompts for enrichment and structuring
contracts/             example payloads passed between pipeline stages
schemas/               JSON schemas for intermediate outputs
evaluation/            benchmarks and recorded results
tests/                 unit, API and integration tests
docs/                  research write-up and project notes
Dockerfile, docker-compose.yml
```

## Team

| Role | Member | Area |
|---|---|---|
| M1 | Arav | LLM and query enrichment, plan structuring |
| M2 | Geetika | Catalog and deeplink matching |
| M3 | Harshit | Backend API, orchestration, cache, validation, Docker, integration tests |
| M4 | Asmi | Frontend, evaluation, demo |
