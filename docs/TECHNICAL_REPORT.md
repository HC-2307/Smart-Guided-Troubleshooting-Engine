# Technical report: Smart Guided Troubleshooting Engine

Samsung PRISM GenAI Hackathon 2026, Theme 2. This report describes how the engine works, why it was built
this way and what is new in it. Measured results are in [EVALUATION.md](EVALUATION.md).

## 1. Problem

Customers describe device problems vaguely ("screen flickers and the battery dies fast"). An agent turns
each description into troubleshooting steps by hand, which takes about 15 minutes per scenario, and the
customer still has to find each setting themselves. Theme 2 asks for a REST API that:

- normalises the complaint into a technical query,
- returns clean, ordered troubleshooting steps as JSON through a two-stage LLM engine,
- attaches the exact Settings deeplink to each step,
- answers repeated and paraphrased questions from a cache in under 300 ms.

The hard constraints are:

- zero URLs in the output,
- deeplinks copied only from the supplied catalog, matched on its descriptive fields and never on the URI,
- no invented steps, returning an empty `contexts` list instead,
- pure JSON output.

## 2. Design principle: the LLM plans, the catalog and the validator decide

A single LLM prompt can produce a plausible plan, but it cannot be trusted with the three things that are
graded hardest:

- which deeplink is attached,
- whether a URL slips through,
- whether a plan is invented.

The engine therefore splits responsibilities:

| Concern | Decided by | Never decided by |
|---|---|---|
| Understanding the complaint and wording the steps | LLM, with a deterministic fallback | — |
| Which Settings deeplink a step gets | Catalog matching on `description` / `message` / `qna_description` | The LLM, or the URI string |
| Whether the answer meets the contract | Contract validator, in code | Prompt instructions alone |
| Whether to answer at all | Relevance gate and reference check | — |
| Latency and cost | Semantic cache and LLM guard | — |

The result is that every request gets a contract-valid answer or a controlled refusal, whether the LLM is
fast, slow, rate-limited or absent.

## 3. Architecture

```
                         POST /v1/troubleshoot  {query, siis_response?}
                                       │
                          ┌────────────▼────────────┐
                          │ Relevance gate (M3)      │── off-topic ─────────► contexts: [], fallback: no_match
                          │ LLM → embeddings → words │
                          └────────────┬────────────┘
                                       │ device question
                          ┌────────────▼────────────┐
                          │ Semantic cache (M3)      │── guarded hit ───────► cached plan  (≈ 60 ms)
                          │ exact / similar / seeded │
                          └────────────┬────────────┘
                                       │ miss
                          ┌────────────▼────────────┐
                          │ Settings planner (M3)    │── settings request ──► Configuration plan from one catalog entry
                          │ keyword + bge-small      │
                          └────────────┬────────────┘
                                       │ fault report
                          ┌────────────▼────────────┐
                          │ Reference check (M3)     │── no text, no topic ─► contexts: [], fallback: no_siis_context
                          └────────────┬────────────┘
                                       │
                ┌──────────────────────▼──────────────────────┐
                │ Stage 1 · Query enrichment (M1)              │  domain, issue, technical query, 8–10 paraphrases
                │ Stage 2 · Plan structuring (M1)              │  LLM → reference-text parser → domain plan
                └──────────────────────┬──────────────────────┘
                                       │
                          ┌────────────▼────────────┐
                          │ Deeplink resolution (M2) │  catalog-only, metadata match, critical last
                          └────────────┬────────────┘
                          ┌────────────▼────────────┐
                          │ Contract validator (M3)  │  repair / quarantine / fallback, polarity, ordering
                          │ URL-leak gate (M3)       │
                          └────────────┬────────────┘
                                       │
                               cache store ──► JSON response + trace headers

   Every LLM call (relevance, enrichment, structuring) goes through the LLM guard:
   shared 5.5 s request budget · circuit breaker · one retry on a busy provider.
```

### 3.1 Query enrichment (M1) — `backend/services/query_enrichment.py`

The first LLM stage turns the raw complaint into a domain (battery, display, connectivity, audio, storage,
camera, performance, system), an issue, a technical query and 8–10 paraphrases in varied registers. The
prompt is in `prompts/enrichment_prompt.txt`. When no LLM answers in time, a deterministic engine does the
same job with keyword and regex rules. Its paraphrase lists are subtopic-aware (Wi-Fi, Bluetooth, mobile
data, Smart Switch, audio, storage), so the paraphrases stay about the user's actual problem.

### 3.2 Plan structuring (M1) — `backend/services/troubleshooting_engine.py`

The second LLM stage turns the enriched query and the SIIS reference text into the Theme 2 plan. The
prompt is in `prompts/structure_prompt.txt`, and a post-processor enforces the schema. Without an LLM plan,
`reference_parser.py` builds actions directly from the reference article's step sections, splitting
instructions so that each step is one physical interaction. A test checks that every parsed step's words
appear in the source text, so parsed plans cannot contain invented steps. If the article has no usable
structure, the engine falls back to a hand-written plan for the domain.

### 3.3 Deeplink resolution (M2) — `backend/services/m2_engine.py`, `action_matcher.py`, `deeplink_resolver.py`

Each action is matched against the 578 catalog entries in stages:

1. exact match,
2. keyword match on the action with its description and steps as context,
3. TF-IDF cosine similarity as a last resort.

Matching uses only the descriptive fields. The URI is copied verbatim from the matched entry and never
built from text. If confidence is too low, the step is left without a deeplink rather than given a guess.
Manual actions never carry a deeplink, and critical actions are moved to the end. Two extra rules came
from testing:

- **On/off polarity.** An "Enable" action cannot map to a `Disable` toggle, and a neutral action cannot
  map to an off switch.
- **Critical actions need a strong match.** A critical action rejects weak semantic matches. A network
  reset had been linked to the factory-reset page.

### 3.4 Settings (Configuration) planner (M3) — `backend/services/config_planner.py`, `catalog_index.py`

Theme 2 includes Configuration goals as well as Troubleshooting goals. A request such as "my phone time
is in 24 hrs" is not a fault. It needs the one Settings screen that changes it.

The planner scores the catalog's usable Settings entries by switch label, name, description and QnA text.
It skips TV and appliance entries, placeholder names and entries whose name contradicts their on/off type.
When keyword matching finds nothing, a dense index (BAAI `bge-small-en-v1.5` embeddings through
`fastembed`, built at image build time) finds the closest screen. The planner builds a one-action
Configuration plan only from that entry's own text and deeplink.

The planner leaves a query to the troubleshooting path when:

- it contains fault words ("keeps", "won't", "not working"),
- the best match is weak,
- two screens tie.

### 3.5 Relevance gate (M3) — `backend/services/relevance.py`

Off-topic questions ("what is the capital of france") must not get a plan. The gate uses three checks in
order:

1. **LLM verdict.** `prompts/relevance_prompt.txt` treats the user text as data, and verdicts are memoized
   per query.
2. **Embedding comparison.** The query is compared with labelled in-scope and out-of-scope examples in
   `data/relevance_prototypes.json`.
3. **Word lists.** Used only if the embedding model is unavailable.

A request that carries its own `siis_response` skips the gate.

### 3.6 Contract validator (M3) — `backend/services/contract_validator.py`, `validator.py`

The graded contract is compiled into coded rules. Each violation gets the least destructive fix:

| Outcome | Examples |
|---|---|
| Repaired, answer kept | deeplink not in catalog removed, catalog metadata restored, manual deeplink removed, critical moved last, Title Case, score clamped, markdown stripped, duplicate action dropped, variations trimmed to 10 |
| Quarantined, only the bad action dropped | description not 5–7 words starting "It will", URL or markdown link in a step, invalid category, empty steps |
| Fallback | nothing valid left → `contexts: []`, `fallback: "validation_failed"` |

Two further rules go beyond schema checks:

- **Toggle polarity.** A deeplink whose on/off type contradicts the action verb is removed. This fixed a
  live bug where "Enable Power Saving Mode" linked to "Disable Power saving".
- **Disruption order.** Actions are ordered toggles → optimizations → reboots → service → critical, the
  plan hierarchy the spec asks for.

A final gate rejects any response with a URL anywhere in the body.

### 3.7 Semantic cache (M3) — `backend/services/cache.py`, `text_similarity.py`

The cache has three lookup tiers:

1. **Exact** match on the normalised query.
2. **Semantic** similarity.
3. **Seeded variations.** When a plan is stored, its own 8–10 `query_variations` are stored as extra keys.

Similarity is 0.75 × weighted cosine + 0.25 × character-trigram overlap. Word weights are inverse document
frequency computed over the trusted catalog. A concept lexicon maps phrases such as "loses charge" and
"won't charge" to intents, device model names are dropped, and misspellings are corrected only toward the
small intent vocabulary.

A candidate hit is served only if it passes two guards:

- **Domain evidence.** The query's domain words must agree with the entry's. This uses M1's own keyword
  table, so the cache and the planner never disagree.
- **Facet conflict.** Hits are refused between front and rear camera, inner and outer screen, Wi-Fi,
  Bluetooth, mobile data and NFC, battery drain and charging failure, and on and off.

Other rules:

- Plans built from a specific reference article need a stricter similarity (0.75) and get no seeded keys,
  so a generic "my screen keeps flickering" is not served the email-specific plan of official query 1.
- Seeded variations that contradict the original query are dropped at store time.
- Only grounded plans are cached: plans from a reference article or the settings planner, or a guessed
  plan whose topic (read from its goal and title) matches topic words in the query. A misspelt query's
  guessed plan is answered but never stored, so it cannot be served to the correctly spelt query.
- The cache is persisted to disk atomically, and the 20 official queries are pre-warmed at start-up
  without LLM calls.
- Identical requests that arrive at the same time are coalesced into one pipeline run.

### 3.8 LLM guard and provider start-up (M3) — `backend/services/llm_guard.py`, `backend/config.py`

- **Shared budget.** All LLM calls in one request share a 5.5 s budget, and each call's timeout shrinks to
  what is left.
- **Circuit breaker.** After 2 consecutive provider failures the LLM is skipped for 60 s. A timeout that
  the budget cut short does not count as a provider failure.
- **Busy retry.** A fast `429` or `503` gets one retry if the budget allows.
- **Provider selection.** At start-up `start.sh` / `start.ps1` ask for an OpenAI key. If one is given, it
  is used with `gpt-4o-mini`. If it is left empty, the team's free NVIDIA tier is used
  (`nvidia/nemotron-3-super-120b-a12b` with thinking switched off, settings in `backend/free_tier.json`).
  The model was chosen after live probes of the free models for latency and reliability.
- **Offline mode.** `LLM_FREE_TIER=false` runs the fully deterministic pipeline.

### 3.9 Telemetry — `backend/services/telemetry.py`

The response body contract is frozen, so tracing uses headers:

- `X-Request-ID`,
- `X-Cache` (tier),
- `X-Pipeline-Ms`,
- `X-LLM-Calls`,
- `X-Est-Cost-USD`,
- `X-Relevance` (which check decided),
- `X-Planner` (which planner answered).

`GET /v1/metrics` aggregates hit rate by tier, p50/p95 latency for cache hits and cold requests,
validation repair codes, estimated cost, circuit-breaker state and the LLM provider in use.

### 3.10 Frontend (M4 baseline, rebuilt) — `frontend/`

A dependency-free single page for demos and judging. For each answer it shows:

- the plan, with category badges and each step group's catalog deeplink,
- how the answer was produced: cache tier, relevance check, planner, LLM calls, cost, server and round-trip
  time,
- the Theme 2 contract checks, run in the browser,
- the clickable query variations, which demonstrate the semantic cache,
- running session metrics and the raw JSON.

## 4. What is new

1. **Catalog-grounded, guarded semantic cache.** Published semantic caches (GPTCache, MeanCache) decide a
   hit by one embedding threshold. vCache and Krites add learned thresholds or an LLM judge to catch wrong
   hits. This engine instead refuses hits with explainable, zero-cost guards built from the domain: facets
   such as front vs rear camera or on vs off, and domain evidence. It also reuses the query variations the
   spec already requires as extra cache keys. On held-out paraphrases this raised the hit rate from 64.3%
   to 80.4% with no wrong hits.
2. **Contract compiler with toggle-polarity verification.** Schema validation checks types, and grounding
   methods such as Gorilla check that an API exists. This engine also checks that the deeplink does what
   the step says, and repairs the smallest invalid unit instead of discarding the whole answer. It follows
   the finding in "Let Me Speak Freely?" that validating after generation beats forcing strict formats
   during decoding.
3. **Settings requests as first-class Configuration plans**, built only from one catalog entry, with a
   dense fallback that does not take over fault reports.
4. **Graceful degradation as a contract.** The relevance gate, reference-text parser, `no_siis_context`
   refusal and LLM guard make every request finish under 8 s with a valid answer or a controlled refusal,
   whether the provider is fast, slow, busy or missing.
5. **Observable by default.** Every response explains how it was produced (headers and frontend), and cost
   and latency percentiles are live at `/v1/metrics`.

## 5. Robustness work

The engine was stress-tested with labelled official, paraphrase, settings, off-topic and adversarial
queries, concurrent load and live free-tier providers. The main defects found and fixed were:

| Found | Fixed by |
|---|---|
| The spec's own raw-text `siis_response` returned HTTP 422 | Accepting raw text or an object |
| All official queries got one generic plan without an LLM | Reference-text parser: 10 distinct grounded plans |
| Settings questions got "System startup failure" | Configuration planner |
| Keywords matched inside words ("c**hang**e" read as a hang) | Word-start matching |
| A slow provider made requests take 30–60 s | LLM guard; now under 8 s |
| Off-topic traps got plans (5/30) | Embedding relevance check (1/30 offline) |
| Concurrency: p95 6.7 s and inconsistent answers under load | Lock-free fingerprinting, request coalescing, exact aliases |
| A generic screen question got the email-specific plan from the cache | Stricter reuse for reference-grounded plans |
| The free-tier provider tripped the breaker during start-up pre-warm | LLM-free pre-warm; budget-cut timeouts no longer count |
| A misspelt query's guessed plan was cached and then served to the correctly spelt query | Only grounded plans are cached; 12/12 correct spellings now get their own plan |

## 6. Tech stack

| Layer | Choice |
|---|---|
| API | Python, FastAPI, Uvicorn, Pydantic v2 |
| LLM access | OpenAI Python SDK against any OpenAI-compatible endpoint (OpenAI `gpt-4o-mini`, or NVIDIA Nemotron free tier); `json_repair` for malformed JSON |
| Embeddings | `fastembed` with BAAI `bge-small-en-v1.5` (CPU, baked into the image) |
| Similarity and cache | NumPy; custom catalog-IDF, trigram and facet logic; atomic JSON persistence |
| Frontend | Plain HTML, CSS and JavaScript served by nginx |
| Packaging | Docker, Docker Compose, start scripts for bash and PowerShell |
| Testing | pytest (433 tests), benchmark, robustness, load and audit scripts |
| AI assistance during development | Antigravity AI (M1), Claude Code (M3); see `docs/LangAI3.0_AI_Disclosure.docx` |

## 7. Future work

- **Validation deeplinks in a closed loop.** The schema's `validationDeeplink` could read device state
  after a step. When a non-destructive step confirms the cause, later critical steps such as a factory
  reset could be dropped. This needs an on-device companion.
- **Hardware vs software triage.** For example, a display defect that does not appear in a screenshot is
  a panel fault, not software. The engine could then route to service before suggesting software steps.
- **Shared cache store** (Redis) for multi-worker deployment, and a learned per-category threshold once
  real traffic provides labelled feedback.
- **Wider settings coverage** by embedding the catalog's QnA text and adding user-phrased aliases for the
  8 held-out settings requests that still miss.
- **Multilingual support**, through an LLM translation step before enrichment.
- **Typo tolerance before routing.** Misspelt queries are handled by the LLM when it is available, but the
  settings planner and reference matching still read the raw text. A context-aware spelling correction
  (for example, one LLM rewrite shared by all stages) would close the gap. A dictionary corrector was
  prototyped and rejected because it changed correct words.

## 8. References

1. F. Bang. GPTCache: An Open-Source Semantic Cache for LLM Applications. NLP-OSS @ EMNLP 2023.
2. W. Gill et al. MeanCache: User-Centric Semantic Caching for LLM Web Services. IPDPS 2025; arXiv:2403.02694.
3. L. G. Schroeder et al. vCache: Verified Semantic Prompt Caching. arXiv:2502.03771.
4. C. Wang et al. Category-Aware Semantic Caching for Heterogeneous LLM Workloads. arXiv:2510.26835.
5. A. K. Singh et al. Asynchronous Verified Semantic Caching for Tiered LLM Architectures (Krites). EuroMLSys 2026; arXiv:2602.13165.
6. Z. R. Tam et al. Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of LLMs. EMNLP 2024 Industry; arXiv:2408.02442.
7. T. Rebedea et al. NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails. EMNLP 2023 Demos.
8. S. G. Patil et al. Gorilla: Large Language Model Connected with Massive APIs. arXiv:2305.15334.
9. A. Madaan et al. Self-Refine: Iterative Refinement with Self-Feedback. NeurIPS 2023; arXiv:2303.17651.
10. S. Xiao et al. C-Pack: Packed Resources for General Chinese Embeddings (BGE models). SIGIR 2024; arXiv:2309.07597.
