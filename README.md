# Smart Guided Troubleshooting Engine

Samsung PRISM Y2026 GenAI Hackathon, Theme 2.

The engine takes a free-text Galaxy device complaint (for example *"my wifi keeps
disconnecting"*) and returns a structured, step-by-step troubleshooting plan as pure JSON.
Each step is a Settings interaction, and each action carries a Settings deeplink matched
from the official catalog. The plan follows the Theme 2 response schema.

## How it works

```
query ──► semantic cache ──► relevance check ──off-topic──────────────────► no_match
                                  │ in scope
              cache hit ◄─────────┤
                                  ▼
        M3  settings planner     catalog-only Configuration plan when one entry clearly matches
                                  │ not a settings request
                                  ▼
        M3  reference check      no reference text and no known topic ──► no_siis_context
                                  ▼
        M1  query enrichment     domain, issue, technical query, 8–10 paraphrases
                                  ▼
        M1  plan structuring     LLM, else reference-text parser, else domain plan
                                  ▼
        M2  deeplink matching    catalog deeplink per action (metadata match only)
                                  ▼
        M3  contract validation  repair or quarantine anything off-spec, disruption order
                                  ▼
        M3  URL-leak check ──► cache store ──► response
```

| Stage | Where | What it guarantees |
|---|---|---|
| Query enrichment | `backend/services/query_enrichment.py` | Normalised query and paraphrases. Uses an LLM if a key is set, otherwise a deterministic fallback. |
| Relevance check | `backend/services/relevance.py` | Rejects questions that are not about a Galaxy device. LLM verdict when available; otherwise an embedding comparison against labelled examples (`data/relevance_prototypes.json`); otherwise word lists. |
| Settings plans | `backend/services/config_planner.py`, `catalog_index.py` | Settings requests (for example *"my phone time is in 24 hrs"*) get a Configuration plan built only from the matching catalog entry: its deeplink, switch label and description. Fault reports and weak matches are left to the troubleshooting path. |
| Plan structuring | `backend/services/troubleshooting_engine.py`, `reference_parser.py` | Without an LLM, steps are parsed from the reference text (SIIS article or raw `siis_response`); every parsed step's words appear in that text. |
| Deeplink matching | `backend/services/m2_engine.py`, `action_matcher.py`, `deeplink_resolver.py` | Deeplinks come only from `data/deeplinks.json`, matched on `description` / `message` / `qna_description`, never on the URI string. |
| Semantic cache | `backend/services/cache.py`, `text_similarity.py` | Paraphrased queries hit the cache. Guards stop wrong reuse, for example front vs rear camera or Wi-Fi vs mobile data. Persisted to disk, pre-warmed with the 20 official queries at startup, and deterministic: identical queries always get the same answer, even under concurrent load. |
| Contract validation | `backend/services/contract_validator.py` | Enforces the graded schema: description of 5–7 words starting "It will", Title Case action names, `auto` / `manual` / `critical` categories, no deeplink on manual actions, toggle polarity, 8–10 variations, and action order toggles → optimizations → reboots → service → critical. |
| LLM guard | `backend/services/llm_guard.py` | Every LLM call shares a per-request time budget and a circuit breaker, so a slow or failing provider cannot push a request past the 8 s target. |
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

The image bakes in the embedding model and the catalog vectors at build time, so the container
needs no internet access at runtime (image size is about 720 MB). The cache is kept on the
`cache-state` volume and survives container restarts.

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

`siis_response` is optional and may be the raw reference text (as in the Theme 2 spec) or an
object `{"title": ..., "content": ...}`. When it is provided, the plan is built from that
reference text and the cache is bypassed.

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

The engine never invents a plan or a deeplink. When it has nothing grounded to offer, it returns
an empty `contexts` list with one of these `fallback` values:

| `fallback` | When |
|---|---|
| `no_match` | The question is not about a Galaxy device. |
| `no_siis_context` | The question is about a device, but there is no reference text and no recognisable topic to build a plan from (for example *"my galaxy has a problem"*). |
| `validation_failed` | The finished plan still contained a link and was withheld. |
| `internal_error` | An unexpected failure (HTTP 500). |

Relevance (`backend/services/relevance.py`, prompt in `prompts/relevance_prompt.txt`):

- If an LLM key is set, the LLM decides. Verdicts are memoized per query.
- Otherwise, or if the LLM call fails, an offline check decides: a confident catalog settings
  match is accepted; else the query embedding is compared with labelled in-scope and
  out-of-scope examples; if the embedding model is unavailable, word lists decide.
- A cache hit accepted by the offline check is served without an LLM call, to keep cache-hit
  latency low. Set `RELEVANCE_LLM_ON_CACHE_HIT=true` to have the LLM check cache hits too.
- A request with `siis_response` skips the check.

### Settings requests

When a query asks to change a setting rather than report a fault, and one catalog entry clearly
matches it, the engine returns a `<Topic> Configuration` plan built only from that entry. For
example, *"my phone time is in 24 hrs"* returns the **Switch Time Format** action with its catalog
deeplink and the steps "Open the 24-hour time format settings page." and "Tap Use 24-hour format.".
On/off requests pick the matching toggle entry ("turn off bluetooth" gives **Disable Bluetooth**).
Queries with fault words (for example "not working", "keeps", "won't") or no clear match go
through the normal troubleshooting path. A request with `siis_response` always uses the
troubleshooting path.

Response headers:

| Header | Meaning |
|---|---|
| `X-Request-ID` | Trace ID. Send your own to correlate logs. |
| `X-Cache` | `exact`, `semantic`, `variation`, `coalesced` (identical request already in flight) or `miss` |
| `X-Pipeline-Ms` | Server-side processing time |
| `X-LLM-Calls`, `X-Est-Cost-USD` | Per-request LLM usage and estimated cost |
| `X-Relevance` | Which check accepted or rejected the query: `llm`, `semantic`, `keywords` or `skipped` |
| `X-Planner` | Which planner built the plan: `catalog` (settings request), `m1` (troubleshooting) or `none` |

Errors: a blank or oversized query, or a `siis_response` that is not text or an object (or is
over 20,000 characters), returns `422`. An unexpected failure returns `500` with
`{"contexts": [], "fallback": "internal_error"}` and is logged with its request ID.

### `GET /health`

Returns `{"status": "ok"}` once the catalog, the dense index, the persisted cache and the
pre-warmed official queries are loaded, or `503` if warm-up fails.

### `GET /v1/metrics`

Returns the cache hit rate, hits by tier, p50/p95 latency for hit and cold requests,
validation repair codes, total estimated cost, dense index status, LLM circuit-breaker state and
the startup report (entries loaded from disk, queries pre-warmed).

## Tests and evaluation

```bash
python -m pytest -q                          # full suite, 394 tests
python evaluation/benchmark.py               # M1: schema checks on the official queries
python evaluation/benchmark_m2.py            # M2: deeplink matching scenarios
python evaluation/benchmark_m3.py            # M3: paraphrase cache hit rate, latency, contract audit
python evaluation/robustness_eval.py         # labelled good/bad queries and adversarial inputs, end to end
python evaluation/load_test.py URL 16 10     # concurrent load against a running server
```

The test suite strips LLM keys, so it is deterministic and never makes billed calls. Set
`M3_TESTS_ALLOW_LLM=1` to allow them.

Latest M3 benchmark results (`evaluation/benchmark_m3_results.json`, no LLM):

| Metric | Result | Target |
|---|---|---|
| Paraphrase cache hit rate, held-out split | **80.4%** (45/56), 0 wrong hits | ≥80% |
| Cache-hit latency, server p95 | about 30 ms | ≤300 ms |
| Cold-path latency, server p95 | about 120 ms | ≤8 s |
| 20 official queries through the contract validator | 20/20 delivered, 0 repairs | — |

Robustness and load (`evaluation/robustness_results.json`, `evaluation/load_test_results.json`,
no LLM):

| Check | Result |
|---|---|
| Official queries with a plan | 20/20, 10 distinct reference-grounded plans |
| Troubleshooting paraphrases with a plan | 126/126 |
| Settings requests (40, 19 held out) | dev 21/21 correct; held-out 10/19 correct, 0 wrong settings plans |
| Off-topic questions given a plan | 1/30 |
| Concurrent load, 16 workers, warm server | 181 requests/s, 580/580 OK, p95 45 ms, identical answers for identical queries |
| Slow LLM provider (live NVIDIA free tier) | every request under 8 s (was 30–60 s before the LLM guard) |

The paraphrase benchmark is small and was written by the team. Method, ablations and
limitations are in [`docs/M3_RESEARCH_UPGRADE.md`](docs/M3_RESEARCH_UPGRADE.md). How the system
was stress-tested, what broke and what was fixed is in
[`docs/M3_ROBUSTNESS_REPORT.md`](docs/M3_ROBUSTNESS_REPORT.md).

## Known limitations

- Without an LLM, the offline relevance check cannot tell another device or a figure of speech
  from a phone complaint when the wording is the same (for example *"my laptop battery drains
  fast"* or *"my patience drains really fast"*). The LLM check handles these when a key is set.
- Settings requests worded very differently from the catalog (for example *"share my internet
  with my laptop"*) can miss the settings planner and get a troubleshooting plan instead.
- Non-English questions are accepted as relevant but get `no_siis_context` without an LLM.
- The cache lives in one process. On a freshly started server a burst of 16 simultaneous new
  queries can take up to about 3 s; running several workers would need a shared cache.
- The Docker image is about 720 MB because it includes the embedding model.

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
