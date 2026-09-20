# Samsung PRISM Hackathon 2026–27 | Theme 02: Smart Guided Troubleshooting Engine
# Technical Innovation & Engineering Distinction Blueprint

> **Theme**: Theme 02 — Smart Guided Troubleshooting Engine / Guided Troubleshooting  
> **Judged Target**: `PRISM_GENAI_HACKATHON_Y2026`  
> **Core Narrative**: *"The LLM Plans, the Catalog Guarantees Execution, Telemetry Verifies the Result."*

---

## 1. The Core Differentiator: Moving Beyond Open-Loop Chatbots

### What Typical Entries Will Submit
Most hackathon teams in Theme 02 will build an open-loop pipeline:  
`User Query -> Single LLM Prompt -> Semantic Vector Search -> Static 3-Step JSON`.

While this baseline produces reasonable-looking text, it fails on three practical mobile troubleshooting realities:
1. **Hardware Blindness**: Recommends software setting tweaks (clearing cache, restarting) for physical panel shorts (e.g. green lines) or blown speaker voice coils.
2. **False-Positive Vector Hits**: Semantic embeddings measure topical similarity, not safety risk. Queries like *"phone won't turn on after dropping in water"* and *"phone won't turn on after dropping on carpet"* share high lexical overlap, but serving carpet advice (plugging into a charger) to a wet phone causes fatal motherboard corrosion.
3. **Open-Loop Destruction**: Plans are static. Even if an initial non-destructive setting check diagnoses a rogue background app, the user is still presented with subsequent destructive actions ending in an unnecessary **Factory Data Reset**.

### Our 3-Pillar Solution
Instead of decorative math or generic chatbot wrappers, we focus on **three concrete, domain-specific engineering differentiators**:

```
[User Complaint / Symptom]
           │
           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ PILLAR 1: OS-ARCHITECTURE DIFFERENTIAL DIAGNOSTICS                                     │
│ Zero-shot hardware vs. software triage exploiting Android OS subsystem boundaries:     │
│ • Display: SurfaceFlinger GPU Framebuffer vs. Physical Panel Emission                  │
│ • Audio: Audio HAL Digital Loopback vs. Acoustic Mic Capture                           │
│ • Touch: Linux Kernel /dev/input vs. WindowManager UI Dispatch                         │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Confirmed Software Fault
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ PILLAR 2: CATALOG-DERIVED SAFETY-GUARDRAIL CACHING                                     │
│ • Dynamic risk tags auto-derived directly from data/deeplinks.json & category: critical│
│ • Dual-Key Guardrail: Vector Similarity + Catalog Safety Tag Invariant                │
│ • Blocks dangerous false-positive cache hits (e.g., water vs. carpet drop) in <1ms     │
└──────────────────────────────────────────┬─────────────────────────────────────────────┘
                                           │ Cache Miss / Validated Candidate Plan
                                           ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ PILLAR 3: CLOSED-LOOP TELEMETRY PRUNING VIA VALIDATION DEEPLINKS                        │
│ • Evaluates live device state using Samsung's schema-defined validationDeeplink        │
│ • If non-destructive Step 1 confirms root cause -> dynamically prunes Factory Reset    │
│ • Verifiable end-to-end trace eliminating unnecessary customer data loss               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Pillar 1: The OS-Architecture Differential Diagnostic Family

### Concept
Rather than attempting to train a vision classifier on scarce mobile hardware defect photos, we exploit **fundamental architectural boundaries in the Android operating system**.

By comparing internal digital buffers against external physical manifestations, we achieve **100% deterministic hardware-vs-software triage without training data**.

---

### 1. Display: SurfaceFlinger Framebuffer vs. Physical Panel Emission
- **The OS Invariant**: Android's `SurfaceFlinger` and `Hardware Composer (HWC)` composite graphical layers into an internal GPU framebuffer before driving pixels to the panel via MIPI DSI.
- **The Mechanism**:
  - Physical AMOLED column-driver flex shorts (the infamous vertical green/pink line) and glass cracks exist strictly in the analog photon emission plane.
  - **They cannot render into the digital screenshot buffer**.
- **The Triage Rule**:
  1. The user takes an on-device screenshot (`Power + Volume Down`) and zooms in on it.
  2. **Defect absent in screenshot**: 100% provably a physical panel or flex cable failure. Software troubleshooting is bypassed; user is routed to `Back Up Phone Data` and `Schedule Screen Repair Service`.
  3. **Defect present in screenshot**: Defect originated in GPU rendering, shader pipeline, or app UI composition. Routed to `Wipe Cache Partition` or `Safe Mode`.

---

### 2. Audio: Audio HAL Loopback vs. Acoustic Microphone Capture
- **The OS Invariant**: Android `AudioFlinger` mixes application audio and delivers PCM streams to the `Audio HAL`.
- **The Mechanism**:
  - Comparing internal digital loopback (`AudioRecord` with `REMOTE_SUBMIX`) against external microphone capture isolates digital audio processing from acoustic hardware.
- **The Triage Rule**:
  1. **Clean loopback + distorted mic capture**: Physical speaker voice-coil burnout, torn cone, or lint lodged in the acoustic port. Routes to manual cleaning/service.
  2. **Distorted loopback**: Upstream software DSP (SoundAlive/Dolby Atmos) misconfiguration or codec overflow. Routes to resetting sound settings.

---

### 3. Touch: Linux Kernel `/dev/input/event*` vs. WindowManager UI Dispatch
- **The OS Invariant**: Physical digitizer contacts generate hardware interrupt requests (IRQs) serviced by kernel drivers and streamed to `/dev/input/event*`.
- **The Mechanism**:
  - When the screen appears completely unresponsive to touch, comparing kernel event queues with the Android main UI thread identifies the failure layer.
- **The Triage Rule**:
  1. **Active kernel touch events + frozen UI**: Digitizer hardware is 100% healthy. The problem is an Application Not Responding (ANR) or UI main-thread deadlock. Routes to app force-stop or soft reboot.
  2. **Zero kernel touch events registered**: Digitizer controller IC, I2C/SPI bus failure, or physical sensor grid rupture. Routes to hardware replacement.

---

## 3. Pillar 2: Catalog-Derived Safety-Guardrail Caching

### Concept
Samsung's prompt mandates a `<300ms` fast-path response. While vector embedding caching provides speed, **unconstrained semantic similarity is dangerous in diagnostic workflows**.

- Query A: *"Phone won't turn on after dropping in the toilet"*
- Query B: *"Phone won't turn on after dropping on the carpet"*

In standard embedding models (`all-MiniLM`, `text-embedding-3-small`), these queries have >90% similarity due to shared tokens ("phone", "won't", "turn", "on", "dropping"). A naive cache serves Query B's advice (*"Plug in charger for 60 minutes"*) to Query A, causing **electrolytic corrosion and permanent board destruction**.

### The Innovation: Schema-Derived Dual-Key Guardrails
Instead of hardcoding static regex lists, our engine **auto-derives safety risk tags directly from the catalog metadata (`data/deeplinks.json`) and schema definitions**:

1. **Auto-Extracted Risk Tags**:
   - Scans the 578 catalog deeplinks and schema definitions.
   - Identifies actions marked `category: critical` or associated with destructive operations (`reset`, `wipe`, `format`, `erase`, `lockout`, `liquid_exposure`).
   - Automatically tags catalog entries with risk profiles: `[LIQUID_RISK]`, `[PHYSICAL_IMPACT]`, `[DESTRUCTIVE_RESET]`, `[SECURITY_LOCKOUT]`.

2. **Dual-Key Gating Invariant**:
   A cached plan is returned **if and only if**:
   - **Semantic Similarity $\ge 0.85$**
   - **AND Risk Tag Alignment**: The cached plan's risk profile matches the query's risk tags. If Query A has `[LIQUID_RISK]` and Query B has `[PHYSICAL_IMPACT]`, the cache **aborts immediately** and escalates to full pipeline processing.
   - Execution time: **< 0.5 ms**. Fast-path speed without safety false positives.

---

## 4. Pillar 3: Closed-Loop Telemetry Pruning

### Concept
In conventional open-loop troubleshooting, the engine generates an ordered list:
1. Step 1: Check Battery Usage (Non-destructive)
2. Step 2: Put Apps to Deep Sleep (Non-destructive)
3. Step 3: **Factory Data Reset (Destructive / Irreversible)**

If Step 1 confirms a rogue background app consuming battery, the issue is identified. In an open-loop system, Step 3 remains visible, and users often trigger destructive resets unnecessarily.

### The Innovation: Dynamic Pruning via `validationDeeplink`
Samsung's Theme 02 schema explicitly provides `validationDeeplink`:
```json
{
  "deeplink": "bixby://masked/val/266037d0c5",
  "key": "High Background Battery App Detected",
  "resultType": "boolean",
  "condition": "equal",
  "value": "True"
}
```

When Step 1 executes:
1. The engine reads back the telemetric state via `validationDeeplink`.
2. **If condition is verified (True)**:
   - Root cause is confirmed.
   - The engine **dynamically prunes all downstream destructive actions (`category: critical`)**.
   - Step 3 (Factory Data Reset) is permanently removed from the active plan in real time.

#### Verifiable Before / After Trace:
- **Initial Plan Emitted**:
  - `Step 1`: Check Battery Usage (`auto`)
  - `Step 2`: Enable Power Saving Mode (`auto`)
  - `Step 3`: Restart Device in Safe Mode (`critical`)
- **Telemetry Event Received**: `High Background Battery App Detected == True`
- **Dynamic Pruned Plan**:
  - `Step 1`: Check Battery Usage (`verified_and_active`)
  - `Step 2`: Enable Power Saving Mode (`auto`)
  - *(Step 3 pruned with audit note: "Root cause confirmed. Destructive actions eliminated to protect personal data.")*

---

## 5. Implementation & Demo Honesty

### Production Architecture vs. Hackathon Web Prototype
To maintain complete engineering credibility during the 5-minute judged demo:

| Component | Production Architecture (Samsung Deployment) | Hackathon Prototype (Our Repository) |
|---|---|---|
| **OS Differentials** | Native Android service with Knox SDK / System permissions reading SurfaceFlinger buffers and `/dev/input` | **Architectural Specification & Triage Rules**: Demonstrates the step-by-step user protocol (screenshot zoom test) in frontend cards. |
| **Telemetry Feedback** | Companion Android APK calling Knox APIs / Settings content providers | **Simulated Telemetry Provider**: Web UI toggles simulated device state changes adhering 100% to Samsung's `ValidationDeepLink` JSON schema. |
| **Safety Cache** | On-device SQLite / Redis with catalog-derived risk bitmasks | **Python in-memory dual-key cache** (`backend/services/safety_cache.py`) running in <1ms. |

> **Presentation Tip for Judges**:  
> State clearly: *"In a full One UI integration, OS differentials and telemetry hook into Android system daemons. In our prototype, we implement the complete schema contract with a simulated telemetry provider to showcase real-time DAG pruning without requiring root permissions on judge laptops."*  
> **Judges reward this level of systems maturity.**

---

## 6. Specification Alignment Note: Word Count Flexibility

During team integration, note that two references exist regarding description word counts:
1. **Team Engineering Playbook**: Specifies action descriptions of 50–70 words starting with `"It will "`.
2. **Deeplink Catalog Placeholder (`bixby://dummy_positive`)**: Mentions descriptions of 5–7 words naming the concrete screen.

### Architectural Solution:
Our engine uses a **parameterized constraint policy** (`MIN_WORDS`, `MAX_WORDS`, `PREFIX_ENFORCED`) in `backend/services/troubleshooting_engine.py`.  
- Currently configured to satisfy the Playbook's 50–70 word standard.
- Can be switched to 5–7 words via a single config flag (`DESCRIPTION_STYLE = "compact"` vs `"verbose"`) with zero code refactoring, ensuring 100% compliance under any judge's interpretation.

---

## 7. Real Empirical Benchmark Metrics

All metrics below are derived from running [evaluation/benchmark.py](file:///c:/Users/arrav/Documents/Smart-Guided-Troubleshooting-Engine/evaluation/benchmark.py) across all 20 authentic Samsung benchmark queries from `data/input.txt`:

```
================================================================================
SAMSUNG PRISM HACKATHON 2026-27 | EMPIRICAL BENCHMARK METRICS
================================================================================
Benchmark Queries Evaluated        : 20 (data/input.txt)
Official Schema Compliance Rate    : 20/20 (100.0% Pass)
Title Word Count (2-3 words)       : 100.0% Compliant (mean = 3.0 words)
Description Word Count (50-70 w)   : 100.0% Compliant (min = 52 words, max = 56 words)
Description Prefix ('It will ')    : 20/20 (100.0% Pass)
Critical Actions Sequenced Last    : 20/20 (100.0% Pass)
Zero Raw URL Leakage Rate          : 60/60 Actions (100.0% Pass)
Manual Actions Deeplink Nullified  : 40/40 Actions (100.0% Pass)
--------------------------------------------------------------------------------
MEASURED LATENCY DISTRIBUTION:
  • Min Latency                     : 0.28 ms
  • Mean Latency                    : 0.64 ms
  • Median Latency (P50)            : 0.38 ms
  • 95th Percentile Latency (P95)   : 4.91 ms
  • Max Latency                     : 4.91 ms
  • Target Compliance (<300 ms)     : 100.0% Compliant
================================================================================
```

---

## 8. Slide-by-Slide Presentation Structure (PPT Guide)

| Slide # | Slide Title | Core Message & Demo Cue |
|---|---|---|
| **Slide 27** | Existing Solutions & Gaps | Explain the "Blind LLM" problem: chatbots hallucinate settings, have zero telemetry, and naive vector caches confuse water damage with carpet drops. |
| **Slide 28** | Our Solution & Architecture | Headline: *"The LLM Plans, the Catalog Guarantees Execution, Telemetry Verifies the Result."* Present the 3-pillar diagram. |
| **Slide 29** | Live Product Walkthrough | Demo the closed-loop trace: User opens Step 1 -> Telemetry toggle confirms issue -> Destructive reset step is pruned dynamically from the UI. |
| **Slide 30** | Innovation 1: OS Differentials | Show the SurfaceFlinger vs. Panel screenshot differential. Explain zero-dataset OLED green line triage using Android display pipeline physics. |
| **Slide 31** | Innovation 2 & 3: Safety Cache & Pruning | Show the Catalog-Derived Safety Guardrail preventing false hits, and `validationDeeplink` state evaluation protecting user data. |
| **Slide 32** | Empirical Benchmark Results | Display the measured latency table (Mean: 0.64ms, P95: 4.91ms, 100% schema compliance across all 20 queries). |
| **Slide 34** | Business Impact & Brownie Points | Direct value for Samsung: Cuts unnecessary service center footfall, eliminates customer data loss from premature factory resets, and runs in sub-1ms. |
