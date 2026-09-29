const form = document.getElementById("query-form");
const input = document.getElementById("query-input");
const submitBtn = document.getElementById("submit-btn");
const resultsEl = document.getElementById("results");
const chipsEl = document.getElementById("example-chips");
const metricsEl = document.getElementById("metrics-strip");
const apiPill = document.getElementById("api-pill");
const llmPill = document.getElementById("llm-pill");
const toastEl = document.getElementById("toast");

const EXAMPLES = [
  { label: "Official query: Flip 6 screen", kind: "official", query: "My Samsung Galaxy Z Flip 6 screen flickers and goes blank whenever I open it, so I can't see anything or access the settings, which stops me from using the phone." },
  { label: "Battery drains fast", kind: "fault", query: "my phone battery drains fast" },
  { label: "Paraphrase (cache hit)", kind: "fault", query: "my battery dies really quickly" },
  { label: "Wi-Fi keeps dropping", kind: "fault", query: "my wifi keeps disconnecting" },
  { label: "Earbuds cut out", kind: "fault", query: "my earbuds keep cutting out during calls" },
  { label: "Settings: 24-hour time", kind: "settings", query: "my phone time is in 24 hrs" },
  { label: "Settings: turn off Bluetooth", kind: "settings", query: "turn off bluetooth" },
  { label: "Off-topic question", kind: "off", query: "what is the capital of france" },
  { label: "Too vague", kind: "off", query: "my galaxy has a problem" },
];

const CATEGORY_INFO = {
  auto: { label: "Auto", hint: "opens the screen" },
  manual: { label: "Manual", hint: "done by hand" },
  critical: { label: "Critical", hint: "disruptive, always last" },
};

const FALLBACK_TEXT = {
  no_match: ["Not a device question", "The relevance check decided this is not about a Galaxy device, so no plan was generated."],
  no_siis_context: ["Not enough to go on", "This is about a device, but there is no reference text and no recognisable topic, so the engine refuses to invent a plan."],
  validation_failed: ["Withheld by the validator", "The finished plan failed the zero-URL check and was not delivered."],
  internal_error: ["Internal error", "The server hit an unexpected error. The request ID below is in the server log."],
};

const CACHE_TEXT = {
  miss: "Miss (full pipeline)",
  exact: "Hit, exact",
  semantic: "Hit, semantic (paraphrase)",
  variation: "Hit, stored query variation",
  coalesced: "Joined identical in-flight request",
};

const RELEVANCE_TEXT = {
  llm: "LLM verdict",
  semantic: "Embedding check (offline)",
  keywords: "Keyword check (offline)",
  skipped: "Skipped (reference text supplied)",
};

const PLANNER_TEXT = {
  catalog: "Settings planner (catalog only)",
  m1: "Troubleshooting planner (M1)",
  none: "None (answer from cache or fallback)",
};

function renderChips() {
  chipsEl.innerHTML = EXAMPLES.map(
    (ex, i) => `<button type="button" class="chip chip-${ex.kind}" data-i="${i}" title="${escapeHtml(ex.query)}">${escapeHtml(ex.label)}</button>`
  ).join("");
  chipsEl.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => run(EXAMPLES[Number(chip.dataset.i)].query));
  });
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const query = input.value.trim();
  if (!query) {
    input.focus();
    return;
  }
  run(query);
});

async function run(query) {
  input.value = query;
  renderLoading(query);
  submitBtn.disabled = true;
  const startedAt = performance.now();
  try {
    const res = await fetch(CONFIG.API_ROOT + CONFIG.TROUBLESHOOT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, siis_response: null }),
    });
    const roundTripMs = Math.round(performance.now() - startedAt);
    const trace = readTrace(res.headers, roundTripMs, res.status);
    let body = null;
    try {
      body = await res.json();
    } catch (_) {
      body = null;
    }
    if (res.status === 422) {
      renderError("The API rejected the request (HTTP 422). Queries must be non-empty and under 2000 characters.", trace, body);
    } else if (!body) {
      renderError(`The API answered with HTTP ${res.status} and no JSON body.`, trace, body);
    } else {
      renderResponse(query, body, trace);
    }
  } catch (err) {
    renderError(`Could not reach the API at ${CONFIG.API_ROOT}. Start it with start.sh / start.ps1 or docker compose up.`, null, null);
  } finally {
    submitBtn.disabled = false;
    refreshMetrics();
  }
}

function readTrace(headers, roundTripMs, status) {
  return {
    status,
    roundTripMs,
    requestId: headers.get("X-Request-ID"),
    cache: headers.get("X-Cache"),
    pipelineMs: headers.get("X-Pipeline-Ms"),
    llmCalls: headers.get("X-LLM-Calls"),
    cost: headers.get("X-Est-Cost-USD"),
    relevance: headers.get("X-Relevance"),
    planner: headers.get("X-Planner"),
  };
}

function renderLoading(query) {
  resultsEl.innerHTML = `
    <div class="state-card">
      <span class="spinner"></span>
      <div>
        <div class="state-title">Working on it…</div>
        <div class="state-text">"${escapeHtml(query)}". A cold request can take a few seconds when the LLM is used; cache hits come back in milliseconds.</div>
      </div>
    </div>`;
}

function renderError(message, trace, body) {
  resultsEl.innerHTML = `
    <div class="result-grid">
      <div class="main-col">
        <div class="state-card error"><div><div class="state-title">Request failed</div><div class="state-text">${escapeHtml(message)}</div></div></div>
      </div>
      <aside class="side-col">${trace ? renderTrace(trace, body) : ""}${body ? renderRaw(body) : ""}</aside>
    </div>`;
}

function renderResponse(query, body, trace) {
  const contexts = body.contexts || [];
  const main = contexts.length ? contexts.map(renderPlan).join("") : renderFallback(body.fallback);
  resultsEl.innerHTML = `
    <div class="result-grid">
      <div class="main-col">
        ${main}
        ${renderVariations(body.query_variations || [])}
      </div>
      <aside class="side-col">
        ${renderTrace(trace, body)}
        ${contexts.length ? renderChecks(body) : ""}
        ${renderRaw(body)}
      </aside>
    </div>`;
  bindResultEvents(body);
}

function renderFallback(fallback) {
  const [title, text] = FALLBACK_TEXT[fallback] || ["No plan", "The engine returned no troubleshooting plan."];
  return `
    <div class="state-card fallback">
      <div>
        <div class="state-title">${escapeHtml(title)} <code>fallback: "${escapeHtml(fallback || "none")}"</code></div>
        <div class="state-text">${escapeHtml(text)} Returning an empty <code>contexts</code> list instead of guessing is part of the contract.</div>
      </div>
    </div>`;
}

function renderPlan(goal) {
  const score = typeof goal.score === "number" ? `<span class="score" title="Plan confidence">score ${goal.score.toFixed(2)}</span>` : "";
  return `
    <article class="plan">
      <p class="plan-goal">${escapeHtml(goal.goal || "")}</p>
      <div class="plan-head">
        <h2 class="plan-title">${escapeHtml(goal.title || "")}</h2>
        ${score}
      </div>
      <div class="legend">
        ${Object.entries(CATEGORY_INFO).map(([k, v]) => `<span class="legend-item"><span class="badge badge-${k}">${v.label}</span>${v.hint}</span>`).join("")}
      </div>
      ${(goal.actions || []).map(renderAction).join("")}
    </article>`;
}

function renderAction(action, index) {
  const category = action.category || "manual";
  const info = CATEGORY_INFO[category] || { label: category, hint: "" };
  return `
    <section class="action-card action-${escapeHtml(category)}">
      <div class="action-head">
        <span class="action-index">${index + 1}</span>
        <h3 class="action-name">${escapeHtml(action.actionName || "")}</h3>
        <span class="badge badge-${escapeHtml(category)}" title="${escapeHtml(info.hint)}">${escapeHtml(info.label)}</span>
      </div>
      <p class="action-description">${escapeHtml(action.description || "")}</p>
      ${(action.stepGroups || []).map(renderStepGroup).join("")}
    </section>`;
}

function renderStepGroup(group) {
  const steps = (group.steps || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("");
  const link = group.actionableDeeplink;
  const deeplink = link
    ? `<div class="deeplink">
         <div class="deeplink-info">
           <span class="deeplink-label">Deeplink</span>
           <code>${escapeHtml(link.deeplink)}</code>
           <span class="deeplink-msg">${escapeHtml(link.message || link.description || "")}</span>
         </div>
         <button class="open-btn" type="button" data-deeplink="${escapeHtml(link.deeplink)}" data-message="${escapeHtml(link.message || "")}">Open</button>
       </div>`
    : `<div class="deeplink none">No deeplink: this step is done by hand or is informational.</div>`;
  return `<div class="step-group"><ol class="step-list">${steps}</ol>${deeplink}</div>`;
}

function renderVariations(variations) {
  if (!variations.length) return "";
  return `
    <section class="panel">
      <div class="panel-title">Query variations <span class="muted">(${variations.length}) · click one to test the semantic cache</span></div>
      <div class="variations">
        ${variations.map((v) => `<button type="button" class="variation" data-query="${escapeHtml(v)}">${escapeHtml(v)}</button>`).join("")}
      </div>
    </section>`;
}

function renderTrace(trace, body) {
  const hit = trace.cache && trace.cache !== "miss";
  const rows = [
    ["Round trip", `${trace.roundTripMs} ms`],
    ["Server pipeline", trace.pipelineMs ? `${Math.round(Number(trace.pipelineMs))} ms` : "—"],
    ["Cache", CACHE_TEXT[trace.cache] || trace.cache || "—"],
    ["Relevance check", RELEVANCE_TEXT[trace.relevance] || trace.relevance || "—"],
    ["Planner", PLANNER_TEXT[trace.planner] || trace.planner || "—"],
    ["LLM calls", trace.llmCalls ?? "—"],
    ["Est. cost", trace.cost ? `$${Number(trace.cost).toFixed(4)}` : "—"],
    ["Fallback", body && body.fallback ? body.fallback : "none"],
    ["HTTP status", trace.status],
    ["Request ID", trace.requestId || "—"],
  ];
  return `
    <section class="panel">
      <div class="panel-title">How this answer was produced ${hit ? '<span class="tag tag-hit">cache hit</span>' : '<span class="tag">cold path</span>'}</div>
      <dl class="trace">${rows.map(([k, v]) => `<div><dt>${k}</dt><dd>${escapeHtml(String(v))}</dd></div>`).join("")}</dl>
    </section>`;
}

function contractChecks(body) {
  const checks = [];
  const text = JSON.stringify(body);
  checks.push(["No URLs or markdown links in the response", !/https?:\/\/|www\.|\]\(/i.test(text)]);
  for (const goal of body.contexts) {
    const actions = goal.actions || [];
    checks.push(['Goal reads "Follow these steps to perform this … Troubleshooting/Configuration"',
      /^Follow these steps to perform this .+ (Troubleshooting|Configuration)$/.test(goal.goal || "")]);
    const titleWords = (goal.title || "").trim().split(/\s+/).filter(Boolean).length;
    checks.push(["Title is 2–3 words", titleWords >= 2 && titleWords <= 3]);
    checks.push(['Every description is 5–7 words and starts "It will"', actions.every((a) => {
      const n = (a.description || "").trim().split(/\s+/).filter(Boolean).length;
      return /^It will\b/.test(a.description || "") && n >= 5 && n <= 7;
    })]);
    checks.push(["Manual actions carry no deeplink", actions.filter((a) => a.category === "manual")
      .every((a) => (a.stepGroups || []).every((g) => !g.actionableDeeplink))]);
    const firstCritical = actions.findIndex((a) => a.category === "critical");
    checks.push(["Critical actions come last", firstCritical === -1 || actions.slice(firstCritical).every((a) => a.category === "critical")]);
    checks.push(["Deeplinks are masked catalog tokens", actions.every((a) => (a.stepGroups || [])
      .every((g) => !g.actionableDeeplink || /^bixby:\/\//.test(g.actionableDeeplink.deeplink)))]);
  }
  const n = (body.query_variations || []).length;
  checks.push([`8–10 query variations (${n})`, n >= 8 && n <= 10]);
  return checks;
}

function renderChecks(body) {
  const checks = contractChecks(body);
  const passed = checks.filter(([, ok]) => ok).length;
  return `
    <section class="panel">
      <div class="panel-title">Theme 2 contract checks <span class="muted">${passed}/${checks.length} pass (checked in the browser)</span></div>
      <ul class="checks">${checks.map(([label, ok]) => `<li class="${ok ? "ok" : "bad"}"><span>${ok ? "✓" : "✗"}</span>${escapeHtml(label)}</li>`).join("")}</ul>
    </section>`;
}

function renderRaw(body) {
  return `
    <section class="panel">
      <div class="panel-title">Raw JSON response <button type="button" class="copy-btn" id="copy-json">Copy</button></div>
      <pre class="raw-json">${escapeHtml(JSON.stringify(body, null, 2))}</pre>
    </section>`;
}

function bindResultEvents(body) {
  resultsEl.querySelectorAll("[data-deeplink]").forEach((btn) => {
    btn.addEventListener("click", () =>
      showToast(`On a Galaxy device this opens "${btn.dataset.message || "the Settings screen"}" (${btn.dataset.deeplink}). Deeplinks only resolve on the device.`)
    );
  });
  resultsEl.querySelectorAll(".variation").forEach((btn) => btn.addEventListener("click", () => run(btn.dataset.query)));
  const copy = document.getElementById("copy-json");
  if (copy) {
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(JSON.stringify(body, null, 2));
        showToast("JSON copied to the clipboard.");
      } catch (_) {
        showToast("Copy failed; select the text instead.");
      }
    });
  }
}

let toastTimer = null;
function showToast(message) {
  toastEl.textContent = message;
  toastEl.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.add("hidden"), 5000);
}

async function checkHealth() {
  try {
    const res = await fetch(CONFIG.API_ROOT + CONFIG.HEALTH_ENDPOINT);
    setPill(apiPill, res.ok ? "ok" : "bad", res.ok ? "API: ready" : `API: HTTP ${res.status}`);
  } catch (_) {
    setPill(apiPill, "bad", "API: unreachable");
  }
}

const PROVIDER_TEXT = { own_key: "your key", free_tier: "free tier", offline: "offline mode" };

async function refreshMetrics() {
  try {
    const res = await fetch(CONFIG.API_ROOT + CONFIG.METRICS_ENDPOINT);
    const data = await res.json();
    const llm = data.llm || {};
    const breaker = data.llm_guard && data.llm_guard.open ? " · paused" : "";
    const model = llm.model ? ` (${llm.model.split("/").pop()})` : "";
    setPill(llmPill, llm.provider === "offline" ? "warn" : "ok", `LLM: ${PROVIDER_TEXT[llm.provider] || "unknown"}${model}${breaker}`);
    renderMetrics(data);
  } catch (_) {
    setPill(llmPill, "bad", "LLM: unknown");
  }
}

function renderMetrics(data) {
  const p = data.pipeline || {};
  const lat = p.latency_ms || {};
  const cache = data.cache || {};
  const pct = (x) => (typeof x === "number" ? `${Math.round(x * 100)}%` : "—");
  const ms = (x) => (x && x.count ? `${Math.round(x.p95)} ms` : "—");
  const tiles = [
    ["Requests this session", p.requests ?? 0],
    ["Cache hit rate", pct(p.cache_hit_rate)],
    ["p95 cache hit", ms(lat.hit), "target ≤ 300 ms"],
    ["p95 cold path", ms(lat.cold), "target ≤ 8 s"],
    ["Cached plans", cache.entries ?? "—"],
    ["Est. LLM cost", typeof p.est_cost_usd === "number" ? `$${p.est_cost_usd.toFixed(4)}` : "—"],
  ];
  metricsEl.innerHTML = tiles.map(([k, v, t]) => `
    <div class="tile"><div class="tile-value">${escapeHtml(String(v))}</div><div class="tile-label">${k}${t ? `<span class="tile-target">${t}</span>` : ""}</div></div>`).join("");
}

function setPill(el, state, text) {
  el.className = `pill pill-${state}`;
  el.textContent = text;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderWelcome() {
  resultsEl.innerHTML = `
    <div class="state-card">
      <div>
        <div class="state-title">Pick an example above or type your own complaint</div>
        <div class="state-text">Each answer shows the plan, the catalog deeplink for every action, how the answer was produced (cache, relevance check, planner, LLM calls, latency) and the raw JSON.</div>
      </div>
    </div>`;
}

renderChips();
checkHealth();
refreshMetrics();
setInterval(checkHealth, 15000);
const initialQuery = new URLSearchParams(window.location.search).get("q");
if (initialQuery) run(initialQuery);
else renderWelcome();
