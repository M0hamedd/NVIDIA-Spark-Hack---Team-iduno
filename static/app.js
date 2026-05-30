const DEFAULT_PROFILE = {
  name: "GTA Mechanical & Controls Ltd.",
  business_type: "commercial HVAC and building automation contractor",
  base_location: "Toronto, GTA",
  team_size: 18,
  max_contract_value: 750000,
  max_sites_per_day: 8,
  active_pursuit_count: 2,
  max_active_pursuits: 3,
  service_area: "Toronto",
  skills: [
    "HVAC maintenance",
    "building automation systems",
    "BAS controls",
    "boiler service",
    "chiller service",
    "preventative maintenance",
    "emergency repair",
    "energy retrofit support",
    "municipal facility service"
  ],
  ready_documents: ["insurance", "WSIB", "HST", "references", "technician certifications"],
  missing_capabilities: [
    "kitchen equipment",
    "road paving",
    "legal services",
    "food supply",
    "large design/build construction"
  ],
  response_days_available: 12
};

const PRIORITY_LABELS = {
  best_win_chance: "Best Win Chance",
  best_fit: "Best Fit",
  highest_value: "Highest Value"
};

const state = {
  health: null,
  scan: null,
  selectedOpportunityId: "",
  activeView: "owner",
  priorityMode: "best_win_chance"
};

const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", () => {
  renderProfile(DEFAULT_PROFILE);
  bindEvents();
  checkHealth();
});

function bindEvents() {
  $("scanButton").addEventListener("click", () => runScan(false));
  $("simulateButton").addEventListener("click", runSimulation);
  $("approveButton").addEventListener("click", approveDraft);
  $("ownerTab").addEventListener("click", () => setView("owner"));
  $("evidenceTab").addEventListener("click", () => setView("evidence"));
  document.querySelectorAll('input[name="priorityMode"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.priorityMode = getPriorityMode();
      if (state.scan) {
        $("lastRun").textContent = `Priority changed to ${PRIORITY_LABELS[state.priorityMode]}`;
      }
    });
  });
}

async function checkHealth() {
  try {
    const health = await apiGet("/api/health");
    state.health = health;
    $("healthStatus").textContent = "System online";
    $("healthStatus").className = "status-pill ok";
    $("gpuStatus").textContent = `DGX Spark: ${formatStatus(health.gpu)}`;
    $("nemotronStatus").textContent = `Nemotron: ${formatStatus(health.nemotron)}`;
  } catch (error) {
    $("healthStatus").textContent = "Backend unavailable";
    $("healthStatus").className = "status-pill error";
    $("gpuStatus").textContent = "DGX Spark: unknown";
    $("nemotronStatus").textContent = "Nemotron: unknown";
    showToast(error.message);
  }
}

async function runScan(refresh) {
  setBusy(true, "Scanning live procurement data");
  try {
    const result = await apiPost("/api/scan", {
      business_profile: DEFAULT_PROFILE,
      priority_mode: getPriorityMode(),
      refresh
    });
    ingestResult(result, "Live scan complete");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
}

async function runSimulation() {
  setBusy(true, "Simulating next monitoring day");
  try {
    const result = await apiPost("/api/simulate", {
      business_profile: DEFAULT_PROFILE,
      priority_mode: getPriorityMode(),
      days: 1
    });
    ingestResult(result, "Next-day simulation complete");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
}

async function approveDraft() {
  if (!state.selectedOpportunityId) {
    showToast("Select an opportunity before approving.");
    return;
  }

  setBusy(true, "Preparing approval packet");
  try {
    const result = await apiPost("/api/approve", {
      business_profile: DEFAULT_PROFILE,
      approved: true,
      opportunity_id: state.selectedOpportunityId
    });
    renderPacket(result.packet, result.approved);
    $("packetStatus").textContent = result.approved ? "Approved" : "Blocked";
    showToast("Approval packet prepared");
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
}

function ingestResult(result, message) {
  state.scan = result;
  const top = result.top_opportunities || [];
  const watch = result.watchlist || [];
  const selected = top[0] || watch[0] || null;
  state.selectedOpportunityId = selected ? getOpportunityId(selected) : "";

  renderProfile(result.business_profile || DEFAULT_PROFILE);
  renderOwner(result);
  renderEvidence(result);
  $("approveButton").disabled = !state.selectedOpportunityId;
  showToast(message);
}

function renderProfile(profile) {
  $("profileName").textContent = profile.name || DEFAULT_PROFILE.name;
  $("profileType").textContent = titleCase(profile.business_type || DEFAULT_PROFILE.business_type);
  $("profileBase").textContent = profile.base_location || DEFAULT_PROFILE.base_location;
  $("profileTeam").textContent = `${profile.team_size || DEFAULT_PROFILE.team_size} people`;
  $("profileCapacity").textContent = `${profile.max_sites_per_day || DEFAULT_PROFILE.max_sites_per_day} city sites/day, up to ${formatMoney(profile.max_contract_value || DEFAULT_PROFILE.max_contract_value)}`;
  $("profilePursuits").textContent = `${profile.active_pursuit_count ?? DEFAULT_PROFILE.active_pursuit_count} active, limit ${profile.max_active_pursuits ?? DEFAULT_PROFILE.max_active_pursuits}`;
  renderTags($("profileSkills"), profile.skills || DEFAULT_PROFILE.skills);
  renderTags($("profileDocs"), profile.ready_documents || DEFAULT_PROFILE.ready_documents);
}

function renderOwner(result) {
  const top = result.top_opportunities || [];
  const watch = result.watchlist || [];
  const timeline = result.timeline || [];
  const metrics = result.metrics || {};
  const topDecision = top[0] || watch[0];

  $("decisionHeadline").textContent = topDecision
    ? `${decisionLabel(topDecision.label)}: ${getTitle(topDecision)}`
    : "No strong pursuit found today";
  $("lastRun").textContent = result.as_of
    ? `As of ${result.as_of} - ${PRIORITY_LABELS[getPriorityMode()]}`
    : `Latest scan - ${PRIORITY_LABELS[getPriorityMode()]}`;

  $("topCount").textContent = String(top.length);
  $("watchCount").textContent = String(watch.length);
  $("timelineCount").textContent = String(timeline.length);

  renderOpportunityList($("topOpportunities"), top, "No pursue or review opportunities found.");
  renderOpportunityList($("watchlist"), watch, "No monitor items yet.");
  renderTimeline(timeline);

  if (!metrics || Object.keys(metrics).length === 0) {
    $("packetStatus").textContent = "Not prepared";
  }
}

function renderEvidence(result) {
  const metrics = result.metrics || {};
  const skipped = result.skipped || [];
  const evaluated = result.all_evaluated || [];
  const scorecard = result.insight_scorecard || {};

  $("metricSolicitations").textContent = number(metrics.solicitations_loaded);
  $("metricAwards").textContent = number(metrics.awards_loaded);
  $("metricRejected").textContent = number(metrics.rejected_count);
  $("metricRuntime").textContent = `${number(metrics.runtime_ms)} ms`;
  $("metricRecordsPerSecond").textContent = number(metrics.records_per_second);
  $("metricModelCallsAvoided").textContent = number(metrics.model_calls_avoided);
  $("metricNvidiaPath").textContent = nvidiaPathLabel(metrics);
  $("metricBacktestInsight").textContent = number(scorecard.realistic_historical_opportunities);
  $("engineLabel").textContent = metrics.engine || "python";
  $("skipCount").textContent = String(skipped.length);
  $("evaluatedCount").textContent = String(evaluated.length);

  renderPipeline(metrics);
  renderOpportunityList($("skippedExamples"), skipped, "No skipped examples returned.");
  renderScorecard(result);
  renderEvaluatedStream(evaluated);
}

function renderOpportunityList(container, items, emptyText) {
  container.className = items.length ? "card-list" : "card-list empty-list";
  if (!items.length) {
    container.innerHTML = `<p>${escapeHtml(emptyText)}</p>`;
    return;
  }

  container.innerHTML = items.map((item) => opportunityCard(item)).join("");
  container.querySelectorAll(".opportunity-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.selectedOpportunityId = card.dataset.id || "";
      $("approveButton").disabled = !state.selectedOpportunityId;
      renderOwner(state.scan);
      renderEvidence(state.scan);
    });
  });
}

function opportunityCard(item) {
  const id = getOpportunityId(item);
  const solicitation = item.solicitation || {};
  const selected = id && id === state.selectedOpportunityId ? " selected" : "";
  const deadline = solicitation.submission_deadline || "No deadline listed";
  const days = item.days_until_deadline ?? "";
  const dayText = days === "" || days === null ? "" : `${days} days left`;
  const displayLabel = decisionLabel(item.label);
  const reasonSource = displayLabel === "Skip"
    ? [
      ...(item.rejection_reasons || []),
      ...(item.missing_requirements || []),
      ...(item.reasons || [])
    ]
    : item.reasons || item.rejection_reasons || [];
  const reasons = firstItems(reasonSource, 3);
  const terms = firstItems(item.matched_terms || [], 4);
  const history = formatHistory(item.historical, item.label);
  const capacityWarnings = capacityWarningItems(item);
  const capacity = capacitySummary(item);

  return `
    <article class="opportunity-card${selected}" data-id="${escapeHtml(id)}" tabindex="0">
      <div class="card-topline">
        <h4 class="card-title">${escapeHtml(getTitle(item))}</h4>
        <span class="label-pill ${labelClass(displayLabel)}">${escapeHtml(displayLabel)}</span>
      </div>
      <div class="card-meta">
        <span>${escapeHtml(solicitation.solicitation_type || "Solicitation")}</span>
        <span>${escapeHtml(solicitation.category || "Uncategorized")}</span>
        <span>Due ${escapeHtml(deadline)}</span>
        ${dayText ? `<span>${escapeHtml(dayText)}</span>` : ""}
      </div>
      ${terms.length ? `<div class="tag-grid compact">${terms.map((term) => `<span class="tag">${escapeHtml(term)}</span>`).join("")}</div>` : ""}
      ${reasons.length ? `<ul class="reason-list">${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>` : ""}
      ${capacity ? `<div class="capacity-line">${escapeHtml(capacity)}</div>` : ""}
      ${capacityWarnings.length ? `<ul class="capacity-warnings">${capacityWarnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}</ul>` : ""}
      ${history ? `<div class="history-line">${escapeHtml(history)}</div>` : ""}
    </article>
  `;
}

function renderPipeline(metrics) {
  const selected = findSelectedOpportunity() || firstDecisionOpportunity();
  const solicitation = (selected && selected.solicitation) || {};
  const structuredRequirements = getStructuredRequirements(selected);
  const requirements = firstItems((selected && selected.matched_terms) || [], 5);
  const reasons = firstItems((selected && (selected.reasons || selected.rejection_reasons)) || [], 3);
  const supporting = supportingLabels(selected);
  const warnings = firstItems(metrics.warnings || [], 2);
  const stages = [
    {
      name: "Open Data Feed",
      output: metrics.solicitations_loaded
        ? `Toronto Open Data returned ${number(metrics.solicitations_loaded)} solicitations and ${number(metrics.awards_loaded)} award records; deterministic shortlisting avoided ${number(metrics.model_calls_avoided)} model call(s).`
        : "Toronto Open Data feed is ready for the next scan."
    },
    {
      name: "Contract Parser",
      output: selected
        ? `${solicitation.solicitation_type || "Solicitation"} from ${solicitation.buyer || solicitation.division || "Toronto buyer"}; deadline ${solicitation.submission_deadline || "not listed"}.`
        : "No contract selected yet."
    },
    {
      name: "Requirement Extractor",
      output: requirementExtractionLanguage(selected, structuredRequirements, requirements, solicitation),
      source: extractorSourceLabel(structuredRequirements)
    },
    {
      name: "Profile Matcher",
      output: supporting.coreFit
        ? `Core Fit: ${supporting.coreFit}. ${reasons[0] || "Compared against HVAC, controls, emergency repair, and municipal facility experience."}`
        : reasons[0] || "Compares scope to GTA Mechanical & Controls Ltd. services and capacity."
    },
    {
      name: "Award Comparator",
      output: awardLanguage(selected)
    },
    {
      name: "Risk Filter",
      output: riskLanguage(selected, supporting, structuredRequirements)
    },
    {
      name: "Recommendation",
      output: selected
        ? `${decisionLabel(selected.label)} under ${PRIORITY_LABELS[getPriorityMode()]}. ${finalReason(selected, structuredRequirements)}`
        : `Waiting for a scan using ${PRIORITY_LABELS[getPriorityMode()]}.`
    }
  ];

  if (warnings.length) {
    stages[0].note = warnings.join(" ");
  }

  $("pipelineDetails").className = "pipeline-list";
  $("pipelineDetails").innerHTML = stages.map((stage, index) => `
    <article class="pipeline-stage">
      <div class="stage-marker" aria-hidden="true">${index + 1}</div>
      <div class="stage-body">
        <h4>${escapeHtml(stage.name)}</h4>
        ${stage.source ? `<div class="source-label">${escapeHtml(stage.source)}</div>` : ""}
        <p>${escapeHtml(stage.output)}</p>
        ${stage.note ? `<span>${escapeHtml(stage.note)}</span>` : ""}
      </div>
    </article>
  `).join("");
}

function renderScorecard(result) {
  const metrics = result.metrics || {};
  const scorecard = result.insight_scorecard || {};
  const container = $("scorecardDetails");
  const hasScorecard = Object.keys(scorecard).length > 0;
  $("scorecardStatus").textContent = hasScorecard ? "Ready" : "Waiting";

  if (!hasScorecard) {
    container.className = "scorecard-grid empty-list";
    container.innerHTML = "<p>Run a scan to see NVIDIA path, model efficiency, false-positive rejection, and historical insight proof.</p>";
    return;
  }

  container.className = "scorecard-grid";
  const activeNvidia = nvidiaPathLabel(metrics);
  const reduction = Number(metrics.shortlist_reduction_ratio || 0);
  const reductionText = `${Math.round(reduction * 100)}% shortlist reduction`;
  container.innerHTML = `
    <article class="scorecard-item">
      <span>NVIDIA Stack</span>
      <strong>${escapeHtml(activeNvidia)}</strong>
      <p>RAPIDS: ${escapeHtml(metrics.rapids_mode || "python_fallback")} | NIM: ${escapeHtml(metrics.nemotron_mode || "deterministic_fallback")}</p>
    </article>
    <article class="scorecard-item">
      <span>Model Efficiency</span>
      <strong>${number(metrics.model_calls_avoided)} avoided</strong>
      <p>${number(metrics.model_calls_attempted)} attempted | ${escapeHtml(reductionText)}</p>
    </article>
    <article class="scorecard-item">
      <span>Insight Proof</span>
      <strong>${number(scorecard.false_positives_skipped)} skipped</strong>
      <p>${number(scorecard.similar_awards_grounded)} similar awards grounded | ${number(scorecard.estimated_bid_hours_saved)} bid-review hours saved</p>
    </article>
    <article class="scorecard-item wide">
      <span>Judge Insight</span>
      <strong>${number(scorecard.realistic_historical_opportunities)} realistic historical opportunities</strong>
      <p>${escapeHtml(scorecard.top_insight || "Historical and false-positive evidence will appear after scan.")}</p>
    </article>
  `;
}

function renderEvaluatedStream(items) {
  const container = $("evaluatedStream");
  container.className = items.length ? "table-list" : "table-list empty-list";
  if (!items.length) {
    container.innerHTML = "<p>No evaluated opportunities yet.</p>";
    return;
  }

  container.innerHTML = items.map((item) => {
    const solicitation = item.solicitation || {};
    return `
      <div class="stream-row">
        <strong>${escapeHtml(getTitle(item))}</strong>
        <span class="label-pill ${labelClass(decisionLabel(item.label))}">${escapeHtml(decisionLabel(item.label))}</span>
        <span>${escapeHtml(solicitation.submission_deadline || "No deadline")}</span>
      </div>
    `;
  }).join("");
}

function renderTimeline(items) {
  const container = $("timeline");
  container.className = items.length ? "timeline" : "timeline empty-list";
  if (!items.length) {
    container.innerHTML = "<p>Run a simulation to see alerts, deadline pressure, and approval events.</p>";
    return;
  }

  container.innerHTML = items.map((item) => {
    const date = item.date || item.day || item.when || "Day";
    const title = item.title || item.event || item.type || "Timeline event";
    const body = item.description || item.message || item.detail || "";
    return `
      <div class="timeline-item">
        <div class="timeline-date">${escapeHtml(String(date))}</div>
        <div class="timeline-body">
          <strong>${escapeHtml(String(title))}</strong>
          <span>${escapeHtml(String(body))}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderPacket(packet, approved) {
  const container = $("packetOutput");
  if (!packet) {
    container.className = "packet-output empty-list";
    container.innerHTML = "<p>No packet returned.</p>";
    return;
  }

  container.className = "packet-output";
  const contact = packet.buyer_contact || {};
  container.innerHTML = `
    <div class="packet-grid">
      <div class="packet-card">
        <strong>${escapeHtml(packet.title || "Bid packet")}</strong>
        <span>${escapeHtml(packet.summary || "Packet prepared from computed evidence.")}</span>
      </div>
      <div class="packet-card">
        <strong>Status</strong>
        <span>${approved ? "Approved by owner. Simulated submission only." : "Owner approval required."}</span>
        ${packet.simulated_receipt ? `<p>${escapeHtml(packet.simulated_receipt)}</p>` : ""}
      </div>
      <div class="packet-card">
        <strong>Checklist</strong>
        ${renderList(packet.checklist || [])}
      </div>
      <div class="packet-card">
        <strong>Buyer Contact</strong>
        ${renderList([contact.name, contact.email, contact.phone].filter(Boolean))}
      </div>
      <div class="packet-card">
        <strong>SAP Ariba Steps</strong>
        ${renderOrderedList(packet.sap_ariba_steps || [])}
      </div>
      <div class="packet-card">
        <strong>Draft Email</strong>
        <p class="draft-email">${escapeHtml(packet.draft_email || "No draft returned.")}</p>
      </div>
    </div>
  `;
}

function setView(view) {
  state.activeView = view;
  $("ownerTab").classList.toggle("active", view === "owner");
  $("evidenceTab").classList.toggle("active", view === "evidence");
  $("ownerView").classList.toggle("active", view === "owner");
  $("evidenceView").classList.toggle("active", view === "evidence");
}

function setBusy(isBusy, message = "") {
  $("scanButton").disabled = isBusy;
  $("simulateButton").disabled = isBusy;
  $("approveButton").disabled = isBusy || !state.selectedOpportunityId;
  if (isBusy && message) {
    showToast(message);
  }
}

async function apiGet(path) {
  const response = await fetch(path);
  return parseResponse(response);
}

async function apiPost(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return parseResponse(response);
}

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function renderTags(container, items) {
  container.innerHTML = (items || [])
    .map((item) => `<span class="tag">${escapeHtml(String(item))}</span>`)
    .join("");
}

function renderList(items) {
  if (!items.length) {
    return "<p>None listed.</p>";
  }
  return `<ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`;
}

function renderOrderedList(items) {
  if (!items.length) {
    return "<p>None listed.</p>";
  }
  return `<ol>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ol>`;
}

function getOpportunityId(item) {
  return String((item.solicitation || {}).document_number || "");
}

function getTitle(item) {
  const solicitation = item.solicitation || {};
  return solicitation.description || solicitation.document_number || "Untitled opportunity";
}

function formatHistory(history, label) {
  if (!history) {
    return "";
  }
  if (!history.similar_count) {
    return history.accessibility ? `History: ${history.accessibility}` : "";
  }
  const median = history.award_median ? formatMoney(history.award_median) : "unknown median";
  if (decisionLabel(label) === "Pursue" && String(history.accessibility || "").includes("partner")) {
    return `History: ${history.similar_count} similar awards, median ${median}; verify final scope before bidding`;
  }
  return `History: ${history.similar_count} similar awards, median ${median}, ${history.accessibility || "comparison available"}`;
}

function labelClass(label) {
  const normalized = String(decisionLabel(label) || "").toLowerCase().replace(/\s+/g, "-");
  return `label-${normalized}`;
}

function decisionLabel(label) {
  const normalized = String(label || "").trim().toLowerCase();
  const replacements = {
    "bid this": "Pursue",
    urgent: "Pursue",
    "get partner": "Review",
    watchlist: "Monitor",
    monitor: "Monitor",
    pursue: "Pursue",
    review: "Review",
    skip: "Skip"
  };
  return replacements[normalized] || (label ? titleCase(label) : "Monitor");
}

function getPriorityMode() {
  const selected = document.querySelector('input[name="priorityMode"]:checked');
  return selected ? selected.value : state.priorityMode;
}

function findSelectedOpportunity() {
  if (!state.scan || !state.selectedOpportunityId) {
    return null;
  }
  const groups = [
    state.scan.top_opportunities || [],
    state.scan.watchlist || [],
    state.scan.skipped || [],
    state.scan.all_evaluated || []
  ];
  return groups.flat().find((item) => getOpportunityId(item) === state.selectedOpportunityId) || null;
}

function firstDecisionOpportunity() {
  if (!state.scan) {
    return null;
  }
  return (state.scan.top_opportunities || [])[0]
    || (state.scan.watchlist || [])[0]
    || (state.scan.skipped || [])[0]
    || (state.scan.all_evaluated || [])[0]
    || null;
}

function supportingLabels(item) {
  if (!item) {
    return {};
  }
  const evidence = item.evidence || item.decision_evidence || {};
  return {
    coreFit: item.core_fit || evidence.core_fit,
    eligibility: item.eligibility || evidence.eligibility,
    competition: item.competition || evidence.competition,
    pursuitEffort: item.pursuit_effort || evidence.pursuit_effort,
    deadlineRisk: item.deadline_risk || evidence.deadline_risk,
    strategicValue: item.strategic_value || evidence.strategic_value
  };
}

function getStructuredRequirements(item) {
  if (!item) {
    return null;
  }
  const requirements = item.requirements || item.nemotron_requirements;
  return requirements && typeof requirements === "object" ? requirements : null;
}

function extractorSourceLabel(requirements) {
  if (!requirements || !requirements.source) {
    return "";
  }
  const sourceLabels = {
    local_nim: "local NIM",
    deterministic_fallback: "deterministic fallback"
  };
  const source = sourceLabels[requirements.source] || humanizeToken(requirements.source);
  return `Extractor: ${source}`;
}

function requirementExtractionLanguage(item, requirements, fallbackTerms, solicitation) {
  if (!item) {
    return "Requirements will appear after a candidate is evaluated.";
  }
  if (requirements) {
    const parts = [];
    const services = firstItems(requirements.services, 3);
    const certifications = firstItems(requirements.certifications, 2);
    const documents = firstItems(requirements.documents, 2);
    const facilitySignals = firstItems(requirements.facility_signals, 2);
    const procurementType = requirements.procurement_type;

    if (services.length) {
      parts.push(`Services: ${services.join(", ")}`);
    }
    if (certifications.length) {
      parts.push(`Certifications: ${certifications.join(", ")}`);
    }
    if (documents.length) {
      parts.push(`Documents: ${documents.join(", ")}`);
    }
    if (facilitySignals.length) {
      parts.push(`Facility signals: ${facilitySignals.join(", ")}`);
    }
    if (procurementType) {
      parts.push(`Procurement type: ${procurementType}`);
    }
    if (parts.length) {
      return parts.join(". ") + ".";
    }
  }
  if (fallbackTerms.length) {
    return `Found scope signals: ${fallbackTerms.join(", ")}.`;
  }
  return `Used category and description to identify ${solicitation.category || "the procurement scope"}.`;
}

function awardLanguage(item) {
  const history = item && item.historical;
  if (!history) {
    return "Checks similar public awards when award history is available.";
  }
  if (!history.similar_count) {
    return history.accessibility || "No strong similar awards found in the comparison set.";
  }
  const median = history.award_median ? formatMoney(history.award_median) : "typical value not listed";
  return `${history.similar_count} similar awards found; typical award ${median}; ${history.accessibility || "scope looks comparable"}.`;
}

function riskLanguage(item, supporting, requirements) {
  if (!item) {
    return "Eligibility, effort, deadline, and capacity risks will be checked after scan.";
  }
  const parts = [];
  const riskFlags = requirements ? firstItems(requirements.risk_flags, 3) : [];
  const capacityFlags = requirements ? firstItems(requirements.capacity_flags, 3) : [];
  const assessment = getCapacityAssessment(item);
  const assessmentWarnings = capacityWarningItems(item);
  const rejectionReasons = item ? firstItems(item.rejection_reasons, 3) : [];
  const deadlineRisk = (requirements && requirements.deadline_risk) || supporting.deadlineRisk;

  if (riskFlags.length) {
    parts.push(`Risk flags: ${riskFlags.join(", ")}`);
  }
  if (capacityFlags.length) {
    parts.push(`Capacity flags: ${capacityFlags.join(", ")}`);
  }
  if (rejectionReasons.length) {
    parts.push(`Blockers: ${rejectionReasons.join(", ")}`);
  }
  if (assessment) {
    parts.push(
      `Pursuit Load: ${assessment.pursuit_load}`,
      `Response Capacity: ${assessment.response_capacity}`,
      `Execution Capacity: ${assessment.execution_capacity}`,
      `Recommended Action: ${assessment.recommended_action}`
    );
  }
  if (assessmentWarnings.length) {
    parts.push(`Warning: ${assessmentWarnings[0]}`);
  }
  if (supporting.eligibility) {
    parts.push(`Eligibility: ${supporting.eligibility}`);
  }
  if (deadlineRisk) {
    parts.push(`Deadline risk: ${deadlineRisk}`);
  }
  if (supporting.pursuitEffort) {
    parts.push(`Pursuit Effort: ${supporting.pursuitEffort}`);
  }
  if (parts.length) {
    return parts.join(". ") + ".";
  }
  const reasons = item.rejection_reasons || item.risks || [];
  return reasons.length ? firstItems(reasons, 2).join(" ") : "No obvious certification or capacity blocker surfaced.";
}

function finalReason(item, requirements) {
  const assessment = getCapacityAssessment(item);
  const rejectionReasons = firstItems(item.rejection_reasons, 2);
  if (decisionLabel(item.label) === "Skip" && rejectionReasons.length) {
    return `Blocked: ${rejectionReasons.join(", ")}`;
  }
  if (assessment && assessment.recommended_action === "Pursue After Review") {
    return `Capacity gate: ${assessment.recommended_action}`;
  }
  if (requirements && requirements.next_action) {
    return `Next action: ${requirements.next_action}`;
  }
  const reasons = item.reasons || item.rejection_reasons || [];
  if (reasons.length) {
    return reasons[0];
  }
  const label = decisionLabel(item.label);
  if (label === "Pursue") {
    return "Strong enough to justify owner attention.";
  }
  if (label === "Review") {
    return "Potential fit with a risk requiring human judgment.";
  }
  if (label === "Skip") {
    return "Poor fit or likely waste of bid effort.";
  }
  return "Relevant, but not yet strong enough for immediate pursuit.";
}

function getCapacityAssessment(item) {
  if (!item || !item.capacity_assessment) {
    return null;
  }
  return item.capacity_assessment;
}

function capacitySummary(item) {
  const assessment = getCapacityAssessment(item);
  if (!assessment) {
    return "";
  }
  return `Capacity: ${assessment.pursuit_load} load, ${assessment.response_capacity.toLowerCase()}, ${assessment.execution_capacity.toLowerCase()}.`;
}

function capacityWarningItems(item) {
  const assessment = getCapacityAssessment(item);
  if (!assessment || !Array.isArray(assessment.warnings)) {
    return [];
  }
  return firstItems(assessment.warnings, 2);
}

function firstItems(items, limit) {
  if (Array.isArray(items)) {
    return items.filter(Boolean).slice(0, limit);
  }
  return items ? [items].slice(0, limit) : [];
}

function humanizeToken(value) {
  return String(value || "").replace(/[_-]+/g, " ").trim();
}

function nvidiaPathLabel(metrics) {
  if (!metrics || !metrics.nvidia_stack_active) {
    return "Fallback";
  }
  const tools = metrics.active_nvidia_tools || [];
  if (tools.length) {
    return tools.join(", ");
  }
  if (metrics.rapids_mode === "rapids_cudf") {
    return "RAPIDS/cuDF";
  }
  if (metrics.nemotron_mode === "local_nim") {
    return "NIM/Nemotron";
  }
  return "Active";
}

function formatStatus(value) {
  if (!value) {
    return "unknown";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "object") {
    if (Object.prototype.hasOwnProperty.call(value, "rapids_cudf_available")) {
      return value.rapids_cudf_available ? "RAPIDS ready" : "CPU fallback";
    }
    if (value.mode && value.fallback) {
      return value.mode === value.fallback ? value.fallback : `${value.mode}, fallback ready`;
    }
    return value.status || value.mode || value.name || JSON.stringify(value);
  }
  return String(value);
}

function formatMoney(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 0
  }).format(amount);
}

function number(value) {
  const amount = Number(value || 0);
  return new Intl.NumberFormat("en-CA").format(amount);
}

function titleCase(value) {
  return String(value || "").replace(/\w\S*/g, (word) => (
    word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  ));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

let toastTimer = 0;
function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => {
    toast.classList.remove("visible");
  }, 2800);
}
