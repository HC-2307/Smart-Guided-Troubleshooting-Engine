# M3 robustness report

Branch `HC_M3_config_plans`. This report records how the engine was stress-tested, what broke,
what was changed, and what is still open. All numbers are from runs without an LLM unless stated,
so they show the behaviour the system falls back to when no provider is available.

## What was tested

| Test | What it checks | Where |
|---|---|---|
| Unit and integration suite | 394 tests, including every fix below | `tests/` |
| Labelled end-to-end evaluation | 20 official queries, 126 troubleshooting paraphrases, 40 settings requests (19 held out), 30 off-topic traps, 17 adversarial inputs | `evaluation/robustness_eval.py` |
| Adversarial API tests | empty, oversized and wrong-type inputs; emoji; Hindi; SQL and script strings; prompt injection asking for URLs; URLs and code fences inside the reference text | `tests/test_robustness.py` |
| Concurrent load | 580 requests from 16 workers against a live server; answers for identical queries must match | `evaluation/load_test.py`, `tests/test_load.py` |
| Live LLM providers | OpenAI key without credits, Gemini free tier, NVIDIA Nemotron free tier | manual runs |
| Docker | image build, health, restart with the persisted cache | manual runs |

Every response in the adversarial and load tests is checked for: no server error, valid schema,
no URL anywhere in the body, catalog-only deeplinks, no deeplink on manual actions, critical
actions last, and a plan present exactly when there is no fallback.

## What broke and what was fixed

| # | Finding | Cause | Fix |
|---|---|---|---|
| 1 | The spec's own request format (`"siis_response": "<raw text>"`) returned HTTP 422 | The request model only accepted an object | Accept raw text or an object; blank text counts as absent; over 20,000 characters is rejected |
| 2 | All 20 official queries got the same generic "Screen display damage" plan without an LLM | The fallback ignored the reference text | New reference parser builds plans from the SIIS article's step sections; 15 of 20 references parse, and every parsed step's words appear in the source text. The rest keep the domain plans |
| 3 | Settings questions (*"my phone time is in 24 hrs"*) got "System startup failure" | No settings plans existed | Catalog-grounded Configuration plans; keyword matching plus a meaning-based fallback (bge-small embeddings). Held-out settings requests: 6/19 correct with keywords only, 10/19 now, 0 wrong settings plans throughout |
| 4 | Short or unrelated queries borrowed an unrelated reference article (*"my"* matched "Email server not responding") | Reference matching accepted any substring and counted words like "the" and "my" | Substring matching only for long queries; overlap counts only meaningful words and must cover half the query. All 20 official queries still map to their own article |
| 5 | *"change to light mode"* was classified as a performance problem | Domain keywords matched inside words ("c**hang**e", "prog**ram**") | Keywords match at word starts only; 0 of 146 official and paraphrase queries changed domain |
| 6 | Topicless questions got an invented "System startup failure" plan | The fallback domain was used when nothing matched | New `no_siis_context` fallback when there is no reference text and no recognisable topic (typo tolerant) |
| 7 | A slow LLM provider made requests take 30–60 s | Each LLM call waited up to 10–15 s and retried | Shared per-request budget and circuit breaker for all LLM calls; live NVIDIA test now under 8 s per request, and the model is skipped for 60 s after repeated failures |
| 8 | Nemotron and newer Gemini models returned thinking text or empty replies | Thinking models spend the token budget on reasoning | `LLM_EXTRA_BODY` and `LLM_REASONING_EFFORT` settings pass the provider's switch to turn thinking off |
| 9 | Without an LLM, 5 of 30 off-topic traps got a plan (*"best wifi router to buy"*) | Word lists cannot tell device words from device problems | Embedding comparison against labelled in- and out-of-scope examples; now 1 of 30 |
| 10 | The cache was lost on every restart | In-memory only | Atomic saves to disk every few seconds and on shutdown; the 20 official queries are pre-warmed and pinned at startup |
| 11 | Under 16 concurrent users, new queries took p95 6.7 s and cache hits up to 6.4 s | The cache held one lock while fingerprinting queries; the embedding runtime oversubscribed the CPU | Fingerprints are computed outside the lock; one runtime thread per request. Warm server: p95 45 ms at 181 requests/s |
| 12 | Identical queries got different answers under load | Concurrent copies of a new query raced; a query answered by similarity could later match a different entry | Identical in-flight requests are coalesced; a similarity answer is pinned to the query with an exact alias. 0 inconsistent answers in repeated runs |
| 13 | A cache hit rejected by the offline relevance check was still served | A branch in the orchestrator skipped the rejection path | Fixed; tests fail when the old branch is restored |
| 14 | Three tests could never fail | They asserted `cache.lookup(...) is not None`, which is always true | They now assert on `.response`; the scenarios were rebuilt with queries that really hit the cache |
| 15 | A misspelling-free SQL string got a plan after adding the embedding check | Topic evidence matched "sim" inside "simpler" and corrected "drop" to "drops" | Topic words need whole-word endings; typo correction only for words of 5+ letters |
| 16 | The action order did not follow the spec's plan hierarchy | Only "critical last" was enforced | Validator orders toggles → optimizations → reboots → service → critical; the one M1 plan out of order (storage) was fixed at the source |

## Results

| Measure | Before this branch's robustness work | Now |
|---|---|---|
| Official queries with a plan | 20/20, 1 distinct plan | 20/20, 10 distinct reference-grounded plans |
| Troubleshooting paraphrases with a plan | 126/126 | 126/126 |
| Held-out settings requests correct | 6/19 | 10/19, 0 wrong settings plans |
| Off-topic traps given a plan | 5/30 | 1/30 |
| Adversarial inputs causing an error or a URL leak | not tested | 0 |
| Paraphrase cache hit rate (held out) | 80.4% | 80.4% |
| Load: throughput, p95 | 35 requests/s, 6.7 s | 181 requests/s, 45 ms |
| Inconsistent answers under load | 1 query | 0 |
| M1 schema benchmark | 20/20 | 20/20 |

## Still open

- Offline relevance accepts look-alikes worded like real complaints: another device (*"my laptop
  battery drains fast"*) or a figure of speech (*"my patience drains really fast"*). Their
  embedding margins overlap with real typo and settings questions, so no threshold separates
  them without losing real questions. The LLM check handles them when a key is set.
- The offline mode accepts *"the weather is too hot today"*.
- 5 held-out settings requests still get no plan and 4 get a troubleshooting plan instead, when
  their wording shares nothing with the catalog (*"share my internet with my laptop"*).
- 5 of 20 reference articles do not parse (glued source text or no step structure) and keep M1's
  domain plans.
- A freshly started server can take up to about 3 s for a burst of 16 simultaneous new queries.
  Multiple workers would need a shared cache.
- The Docker image grew from about 310 MB to about 720 MB because of the embedding model.

## How to re-run

```bash
python -m pytest -q
python evaluation/robustness_eval.py
python evaluation/benchmark_m3.py
uvicorn backend.main:app --port 8000 &
python evaluation/load_test.py http://localhost:8000 16 10
```
