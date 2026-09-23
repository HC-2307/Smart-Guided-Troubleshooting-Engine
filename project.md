# Samsung PRISM Hackathon 2026–27 | Theme 02: Smart Guided Troubleshooting Engine
## Role 1: AI / ML Pipeline & LLM Engine — Complete Engineering Blueprint & Execution Guide

---

## 1. Executive Overview & Role Mission

### 1.1 Project Identity
- **Hackathon**: Samsung PRISM Generative AI Hackathon 2026–27
- **Theme**: Theme 02 — Smart Guided Troubleshooting Engine / Guided Troubleshooting
- **Judged Git Commit Tag**: `PRISM_GENAI_HACKATHON_Y2026`
- **Final Submission Deadline**: 25 September 2026, 11:59 PM

### 1.2 Role 1 Mission Statement
You are **Member 1 (M1)**: the **AI / ML Pipeline & LLM Engine Architect**.

Your core responsibility is to translate messy, colloquial, emotionally-charged, or ambiguous user device complaints into structured, technically-grounded, and schema-compliant troubleshooting plans that can be deterministically resolved against Samsung Settings deeplinks.

### 1.3 The Cardinal Engineering Rule: "LLM Plans, Catalog Executes"
> **CRITICAL ARCHITECTURAL BOUNDARY:**
> - **The LLM NEVER invents or outputs final deeplink URIs.**
> - The LLM is an intent parser, symptom normalizer, and action synthesizer.
> - Final deeplinks are strictly resolved downstream by **Member 2 (Knowledge / Deeplink Engine)** against the official Samsung settings catalog (`data/deeplinks.json`).
> - If an LLM fabricates a deeplink URI (e.g. inventing a scheme or URL), the entire engine fails compliance.

---

## 2. Team Architecture & Integration Context

The system consists of 4 distinct member roles working collaboratively:

```
                  ┌──────────────────────────────────────────────┐
                  │                 USER COMPLAINT               │
                  │   "My phone dies super quick and gets hot"   │
                  └───────────────────────┬──────────────────────┘
                                          │
                                          ▼
                  ┌──────────────────────────────────────────────┐
                  │           M3: Backend / Orchestrator         │
                  │  - Cache Lookup (<300ms hit path)            │
                  │  - Request Validation & Tracing              │
                  └───────────────┬──────────────────────────────┘
                                  │ Cache MISS: Raw query
                                  ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ ★ MEMBER 1 (YOU): AI / ML PIPELINE & LLM ENGINE                                │
│                                                                                │
│  Stage 1: Query Enrichment (backend/services/query_enrichment.py)             │
│  - Colloquial -> Technical translation                                        │
│  - Symptom preservation (zero hallucinated defects)                           │
│  - Domain, Issue, and Context feature extraction                              │
│  - 8–10 Varied Register Paraphrases (Slang, Formal, Panic, Brief, Verbose)     │
│                                                                                │
│                                  │                                             │
│                                  ▼ Enriched Query                              │
│                                                                                │
│  Stage 2: Structure Extraction (backend/services/troubleshooting_engine.py)   │
│  - SIIS grounding (internal knowledge store integration)                      │
│  - Ordered action generation                                                  │
│  - Schema compliance:                                                          │
│      • 2-3 word Title                                                          │
│      • Description: EXACTLY 50–70 words, starts with "It will"                │
│      • Step groups: Imperative UI steps (ZERO URLs)                            │
│      • Action Categories: standard/auto, critical (LAST), manual (no deeplink) │
│  - JSON repair & retry wrapper                                                 │
└─────────────────────────────────┬──────────────────────────────────────────────┘
                                  │ Troubleshooting Plan (Actions without final URLs)
                                  ▼
                  ┌──────────────────────────────────────────────┐
                  │      M2: Knowledge / Deeplink Engine         │
                  │  - Action name matching against catalog      │
                  │  - Exact/semantic deeplink injection         │
                  │  - Validation deeplink mapping               │
                  └───────────────┬──────────────────────────────┘
                                  │ Resolved actions
                                  ▼
                  ┌──────────────────────────────────────────────┐
                  │          M3: Validation & Cache Write        │
                  │  - Schema integrity & sequence check         │
                  │  - Fast-path cache storage                   │
                  │  - REST API response (POST /troubleshoot)    │
                  └───────────────┬──────────────────────────────┘
                                  │ Validated JSON response
                                  ▼
                  ┌──────────────────────────────────────────────┐
                  │            M4: Frontend & Benchmark          │
                  │  - Interactive Card UI & "OPEN" deeplink     │
                  │  - End-to-end evaluation runner              │
                  └──────────────────────────────────────────────┘
```

### 2.1 Upstream & Downstream Contracts for Member 1

| Direction | Interfacing Member | Data Structure / Object | Description |
|---|---|---|---|
| **Input (Upstream)** | M3 (Backend) | `TroubleshootRequest` (`query: str`, `siis_response: Optional[Dict]`) | Raw user complaint string, plus optional SIIS document if available |
| **Internal (Stage 1 -> Stage 2)** | M1 Internal | `EnrichedQuery` | Technical representation, domain, issue, context, and query variations |
| **Output (Downstream)** | M2 (Deeplink Engine) & M3 | `TroubleshootingPlan` | Validated Pydantic structure with `goal`, `title`, `score`, `actions[]`, and `query_variations` |

---

## 3. Strict Theme 02 Schema & Behavioral Constraints Matrix

Every single output produced by Member 1's services must strictly adhere to the Samsung Theme 02 specifications. Below is the non-negotiable constraint matrix:

| Field / Attribute | Strict Constraint Rule | Example / Pattern |
|---|---|---|
| **`goal`** | Must follow the pattern `"Follow these steps to perform this <Topic> Troubleshooting"` or `"Troubleshooting"` / `"<Topic> Configuration"`. | `"Follow these steps to perform this Screen Damage Troubleshooting"` |
| **`title`** | Exactly **2 to 3 words**, in Sentence/Title case, identifying the core root issue. | `"Screen display damage"`, `"Battery drain issue"`, `"Camera focus failure"` |
| **`score`** | Float between `0.0` and `1.0` representing model confidence. | `0.95` |
| **`actionName`** | Physical screen or use-case name. Steps occurring on the same UI screen must be grouped under a single action name. | `"Back Up Phone Data"`, `"Check Battery Usage"` |
| **`description`** | **CRITICAL:** The official specification mandates **EXACTLY 50 to 70 words** and must start with the prefix **`"It will "`**. | `"It will facilitate secure data transfer between your devices by backing up essential contacts, photos, and system preferences to your Samsung Cloud storage. This preliminary safeguard guarantees that no critical personal information or application configuration is lost should your device undergo unexpected shutdowns, display replacements, or complete system resets during the upcoming troubleshooting procedure."` *(60 words)* |
| **`stepGroups`** | Array of objects, each containing `steps: List[str]`. Must contain clear, imperative UI directions (e.g. `"Navigate to Settings."`, `"Tap Battery."`). **STRICTLY PROHIBITED:** No external HTTP/HTTPS URLs, no markdown links. | `["Navigate to and open Settings.", "Tap on Accounts and backup.", "Select Back up data."] ` |
| **`category`** | Enum: `"auto"` (or `"standard"`), `"critical"`, or `"manual"`. | `"auto"`, `"critical"`, `"manual"` |
| **Critical Action Rule** | Any disruptive, irreversible, or severe operation (e.g. Factory Data Reset, Wipe Cache, Reboot into Safe Mode, Firmware Flash) **MUST BE ORDERED LAST** in the actions array. | Step 1: Backup -> Step 2: Settings check -> Step 3: Factory Reset |
| **Manual Action Rule** | Any physical intervention (cleaning USB port, replacing cracked glass, visiting Samsung Service Center) must have category `"manual"`. M1 must ensure `actionableDeeplink` is `null` for manual steps. | `"Schedule Screen Repair Service"` -> `actionableDeeplink: null` |
| **`query_variations`** | Must generate **8 to 10 distinct paraphrases** spanning varied registers: Slang/Colloquial, Formal/Technical, Frustrated/Urgent, Succinct, and Verbose. | Used to warm and test the M3 fast-path cache. |
| **SIIS Grounding Rule** | When a `siis_response` payload is provided in the input, generated steps must be **faithfully derived from the provided SIIS text**. Do NOT invent steps unsupported by the document. | If SIIS mentions Safe Mode, include Safe Mode. Do not invent third-party apps. |

---

## 4. Role 1 File Map & Directory Ownership

All files listed below are owned and implemented by **Member 1**:

```
Smart-Guided-Troubleshooting-Engine/
├── backend/
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── enriched_query.py          # [NEW] Pydantic models for Stage 1 enrichment
│   │   └── troubleshooting_plan.py    # [NEW] Pydantic models for Stage 2 plan (compatible with schema.py)
│   └── services/
│       ├── __init__.py
│       ├── query_enrichment.py        # [IMPLEMENT] Stage 1 Service (normalization + variations)
│       └── troubleshooting_engine.py  # [IMPLEMENT] Stage 2 Service (actions, constraints, repair)
├── prompts/
│   ├── enrichment_prompt.txt          # [IMPLEMENT] Prompt for Stage 1 Query Enrichment
│   └── structure_prompt.txt           # [IMPLEMENT] Prompt for Stage 2 Troubleshooting Structure
├── schemas/
│   ├── enriched_query.json            # [NEW] JSONSchema export of Stage 1
│   └── troubleshooting_plan.json      # [NEW] JSONSchema export of Stage 2
├── tests/
│   ├── test_enrichment.py             # [NEW] Unit tests for Query Enrichment
│   ├── test_structure.py              # [NEW] Unit tests for Troubleshooting Engine & Constraints
│   └── test_prompt_regression.py      # [NEW] Paraphrase & 20-query regression test suite
└── docs/
    └── AI_DISCLOSURE_M1.md            # [NEW] Samsung Hackathon AI Usage Disclosure log for Role 1
```

---

## 5. Detailed Component Specifications & Code Architecture

### 5.1 Data Models & Schemas

#### File: `backend/schemas/enriched_query.py`
Defines the output of Stage 1 Query Enrichment.
```python
from typing import List, Optional
from pydantic import BaseModel, Field

class EnrichedQuery(BaseModel):
    original_query: str = Field(..., description="Raw user input string")
    technical_query: str = Field(..., description="Normalized technical query representing root defect")
    domain: str = Field(..., description="Target hardware/software domain: battery, display, camera, performance, connectivity, audio, storage, system")
    issue: str = Field(..., description="Concise statement of the core issue")
    context: List[str] = Field(default_factory=list, description="Extracted situational modifiers (e.g., overheating, charging, startup)")
    query_variations: List[str] = Field(..., min_items=8, max_items=12, description="8-10 diverse register paraphrases")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")
```

#### File: `backend/schemas/troubleshooting_plan.py`
Matches the official Samsung schema defined in `data/schema.py` and `student_kit/schema.py`.
```python
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, validator

class Condition(str, Enum):
    greater = "greater"
    equal = "equal"
    less = "less"

class ResultTypes(str, Enum):
    boolean = "boolean"
    intNum = "integer"
    string = "str"
    floatNum = "float"

class ActionCategory(str, Enum):
    auto = "auto"
    manual = "manual"
    critical = "critical"

class BaseDeeplink(BaseModel):
    deeplink: str

class Deeplink(BaseDeeplink):
    description: str
    message: Optional[str] = ""
    classes: Optional[Dict[str, str]] = None
    originalType: Optional[str] = None

class ValidationDeepLink(BaseDeeplink):
    key: str
    resultType: Optional[ResultTypes] = None
    condition: Optional[Condition] = None
    value: Optional[str] = None

class StepGroup(BaseModel):
    steps: List[str]
    validationDeeplink: Optional[ValidationDeepLink] = None
    actionableDeeplink: Optional[Deeplink] = None

class Action(BaseModel):
    actionName: str
    description: str
    stepGroups: List[StepGroup]
    category: Optional[ActionCategory] = ActionCategory.manual

class Goal(BaseModel):
    goal: str
    title: str
    actions: List[Action]
    score: float

class TroubleshootingPlan(BaseModel):
    contexts: List[Goal] = []
    query_variations: Optional[List[str]] = []
```

---

### 5.2 Prompt Engineering Specifications

#### Prompt 1: `prompts/enrichment_prompt.txt`
**Task**: Normalize a raw, colloquial smartphone issue into a technical query and produce 8–10 diverse paraphrases without hallucinating symptoms.

**Key Prompt Requirements**:
1. **Zero Symptom Hallucination**: Only extract what the user explicitly said or directly implied.
2. **Domain Classification**: Map to one of: `battery`, `display`, `camera`, `performance`, `connectivity`, `audio`, `storage`, `system`.
3. **Multi-Register Paraphrasing**: Generate exactly 8–10 distinct variants:
   - *Slang / Casual*: "my screen is bugging out"
   - *Panic / Emotional*: "omg my phone won't turn on I need my data"
   - *Technical / Concise*: "AMOLED blank screen unresponsive to digitizer input"
   - *Formal Inquiry*: "The display panel fails to illuminate upon power trigger"
   - *Symptom + Context*: "screen goes completely dark when plugging in charger"
4. **Output Format**: Strictly valid JSON matching `EnrichedQuery`.

#### Prompt 2: `prompts/structure_prompt.txt`
**Task**: Take `EnrichedQuery` and optional `siis_content`, and generate the structured troubleshooting plan.

**Key Prompt Requirements**:
1. **Title Constraint**: Exactly 2–3 words, Title/Sentence Case (e.g. `"Battery drain issue"`, `"Screen display damage"`).
2. **Description Word-Count & Prefix Constraint**:
   - MUST start with: `"It will "`
   - MUST contain: **Between 50 and 70 words**.
   - Must explain the exact technical benefit of performing this specific action before proceeding.
3. **Imperative Step Groups**:
   - Numbered or clean imperative instructions: `"Navigate to Settings."`, `"Tap on Battery and device care."`, `"Select Battery."`
   - ZERO links, ZERO URLs, ZERO markdown `[link](...)`.
4. **Action Categorization & Sequencing**:
   - Standard settings screens -> `"auto"`
   - Physical cleaning, port inspection, technician visit -> `"manual"`
   - Irreversible actions (Factory reset, firmware update, safe mode reboot) -> `"critical"`
   - **CRITICAL ACTIONS MUST ALWAYS BE ORDERED LAST.**
5. **SIIS Grounding**: If `SIIS_CONTENT` is provided, prioritize the exact steps outlined in the document.

---

### 5.3 Core Service Implementations

#### File: `backend/services/query_enrichment.py`
Provides the `enrich_query(query: str) -> Dict` interface.
Features required:
1. **Multi-Provider LLM Integration**:
   - Primary: LLM call (e.g., via OpenAI, Google Gemini, Anthropic, or Ollama using environment variables like `LLM_PROVIDER`, `GEMINI_API_KEY`, `OPENAI_API_KEY`).
   - Fallback Engine: High-precision deterministic fallback using rule-based regular expressions and semantic domain keyword dictionaries. This guarantees the entire test suite and API run flawlessly in local/offline test environments!
2. **Paraphrase Generator**:
   - Extracts key entities and combines templates to produce 8–10 high-quality variations across registers.
3. **Symptom Sanitizer**:
   - Ensures no spurious symptoms are introduced during normalization.

#### File: `backend/services/troubleshooting_engine.py`
Provides the `generate_troubleshooting_plan(enriched_query: Dict, siis_response: Optional[Dict] = None) -> Dict` interface.
Features required:
1. **SIIS Knowledge Extraction**:
   - Checks if a corresponding SIIS entry exists in `data/siis_responses.json` or is passed directly in the request.
   - Extracts steps directly from the SIIS document sections if present.
2. **LLM Execution with Robust JSON Repair**:
   - Parses LLM completion.
   - Automatically handles markdown code fence stripping (````json ... ````), trailing commas, and escaped quote repairs.
   - Retries up to 2 times with a repair prompt if JSON validation fails.
3. **Enforcement & Sanitization Post-Processor**:
   - **Word Count Enforcer**: Programmatically verifies that `action.description` starts with `"It will "` and falls within 50–70 words. If the LLM generates 45 words or 75 words, the post-processor deterministically adjusts or pads/trims the sentence to guarantee 100% compliance with the 50–70 word rule!
   - **Critical Action Re-orderer**: Inspects all actions. Identifies actions with `category == "critical"` or names containing `["Reset", "Factory", "Safe mode", "Wipe"]`. Moves all such actions to the very end of the `actions` list.
   - **Manual Action Deeplink Nullifier**: Guarantees that any action categorized as `"manual"` has `actionableDeeplink = None`.
   - **URL Stripper**: Scans all `steps` and removes any raw URLs or HTTP/HTTPS patterns.
4. **Deterministic Fallback Generator**:
   - Contains rich built-in troubleshooting templates for the 4 core domains (`Battery`, `Display`, `Camera`, `Performance`) to ensure 100% test reliability even without live external LLM API keys.

---

## 6. Testing, Evaluation, and Regression Suite

Role 1 is responsible for three robust test files in `tests/`:

### 6.1 `tests/test_enrichment.py`
- **Goal**: Validate query enrichment behavior.
- **Test Cases**:
  1. `test_battery_enrichment`: Colloquial query `"My phone battery drains in two hours"` -> domain `battery`, issue `rapid battery drain`.
  2. `test_display_enrichment`: Colloquial query `"Screen flickers green and goes black"` -> domain `display`, issue `screen flickering and blank display`.
  3. `test_camera_enrichment`: Colloquial query `"Back camera is super blurry and won't focus"` -> domain `camera`.
  4. `test_performance_enrichment`: Colloquial query `"Apps keep crashing and phone is lagging"` -> domain `performance`.
  5. `test_symptom_preservation`: Verify no unmentioned symptoms (e.g. liquid damage or cracked glass) are added.
  6. `test_query_variations_count`: Verify that generated query variations count is between 8 and 10.

### 6.2 `tests/test_structure.py`
- **Goal**: Validate schema constraints and business rules.
- **Test Cases**:
  1. `test_title_word_count`: Every plan title must be 2 to 3 words.
  2. `test_description_prefix`: Every action description must start with `"It will "`.
  3. `test_description_word_count`: Every action description must be between 50 and 70 words (inclusive).
  4. `test_step_groups_no_urls`: Every step in `stepGroups` must be free of `http://`, `https://`, and `bixby://` strings.
  5. `test_critical_actions_last`: If a plan contains critical actions (like factory reset), it must be the last action.
  6. `test_manual_actions_no_deeplink`: Any manual action must have `actionableDeeplink` set to `None`.
  7. `test_pydantic_schema_validity`: All generated plans must pass validation through `TroubleshootingPlan` or `ContextDeeplinkResponse` from `data/schema.py`.

### 6.3 `tests/test_prompt_regression.py`
- **Goal**: Run regression on the 20 official hackathon test queries from `data/input.txt`.
- **Test Cases**:
  1. Iterate through all lines of `data/input.txt`.
  2. Run enrichment and troubleshooting plan generation for each.
  3. Assert 100% schema validity and zero runtime exceptions.
  4. Measure latency per query and verify output stability.

---

## 7. Step-by-Step AI Execution Guide (How to Complete the Task)

If you are an AI assistant executing this project, execute the following steps in sequence:

### Phase 1: Starter Assets & Schemas
- [ ] **Step 1.1**: Verify `data/` directory contains `deeplinks.json`, `input.txt`, `sample_output.json`, `schema.py`, and `siis_responses.json`.
- [ ] **Step 1.2**: Create `backend/schemas/enriched_query.py` with the Pydantic model for Stage 1.
- [ ] **Step 1.3**: Create `backend/schemas/troubleshooting_plan.py` matching `student_kit/schema.py` and `data/schema.py`.
- [ ] **Step 1.4**: Export JSONSchema representations to `schemas/enriched_query.json` and `schemas/troubleshooting_plan.json`.

### Phase 2: Prompts
- [ ] **Step 2.1**: Write `prompts/enrichment_prompt.txt` with clear system instructions, few-shot examples for the 4 core domains, and 8–10 register paraphrase formatting.
- [ ] **Step 2.2**: Write `prompts/structure_prompt.txt` with instructions for 2-3 word titles, 50-70 word descriptions starting with `"It will"`, imperative steps, and critical action sequencing.

### Phase 3: Service Implementation
- [ ] **Step 3.1**: Implement `backend/services/query_enrichment.py`:
  - Implement `enrich_query(query: str) -> dict`.
  - Include LLM caller (supporting Gemini / OpenAI / Ollama via environment variables) + robust rule-based fallback.
  - Include 8–10 paraphrase generator.
- [ ] **Step 3.2**: Implement `backend/services/troubleshooting_engine.py`:
  - Implement `generate_troubleshooting_plan(enriched_query: dict, siis_response: Optional[dict] = None) -> dict`.
  - Implement SIIS ground-truth extractor from `data/siis_responses.json`.
  - Implement post-processing validators:
    - 50–70 word description formatter with `"It will "` prefix.
    - Critical actions sorter (placing critical actions last).
    - URL sanitizer (stripping links).
    - Manual action cleaner.
  - Implement rich fallback plans for all core domains.

### Phase 4: Test Suites & Verification
- [ ] **Step 4.1**: Create `tests/test_enrichment.py`.
- [ ] **Step 4.2**: Create `tests/test_structure.py`.
- [ ] **Step 4.3**: Create `tests/test_prompt_regression.py`.
- [ ] **Step 4.4**: Run `pytest tests/` and verify all tests pass with 100% green status.
- [ ] **Step 4.5**: Run regression test across all 20 lines of `data/input.txt`.

### Phase 5: AI Disclosure Documentation
- [ ] **Step 5.1**: Create `docs/AI_DISCLOSURE_M1.md` documenting:
  - Feature name (Query Enrichment, Troubleshooting Structure, Prompt Design, Testing).
  - Origin (AI-assisted / Self-generated).
  - Tool/platform used.
  - Prompts used and modifications recorded (required by Samsung PRISM AI Disclosure form).

---

## 8. Definition of Done (Role 1 Acceptance Checklist)

Before Member 1 hands off to Member 2 and Member 3, every item below must be satisfied:

- [ ] **Schema Compliance**: All generated outputs strictly validate against `student_kit/schema.py` without Pydantic validation errors.
- [ ] **50–70 Word Description**: Every action description begins with `"It will "` and contains between 50 and 70 words.
- [ ] **2–3 Word Title**: Plan title is exactly 2 to 3 words.
- [ ] **Sequencing Guarantee**: All critical actions (e.g. factory reset, safe mode) are ordered last.
- [ ] **Zero URL Hallucination**: No raw deeplink URLs or HTTP links are generated by the LLM.
- [ ] **Manual Action Integrity**: Manual actions have `actionableDeeplink = null`.
- [ ] **Paraphrase Coverage**: Exactly 8–10 distinct paraphrases generated per query.
- [ ] **Core Domains Covered**: Battery, Display, Camera, Performance fully supported.
- [ ] **Offline / Fallback Reliability**: Engine executes cleanly and passes all tests even without external API keys.
- [ ] **Test Suite 100% Pass**: `pytest tests/test_enrichment.py tests/test_structure.py tests/test_prompt_regression.py` passes with zero failures.
- [ ] **AI Disclosure Documented**: `docs/AI_DISCLOSURE_M1.md` is complete and up to date.
