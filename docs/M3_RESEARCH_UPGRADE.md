# M3 Research Upgrade — Guarded Semantic Cache, Contract Compiler, Traceable Pipeline

Owner: M3 (backend / orchestration / cache / final validation). Branch: `HC_M3_research_upgrade`.
All numbers in this document were measured with `python evaluation/benchmark_m3.py`
(results: `evaluation/benchmark_m3_results.json`) on Python 3.14.2 with the LLM provider
disabled, so M1 ran its deterministic fallback. Nothing here is estimated unless it says so.

---

## 1. The problem M3 had before this upgrade

| Graded requirement (Theme 2 PDF) | State before the upgrade |
|---|---|
| ≥80% cache hit rate on **paraphrased** queries | Exact-string cache (lowercase + whitespace). **0%** hit rate on paraphrases (measured, config A). |
| P95 ≤300 ms on hit, ≤8 s cold | Met, but nothing measured it inside the service. |
| Zero URL leakage, enforced in code | Only a URL regex over text fields. |
| Catalog integrity, no invented deeplinks | Trusted to M2. M3 never re-checked what reached the client. |
| Deterministic execution, per-query cost tracking | No request IDs, stage timings, or cost accounting. |
| Unexpected exception → log request ID, controlled error | An unhandled exception became a bare 500. |
| `/health` ok only once indexes are ready | Always returned ok. |

The live system test also found a correctness bug that no M3 check could see. The
action **"Enable Power Saving Mode"** was delivered with the catalog deeplink
**"Disable Power saving"** (`originalType: offURL`), a *real* catalog URI that does the
opposite of what the step says.

---

## 2. Related research and the gaps we found

### 2.1 Semantic caching for LLM services

| Work | What it does | Gap for our use case |
|---|---|---|
| **GPTCache** (Bang, NLP-OSS @ EMNLP 2023) | Embeds queries and returns a cached answer when cosine similarity passes a threshold. Motivated by keyword caches' low hit rate. | One global threshold. Needs an embedding model. No notion of "similar text, different fix" (front vs rear camera). |
| **MeanCache** (Gill et al., arXiv 2403.02694, IPDPS 2025) | User-side semantic cache with a small embedding model (MPNet) and context-chain matching. Reports ~31% of queries are repeats. | Still an embedding + threshold decision. Focused on privacy and conversation context, not domain-safety. |
| **vCache** (Schroeder et al., arXiv 2502.03771) | Shows static thresholds give no correctness guarantee. Learns a threshold **per cached prompt** online, with a user-set error bound. | Needs online feedback on correctness, which we don't have for new complaints at inference time. Adds learning machinery. |
| **Category-Aware Semantic Caching** (Wang et al., arXiv 2510.26835) | Different query categories need different thresholds and TTLs. A fixed threshold causes false positives in dense regions. | A position paper at workload level. Doesn't handle *intra*-category contradictions (enable vs disable, Wi-Fi vs mobile data). |
| **Krites** (Singh et al., arXiv 2602.13165, EuroMLSys 2026) | Uses an LLM judge to verify near-miss hits asynchronously and promote them. | The verification is itself an LLM call. That adds cost and non-determinism, which our spec explicitly penalises. |

**Gap 1: safety of a hit.** All of these decide a hit mainly by embedding distance.
In troubleshooting, two sentences can be about 90% the same words and still need
**different fixes**: *front* vs *rear* camera, *drains* vs *won't charge*, *turn on* vs
*remove*. A wrong hit here is worse than a miss, because the user gets a confident, wrong
plan.

**Gap 2: cost of verification.** The published fixes for Gap 1 are learned per-entry
thresholds (vCache) or an LLM judge (Krites). Both need extra machinery or model calls.
Our spec asks for determinism and per-query cost control.

**Gap 3: unused signal.** Theme 2 forces the pipeline to produce **8–10 query
paraphrases** (`query_variations`) for every answer. We found no cache in the works above
that uses the application's own mandated paraphrase output as extra cache keys.

### 2.2 Output validation for structured LLM output

| Work | Relevance |
|---|---|
| **Let Me Speak Freely?** (Tam et al., EMNLP 2024 Industry, arXiv 2408.02442) | Strict format constraints during generation can **degrade LLM reasoning**. This supports validating and repairing *after* generation instead of forcing everything into the decoder. |
| **NeMo Guardrails** (Rebedea et al., EMNLP 2023 Demos) | Programmable, interpretable "rails" around LLM apps, mostly dialogue- and topic-level. |
| **Self-Refine** (Madaan et al., NeurIPS 2023) | Iterative self-feedback repair. Effective, but each round is another LLM call. |
| **Gorilla** (Patil et al., arXiv 2305.15334) | LLMs **hallucinate API calls**, and retrieval grounding reduces it. Our deeplinks are the same kind of thing as API calls. |

**Gap 4: a validity check isn't the same as a correctness check.** JSON-schema validation
checks types. Guardrail rails check topics. Neither checks graded business rules (word
counts, "It will" prefix, critical-last ordering, manual = no deeplink, catalog
membership). They also don't catch a deeplink that exists in the catalog and is
well-formed but has **inverted meaning** (enable vs disable). Gorilla-style grounding
checks that the API *exists*, not that it does what the step says.

---

## 3. What we built and why each part is new

### N1. Paraphrase-seeded cache keys with a consistency filter (`backend/services/cache.py`)

When a plan is stored, its `query_variations` are stored as extra keys pointing to the same
entry. The cache "pre-learns" paraphrases it hasn't seen yet, at zero extra cost, because
the pipeline already had to generate them.

Seeding without a filter is dangerous, and the live test proved it. M1's fallback
variations for a *front*-camera complaint mention the *rear* camera, so a later rear-camera
query was served the front-camera entry. The fix works at two points:

- **At store time:** any variation whose facets contradict the original query is dropped.
  15 were dropped during the benchmark run.
- **At lookup time:** the query must agree with the entry's *original* query, not only
  with the key it matched.

### N2. Deterministic, explainable hit verification (`text_similarity.py`, `cache.py`)

Instead of a learned threshold or an LLM judge, a candidate hit must pass two checks, each
of which gives a readable reason when it rejects:

- **Domain-evidence guard.** It uses M1's own `DOMAIN_KEYWORDS`, so the cache and the
  planner can't disagree. A query with no domain evidence ("remove floating button") is
  treated as *unknown* and isn't blocked.
- **Facet-conflict guard.** Facet groups: camera side, fold screen (inner/outer), radio
  (Wi-Fi/Bluetooth/mobile data/NFC), power issue (drain/charge-fail), and polarity (on/off).
  A hit is refused when both queries name a value in the same group and the values differ.

It adds no model calls, it's deterministic, and every rejection is counted in
`/v1/metrics`.

### N3. Catalog-grounded, dependency-free similarity (`text_similarity.py`)

- **Concept canonicalisation:** a lexicon maps phrases ("loses charge", "won't charge",
  "out of focus") to intent concepts (`drain`, `chargefail`, `blurry`). Device model names
  (S22, A15, Flip 7) and filler words are removed.
- **Typo repair:** out-of-vocabulary words are corrected **only toward the small intent
  vocabulary**. Correcting toward the full catalog turned "front" into "font" and "rear"
  into "ear", and a unit test caught it.
- **Weighting:** concepts get a fixed high weight. Other words use IDF computed from the
  **trusted deeplink catalog**, capped so generic words the catalog rarely uses ("during",
  "normal") can't dominate.
- **Score:** 0.75 × weighted cosine + 0.25 × character-trigram Jaccard. A candidate
  shortlist comes from an inverted index.

It needs no embedding model, GPU, or new dependency. A hit costs about 5 ms server-side,
including the whole HTTP stack.

### N4. Contract compiler with repair and quarantine (`backend/services/contract_validator.py`)

The graded contract (Theme 2 §4.1 / §7) becomes executable rules with **violation codes**.
Each violation gets the least destructive outcome:

| Outcome | Examples |
|---|---|
| **repaired** (answer kept) | untrusted deeplink removed · catalog metadata restored · manual deeplink removed · critical moved last · Title Case · score clamped · markdown stripped · duplicate action dropped · variations de-duplicated and trimmed |
| **quarantined** (only the smallest invalid unit is dropped) | description not "It will" + 5–7 words · URL / markdown link / raw scheme in a step · invalid category · empty steps. The action is dropped, not the whole answer. A bad goal phrasing or title drops that goal. |
| **fallback** | nothing valid left → `contexts: []`, `fallback: "validation_failed"` |

This follows the "validate after generation" lesson from *Let Me Speak Freely?*, but without
Self-Refine's extra LLM rounds.

### N5. Toggle-polarity verification of deeplinks

The catalog marks 138 entries `onURL` and 138 `offURL`. M3 compares the action's intent
("Enable…", "Turn off…", "Remove…") with the entry's polarity. On a mismatch the deeplink is
removed (code `TOGGLE_POLARITY_CONFLICT`) rather than sending the user to a switch that does
the opposite. This goes past Gorilla-style "does the API exist" grounding to "does the API
do what the step says". It fixed the live Power Saving bug.

### N6. Traceable pipeline without changing the frozen contract (`telemetry.py`, `main.py`)

- **Response headers** (the body schema is unchanged, which a test enforces):
  `X-Request-ID` (echoed from the caller if sent), `X-Cache` (miss / exact / semantic /
  variation), `X-Pipeline-Ms`, `X-LLM-Calls`, `X-Est-Cost-USD`.
- **`GET /v1/metrics`:** hit rate by tier, p50/p95 latency for the hit and cold paths
  separately, validation codes, guard rejections, estimated cost.
- **Failure contract (playbook §8.5):**
  - Cache failures fail open: the request continues and the error is recorded.
  - Unexpected exceptions return a controlled `500 {"contexts": [], "fallback": "internal_error"}`
    with the request ID and no internal details.
  - `/health` warms the catalog, M2 engine and IDF index, and returns 503 if that fails.
  - Blank or oversized queries return 422.

### Also: exact M2 resolution memo (`query_processor.py`)

M2's matcher takes about 190 ms per plan (a `SequenceMatcher` over all 578 catalog
entries). The catalog is static and resolution is deterministic, so M3 memoises it by the
plan's canonical JSON. This is exact memoisation, not semantic, with bounded LRU and copies
on read and write.

Other design choices:

- Requests carrying their own `siis_response` bypass the cache, because the same text with
  different evidence can need a different plan.
- Only clean, successful responses are cached. `no_match` and `validation_failed` are never
  cached.

---

## 4. Evaluation

### 4.1 Protocol

- **Dataset:** `evaluation/m3_paraphrase_set.json`, written **before** any threshold was
  tuned.
  - 14 intents, each with a seed and 8 paraphrases across registers: casual, formal,
    panicked, terse, verbose, typo.
  - 12 **hard-negative probes**: near-miss complaints that must *not* be served a cached
    answer (front vs rear camera, mobile data vs Wi-Fi, turn on vs remove, microphone vs
    speaker, and so on).
- **Split:** even-index paraphrases and probes form the **dev** split (tuning). Odd-index
  ones form the **held-out test** split. Each split has 56 paraphrases and 6 probes.
- **Seeds:** cached through the real M1 → M2 → contract-validator pipeline.
- **Tuning:** each config gets its own thresholds, chosen on dev as the highest hit rate
  with **zero wrong hits and zero probe false hits**. A tie goes to the stricter threshold.
- **Metrics:**
  - *hit rate* = correct-intent hits / paraphrases
  - *wrong hit* = served another intent's answer
  - *probe FP* = a probe got any cached answer

### 4.2 Results: held-out test split

| Config | Thr. (sem/var) | Hit rate | Wrong hits | Probe FP |
|---|---|---|---|---|
| A. Exact cache (the old M3) | — | **0.0%** (0/56) | 0 | 0/6 |
| B. Semantic, no guards, no seeding | 0.65 / 0.65 | 64.3% (36/56) | 0 | 1/6 |
| C. Semantic + guards | 0.60 / 0.60 | **75.0%** (42/56) | 0 | 1/6 |
| D. Semantic + guards + seeding (**shipped**) | 0.60 / 0.60 | **80.4%** (45/56) | 0 | 1/6 |
| E. D with query-specific variations (simulated LLM) | 0.60 / 0.60 | 76.8% (43/56) | 0 | 1/6 |

On dev, D scored 96.4% (54/56) with 0 wrong hits and 0/6 probe FP.

What the numbers show:

- **The guards are what allow a lower threshold safely.** Without guards, B needs 0.65 to
  have zero false hits on dev, and gets 64.3% on test. With guards, 0.60 is safe, and C
  gets 75.0%. That is +10.7 points on held-out data with no wrong hits added. Across the dev
  grid at thresholds ≤0.55, the guards also cut probe false hits from 4 to 3.
- **Seeding helps only when the variations are real paraphrases.**
  - Originally M1's deterministic fallback returned one canned list per domain; every
    connectivity query got Smart Switch paraphrases, and audio/storage got boot-loop ones.
    D then only tied C (75.0%).
  - After the fallback was made subtopic-aware (Wi-Fi, Bluetooth, mobile data, Smart
    Switch, general network, plus audio and storage lists), D reached 80.4%: 12 of its 45
    test hits came through variation keys, recovering three misses C cannot catch
    ("loses its wireless LAN connection" and both storage-full paraphrases). A first draft
    of the Bluetooth list mixed disconnect and pairing phrasing and caused a dev probe
    false hit, which pushed tuning to 0.85; it was narrowed to pairing only.
  - In E we used the dev paraphrases as stand-ins for the query-specific variations a live
    LLM would produce, and got 76.8%. That is a simulation, and we label it as one. We did
    **not** run the live LLM path: the configured OpenAI key returned
    `429 insufficient_quota`.
- **The only false hit on test** is the compound probe *"Battery drains fast and it also
  won't charge past 50 percent"*, served the battery-drain plan. We pre-labelled it a hard
  negative. It is arguably half-correct.

### 4.3 Latency (API, through FastAPI, 70 requests)

| Path | Server-side p50 | Server-side p95 | Spec target |
|---|---|---|---|
| Cache hit | 5.1 ms | **7.9 ms** | ≤300 ms |
| Cold (full M1 → M2 → validate) | 19.2 ms | **27.3 ms** | ≤8 s |

Client-side wall time through `TestClient` adds about 6 ms on hits (hit p95 16.4 ms). The
client-side cold p95 is 226.7 ms, because each new distinct plan pays one first-time M2
resolution (~190 ms) before the memo takes over. In a real `uvicorn` run, the first cold request of a new domain took up to 525 ms,
because M2 resolved a plan it hadn't memoised yet. That is still far under 8 s.

### 4.4 Contract audit on the 20 official `data/input.txt` queries

All 20 responses were delivered with **0 repairs and 0 quarantines**. The validator adds
safety without disturbing valid output. On the live battery query it repaired
`TOGGLE_POLARITY_CONFLICT`, which is the Power Saving bug.

### 4.5 Tests

- **165 passing**, up from 53 (127 after the upgrade, plus 31 regression tests for the teammate-code fixes in §6, plus 7 for the subtopic-aware enrichment fallback).
- New: `test_similarity.py` (10), `test_contract_validator.py` (27).
- Rewritten or extended: `test_cache.py` (24), `test_api.py` (13), `test_integration.py` (11).
- `tests/conftest.py` now strips LLM keys (opt back in with `M3_TESTS_ALLOW_LLM=1`) and
  clears the cache between tests, so the suite is deterministic and can't make billed calls.

---

## 5. Limitations (read before quoting numbers)

1. **We only just meet the graded ≥80% on this test set: 80.4%.** Remaining misses are
   mostly formal or verbose paraphrases with no shared vocabulary ("Applications terminate
   abnormally", "Touch input exhibits significant latency"). A lexical method has this ceiling.
   Next step: a small local sentence-embedding model as a *third* similarity signal, still
   behind the same guards.
2. **The benchmark is small and self-written:** 112 paraphrases and 12 probes from one
   developer. The official evaluation set may behave differently.
3. **Tuning history, disclosed in full:**
   - v1 of the similarity scored 48.2% on test.
   - We saw the test misses once, then revised the method using **dev misses** only.
   - v2 had a regex bug that silently disabled the domain guard.
   - v3/v4 fixed that bug and the typo-correction bug.

   All thresholds were re-selected on dev each time. Some indirect test leakage through
   lexicon choices can't be ruled out.
4. **The lexicon and facet groups are hand-written.** New complaint types need new entries.
5. **Cost is an estimate:** 2 LLM calls × `LLM_COST_PER_CALL_USD` when a provider is
   configured, 0 on a cache hit or the deterministic path. It isn't metered tokens, because
   M1's client doesn't expose usage.
6. **The cache is in-process.** Several uvicorn workers won't share it. A Redis backend
   would be the production path.
7. **The Docker build is still unverified.** The Docker Desktop engine wasn't running on the
   dev machine.

---

## 6. Upstream fixes made on this branch

The M3 validator found these problems; they are now fixed **at the source** on this branch
only (not on `main`), so the validator no longer has to repair anything on the 20 official
queries or on the new domain probes (a test enforces zero repairs):

- **M1 plans:** connectivity, audio, storage and system complaints used to fall back to the
  display plan. They now have their own plans. The network plan keeps only the radio the
  user named (Wi-Fi, Bluetooth or mobile data). Connectivity reports without network words
  (the two official Smart Switch blank-screen queries) still get the screen plan.
- **M1 descriptions:** every action description is now a complete 5–7 word sentence (e.g.
  "It will show which apps drain battery."), not a 50–70 word paragraph cut off mid-phrase
  ("It will allow you to inspect.").
- **M2 polarity:** the matcher excludes catalog entries whose `onURL`/`offURL` polarity
  contradicts the action, and neutral actions ("Back Up Phone Data") can no longer map to a
  Disable toggle. Power Saving now resolves to "Enable Power saving".
- **M2 critical safety:** a critical action no longer accepts a weak semantic match.
  "Reset Network Settings" had been linked to the *auto factory reset* page.
- **M2 benchmark:** `data/scenarios.json` was empty. It is now built from
  `siis_responses.json` (query + SIIS title, `expected_catalog_ids` left empty for manual
  review), and the script sets its own import path.

M3's validator stays in place as defence in depth, and the paraphrase benchmark numbers in
§4.2 are unchanged by these fixes.

## 7. References (all verified to exist, September 2026)

1. F. Bang. *GPTCache: An Open-Source Semantic Cache for LLM Applications Enabling Faster Answers and Cost Savings.* NLP-OSS Workshop @ EMNLP 2023. aclanthology.org/2023.nlposs-1.24
2. W. Gill et al. *MeanCache: User-Centric Semantic Caching for LLM Web Services.* arXiv:2403.02694; IEEE IPDPS 2025.
3. L. G. Schroeder, A. Desai, A. Cuadron, K. Chu, S. Liu, M. Zhao, S. Krusche, A. Kemper, M. Zaharia, J. E. Gonzalez. *vCache: Verified Semantic Prompt Caching.* arXiv:2502.03771.
4. C. Wang, X. Liu, Y. Zhu, A. Youssef, P. Nagpurkar, H. Chen. *Category-Aware Semantic Caching for Heterogeneous LLM Workloads.* arXiv:2510.26835.
5. A. K. Singh, H. Wang, L. N. S. Attaluri, T. Chiam, W. Zhu. *Asynchronous Verified Semantic Caching for Tiered LLM Architectures (Krites).* arXiv:2602.13165; EuroMLSys 2026.
6. Z. R. Tam, C.-K. Wu, Y.-L. Tsai, C.-Y. Lin, H.-y. Lee, Y.-N. Chen. *Let Me Speak Freely? A Study on the Impact of Format Restrictions on Performance of Large Language Models.* EMNLP 2024 Industry Track; arXiv:2408.02442.
7. T. Rebedea, R. Dinu, M. N. Sreedhar, C. Parisien, J. Cohen. *NeMo Guardrails: A Toolkit for Controllable and Safe LLM Applications with Programmable Rails.* EMNLP 2023 System Demonstrations, pp. 431–445.
8. S. G. Patil, T. Zhang, X. Wang, J. E. Gonzalez. *Gorilla: Large Language Model Connected with Massive APIs.* arXiv:2305.15334.
9. A. Madaan et al. *Self-Refine: Iterative Refinement with Self-Feedback.* NeurIPS 2023; arXiv:2303.17651.

---

## 8. How to reproduce

```bash
python -m pytest -q                      # 158 tests, deterministic
python evaluation/benchmark_m3.py        # writes evaluation/benchmark_m3_results.json
uvicorn backend.main:app --port 8000     # then GET /health, POST /v1/troubleshoot, GET /v1/metrics
```

Every tuned value can be overridden by an environment variable. See `.env.example`
(`SEMANTIC_CACHE_THRESHOLD`, `SEMANTIC_CACHE_VARIATION_THRESHOLD`,
`SEMANTIC_CACHE_SEED_VARIATIONS`, `SEMANTIC_CACHE_ENABLED`, `CACHE_TTL_SECONDS`,
`CACHE_MAX_ENTRIES`, `MAX_QUERY_CHARS`, `LLM_COST_PER_CALL_USD`).
