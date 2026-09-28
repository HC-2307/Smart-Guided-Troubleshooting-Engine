const form = document.getElementById("query-form");
const input = document.getElementById("query-input");
const submitBtn = document.getElementById("submit-btn");
const resultsEl = document.getElementById("results");

const devToggle = document.getElementById("dev-toggle");
const devClose = document.getElementById("dev-close");
const devPanel = document.getElementById("dev-panel");
const devMeta = document.getElementById("dev-meta");
const devJson = document.getElementById("dev-json");

const CATEGORY_LABEL = { auto: "Auto", manual: "Manual", critical: "Critical" };

devToggle.addEventListener("click", () => devPanel.classList.toggle("hidden"));
devClose.addEventListener("click", () => devPanel.classList.add("hidden"));

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = input.value.trim();
  if (!query) {
    renderEmpty();
    return;
  }
  await runTroubleshoot(query);
});

async function runTroubleshoot(query) {
  renderLoading();
  submitBtn.disabled = true;

  const startedAt = performance.now();
  try {
    const res = await fetch(CONFIG.API_BASE_URL + CONFIG.TROUBLESHOOT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, siis_response: null }),
    });

    const latencyMs = Math.round(performance.now() - startedAt);

    if (!res.ok) {
      renderError(`Server responded with ${res.status}. Is the backend running?`);
      updateDevPanel({ query, latencyMs, status: res.status, body: null });
      return;
    }

    const data = await res.json();
    updateDevPanel({ query, latencyMs, status: res.status, body: data });

    if (!data.contexts || data.contexts.length === 0) {
      renderEmpty(data.fallback || "No troubleshooting plan found for that description.");
      return;
    }

    renderPlan(data.contexts[0]);
  } catch (err) {
    renderError(
      "Couldn't reach the backend. Check it's running, and that CORS is enabled if you're opening this file directly."
    );
    updateDevPanel({ query, latencyMs: null, status: null, body: { error: String(err) } });
  } finally {
    submitBtn.disabled = false;
  }
}

function renderLoading() {
  resultsEl.innerHTML = `
    <div class="state-message">
      <span class="spinner"></span>Finding the right steps...
    </div>
  `;
}

function renderEmpty(message) {
  resultsEl.innerHTML = `
    <div class="state-message">${escapeHtml(message || "Describe what's going wrong with your device to get started.")}</div>
  `;
}

function renderError(message) {
  resultsEl.innerHTML = `
    <div class="state-message error">${escapeHtml(message)}</div>
  `;
}

function renderPlan(goal) {
  const actionsHtml = goal.actions.map(renderActionCard).join("");
  resultsEl.innerHTML = `
    <p class="plan-goal">${escapeHtml(goal.goal || "")}</p>
    <h2 class="plan-title">${escapeHtml(goal.title || "")}</h2>
    ${actionsHtml}
  `;

  resultsEl.querySelectorAll("[data-deeplink]").forEach((btn) => {
    btn.addEventListener("click", () => handleOpen(btn.dataset.deeplink, btn.dataset.message));
  });
}

function renderActionCard(action) {
  const category = action.category || "manual";
  const badgeClass = `badge-${category}`;
  const stepGroupsHtml = (action.stepGroups || []).map(renderStepGroup).join("");

  return `
    <article class="action-card">
      <div class="action-head">
        <h3 class="action-name">${escapeHtml(action.actionName || "")}</h3>
        <span class="badge ${badgeClass}">${CATEGORY_LABEL[category] || category}</span>
      </div>
      <p class="action-description">${escapeHtml(action.description || "")}</p>
      ${stepGroupsHtml}
    </article>
  `;
}

function renderStepGroup(group) {
  const stepsHtml = (group.steps || []).map((s) => `<li>${escapeHtml(s)}</li>`).join("");
  const link = group.actionableDeeplink;

  const openHtml = link
    ? `<button class="open-btn" data-deeplink="${escapeHtml(link.deeplink)}" data-message="${escapeHtml(link.message || "")}">OPEN</button>`
    : `<p class="open-hint">No device action for this step &mdash; manual or informational only.</p>`;

  return `
    <div class="step-group">
      <ol class="step-list">${stepsHtml}</ol>
      ${openHtml}
    </div>
  `;
}

function handleOpen(deeplink, message) {
  // bixby:// deeplinks only resolve on an actual Samsung device.
  // In a browser demo we can't follow them, so show what would happen instead
  // of pretending the click did something real.
  window.alert(
    `On a Galaxy device this would open:\n\n"${message || deeplink}"\n\n(${deeplink})`
  );
}

function updateDevPanel({ query, latencyMs, status, body }) {
  devMeta.innerHTML = `
    <div><dt>Query</dt><dd>${escapeHtml(query)}</dd></div>
    <div><dt>Status</dt><dd>${status ?? "—"}</dd></div>
    <div><dt>Latency</dt><dd>${latencyMs != null ? latencyMs + " ms" : "—"}</dd></div>
  `;
  devJson.textContent = body ? JSON.stringify(body, null, 2) : "";
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

renderEmpty();
