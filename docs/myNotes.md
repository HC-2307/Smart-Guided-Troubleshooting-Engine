# My Notes — The Whole Project, Taught From Zero

> How to read this: it's written like a teacher talking to a student who has never seen
> this project. Read it top to bottom once. Each "Lesson" builds on the previous one. The
> "Try it" boxes are commands you can run yourself. The quiz at the end checks whether it
> stuck. My original development log from 20 Sep is kept at the very bottom.

---

## Lesson 0 — What are we even building?

**Teacher:** Imagine your mum types into her Samsung phone: *"my battery dies so fast and
the phone gets hot."* What does she actually want?

**Student:** Someone to tell her what to do?

**Teacher:** Exactly. And not an essay. She wants:

1. a short list of **things to try**, in a sensible order (easy ones first, scary ones like
   "factory reset" last),
2. each one broken into **tiny tap-by-tap steps** ("Open Settings", "Tap Battery"),
3. ideally a **button that jumps straight to the right Settings screen**, so she doesn't
   have to hunt for it.

That jump-button is called a **deeplink**. Our project, the *Smart Guided Troubleshooting
Engine*, is the server that turns her messy sentence into that clean, ordered, clickable
plan, returned as **JSON** that a phone app can draw on screen.

**Student:** Why JSON and not just text?

**Teacher:** Because a *program* (the phone app) reads it, not a human. Programs need a
fixed shape: "the title is always in the field called `title`". A human-friendly paragraph
would be impossible for the app to turn into buttons.

---

## Lesson 1 — The competition and its rules

This is **Samsung PRISM GenAI Hackathon 2026, Theme 2**. Samsung gave us:

- a **PDF spec** (the "graded contract"): the exact JSON shape and rules the judges check,
- a **data kit** in `data/`,
- a **deadline**: final submission 25 Sep 2026, 11:59 PM, with a team milestone on 21 Sep.

Remember one rule forever: **when the team playbook and the Samsung PDF disagree, the PDF
wins.** Three real examples from this project:

| Topic | Playbook said | PDF (wins) says |
|---|---|---|
| Action description length | 50–70 words | **exactly 5–7 words, starting "It will"** |
| Category name | "standard" | **`auto` / `manual` / `critical`** |
| API path | `/api/v1/troubleshoot` | **`/v1/troubleshoot`** |

**Student:** Why does it matter so much?

**Teacher:** Because the judges run an automatic checker. If you send `/api/v1` and the
checker calls `/v1`, your whole system scores zero, even though it "works on your laptop".
That happened to us early on and we caught it.

---

## Lesson 2 — The team: four jobs, four people

A good way to build something big is to cut it into pieces with **clear hand-offs**.

| Member | Code name | Job | Main files |
|---|---|---|---|
| arav | **M1** | Understand the complaint (LLM / query enrichment) and write the plan | `backend/services/query_enrichment.py`, `troubleshooting_engine.py` |
| geetika | **M2** | Find the right deeplink in Samsung's catalog for each action | `action_matcher.py`, `deeplink_resolver.py`, `sequence_engine.py`, `m2_engine.py` |
| **Harshit (me)** | **M3** | The backend: API, orchestration, **cache**, **final validation**, Docker, integration tests | `backend/main.py`, `api/`, `orchestrator.py`, `cache.py`, validators, `config.py`, tests |
| asmi | **M4** | Frontend, evaluation, demo | `frontend/` (empty so far) |

**Teacher:** M3 is like the **conductor of an orchestra plus the security guard at the
door**. I don't play the violin (M1) or the drums (M2), but I make sure everyone plays in
order, nothing wrong leaves the building, and repeat questions get answered instantly.

**Rule:** never silently change a field someone else depends on. If M4's frontend reads
`contexts`, I may not rename it. That's why all my new information goes into **HTTP
headers** and a **new endpoint** rather than into the JSON body.

---

## Lesson 3 — The data kit (what Samsung gave us)

Open the `data/` folder. The important files:

- **`deeplinks.json`**: the **catalog**. 578 entries. Each one looks like:
  ```json
  { "id": "DL-0001",
    "deeplink": "bixby://masked/act/aa73a35e8d",
    "description": "Opens the 24-hour time format settings page ...",
    "message": "Switch Time Format",
    "originalType": "onClickURL",
    "qna_description": "Switches between 12-hour and 24-hour time format ..." }
  ```
  The URI is **masked**: `aa73a35e8d` means nothing. So how do you find the right one?
  **You read the description, message and qna_description**, never the URI itself. That's
  a graded rule. `originalType` tells you what the link does: `onURL` turns something
  **on**, `offURL` turns it **off**, `onClickURL` just opens a page. Remember this; it
  becomes important in Lesson 9.
- **`bixby://dummy_positive`**: one special placeholder, for "this is a real Settings
  screen, but it isn't in the catalog".
- **`siis_responses.json`**: Samsung's internal knowledge articles, one per official query.
  "Derive steps from this text, don't invent steps."
- **`input.txt`**: the **20 official test complaints** (mostly screen problems on Galaxy
  phones, tablets and Flips).
- **`schema.py`**: the official **Pydantic** model of the response. Pydantic is a Python
  library that says "this dict must have these fields of these types", and raises an error
  if not.
- **`sample_output.json`**: an example of a correct answer.

---

## Lesson 4 — The answer, field by field

Here is a real answer (shortened) for *"phone battery drains fast"*:

```json
{
  "contexts": [{
    "goal":  "Follow these steps to perform this Battery Troubleshooting",
    "title": "Battery drain issue",
    "score": 0.95,
    "actions": [
      { "actionName": "Check Battery Usage",
        "description": "It will allow you to inspect.",
        "category": "auto",
        "stepGroups": [{
          "steps": ["Navigate to and open Settings.", "Tap on Battery and device care.", "Select Battery ..."],
          "actionableDeeplink": { "deeplink": "bixby://masked/act/f1b4aa5570", "message": "Check Battery Performance", ... }
        }]
      },
      { "actionName": "Restart Device in Safe Mode", "category": "critical", ... }
    ]
  }],
  "query_variations": ["My Galaxy phone battery drains unusually fast ...", "... 8 to 10 of these ..."],
  "fallback": null
}
```

Walk through it like a checklist (these are the graded rules):

- `goal` must be **exactly** "Follow these steps to perform this *<Topic>* Troubleshooting"
  (or Configuration).
- `title`: **2–3 words**, sentence case.
- `score`: a number between 0.0 and 1.0.
- `actionName`: **Title Case**. **One action = one screen.** If two steps happen on the
  same screen, they belong to the same action.
- `description`: **exactly 5–7 words, starting "It will"**.
- `steps`: one physical tap each, **no URLs, no links**.
- `category`:
  - `auto`: we can jump there with a deeplink.
  - `manual`: needs a human or physical action (e.g. "visit a service centre"). It must
    **not** carry a deeplink.
  - `critical`: disruptive or irreversible (factory reset, safe-mode reboot). It must come
    **last**.
- `actionableDeeplink`: copied **verbatim** from the catalog, never invented.
- `query_variations`: 8–10 different ways a person might phrase the same complaint.
- `fallback`: `null` when all is well; `"no_match"` when nothing fits; our own
  `"validation_failed"` / `"internal_error"` for controlled failures.

**Student:** Why must critical actions be last?

**Teacher:** Because you don't tell someone to wipe their phone *before* trying "turn on
power saving". The plan should go from gentle to drastic: **toggles → optimisations →
reboots**.

---

## Lesson 5 — Follow one request through the whole machine

This is the most important lesson. Let's trace *"battery draining super quick on my
galaxy"* from the moment it arrives.

```
Phone app
   │  POST /v1/troubleshoot  {"query": "..."}
   ▼
backend/main.py ── middleware starts a RequestTrace (request id, stopwatch)
   │
backend/api/troubleshoot.py ── checks the request (not blank, ≤2000 chars, else 422)
   │
backend/services/orchestrator.py  (the conductor)
   │
   ├─1─► cache.lookup(query) ── HIT? ──► return the stored answer (≈5 ms)
   │                        └─ MISS ─┐
   │                                 ▼
   ├─2─► query_processor.process_query
   │        ├─ M1 enrich_query      → domain, technical_query, 9 query_variations
   │        ├─ M1 generate_plan     → goal/title/actions/steps (no deeplinks yet)
   │        └─ M2 resolve_plan      → attach catalog deeplinks, critical last, manual = none
   │
   ├─3─► contract_validator.validate_and_repair  (M3 security guard #1)
   ├─4─► check_no_url_leakage                   (M3 security guard #2)
   ├─5─► cache.store(query, answer, query_variations)   (only if the answer is good)
   ▼
middleware adds headers: X-Request-ID, X-Cache, X-Pipeline-Ms, X-LLM-Calls, X-Est-Cost-USD
   ▼
Phone app receives JSON
```

**Try it:**
```bash
uvicorn backend.main:app --port 8000
curl -i -X POST localhost:8000/v1/troubleshoot -H "Content-Type: application/json" -d "{\"query\": \"my battery drains fast\"}"
curl -i -X POST localhost:8000/v1/troubleshoot -H "Content-Type: application/json" -d "{\"query\": \"battery dying so quickly\"}"
curl localhost:8000/v1/metrics
```
The first call shows `X-Cache: miss`. The second shows `X-Cache: semantic` and is several
times faster.

---

## Lesson 6 — M1: understanding the complaint (arav's part)

M1 has **two engines**:

1. **LLM mode:** if `OPENAI_API_KEY` or `GEMINI_API_KEY` is set, it asks a large language
   model to rewrite the complaint and write the plan.
2. **Deterministic mode:** if there's no key, or the call fails, it uses hand-written rules:
   - `DOMAIN_KEYWORDS` maps words to a domain. "battery", "drain", "hot" → **battery**;
     "screen", "flicker" → **display**; and so on across 8 domains.
   - Each domain has a prepared plan and 9 prepared `query_variations`.

**Student:** Why keep the boring deterministic mode?

**Teacher:** Three reasons:

- **Reliability:** the demo works without the internet.
- **Cost:** it's free.
- **Determinism:** the same input always gives the same output, which the spec asks for.

Also, today we discovered the API key in the shell has **no credits** (OpenAI answered
`429 insufficient_quota`), so deterministic mode is what actually runs.

**Weaknesses we found (for arav to fix):**

- Wi-Fi, audio and storage complaints fall back to the **display** plan.
- Every battery complaint gets the same "battery drain" plan, even "won't charge".
- The 9 variations are identical for every query in a domain.

---

## Lesson 7 — M2: finding the right deeplink (geetika's part)

M2 takes each action, e.g. "Check Battery Usage", and searches the 578-entry catalog in
three passes:

1. **Exact:** does any entry's `message` equal the action name? (After cleaning case and
   punctuation.)
2. **Keyword:** how many important words overlap, plus a string-similarity score. Accept if
   the combined score ≥ 0.56.
3. **TF-IDF:** a classic "important rare words count more" similarity. Accept if the score
   is high enough.

If nothing is confident, the action gets **no** deeplink. Never a made-up one. M2 also:

- forces **manual** actions to have no deeplink,
- moves **critical** actions to the end.

**Weakness we found:** "Enable Power Saving Mode" was matched to "**Disable** Power saving",
because the words overlap almost perfectly. The words are the same; the meaning is
opposite. Keep this in mind for Lesson 9.

---

## Lesson 8 — M3's cache: answering repeat questions instantly

### 8.1 Why a cache at all?

Running M1 + M2 costs time (and money, when the LLM is on). Many people ask the **same
thing in different words**. If we already answered *"battery drains fast"*, then
*"battery dying so quickly"* should reuse that answer. The spec demands **≥80% cache hits on
paraphrased queries** and **≤300 ms** for a hit.

### 8.2 The old cache and why it scored 0%

The old cache only lower-cased the text and squashed spaces. "Battery drains fast" and
"battery  DRAINS fast" matched. "battery dying so quickly" did **not**: different words. We
measured it: **0% hits on paraphrases**.

### 8.3 The new cache, step by step

**Step A: turn a sentence into a "fingerprint"** (`text_similarity.py`).

1. Lower-case, remove numbering like "1.", fix "wi-fi" → "wifi".
2. **Fix typos**, but only toward our small list of intent words ("battry" → "battery",
   "wify" → "wifi"). Lesson learned the hard way: when we let it snap to *any* catalog word,
   it turned "front" into "font" and "rear" into "ear"!
3. Replace phrases with **concepts**:
   - "loses charge", "dies fast", "draining" → `drain`
   - "won't charge", "not charging" → `chargefail` (a *different* concept!)
   - "out of focus", "fuzzy" → `blurry`
4. Throw away words that don't carry meaning: "my", "phone", "samsung", "galaxy", "really",
   and model names like "S22", "A15".
5. Give each remaining token a **weight**:
   - Concepts get 3.0, because they carry the intent.
   - Other words get their **IDF from the Samsung catalog**, capped at 2.0. IDF means
     "rare words are more informative".

**Real example, computed by the code:**

| Sentence | Tokens | Weights |
|---|---|---|
| "My phone battery drains really fast" | `battery, drain` | battery 3.0, drain 3.0 |
| "battery draining super quick on my galaxy" | `battery, drain, quick` | 3.0, 3.0, 2.0 |

**Step B: compare two fingerprints.**

`similarity = 0.75 × cosine(weights) + 0.25 × character-trigram overlap`

- *Cosine* asks: do the important tokens point in the same direction?
- *Trigrams* ("bat", "att", "tte", ...) forgive small spelling differences.

For the pair above, similarity = **0.849**. Our threshold is **0.60**, so it's a **hit**.

**Step C: the guards.** Now the scary example:

| Sentence | Tokens | similarity |
|---|---|---|
| "Rear camera photos are blurry" | `rear, camera, photo, blurry` | |
| "Front camera photos are blurry" | `front, camera, photo, blurry` | **0.882** |

0.882 is *above* the threshold! A plain semantic cache (like GPTCache) would serve the rear-
camera answer to a front-camera problem. **Wrong answer, delivered confidently.** So we add
two guards:

- **Facet guard.** We know certain word groups are **mutually exclusive**:
  - camera side: front / rear
  - fold screen: inner / outer (cover)
  - radio: Wi-Fi / Bluetooth / mobile data / NFC
  - power: drain / chargefail
  - polarity: turn on / turn off (remove)

  If both sentences name something from the same group, and they're different, then **no
  hit**, whatever the score.
- **Domain guard.** Using M1's own domain keyword list: if the new query clearly talks about
  "camera", it may not reuse a "battery" answer. If a query has **no** domain words at all
  ("remove floating button"), we don't block it, because we simply don't know its domain.

**Step D: seeding with variations.** M1 already writes 8–10 paraphrases for every answer.
We store those as **extra keys** pointing at the same answer, so the cache has "seen"
paraphrases before any user types them. That's free, because M1 had to produce them anyway.

**Step E: the poisoning bug and the consistency filter.** During the live test:

1. Someone asked about the **front** camera.
2. M1's generic variations for the camera domain talk about the **rear** camera.
3. Those were stored as keys for the front-camera answer.
4. A later **rear**-camera question matched one of those keys and got the front answer.

Fix: before storing a variation, check it doesn't contradict the original question; if it
does, drop it. At lookup, the query must also agree with the entry's *original* question.

**Step F: housekeeping.**

- **TTL:** answers expire after an hour.
- **LRU:** keep at most 5000 answers, and throw out the least recently used first.
- **Lock:** FastAPI runs requests in parallel threads, so the cache is protected by a
  thread lock. Without it, two threads editing the same dict could corrupt it.

**Step G: fail open.** If the cache ever crashes, we **log the error and continue with the
normal pipeline**. The user still gets an answer, just slower. That's written in the
playbook's failure contract.

**Also: when NOT to cache.**

- If the request brings its own `siis_response` (its own evidence), we skip the cache,
  because the same words with different evidence may need a different answer.
- We never cache failures (`no_match`, `validation_failed`).

---

## Lesson 9 — M3's contract compiler: the security guard

**Teacher:** M1 and M2 are good, but an LLM can misbehave, and matchers make mistakes.
Should one bad sentence make us throw away the entire answer?

**Student:** No, just fix or drop the bad bit?

**Teacher:** Exactly. That's `contract_validator.py`. It turns every graded rule into code,
and gives each problem a **code** and one of three outcomes:

- **repaired:** we can fix it safely and keep going.
  - deeplink not in the catalog → remove it
  - deeplink details altered → restore them from the catalog
  - manual action with a deeplink → remove the deeplink
  - critical action not last → move it
  - "check battery usage" → "Check Battery Usage"
  - score 1.7 → 1.0
  - `**bold**` in a step → plain text
  - duplicate action → drop the copy
- **quarantined:** it can't be fixed without inventing text, which we must never do.
  - description not "It will" + 5–7 words
  - a link inside a step
  - an unknown category ("standard"!)

  We drop **only that action**, and the rest of the plan survives. A goal with the wrong
  phrasing or a bad title is dropped as a whole goal.
- **fallback:** if nothing valid is left, we return `contexts: []` with
  `fallback: "validation_failed"`.

**The polarity check.** Remember "Enable Power Saving Mode" → "Disable Power saving"? The
catalog's `originalType` says `offURL`. The validator reads the action name ("Enable" = on),
reads the entry (off), sees they disagree, and **removes the deeplink**. The user then
follows the written steps instead of pressing a button that does the opposite. Code:
`TOGGLE_POLARITY_CONFLICT`.

Then a second, simpler guard, `check_no_url_leakage`, re-scans every text field for
`http://`, `www.` and markdown links. **Belt and braces**: zero URL leakage is a
non-negotiable rule, so we check it twice.

---

## Lesson 10 — Watching the system: telemetry

You can't improve what you can't see. For every request, `telemetry.py` records:

- a **request ID**: if the app sends `X-Request-ID`, we reuse it; otherwise we create one,
  so a bug report can be traced to exactly one request;
- **stage timings**: cache lookup, enrich, plan, resolve, validation;
- **which cache tier answered**: `miss` / `exact` / `semantic` / `variation`;
- **estimated LLM calls and cost**: 2 calls × a configurable price when an LLM key is
  present, 0 on a cache hit.

These come back as **headers**, so the JSON body the frontend depends on is untouched. A
test enforces that the body still has exactly `contexts`, `query_variations`, `fallback`.

`GET /v1/metrics` summarises everything: requests, hit rate, **p50/p95** latency for hits
and cold runs separately, validation codes seen, guard rejections, estimated cost.

**Student:** What's p95?

**Teacher:** Sort all the response times. p95 is the time that 95% of requests were
*faster* than. It tells you about the slow tail. The average can look great while 5% of
users suffer.

Other safety features:

- `/health` first **warms up** the catalog, M2 engine and IDF table, and only says `ok` when
  they're loaded; otherwise it returns 503.
- A crash anywhere returns a clean
  `500 {"contexts": [], "fallback": "internal_error"}` with the request ID, and **never**
  leaks the internal error text.
- A blank or 2001-character query gets **422** ("your request is invalid").

---

## Lesson 11 — Testing: three kinds, and why you need all three

1. **Unit tests** check one small piece in isolation. Example: "`facets('front camera')`
   contains `front`". Fast, and they pinpoint the exact broken function.
2. **Integration tests** run the real M1 → M2 → M3 chain together. Example: "every
   deeplink delivered is verbatim from the catalog and has the right polarity".
3. **Live system test**: start the real server (`uvicorn`) and send real HTTP requests.
   This is what caught the **variation-poisoning bug**, which no unit test had imagined.

`tests/conftest.py` runs before every test and:

- deletes the LLM keys from the environment, so tests never make paid network calls
  (set `M3_TESTS_ALLOW_LLM=1` if you *want* the live path),
- clears the cache and metrics, so one test's leftovers can't make another test
  pass or fail.

**Try it:** `python -m pytest -q`. You should see **127 passed**.

---

## Lesson 12 — Benchmarking honestly

**Teacher:** Saying "our cache is better" is worthless without numbers. And numbers are
worthless if you cheated to get them. How could you cheat without meaning to?

**Student:** By tuning the threshold on the same questions you report?

**Teacher:** Yes. That's called **overfitting to the test set**. So we:

1. Wrote `evaluation/m3_paraphrase_set.json` **before tuning anything**:
   - 14 intents, each with a seed and 8 paraphrases (casual, formal, panicked, terse,
     verbose, with typos),
   - 12 **probes**: tricky near-misses that must *not* hit (front vs rear camera,
     mobile data vs Wi-Fi, microphone vs speaker, ...).
2. **Split** them: even-numbered items are **dev** (for tuning), odd-numbered are **test**
   (for the final score only).
3. For each configuration, picked the threshold with the highest dev hit rate that had
   **zero wrong hits and zero probe false hits**.
4. Reported the **test** numbers.

The result on the held-out test split:

| Config | Hit rate | Wrong hits | Probe false hits |
|---|---|---|---|
| A. Old exact cache | 0.0% | 0 | 0/6 |
| B. Semantic, no guards | 64.3% | 0 | 1/6 |
| C. Semantic + guards | **75.0%** | 0 | 1/6 |
| D. + variation seeding (shipped) | **75.0%** | 0 | 1/6 |
| E. D with LLM-like variations (simulated) | 76.8% | 0 | 1/6 |

How to read it:

- **Guards are what make a lower threshold safe.** Without guards we needed 0.65 to stay
  safe on dev; with guards, 0.60 was safe. That lowered threshold is worth +10.7 points on
  unseen data.
- **Seeding only helps when variations are real paraphrases.** M1's deterministic
  variations are generic, so D equals C. With query-specific variations (E) it rises.
- **We did not reach 80%.** The misses are mostly very formal sentences ("Applications
  terminate abnormally") that share no words with the seed. A word-based method can't
  bridge that. The honest next step is a small embedding model as a third signal.

**Latency (server side):** hit p95 **6.9 ms**, cold p95 **26.7 ms**. Targets are 300 ms and
8 s, so we're comfortably inside both.

**Honesty rule we followed:**

- Version 1 scored 48.2%.
- We looked at the test mistakes once, and after that changed things based only on *dev*
  mistakes.
- Two bugs (the regex and the typo corrector) were found and fixed.

All of that is written down in the research doc, because hiding it would be dishonest, and
judges respect it.

---

## Lesson 13 — The research, in plain words

| Paper | One-line idea | What we learned / did differently |
|---|---|---|
| GPTCache (2023) | Cache LLM answers by meaning, not exact words | We do too, but without an embedding model, and never trusting the score alone |
| MeanCache (2024/25) | ~31% of questions are repeats; a small local model is enough | Good reason to cache; small and local is fine |
| vCache (2025) | One fixed threshold is unsafe, so learn one per entry | We agree it's unsafe; we use explainable rules instead of learning |
| Category-aware caching (2025) | Different categories need different rules | We gate by domain, and also catch contradictions *inside* a domain |
| Krites (2026) | Let an LLM judge check near-misses | Same goal, but our checks cost zero model calls |
| Let Me Speak Freely? (2024) | Forcing strict formats can hurt LLM reasoning | So validate and repair *after* generation |
| NeMo Guardrails (2023) | Programmable rails around LLM apps | Our rails are the graded business rules |
| Gorilla (2023) | LLMs hallucinate API calls | Deeplinks are API calls: check existence *and* meaning (polarity) |
| Self-Refine (2023) | LLM critiques and fixes itself | Our fixes are plain code: no extra calls, deterministic |

**The gaps we filled, in one breath:** safe hits without extra model calls
(guards), using the paraphrases we're forced to generate anyway (seeding and its filter),
checking that a deeplink *means* what the step says (polarity), and fixing the smallest
broken part instead of throwing away the whole answer (quarantine).

---

## Lesson 14 — Git: how the work was saved

- `main` is the shared, "official" branch. **We didn't touch it.**
- All this work is on **`HC_M3_research_upgrade`**.
- Commit rules for this repo:
  - one line, past tense, lists what was done;
  - no description body;
  - **never** a "Co-Authored-By: Claude" line.
- Today's commits:
  1. the code and tests,
  2. the benchmark and results,
  3. the documents.
- Nothing is merged or pushed. When you're ready: `git push -u origin HC_M3_research_upgrade`
  and open a pull request for the team to review.

---

## Lesson 15 — Mistakes we made, and what they teach

| Mistake | How it was caught | Lesson |
|---|---|---|
| Wrote `\b` through a shell heredoc and it became a backspace character; the domain guard silently did nothing | A unit test with an obvious input ("battery drains fast" must be in the battery domain) | Test even "obviously correct" helpers. Silent no-ops are the worst bugs. |
| Typo-fixer turned "front" into "font" | The front-vs-rear test | A fixer that's too eager is a corrupter. Restrict what it may produce. |
| Variation poisoning (front answer served to rear question) | **Only** the live HTTP test | Unit tests test what you imagined; live tests find what you didn't. |
| Title Case made "Restart Device **In** Safe Mode" | Reading real output | Real style rules have exceptions (small words stay lowercase). |
| 422 errors counted as slow requests in metrics | Reading `/v1/metrics` after a smoke test | Metrics are code too; test them. |
| Forgot to blank the API key on one diagnostic command | Saw the 429 in the output | Protect against paid calls by default (the conftest fixture does now). |

---

## Lesson 16 — Glossary

- **API / endpoint:** a URL your program answers, e.g. `POST /v1/troubleshoot`.
- **JSON:** text format for structured data (`{"key": "value"}`).
- **Pydantic:** a Python library that validates data shapes.
- **FastAPI / uvicorn:** the web framework / the server that runs it.
- **Middleware:** code that wraps every request (we use it for tracing).
- **Deeplink:** a link that opens a specific Settings screen.
- **Masked URI:** a deeplink whose text is scrambled, so you must match by description.
- **Cache hit / miss:** found a stored answer / had to compute one.
- **TTL:** time-to-live, how long a cached answer stays valid.
- **LRU:** least-recently-used eviction; throw out what nobody asked for lately.
- **Semantic similarity:** closeness in *meaning*, not exact words.
- **IDF:** inverse document frequency; rare words weigh more.
- **Cosine similarity:** the angle between two weighted word lists (1 = same direction).
- **Trigram:** a 3-letter chunk; helps with typos.
- **Facet:** a mutually exclusive choice inside a topic (front/rear).
- **Guard:** a rule that can veto a cache hit.
- **Seeding:** pre-loading extra keys (the paraphrases) for an answer.
- **Quarantine:** dropping just the invalid part of an answer.
- **p50 / p95:** median / 95th-percentile response time.
- **Dev / test split:** tune on one half, report on the untouched half.
- **Ablation:** switch parts off one at a time to see what each contributes.
- **Fail open:** if a helper (cache) breaks, carry on without it.

---

## Quiz (answers below — try first!)

1. Why can't we find a deeplink by looking at its URI?
2. A description reads "It will reset your phone and remove every single app." Valid?
3. Two queries score 0.88 similarity. Why might we still refuse the cache hit?
4. What does `X-Cache: variation` mean?
5. Why doesn't a request with its own `siis_response` use the cache?
6. The validator finds a step containing `www.samsung.com`. What happens?
7. Why did we split the benchmark into dev and test?
8. Our held-out hit rate is 75%. What should the slide say about the 80% target?

**Answers:**

1. The URIs are masked (random tokens). The graded rule is to match on
   description / message / qna_description.
2. No: that's 10 words. It must be 5–7, so the action is quarantined.
3. A facet conflict (front vs rear, Wi-Fi vs mobile data, on vs off) or a domain
   conflict. Similar words, different fix.
4. The answer came from a seeded paraphrase key (one of M1's `query_variations`).
5. The same words with different evidence could need a different plan.
6. That action is quarantined (code `URL_LEAK`), and the rest of the plan is kept.
7. So the reported score isn't inflated by tuning on the same data.
8. The truth: 75.0% on our held-out set (up from 0%), with zero wrong hits. Not yet 80%,
   and the named next step is a small embedding model as an extra signal.

---
---

# Appendix — Original development log


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
