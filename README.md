# Smart Guided Troubleshooting Engine

**Samsung PRISM GenAI Hackathon 2026 · Theme 2: Smart Guided Troubleshooting Engine**

The engine turns a vague Galaxy device complaint, such as *"my phone gets really hot while charging"*, into
an ordered, step-by-step troubleshooting plan as pure JSON. Each action carries the exact Settings
deeplink from the official catalog, so the fix is one tap away. Paraphrased questions are answered from a
guarded semantic cache in milliseconds. Questions that are not about a device, or that are too vague to
answer, get an empty result instead of an invented plan.

| | |
|---|---|
| API | `POST /v1/troubleshoot`, `GET /health`, `GET /v1/metrics` |
| Demo UI | `http://localhost:5500` |
| Documentation | [Technical report](docs/TECHNICAL_REPORT.md) · [Evaluation and test report](docs/EVALUATION.md) · [AI usage disclosure](docs/LangAI3.0_AI_Disclosure.docx) |

## Results at a glance

All measured on the submitted code. Details and commands are in [docs/EVALUATION.md](docs/EVALUATION.md).

| Theme 2 target | Result |
|---|---|
| JSON contract on the 20 official queries | 20/20 valid, 0 repairs needed |
| Zero URL leakage | 0 URLs across all official, adversarial and prompt-injection tests |
| Deeplinks only from the catalog | 74/74 delivered deeplinks are catalog entries, 0 on/off polarity conflicts |
| ≥ 80% cache hits on paraphrases | **80.4%** on held-out paraphrases, 0 wrong hits |
| Cache hit P95 ≤ 300 ms | 81 ms under 16 concurrent users |
| Cold path P95 ≤ 8 s | 6.5 s with the live free-tier LLM, 272 ms offline |
| Refuse off-topic questions | 15/15 correct with the LLM, 29/30 offline |
| Misspelt queries | 0 errors; a typo never changes the answer to the correctly spelt query (12/12) |
| Tests | 433 passing |

## Quick start

You need Docker Desktop, or Docker Engine with Compose v2. Run from the repository root:

```bash
./start.sh          # macOS / Linux / Git Bash
```

```powershell
.\start.ps1         # Windows PowerShell
```

The script asks for up to two keys. No key is ever stored in this repository.

```
OpenAI API key (leave empty to use the free NVIDIA tier or offline mode):
NVIDIA API key (free at build.nvidia.com; leave empty to run offline without an LLM):
```

- **OpenAI key.** Paste one to use OpenAI `gpt-4o-mini`.
- **NVIDIA key.** Leave the OpenAI key empty and paste a free NVIDIA key to use Nemotron
  (`nvidia/nemotron-3-super-120b-a12b`). The key is free after sign-up at
  [build.nvidia.com](https://build.nvidia.com). If `NVIDIA_API_KEY` is already set in your shell or `.env`,
  this question is skipped.
- **No key.** Leave both empty to run the fully deterministic offline pipeline. Every feature works
  without an LLM; only the LLM relevance check and LLM-written plans are skipped.

The script then builds and starts two containers. The first build downloads dependencies and takes a few
minutes.

| Service | URL |
|---|---|
| Demo UI | http://localhost:5500 |
| API | http://localhost:8000 (`/health`, `/v1/troubleshoot`, `/v1/metrics`) |

The UI waits until the API reports healthy. Stop everything with `Ctrl+C`, then `docker compose down`.

### Without the start script

```bash
NVIDIA_API_KEY=nvapi-... docker compose up --build           # free NVIDIA tier
OPENAI_API_KEY=sk-... LLM_MODEL=gpt-4o-mini docker compose up --build   # your own OpenAI key
docker compose up --build                                    # no key: fully offline, no LLM
```

### Local run without Docker (Python 3.11+)

```bash
pip install -r requirements.txt
uvicorn backend.main:app --port 8000
python -m http.server 5500 --directory frontend              # optional, serves the UI
```

The provider rules are the same as in Docker:

- If `OPENAI_API_KEY` (or `GEMINI_API_KEY`) is set, in the shell or in `.env`, that key is used.
- Otherwise, if `NVIDIA_API_KEY` is set, the free NVIDIA tier is used.
- Otherwise, or with `LLM_FREE_TIER=false`, the app runs offline with no LLM.

Put keys in a `.env` file copied from [.env.example](.env.example). `.env` is gitignored, so keys never
reach the repository.

The server logs the provider it chose at start-up, and `GET /v1/metrics` reports it. Every setting is
listed in [.env.example](.env.example).

## Using the demo UI

- **Example chips** fill in a query and run it. They cover an official query, fault reports, a
  paraphrase (to show a cache hit), settings requests, an off-topic question and a query too vague to
  answer.
- **The plan** shows each action with its category (Auto opens the screen, Manual is done by hand,
  Critical is disruptive and always last), its steps and its catalog deeplink. *Open* explains what the
  deeplink would do; `bixby://` links only resolve on a Galaxy device.
- **"How this answer was produced"** shows the cache tier, the relevance check, the planner, the number of
  LLM calls, the estimated cost, the server and round-trip time, and the request ID.
- **Theme 2 contract checks** re-check the response in the browser: goal phrasing, title length, 5–7 word
  "It will" descriptions, no URLs, manual actions without deeplinks, critical actions last, and 8–10
  variations.
- **Query variations** are clickable. Each one re-runs the engine and should come back from the semantic
  cache.
- **Session metrics** show requests, cache hit rate, p95 latency for cache hits and cold requests, and
  cost.
- **The raw JSON response** is shown with a copy button.
- **Shareable links.** `http://localhost:5500/?q=your+question` runs a query on page load.

## How it works

```
query ─► relevance gate ─► semantic cache ─► settings planner ─► reference check
            │ off-topic        │ hit              │ settings          │ nothing to go on
            ▼                  ▼                  ▼                   ▼
         no_match         cached plan     Configuration plan    no_siis_context
                                                   │ fault report
                                                   ▼
               M1 query enrichment ─► M1 plan structuring (LLM → reference parser → domain plan)
                                                   ▼
               M2 catalog deeplink resolution ─► M3 contract validator + URL gate ─► cache ─► JSON
```

| Stage | Code | What it guarantees |
|---|---|---|
| Relevance gate | `backend/services/relevance.py` | Refuses non-device questions. Uses the LLM verdict when available, then embeddings against labelled examples, then word lists. |
| Semantic cache | `cache.py`, `text_similarity.py` | Paraphrases hit the cache. Domain and facet guards stop wrong reuse (front vs rear camera, Wi-Fi vs mobile data, on vs off). Persisted to disk and pre-warmed with the 20 official queries. |
| Settings planner | `config_planner.py`, `catalog_index.py` | "My phone time is in 24 hrs" gets a Configuration plan built only from the matching catalog entry. |
| Query enrichment (M1) | `query_enrichment.py` | Domain, issue, technical query and 8–10 paraphrases, from the LLM or a deterministic fallback. |
| Plan structuring (M1) | `troubleshooting_engine.py`, `reference_parser.py` | Plan grounded in the reference text. Without an LLM, steps are parsed from the article. |
| Deeplink resolution (M2) | `m2_engine.py`, `action_matcher.py`, `deeplink_resolver.py` | Deeplinks copied only from `data/deeplinks.json`, matched on description / message / qna_description, never on the URI. |
| Contract validator | `contract_validator.py`, `validator.py` | Enforces the graded schema in code, removes deeplinks with the wrong on/off polarity, orders actions from toggles to critical, and blocks any URL. |
| LLM guard | `llm_guard.py` | Shared 5.5 s budget per request, circuit breaker and one retry on a busy provider, so requests stay under 8 s. |
| Telemetry | `telemetry.py` | Request ID, stage timings, cache tier, LLM calls and cost on every request. |

The full design, the research it builds on and what is new are in
[docs/TECHNICAL_REPORT.md](docs/TECHNICAL_REPORT.md).

## API

### `POST /v1/troubleshoot`

```json
{ "query": "my wifi keeps disconnecting", "siis_response": null }
```

`siis_response` is optional. It may be the raw reference text, as in the Theme 2 spec, or an object
`{"title": ..., "content": ...}`. When it is given, the plan is built from that text and the cache is
bypassed.

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

When the engine has nothing grounded to offer, it returns an empty `contexts` list and a `fallback`:

| `fallback` | When |
|---|---|
| `no_match` | The question is not about a Galaxy device. |
| `no_siis_context` | It is about a device, but there is no reference text and no recognisable topic (*"my galaxy has a problem"*). |
| `validation_failed` | The finished plan still contained a link and was withheld. |
| `internal_error` | Unexpected failure (HTTP 500), logged with the request ID. |

Response headers:

| Header | Meaning |
|---|---|
| `X-Request-ID` | Trace ID. Send your own to correlate logs. |
| `X-Cache` | `exact`, `semantic`, `variation`, `coalesced` or `miss` |
| `X-Pipeline-Ms` | Server-side processing time |
| `X-LLM-Calls`, `X-Est-Cost-USD` | LLM usage and estimated cost of this request |
| `X-Relevance` | Which check decided relevance: `llm`, `semantic`, `keywords` or `skipped` |
| `X-Planner` | Which planner built the plan: `catalog`, `m1` or `none` |

A blank or oversized query, or an invalid `siis_response`, returns `422`.

### `GET /health`

Returns `{"status": "ok"}` once the catalog, dense index, persisted cache and pre-warmed official queries
are loaded. Returns `503` if warm-up fails.

### `GET /v1/metrics`

Returns:

- cache hit rate and hits by tier,
- p50/p95 latency for cache hits and cold requests,
- validation repair codes and total estimated cost,
- dense index status,
- LLM provider and circuit-breaker state,
- the start-up report.

## Tests and evaluation

```bash
python -m pytest -q                              # 433 unit and integration tests, no network calls
python evaluation/benchmark.py                   # M1 schema checks on the 20 official queries
python evaluation/deeplink_audit.py              # every delivered deeplink checked against the catalog
python evaluation/benchmark_m2.py                # M2 whole-query matcher benchmark
python evaluation/benchmark_m3.py                # paraphrase cache hit rate, latency, contract audit
python evaluation/robustness_eval.py             # labelled official, paraphrase, settings, off-topic, adversarial
python evaluation/load_test.py http://127.0.0.1:8000 16 10   # concurrent load against a running server
python evaluation/typo_eval.py http://127.0.0.1:8000 typo-first   # misspelt vs correctly spelt queries
```

The tests and benchmarks run without an LLM, so they are deterministic and free. Results, the live
free-tier run and the Docker run are written up in [docs/EVALUATION.md](docs/EVALUATION.md).

## Known limitations

- A misspelt query without recognisable topic words ("blutooth wont pair", "my phone tiem is in 24 hr") can get
  a generic plan or a refusal. Without an LLM this happens for 7 of 12 test typos, and with the free tier for 4 of 12.
  Guessed plans are never cached, so a typo never changes the answer to the correctly spelt query. A
  spelling-correction step was tried and left out because it also changed correct words.
- Without an LLM, look-alike questions worded like real complaints can get a plan ("my laptop battery
  drains fast"). With the free tier or an OpenAI key, the LLM refuses them.
- Settings requests worded unlike anything in the catalog ("share my internet with my laptop") can miss
  the settings planner.
- 5 of the 20 reference articles cannot be parsed into steps, so those queries get the domain plan.
- Some auto actions have no confident catalog match and are delivered without a deeplink rather than with
  a guessed one.
- The free NVIDIA tier is slower than a paid provider (about 5–6 s on a cold request) and is sometimes
  overloaded. The engine then continues without the LLM.
- The cache lives in one process. Several workers would need a shared store.
- The Docker image is about 720 MB because it includes the embedding model, so it runs without internet
  access for embeddings.

## Repository layout

```
backend/
  main.py              FastAPI app, request tracing, /health, /v1/metrics
  config.py            settings and LLM provider selection (own key / free tier / offline)
  free_tier.json       free NVIDIA tier endpoint and model (the key comes from NVIDIA_API_KEY)
  api/                 /v1/troubleshoot route
  schemas/             request and response models
  services/            pipeline stages (see "How it works")
frontend/              demo UI (HTML, CSS, JavaScript)
data/                  catalog (deeplinks.json), official queries (input.txt), SIIS references, schema.py
prompts/               LLM prompts for relevance, enrichment and structuring
contracts/, schemas/   example payloads and JSON schemas passed between pipeline stages
evaluation/            benchmarks, audits, labelled sets and recorded results
tests/                 unit, API, integration, robustness and load tests
docs/                  technical report, evaluation report, AI usage disclosure
start.sh, start.ps1    start-up scripts (ask for a key, then docker compose up)
Dockerfile, docker-compose.yml
```

## Team

| Role | Member | Area |
|---|---|---|
| M1 | Arav | LLM query enrichment and plan structuring |
| M2 | Geetika | Catalog and deeplink matching |
| M3 | Harshit | Backend API, orchestration, cache, validation, Docker, integration tests |
| M4 | Asmi | Frontend, evaluation, demo |

AI assistance used during development is declared feature by feature in
[docs/LangAI3.0_AI_Disclosure.docx](docs/LangAI3.0_AI_Disclosure.docx).
