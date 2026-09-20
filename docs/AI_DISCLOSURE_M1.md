# Samsung PRISM Hackathon 2026–27 | AI Usage Disclosure Log
## Member 1: AI / ML Pipeline & LLM Engine

As mandated by the Samsung PRISM Hackathon guidelines and the AI Usage Disclosure Form (`LangAI3.0_AI_Disclosure.docx`), this log documents AI-assisted and self-generated technical work for Member 1's features.

---

### Internal Feature Disclosure Table

| Feature / Artifact | Origin (Self / AI / Both) | Tool / Platform | Prompt Saved? | Output Saved? | Human Modification Recorded? |
|---|---|---|---|---|---|
| **Query Enrichment Service** (`backend/services/query_enrichment.py`) | Both | Antigravity AI / Python 3.14 | Yes (`prompts/enrichment_prompt.txt`) | Yes | Designed multi-tier architecture with OpenAI/Gemini caller and deterministic keyword/regex fallback engine for zero-dependency execution. |
| **Troubleshooting Engine** (`backend/services/troubleshooting_engine.py`) | Both | Antigravity AI / Python 3.14 | Yes (`prompts/structure_prompt.txt`) | Yes | Built strict constraint post-processor enforcing 50–70 word counts starting with "It will", 2–3 word titles, critical action ordering, and zero-URL sanitization. |
| **Enrichment Prompt Template** (`prompts/enrichment_prompt.txt`) | Both | Antigravity AI | Yes | Yes | Tuned few-shot examples across Battery, Display, Camera, and Performance with multi-register paraphrasing guidelines. |
| **Structure Prompt Template** (`prompts/structure_prompt.txt`) | Both | Antigravity AI | Yes | Yes | Engineered prompt specifying JSON schema, SIIS grounding, and imperative step groups without external links. |
| **Pydantic Schemas** (`backend/schemas/enriched_query.py`, `backend/schemas/troubleshooting_plan.py`) | Both | Antigravity AI | Yes | Yes | Formatted to match official `student_kit/schema.py` and `data/schema.py` with full type validation. |
| **Unit & Constraint Tests** (`tests/test_enrichment.py`, `tests/test_structure.py`) | Both | Antigravity AI / pytest | Yes | Yes | Programmed assertions for word counts, prefix verification, category ordering, and symptom preservation. |
| **Regression Benchmark Test** (`tests/test_prompt_regression.py`) | Both | Antigravity AI / pytest | Yes | Yes | Authored automated test harness running across all 20 real benchmark queries from `data/input.txt`. |

---

### Verification Summary
- **Test Suite Status**: 34/34 tests passing (`pytest tests/`)
- **Latency**: ~0.31s execution across all tests
- **Schema Conformance**: 100% compliant with `ContextDeeplinkResponse` in `data/schema.py`
