# Evaluation and test report

Everything below was run on 29 September 2026 on the submitted code (Windows 11, Python 3.14.2 for the
local runs, Python 3.11 inside the Docker image). Each number comes from a script in this repository, and
its raw output is saved next to it in `evaluation/`. Nothing is estimated.

Two modes were measured:

- **Offline (deterministic).** No LLM. This is the floor the system falls back to when a provider is slow or
  down, and it is what the unit tests, benchmarks and robustness evaluation use, so they give the same
  result on every run.
- **Live free tier.** The default when the app is started without an OpenAI key: NVIDIA Nemotron
  (`nvidia/nemotron-3-super-120b-a12b`) through NVIDIA's OpenAI-compatible endpoint.

## Summary against the Theme 2 targets

| Target (Theme 2) | Result | Evidence |
|---|---|---|
| Response follows the JSON contract (goal phrasing, 2–3 word title, 5–7 word "It will" descriptions, categories, critical last) | 20/20 official queries delivered with **0 repairs** needed by the validator | `benchmark_m3.py` contract audit, `benchmark.py` |
| Zero URL leakage | 0 URLs in 62/62 official actions and in every adversarial response, including prompt injection asking for a URL and reference texts containing links | `benchmark.py`, `tests/test_robustness.py` |
| Deeplinks only from the catalog | 74/74 delivered deeplinks are catalog entries; 0 manual actions with a deeplink; 0 on/off polarity conflicts | `deeplink_audit.py` |
| ≥ 80% cache hits on paraphrased queries | **80.4%** (45/56) on the held-out split, **0 wrong hits** | `benchmark_m3.py` |
| P95 ≤ 300 ms on a cache hit | 81 ms under 16 concurrent users (live server); 24 ms single-user | `load_test.py`, `benchmark_m3.py` |
| P95 ≤ 8 s on the cold path | 6.5 s with the live free-tier LLM (15 cold queries); 116 ms offline | live run below, `benchmark_m3.py` |
| No hallucinated plans; return `contexts: []` when nothing fits | 29/30 off-topic questions refused offline, 15/15 live queries judged correctly by the LLM | `robustness_eval.py`, live run |
| Per-query cost tracking | `X-LLM-Calls` and `X-Est-Cost-USD` on every response, totals in `GET /v1/metrics` | `tests/test_api.py` |
| Misspelt queries | 0 errors; a misspelt query never changes the answer to the correctly spelt one (12/12) | `typo_eval.py` |

## 1. Unit and integration tests

```bash
python -m pytest -q
```

Result: **433 passed**, 0 failed (about 25 s). The suite removes every LLM setting before each test, so it
is deterministic and never makes a paid or network call.

| Area | Test files (number of tests) |
|---|---|
| API contract, headers, CORS, errors, metrics | `test_api.py` (15) |
| End-to-end pipeline M1 → M2 → M3, official queries, zero repairs, no cache poisoning by misspelt queries | `test_integration.py` (14), `test_sample_integration.py` (1) |
| Semantic cache, similarity, persistence, confident-only caching | `test_cache.py` (31), `test_similarity.py` (10), `test_cache_persistence.py` (23) |
| Contract validator and action ordering | `test_contract_validator.py` (27), `test_disruption_order.py` (12) |
| Relevance gate (LLM with a fake provider, embeddings, keywords) | `test_relevance.py` (45) |
| Settings (Configuration) plans and dense catalog index | `test_config_planner.py` (57), `test_catalog_index.py` (8) |
| Reference-text parser and `no_siis_context` fallback | `test_reference_parser.py` (15), `test_no_context.py` (29) |
| LLM guard: budget, circuit breaker, busy retry, LLM-free pre-warm | `test_llm_guard.py` (15) |
| Start-up provider selection and free tier | `test_config.py` (8), `test_docker.py` (7) |
| M1 enrichment and structuring | `test_enrichment.py` (14), `test_structure.py` (6), `test_prompt_regression.py` (21), `test_domain_plans.py` (25) |
| M2 catalog, matching and sequencing | `test_catalog.py` (1), `test_matcher.py` (9), `test_sequence.py` (2) |
| Adversarial inputs and concurrent load | `test_robustness.py` (32), `test_load.py` (4) |
| Deeplink audit script | `test_deeplink_audit.py` (2) |

## 2. M1 schema benchmark (20 official queries)

```bash
python evaluation/benchmark.py        # evaluation/benchmark_results.json
```

| Check | Result |
|---|---|
| Official schema conformance (`data/schema.py`) | 20/20 |
| Title 2–3 words | min 2, max 3 |
| Description 5–7 words starting "It will" | min 5, max 7 |
| Critical actions last | 20/20 |
| No raw URL in any action | 62/62 |
| Manual actions without a deeplink | 31/31 |
| Enrichment + structuring latency (offline) | p50 1.4 ms, p95 11.7 ms |

## 3. Deeplink resolution

```bash
python evaluation/deeplink_audit.py   # evaluation/deeplink_audit_results.json
python evaluation/benchmark_m2.py     # M2's own whole-query matcher benchmark
```

`deeplink_audit.py` runs queries through the full API and checks every delivered deeplink against
`data/deeplinks.json`.

| Query set | Actions (auto / manual / critical) | Auto actions with a deeplink | Deeplinks in catalog | Problems |
|---|---|---|---|---|
| 20 official queries | 25 / 31 / 6 | 13/25 | 13/13 | 0 |
| 14 domain seed complaints | 27 / 9 / 9 | 22/27 | 22/22 | 0 |
| 40 settings requests | 39 / 2 / 2 | 39/39 | 39/39 | 0 |

"Problems" counts deeplinks outside the catalog, manual actions with a deeplink, on/off polarity conflicts
and critical actions that are not last. The official queries are long, reference-grounded plans whose
steps often have no single Settings screen in the catalog. In those 12 cases the engine leaves the step
without a deeplink instead of guessing one.

`benchmark_m2.py` measures something different: it matches each **whole complaint** to a single catalog
entry, not each action. It resolves 1/20 at that level. That is expected, because a complaint such as
"my screen goes blank when I open Gmail" is not the description of any one Settings screen. The pipeline
resolves individual actions instead, as measured above.

## 4. Semantic cache (paraphrased queries)

```bash
python evaluation/benchmark_m3.py     # evaluation/benchmark_m3_results.json
```

Dataset: `evaluation/m3_paraphrase_set.json`, written before any tuning. It has 14 complaint intents with 8
paraphrases each (casual, formal, panicked, terse, verbose and misspelt), plus 12 hard negatives:
near-miss complaints that must **not** get a cached answer (front vs rear camera, Wi-Fi vs mobile data and
similar). Even-numbered items form the dev split used for tuning. Odd-numbered items form the held-out test
split reported here.

| Configuration | Threshold | Held-out hit rate | Wrong hits | Hard negatives served |
|---|---|---|---|---|
| A. Exact-string cache (baseline) | — | 0.0% | 0 | 0/6 |
| B. Semantic similarity, no guards | 0.65 | 64.3% | 0 | 1/6 |
| C. Semantic + domain and facet guards | 0.60 | 75.0% | 0 | 1/6 |
| **D. C + paraphrase-seeded keys (shipped)** | 0.60 | **80.4%** | **0** | 1/6 |
| E. D with simulated LLM paraphrases | 0.60 | 76.8% | 0 | 1/6 |

The one hard negative served is the compound complaint "battery drains fast and it also won't charge past
50 percent", which received the battery-drain plan.

## 5. Latency

| Path | Setting | p50 | p95 | Target |
|---|---|---|---|---|
| Cache hit | single user, through the API (`benchmark_m3.py`) | 19 ms | 24 ms | ≤ 300 ms |
| Cache hit | 16 concurrent users, live server (`load_test.py`) | 59 ms | 81 ms | ≤ 300 ms |
| Cold path, offline | single user (`benchmark_m3.py`) | 25 ms | 116 ms | ≤ 8 s |
| Cold path, live free-tier LLM | 15 new queries, live server | 4.9 s | 6.5 s | ≤ 8 s |

## 6. Load test

```bash
uvicorn backend.main:app --port 8000
python evaluation/load_test.py http://127.0.0.1:8000 16 10   # evaluation/load_test_results.json
```

| Server state | Requests | Throughput | Errors | Identical queries with different answers |
|---|---|---|---|---|
| Freshly started | 580 | 73 requests/s | 0 | 0 |
| Warm | 580 | 261 requests/s | 0 | 0 |

## 7. Robustness evaluation (labelled, end to end, offline)

```bash
python evaluation/robustness_eval.py  # evaluation/robustness_results.json
```

| Set | Result |
|---|---|
| 20 official queries | 20/20 with a plan, 10 distinct reference-grounded plans |
| 126 troubleshooting paraphrases | 126/126 with a plan, none taken by the settings planner |
| 40 settings requests | dev 21/21 correct; held-out 11/19 correct, 5 without a plan, 3 given a troubleshooting plan, **0 wrong settings plans** |
| 30 off-topic questions | 29/30 refused (26 `no_match`, 3 `no_siis_context`); 1 given a plan ("the weather is too hot today") |
| 17 adversarial inputs (emoji, Hindi, SQL, script tags, prompt injection, URLs in the query, 2,000-character repetition) | 17/17 answered with HTTP 200; the contract checks on these inputs (schema, no URL, catalog-only deeplinks, critical last) are asserted in `tests/test_robustness.py` and pass |

## 8. Live free-tier LLM run

Server started with no key, so it used the free NVIDIA tier. Fifteen new queries were sent one at a time
(`evaluation/live_free_tier_results.json`).

| Measure | Result |
|---|---|
| Relevance decided by the LLM | 15/15 |
| Off-topic questions refused | 3/3, including "my laptop battery drains fast", which the offline check accepts |
| Settings request | "how do I turn off auto brightness" → Auto dim screen Configuration plan |
| Too vague to answer | "notifications are not showing up" → `no_siis_context` |
| Latency | p50 4.9 s, p95 6.5 s, max 6.5 s (target ≤ 8 s) |
| LLM calls per request | 1 to 3; 3 enrichment calls ran out of the 5.5 s budget and fell back to the deterministic engine |
| Circuit breaker trips | 0 |

The free NVIDIA endpoint sometimes answers "503 Service temporarily overloaded". The guard retries such a
fast failure once, and the request then continues without the LLM, so a busy provider costs at most a
second and never an error.

## 9. Misspelt queries

```bash
uvicorn backend.main:app --port 8000
python evaluation/typo_eval.py http://127.0.0.1:8000 typo-first    # or clean-first
```

`typo_eval.py` sends 12 complaints twice: once misspelt ("mobil data not wrking", "blutooth wont pair
with my car", "my phone tiem is in 24 hr") and once spelt correctly. Each order was run on a freshly
started server. Results are in `evaluation/typo_eval_results.json`.

| Mode and order | HTTP errors | Correct spelling gets its own correct plan | Misspelt query gets the same plan as the correct spelling |
|---|---|---|---|
| Offline, misspelt first | 0/24 | 12/12 | 5/12 |
| Offline, correct first | 0/24 | 12/12 | 11/12 |
| Free-tier LLM, misspelt first | 0/24 | 12/12 | 8/12 |

**Cache poisoning found and fixed.** Before this fix, a misspelt query with no recognisable topic words
could get a guessed plan. That plan was cached, and the correctly spelt query was then served the wrong
plan: "mobil data not wrking" got "Screen display damage", and "mobile data not working" received it from
the cache.

Now a plan is cached only if it is grounded:
- built from a reference article,
- built by the settings planner, or
- a guessed plan whose topic, read from its goal and title, matches topic words in the query itself.

A misspelt query still gets an answer, but it is not stored, so it can never spread to other queries. The
held-out paraphrase hit rate is unchanged at 80.4% with 0 wrong hits.

**What is still limited.** The misspelt query itself can get a weaker plan when no LLM is available (7/12
offline differ, mostly the generic "System startup failure"). The LLM fixes most of these, but not all.
The settings planner, reference matching and the "nothing to go on" check read the raw query before the
LLM sees it, so "my phone tiem is in 24 hr" is refused in both modes. A spelling-correction step was
prototyped with a vocabulary taken from the catalog and reference articles. It cost about 5 ms per
query, but it also changed correct words ("hrs" became "has") and missed some typos ("blury"), so it was
not shipped. A stronger model with thinking enabled would handle more typos, but it would push cold
requests past the 8 s target on the free tier.

## 10. Docker

```bash
./start.sh          # or .\start.ps1 on Windows; press Enter at the key prompt for the free tier
```

The image was built from a clean cache and started through `start.sh` with an empty key. Results:

- Image size: 724 MB, including the embedding model and the catalog vectors, so the container needs no
  download at run time.
- `/health` returned `ok` after the 20 official plans were pre-warmed without LLM calls.
- `GET /v1/metrics` reported provider `free_tier`.
- A Wi-Fi complaint took 5.7 s cold (3 LLM calls), its paraphrase took 27 ms from the cache, an off-topic
  question returned `no_match`, and "turn off bluetooth" returned a Bluetooth Configuration plan.
- The frontend at `http://localhost:5500` rendered plans, trace data and contract checks from the API.

## 11. Known limitations

- **Misspelt queries.** A misspelt query without recognisable topic words can get a generic plan or a
  refusal, especially without an LLM (§9). It no longer affects the answer to the correctly spelt query.
- **Offline relevance.** Without an LLM, look-alike queries worded like real complaints can get a plan:
  another device ("my laptop battery drains fast") or small talk ("the weather is too hot today"). With the
  free tier or an OpenAI key the LLM rejects them.
- **Settings requests with unusual wording.** Requests worded unlike anything in the catalog ("share my
  internet with my laptop") can miss the settings planner: 8 of 19 held-out requests.
- **Unparseable reference articles.** 5 of the 20 reference articles have no step structure the parser
  can use, so those queries get the domain plan.
- **Shortened official queries.** A shortened rewording of an official query can be matched to a
  neighbouring reference article. For example, "Flip 6 screen flickers and goes blank whenever I open it"
  was matched to the email article of official query 1. The full official texts all map to their own
  article.
- **Deeplink coverage.** 12 of 25 auto actions on the official queries have no catalog deeplink (see §3).
- **Free-tier latency.** A cold request with the free tier takes about 5–6 s, inside the 8 s target but
  well above a paid provider. Cache hits are unaffected.
- **Single-process cache.** The cache lives in one process. Several workers would need a shared store
  such as Redis.
- **Benchmark size.** The paraphrase benchmark is small and was written by the team, so the official
  evaluation set may behave differently.
