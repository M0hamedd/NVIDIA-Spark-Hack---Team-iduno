const form = document.querySelector("#scenarioForm");
const loading = document.querySelector("#loading");
const loadingTitle = document.querySelector("#loadingTitle");
const loadingDetail = document.querySelector("#loadingDetail");
const errorBox = document.querySelector("#errorBox");
const resultTitle = document.querySelector("#resultTitle");
const agentMode = document.querySelector("#agentMode");
const agentReport = document.querySelector("#agentReport");
const engineStatus = document.querySelector("#engineStatus");
const engineLabel = document.querySelector("#engineLabel");
const pipelineSteps = document.querySelector("#pipelineSteps");
const benchmarks = document.querySelector("#benchmarks");
const mapZones = document.querySelector("#mapZones");
const mapPreview = document.querySelector("#mapPreview");
const mapSubtitle = document.querySelector("#mapSubtitle");
const zonePanel = document.querySelector("#zonePanel");
const targetTable = document.querySelector("#targetTable");
const targetCount = document.querySelector("#targetCount");
const briefButton = document.querySelector("#briefButton");
const businessType = document.querySelector("#businessType");

const presetCopy = {
  window_washing: {
    label: "Exterior + window cleaning",
    driver: "condos, apartments, post-construction glass, commercial corridors"
  },
  cleaning_maintenance: {
    label: "Commercial cleaning",
    driver: "offices, retail corridors, apartment common areas, institutional anchors"
  },
  hvac: {
    label: "HVAC service",
    driver: "renovation permits, older buildings, commercial density, maintenance cycles"
  },
  pest_control: {
    label: "Pest control",
    driver: "apartments, food corridors, mixed-use buildings, maintenance pressure"
  },
  landscaping: {
    label: "Grounds + landscaping",
    driver: "residential density, grounds contracts, income fit, route practicality"
  }
};

const loadingStages = [
  ["Loading Toronto Open Data", "Permits, development, neighbourhood profiles, and fallback samples are being prepared."],
  ["Normalizing civic signals", "Schemas are being aligned into demand, growth, prospect, and feasibility features."],
  ["Scoring opportunity zones", "Weights are adjusted for the selected service preset and priority mode."],
  ["Preparing local brief", "The recommendation context is grounded in computed evidence."]
];

let latestResult = null;
let selectedZoneId = null;
let activeLayers = new Set(["permits", "development", "prospects", "feasibility"]);
let loadingTimer = null;

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    const engine = health.rapids_cudf_available ? "RAPIDS/cuDF ready" : "CPU fallback ready";
    engineStatus.textContent = engine;
    engineLabel.textContent = health.rapids_cudf_available ? "DGX-ready pipeline" : "Local fallback pipeline";
    benchmarks.innerHTML = `
      <div><span>Data engine</span><strong>${escapeHtml(health.dataframe_engine)}</strong></div>
      <div><span>Model</span><strong>${escapeHtml(health.nim_model.split("/").pop())}</strong></div>
    `;
  } catch (error) {
    engineStatus.textContent = "Health unavailable";
    engineLabel.textContent = "Fallback mode";
  }
}

function payloadFromForm() {
  const data = new FormData(form);
  return {
    business_type: data.get("business_type"),
    crew_size: Number(data.get("crew_size")),
    base_neighbourhood: data.get("base_neighbourhood"),
    max_travel_minutes: Number(data.get("max_travel_minutes")),
    customer_focus: data.get("customer_focus"),
    priority_mode: data.get("priority_mode")
  };
}

async function scoreScenario(event) {
  if (event) event.preventDefault();
  setBusy(true);
  try {
    const response = await fetch("/api/recommend", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payloadFromForm())
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Recommendation failed");
    }
    latestResult = result;
    selectedZoneId = result.ranked_neighbourhoods[0]?.id || null;
    renderResult(result);
  } catch (error) {
    errorBox.textContent = `${error.message}. Demo fallback data is still available by running with SPARKTERRITORY_OFFLINE=1.`;
    errorBox.classList.remove("hidden");
  } finally {
    setBusy(false);
  }
}

function setBusy(isBusy) {
  loading.classList.toggle("hidden", !isBusy);
  errorBox.classList.add("hidden");
  form.querySelector("button").disabled = isBusy;
  if (isBusy) {
    let stage = 0;
    updateLoadingStage(stage);
    loadingTimer = window.setInterval(() => {
      stage = Math.min(stage + 1, loadingStages.length - 1);
      updateLoadingStage(stage);
    }, 520);
  } else {
    window.clearInterval(loadingTimer);
  }
}

function updateLoadingStage(stage) {
  loadingTitle.textContent = loadingStages[stage][0];
  loadingDetail.textContent = loadingStages[stage][1];
}

function renderResult(result) {
  const profile = result.business_profile;
  const preset = presetCopy[profile.business_type] || presetCopy.window_washing;
  const selected = selectedZone(result);
  resultTitle.textContent = selected
    ? `${selected.name} is the best next zone for ${preset.label}`
    : "No scored zones returned";
  mapSubtitle.textContent = `${preset.label}: ${preset.driver}`;
  agentMode.textContent = result.agent_mode === "nemotron_nim" ? "Nemotron NIM" : "Deterministic fallback";
  agentReport.textContent = "Expansion brief is ready. Select a zone or generate the judge-ready narrative.";
  briefButton.disabled = !selected;
  renderPipeline(result);
  renderMap(result);
  renderZonePanel(selected, result);
  renderRankedTargets(result);
}

function renderPipeline(result) {
  const steps = result.metadata.pipeline_steps || [];
  pipelineSteps.innerHTML = steps.map(step => `
    <li><span></span>${escapeHtml(step.label)} <em>${escapeHtml(step.detail)}</em></li>
  `).join("");
  const warnings = result.metadata.warnings || [];
  const mode = result.agent_mode === "nemotron_nim" ? "Local NIM" : "Fallback";
  benchmarks.innerHTML = `
    <div><span>Data engine</span><strong>${escapeHtml(result.metadata.dataframe_engine)}</strong></div>
    <div><span>Brief mode</span><strong>${mode}</strong></div>
    <div><span>Warnings</span><strong>${warnings.length}</strong></div>
  `;
}

function renderMap(result) {
  const zones = result.ranked_neighbourhoods.concat(result.future_expansion_neighbourhoods || []);
  const unique = new Map(zones.map(zone => [zone.id, zone]));
  mapZones.innerHTML = Array.from(unique.values()).map(zone => renderMapZone(zone)).join("");
  mapZones.querySelectorAll(".map-zone").forEach(node => {
    node.addEventListener("mouseenter", () => showPreview(node.dataset.zoneId));
    node.addEventListener("mouseleave", hidePreview);
    node.addEventListener("click", () => selectZone(node.dataset.zoneId));
  });
}

function renderMapZone(zone) {
  const score = Number(zone.overall_score) || 0;
  const size = 16 + score / 8;
  const isSelected = zone.id === selectedZoneId;
  const classes = ["map-zone", isSelected ? "selected" : "", `confidence-${confidenceClass(zone.confidence)}`].join(" ");
  const markers = markerDots(zone);
  return `
    <button class="${classes}" data-zone-id="${escapeHtml(zone.id)}"
      style="left:${zone.map.x}%; top:${zone.map.y}%; width:${size}px; height:${size}px;"
      title="${escapeHtml(zone.name)}: ${zone.overall_score}/100">
      <span>${zone.overall_score}</span>
    </button>
    <div class="zone-label" style="left:${zone.map.x}%; top:calc(${zone.map.y}% + ${size + 5}px);">
      ${escapeHtml(shortName(zone.name))}
    </div>
    ${markers}
  `;
}

function markerDots(zone) {
  const map = zone.map;
  const dots = [];
  if (activeLayers.has("permits")) {
    dots.push(dot("permit", map.x - 3, map.y + 4, "Permit demand"));
  }
  if (activeLayers.has("development")) {
    dots.push(dot("growth", map.x + 4, map.y - 4, "Growth pipeline"));
  }
  if (activeLayers.has("prospects")) {
    dots.push(dot("prospect", map.x + 6, map.y + 5, "Sales targets nearby"));
  }
  if (activeLayers.has("feasibility")) {
    dots.push(dot("feasible", map.x - 5, map.y - 5, "Crew feasibility"));
  }
  return dots.join("");
}

function dot(kind, x, y, label) {
  return `<span class="map-dot ${kind}" style="left:${x}%; top:${y}%;" title="${escapeHtml(label)}"></span>`;
}

function showPreview(zoneId) {
  const zone = findZone(zoneId);
  if (!zone) return;
  mapPreview.classList.remove("hidden");
  mapPreview.style.left = `${Math.min(72, zone.map.x + 4)}%`;
  mapPreview.style.top = `${Math.max(8, zone.map.y - 12)}%`;
  mapPreview.innerHTML = `
    <strong>${escapeHtml(zone.name)}</strong>
    <span>${zone.overall_score}/100 opportunity</span>
    <small>${escapeHtml(zone.top_positive_factors?.[0] || zone.evidence?.[0] || "Strong composite signal.")}</small>
  `;
}

function hidePreview() {
  mapPreview.classList.add("hidden");
}

function selectZone(zoneId) {
  selectedZoneId = zoneId;
  renderResult(latestResult);
}

function renderZonePanel(zone, result) {
  if (!zone) {
    zonePanel.innerHTML = `<div class="empty-zone"><p class="eyebrow">Zone explanation</p><h3>No zone selected</h3></div>`;
    return;
  }
  const profile = result.business_profile;
  const preset = presetCopy[profile.business_type] || presetCopy.window_washing;
  zonePanel.innerHTML = `
    <div class="zone-head">
      <div>
        <p class="eyebrow">Why this area wins</p>
        <h3>${escapeHtml(zone.name)}</h3>
        <span>${escapeHtml(zone.district)} for ${escapeHtml(preset.label)}</span>
      </div>
      <div class="big-score">${zone.overall_score}</div>
    </div>

    <div class="confidence-card">
      <strong>${escapeHtml(zone.confidence)} confidence</strong>
      <p>${escapeHtml(zone.confidence_reason)}</p>
    </div>

    <div class="score-grid">
      ${scoreTile("Demand", zone.component_scores.demand, "where work is likely")}
      ${scoreTile("Prospects", zone.component_scores.prospects, "who to sell to")}
      ${scoreTile("Growth", zone.component_scores.growth, "future work")}
      ${scoreTile("Feasibility", zone.component_scores.crew_feasibility, "crew practicality")}
    </div>

    <section class="factor-block good">
      <h4>Top drivers</h4>
      <ul>${zone.top_positive_factors.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>

    <section class="factor-block risk">
      <h4>Constraints</h4>
      <ul>${zone.top_negative_factors.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section>

    <section class="action-card">
      <h4>Next action</h4>
      <p>${escapeHtml(zone.recommended_action)}</p>
      <div class="prospects">
        <strong>${zone.sales_targets_nearby.estimated_targets}</strong>
        <span>estimated sales targets nearby</span>
      </div>
      <small>${escapeHtml(zone.sales_targets_nearby.examples.join(" / "))}</small>
    </section>
  `;
}

function scoreTile(label, value, caption) {
  return `
    <div class="score-tile">
      <span>${escapeHtml(label)}</span>
      <strong>${value}</strong>
      <em>${escapeHtml(caption)}</em>
    </div>
  `;
}

function renderRankedTargets(result) {
  const rows = result.ranked_neighbourhoods || [];
  targetCount.textContent = `${rows.length} zones`;
  targetTable.innerHTML = `
    <div class="table-head">
      <span>Zone</span><span>Score</span><span>Sales targets</span><span>Crew feasibility</span><span>Action</span>
    </div>
    ${rows.map(row => `
      <button class="target-row ${row.id === selectedZoneId ? "active" : ""}" data-zone-id="${escapeHtml(row.id)}">
        <span><strong>${escapeHtml(row.name)}</strong><em>${escapeHtml(row.district)} - ${escapeHtml(row.confidence)} confidence</em></span>
        <span>${row.overall_score}</span>
        <span>${row.prospect_count}</span>
        <span>${frictionLabel(row.operational_feasibility_score)}</span>
        <span>${escapeHtml(row.recommended_action)}</span>
      </button>
    `).join("")}
  `;
  targetTable.querySelectorAll(".target-row").forEach(row => {
    row.addEventListener("click", () => selectZone(row.dataset.zoneId));
  });
}

function generateBrief() {
  if (!latestResult) return;
  const zone = selectedZone(latestResult);
  if (!zone) return;
  const report = formatBrief(latestResult, zone);
  agentReport.textContent = "";
  briefButton.disabled = true;
  let index = 0;
  const timer = window.setInterval(() => {
    agentReport.textContent += report.slice(index, index + 18);
    index += 18;
    agentReport.scrollTop = agentReport.scrollHeight;
    if (index >= report.length) {
      window.clearInterval(timer);
      briefButton.disabled = false;
    }
  }, 18);
}

function formatBrief(result, zone) {
  const profile = result.business_profile;
  const preset = presetCopy[profile.business_type] || presetCopy.window_washing;
  const topZones = result.ranked_neighbourhoods.slice(0, 3).map((item, index) =>
    `${index + 1}. ${item.name} - ${item.overall_score}/100, ${item.confidence} confidence`
  ).join("\n");
  const agentText = result.agent_report || "No generated report was returned.";
  return [
    `EXPANSION BRIEF: ${preset.label.toUpperCase()}`,
    "",
    `Executive recommendation: Start with ${zone.name}. It is the strongest zone because ${zone.top_positive_factors[0]}`,
    "",
    "Top zones:",
    topZones,
    "",
    "Evidence summary:",
    `- Demand: ${zone.component_scores.demand}/100 from active permit signals.`,
    `- Growth: ${zone.component_scores.growth}/100 from development and cleared-permit momentum.`,
    `- Prospects: ${zone.sales_targets_nearby.estimated_targets} likely sales targets across ${zone.sales_targets_nearby.examples.join(", ")}.`,
    `- Crew feasibility: ${zone.component_scores.crew_feasibility}/100 from ${profile.base_neighbourhood} within ${profile.max_travel_minutes} minutes.`,
    "",
    "Operational notes:",
    `- ${zone.top_negative_factors[0]}`,
    `- Cluster the first week of outreach so a ${profile.crew_size}-person crew can protect drive time.`,
    "",
    "Grounded agent output:",
    agentText
  ].join("\n");
}

function selectedZone(result) {
  return findZone(selectedZoneId, result) || result?.ranked_neighbourhoods?.[0] || null;
}

function findZone(zoneId, result = latestResult) {
  if (!result || !zoneId) return null;
  return result.ranked_neighbourhoods.concat(result.future_expansion_neighbourhoods || [])
    .find(zone => zone.id === zoneId);
}

function confidenceClass(confidence) {
  return String(confidence || "medium").toLowerCase().replace(/[^a-z]/g, "-");
}

function frictionLabel(value) {
  if (value >= 75) return "Low friction";
  if (value >= 55) return "Moderate";
  return "Harder route";
}

function shortName(name) {
  return String(name).replace(" (includes Humber Bay Shores)", "");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

form.addEventListener("submit", scoreScenario);
briefButton.addEventListener("click", generateBrief);
businessType.addEventListener("change", () => {
  const preset = presetCopy[businessType.value] || presetCopy.window_washing;
  mapSubtitle.textContent = `${preset.label}: ${preset.driver}`;
});
document.querySelectorAll(".layer-toggles input").forEach(input => {
  input.addEventListener("change", () => {
    activeLayers = new Set(
      Array.from(document.querySelectorAll(".layer-toggles input:checked")).map(item => item.dataset.layer)
    );
    if (latestResult) renderMap(latestResult);
  });
});

loadHealth();
scoreScenario();
