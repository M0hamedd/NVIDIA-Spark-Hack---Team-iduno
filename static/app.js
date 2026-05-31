const DEMO_PROFILE_ORDER = [
  "road_civil_infrastructure",
  "parks_landscape",
  "professional_engineering_design"
];

const DEFAULT_PROFILE_ID = DEMO_PROFILE_ORDER[0];

const LOADING_PROFILE = {
  profile_id: "",
  label: "Loading profiles",
  name: "Loading supported profiles",
  business_type: "Waiting for /api/health",
  base_location: "Toronto",
  skills: [],
  ready_documents: [],
  top_divisions: [],
  good_fit_examples: [],
  bad_fit_examples: []
};

const PRIORITY_LABELS = {
  best_win_chance: "Best Win Chance",
  best_fit: "Best Fit",
  highest_value: "Highest Value"
};

const state = {
  health: null,
  supportedProfiles: [],
  scan: null,
  selectedOpportunityId: "",
  activeView: "owner",
  priorityMode: "best_win_chance",
  selectedProfileId: DEFAULT_PROFILE_ID
};

const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", () => {
  renderProfileSelector();
  renderProfile(currentProfile());
  bindEvents();
  resetWorkspace("Loading supported profiles from /api/health");
  setBusy(false);
  checkHealth();
});

function bindEvents() {
  $("scanButton").addEventListener("click", () => runScan(false));
  $("simulateButton").addEventListener("click", runSimulation);
  $("approveButton").addEventListener("click", approveDraft);
  $("ownerTab").addEventListener("click", () => setView("owner"));
  $("evidenceTab").addEventListener("click", () => setView("evidence"));
  $("profileOptions").addEventListener("change", (event) => {
    const input = event.target;
    if (input && input.matches('input[name="supportedProfile"]')) {
      state.selectedProfileId = input.value;
      state.selectedOpportunityId = "";
      state.scan = null;
      const profile = currentProfile();
      renderProfile(profile);
      resetWorkspace(`${profileLabel(profile)} selected. Run a fresh scan for this persona.`);
      showToast(`${profileLabel(profile)} selected. Run a fresh scan.`);
    }
  });
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
    state.supportedProfiles = supportedProfilesFromHealth(health);
    state.selectedProfileId = selectProfileId(state.selectedProfileId);
    renderProfileSelector();
    renderProfile(currentProfile());
    if (!state.scan) {
      resetWorkspace(`${profileLabel(currentProfile())} loaded. Run a live scan to rank current Toronto opportunities.`);
    }
    $("healthStatus").textContent = "System online";
    $("healthStatus").className = "status-pill ok";
    $("gpuStatus").textContent = `DGX: ${compactRuntimeStatus(health.gpu)}`;
    $("nemotronStatus").textContent = `NIM: ${compactRuntimeStatus(health.nemotron)}`;
    setBusy(false);
    if (!state.supportedProfiles.length) {
      showToast("Health returned no supported demo profiles.");
    }
  } catch (error) {
    $("healthStatus").textContent = "Backend unavailable";
    $("healthStatus").className = "status-pill error";
    $("gpuStatus").textContent = "DGX Spark: unknown";
    $("nemotronStatus").textContent = "Nemotron: unknown";
    state.supportedProfiles = [];
    renderProfileSelector();
    renderProfile(currentProfile());
    setBusy(false);
    showToast(error.message);
  }
}

async function runScan(refresh) {
  const profile = currentProfile();
  if (!profile.profile_id) {
    showToast("Supported profiles are still loading from /api/health.");
    return;
  }
  setBusy(true, "Scanning live procurement data");
  try {
    const result = await apiPost("/api/scan", {
      profile_id: profile.profile_id,
      business_profile: profile,
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
  const profile = currentProfile();
  if (!profile.profile_id) {
    showToast("Supported profiles are still loading from /api/health.");
    return;
  }
  setBusy(true, "Simulating next monitoring day");
  try {
    const result = await apiPost("/api/simulate", {
      profile_id: profile.profile_id,
      business_profile: profile,
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
    const profile = currentProfile();
    const result = await apiPost("/api/approve", {
      profile_id: profile.profile_id,
      business_profile: profile,
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
  state.selectedProfileId = selectProfileId(
    (result.business_profile && result.business_profile.profile_id) || state.selectedProfileId
  );
  const top = result.top_opportunities || [];
  const watch = result.watchlist || [];
  const selected = top[0] || watch[0] || null;
  state.selectedOpportunityId = selected ? getOpportunityId(selected) : "";

  renderProfileSelector();
  renderProfile(result.business_profile || currentProfile());
  renderOwner(result);
  renderEvidence(result);
  $("approveButton").disabled = !canApproveCurrent();
  showToast(message);
}

function renderProfileSelector() {
  const container = $("profileOptions");
  if (!container) {
    return;
  }
  const profiles = state.supportedProfiles;
  if (!profiles.length) {
    container.innerHTML = "<p class=\"profile-loading\">Loading supported profiles from /api/health...</p>";
    return;
  }
  container.innerHTML = profiles.map((profile) => `
    <label>
      <input type="radio" name="supportedProfile" value="${escapeHtml(profile.profile_id)}" ${profile.profile_id === state.selectedProfileId ? "checked" : ""}>
      <span class="profile-lens-copy">
        <strong>${escapeHtml(compactProfileLabel(profile))}</strong>
      </span>
    </label>
  `).join("");
}

function renderProfile(profile) {
  const active = profile && profile.profile_id ? profileWithSupportedEvidence(profile) : currentProfile();
  $("profileName").textContent = compactProfileLabel(active);
  $("profileType").textContent = titleCase(active.business_type || "Not listed");
  $("profileBase").textContent = active.base_location || active.service_area || "Not listed";
  $("profileTeam").textContent = active.team_size ? `${active.team_size} people` : "Not listed";
  $("profileCapacity").textContent = profileCapacityText(active);
  $("profilePursuits").textContent = profilePursuitsText(active);
  renderTags($("profileSkills"), active.skills || []);
  renderTags($("profileDocs"), active.ready_documents || []);
  renderProfileEvidence(active);
  renderActiveProfileEvidence(active);
}

function resetWorkspace(message) {
  $("decisionHeadline").textContent = "Ready to scan city opportunities";
  $("lastRun").textContent = message || "No scan yet";
  $("summaryRecommendation").textContent = "Waiting";
  $("summaryDeadline").textContent = "Not scanned";
  $("summaryTask").textContent = "Run scan";
  $("summaryFit").textContent = "No signal yet";
  $("topCount").textContent = "0";
  $("watchCount").textContent = "0";
  $("timelineCount").textContent = "0";
  $("topOpportunities").className = "docket-list empty-list";
  $("topOpportunities").innerHTML = "<p>Run a scan to find contracts worth acting on.</p>";
  $("watchlist").className = "docket-list empty-list";
  $("watchlist").innerHTML = "<p>Relevant but not ready opportunities will appear here.</p>";
  $("selectedOpportunityDetail").className = "selected-detail empty-list";
  $("selectedOpportunityDetail").innerHTML = "<p>Select an opportunity after a scan to inspect deadline pressure, award history, capacity, and approval readiness.</p>";
  $("gateStatus").textContent = "Waiting";
  $("decisionGateChecklist").className = "gate-checklist empty-list";
  $("decisionGateChecklist").innerHTML = "<p>Run a scan to build the bid gate.</p>";
  $("timeline").className = "timeline empty-list";
  $("timeline").innerHTML = "<p>Run a simulation to see alerts, deadline pressure, and approval events.</p>";
  $("packetStatus").textContent = "Not prepared";
  $("packetOutput").className = "packet-output empty-list";
  $("packetOutput").innerHTML = "<p>Select an opportunity and approve the draft to prepare the packet.</p>";
  $("metricSolicitations").textContent = "0";
  $("metricAwards").textContent = "0";
  $("metricRejected").textContent = "0";
  $("metricRuntime").textContent = "0 ms";
  $("metricRecordsPerSecond").textContent = "0";
  $("metricModelCallsAvoided").textContent = "0";
  $("metricNvidiaPath").textContent = "Fallback";
  $("metricBacktestInsight").textContent = "0";
  $("engineLabel").textContent = "Python";
  $("skipCount").textContent = "0";
  $("evaluatedCount").textContent = "0";
  $("pipelineDetails").className = "pipeline-list empty-list";
  $("pipelineDetails").innerHTML = "<p>Evidence appears after a scan.</p>";
  $("skippedExamples").className = "docket-list empty-list";
  $("skippedExamples").innerHTML = "<p>Rejected opportunities will show why the system saves owner time.</p>";
  $("scorecardStatus").textContent = "Waiting";
  $("scorecardDetails").className = "scorecard-grid empty-list";
  $("scorecardDetails").innerHTML = "<p>Run a scan to see NVIDIA path, model efficiency, false-positive rejection, and historical insight proof.</p>";
  $("evaluatedStream").className = "table-list empty-list";
  $("evaluatedStream").innerHTML = "<p>Run a live scan to inspect the ranked stream.</p>";
  $("approveButton").disabled = true;
}

function renderOwner(result) {
  const top = result.top_opportunities || [];
  const watch = result.watchlist || [];
  const timeline = result.timeline || [];
  const metrics = result.metrics || {};
  const topDecision = top[0] || watch[0];
  const selected = findSelectedOpportunity() || topDecision;
  const summary = selected ? nextActionSummary(selected) : null;

  $("decisionHeadline").textContent = selected
    ? `${summary.recommendation} / ${summary.deadline} / ${shortText(summary.task, 78)}`
    : "No strong pursuit found today";
  $("lastRun").textContent = result.as_of
    ? `As of ${result.as_of} - ${PRIORITY_LABELS[getPriorityMode()]}`
    : `Latest scan - ${PRIORITY_LABELS[getPriorityMode()]}`;
  $("summaryRecommendation").textContent = summary ? summary.recommendation : "No Pursue";
  $("summaryDeadline").textContent = summary ? summary.deadline : "No active file";
  $("summaryTask").textContent = summary ? summary.task : "Check Audit for skipped records";
  $("summaryFit").textContent = summary ? summary.fit : "No strong match";

  $("topCount").textContent = String(top.length);
  $("watchCount").textContent = String(watch.length);
  $("timelineCount").textContent = String(timeline.length);

  renderOpportunityList($("topOpportunities"), top, "No pursue or review opportunities found.");
  renderOpportunityList($("watchlist"), watch, "No monitor items yet.");
  renderSelectedOpportunityDetail(selected);
  renderDecisionGate(selected, result);
  renderTimeline(timeline);

  if (!metrics || Object.keys(metrics).length === 0) {
    $("packetStatus").textContent = "Not prepared";
  }
}

function renderEvidence(result) {
  const metrics = result.metrics || {};
  const skipped = result.skipped || [];
  const evaluated = result.all_evaluated || [];
  const scorecard = result.insight_scorecard || result.scorecard || {};

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
  container.className = items.length ? "docket-list" : "docket-list empty-list";
  if (!items.length) {
    container.innerHTML = `<p>${escapeHtml(emptyText)}</p>`;
    return;
  }

  container.innerHTML = items.map((item) => opportunityCard(item)).join("");
  container.querySelectorAll(".opportunity-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.selectedOpportunityId = card.dataset.id || "";
      $("approveButton").disabled = !canApproveCurrent();
      renderOwner(state.scan);
      renderEvidence(state.scan);
    });
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        card.click();
      }
    });
  });
}

function opportunityCard(item) {
  const id = getOpportunityId(item);
  const solicitation = item.solicitation || {};
  const selected = id && id === state.selectedOpportunityId ? " selected" : "";
  const deadline = solicitation.submission_deadline || "No deadline listed";
  const dayText = deadlinePressureText(item);
  const displayLabel = decisionLabel(item.label);
  const decisionClass = `decision-${displayLabel.toLowerCase()}`;
  const reason = queueReason(item);
  const score = item.rank_score === undefined || item.rank_score === null ? "" : `Score ${item.rank_score}`;

  return `
    <article class="opportunity-card ${decisionClass}${selected}" data-id="${escapeHtml(id)}" tabindex="0" role="button" aria-pressed="${selected ? "true" : "false"}">
      <div class="docket-main">
        <div class="card-topline">
          <h4 class="card-title">${escapeHtml(getCompactOpportunityTitle(item, 120))}</h4>
          ${score ? `<span class="docket-score">${escapeHtml(score)}</span>` : ""}
        </div>
        <div class="card-meta">
          <span>Doc ${escapeHtml(id || "pending")}</span>
          <span>Due ${escapeHtml(deadline)}</span>
          <span>${escapeHtml(dayText)}</span>
        </div>
        <p class="docket-rationale">${escapeHtml(reason)}</p>
      </div>
    </article>
  `;
}

function renderSelectedOpportunityDetail(item) {
  const container = $("selectedOpportunityDetail");
  if (!container) {
    return;
  }
  if (!item) {
    container.className = "selected-detail empty-list";
    container.innerHTML = "<p>No actionable opportunity selected. Run a scan or choose a file from the queue.</p>";
    return;
  }

  const solicitation = item.solicitation || {};
  const requirements = getStructuredRequirements(item);
  const trace = normalizedBidFitnessTrace(item, requirements);
  const brief = getOpportunityBrief(item);
  const deadline = solicitation.submission_deadline || "No deadline listed";
  const dayText = deadlinePressureText(item);
  const buyer = [
    solicitation.division,
    solicitation.buyer_name,
    solicitation.buyer_email
  ].filter(Boolean).join(" / ");
  const officialDescription = String(solicitation.description || "").trim();
  const whatThisIs = shortText(
    getPlainOpportunitySummary(item) || officialDescription || "Official scope summary is not listed in the feed.",
    280
  );
  const whyMatched = compactSentenceList(
    whyMatchedItems(item, trace, requirements),
    "Matched against this business lane using category, scope terms, and profile evidence.",
    2,
    240
  );
  const blockers = blockerItems(item, trace, brief);
  const blockerText = compactSentenceList(
    blockers,
    "No hard blocker surfaced. Confirm the source package before committing estimator time.",
    2,
    240
  );
  const nextStep = ownerTaskText(item);
  const fit = fitConfidenceText(item, trace);

  container.className = "selected-detail";
  container.innerHTML = `
    <article class="selected-detail-card decision-brief">
      <div class="decision-brief-title">
        <div>
          <p class="eyebrow">Decision Brief</p>
          <h4>${escapeHtml(getCompactOpportunityTitle(item, 180))}</h4>
        </div>
      </div>

      <div class="brief-meta">
        ${renderSelectedKpi("Document", getOpportunityId(item) || "Not listed")}
        ${renderSelectedKpi("Deadline", `${deadline} / ${dayText}`)}
        ${renderSelectedKpi("Buyer Contact", buyer || "Toronto buyer not listed")}
        ${renderSelectedKpi("Fit", fit)}
      </div>

      <div class="brief-grid">
        ${renderDecisionBriefBlock("What this is", whatThisIs)}
        ${renderDecisionBriefBlock("Why it matched", whyMatched)}
        ${renderDecisionBriefBlock("What could block us", blockerText, blockers.length ? "warning" : "")}
        ${renderDecisionBriefBlock("What to do next", nextStep, "action")}
      </div>
    </article>
  `;
}

function renderSelectedKpi(label, value) {
  return `
    <div class="selected-kpi">
      <span class="selected-detail-label">${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderDecisionBriefBlock(label, body, tone = "") {
  return `
    <section class="brief-block ${tone ? `brief-${escapeHtml(tone)}` : ""}">
      <span class="selected-detail-label">${escapeHtml(label)}</span>
      <p>${escapeHtml(body)}</p>
    </section>
  `;
}

function renderDossierBucket(label, items, emptyText) {
  const safeItems = firstItems(uniqueTextItems(textItems(items)), 6);
  return `
    <section class="dossier-bucket">
      <span class="selected-detail-label">${escapeHtml(label)}</span>
      ${safeItems.length
    ? `<ul>${safeItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : `<p>${escapeHtml(emptyText)}</p>`}
    </section>
  `;
}

function renderDecisionGate(item, result) {
  const gateStatus = $("gateStatus");
  const checklist = $("decisionGateChecklist");
  if (!gateStatus || !checklist) {
    return;
  }
  if (!item) {
    gateStatus.textContent = "Waiting";
    checklist.className = "gate-checklist empty-list";
    checklist.innerHTML = "<p>Run a scan to build the bid gate.</p>";
    return;
  }

  const requirements = getStructuredRequirements(item);
  const brief = getOpportunityBrief(item);
  const assessment = getCapacityAssessment(item);
  const source = getSourceLinks(item);
  const trace = normalizedBidFitnessTrace(item, requirements);
  const capacityWarnings = uniqueTextItems([
    ...trace.hardBlockers,
    ...capacityWarningItems(item),
    ...textItems(brief && (brief.blockers || brief.missing_items))
  ]);
  const documents = documentItems(item, requirements, brief);
  const sourceReady = Boolean(source && !source.is_demo_record);
  const capacityReady = !capacityWarnings.length;
  const documentsReady = Boolean(documents.length || sourceReady);
  const packetReady = Boolean(brief && brief.source === "local_nim" && decisionLabel(item.label) !== "Skip");
  const deadlineReady = item.days_until_deadline === undefined || item.days_until_deadline === null
    ? false
    : item.days_until_deadline >= 0;
  const checks = [
    ["Deadline", deadlineReady ? deadlinePressureText(item) : "Deadline missing or expired", deadlineReady],
    ["Capacity", capacityReady ? (assessment && assessment.recommended_action ? assessment.recommended_action : "No owner blocker surfaced") : shortText(capacityWarnings[0], 110), capacityReady],
    ["Documents", documentsReady ? shortText(documents.length ? documents.slice(0, 2).join(", ") : "Source package available", 110) : "Open source package before bid work", documentsReady],
    ["Nemotron / Packet", packetReady ? "Owner-ready brief can support approval packet" : "Packet stays guarded until local brief is ready", packetReady]
  ];
  const approvedChecks = checks.filter(([, , ok]) => ok).length;
  gateStatus.textContent = `${approvedChecks}/${checks.length} clear`;
  gateStatus.className = `count-pill ${approvedChecks === checks.length ? "gate-ready" : "gate-review"}`;
  checklist.className = "gate-checklist";
  checklist.innerHTML = `
    <div class="gate-owner-task">
      <span>Required action</span>
      <strong>${escapeHtml(ownerTaskText(item))}</strong>
    </div>
    <ol>
      ${checks.map(([name, detail, ok]) => `
        <li class="${ok ? "gate-ok" : "gate-warn"}">
          <span>${escapeHtml(name)}</span>
          <strong>${escapeHtml(detail)}</strong>
        </li>
      `).join("")}
    </ol>
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
        ? `Core Fit: ${supporting.coreFit}. ${reasons[0] || `Compared against ${currentProfile().label} capabilities.`}`
        : reasons[0] || `Compares scope to ${currentProfile().name} services and capacity.`
    },
    {
      name: "Award Comparator",
      output: awardLanguage(selected)
    },
    {
      name: "Award-History Ranker",
      output: marketFitLanguage(selected),
      source: selected && getMarketFit(selected) ? "scikit-learn local model" : ""
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
  `).join("") + renderBidFitnessTrace(selected, structuredRequirements);
}

function renderScorecard(result) {
  const metrics = result.metrics || {};
  const scorecard = result.insight_scorecard || result.scorecard || {};
  const container = $("scorecardDetails");
  const scorecardProof = renderScorecardProofArtifacts(result, scorecard);
  const hasScorecard = Object.keys(scorecard).length > 0 || Boolean(scorecardProof);
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
      <p>${number(metrics.model_calls_attempted)} attempted | ${number(metrics.model_calls_successful)} successful | ${number(metrics.briefs_generated)} brief(s) | ${escapeHtml(reductionText)}</p>
    </article>
    <article class="scorecard-item">
      <span>Decision Reconciliation</span>
      <strong>${number(metrics.label_changes_after_extraction)} changed</strong>
      <p>Validated Nemotron blockers can downgrade a pursuit to owner review before packet generation.</p>
    </article>
    <article class="scorecard-item">
      <span>Market Model</span>
      <strong>${escapeHtml(metrics.market_model_mode || "not scored")}</strong>
      <p>${number(metrics.market_model_examples)} examples | precision@10 ${number(metrics.market_model_precision_at_10)} | lift ${number(metrics.market_model_top_decile_lift)}x</p>
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
    ${renderInsightOpportunityCard(scorecard)}
    ${renderSimilarAwardsCard(scorecard)}
    ${renderFalsePositiveCategoriesCard(scorecard)}
    ${renderCapacityReviewCard(scorecard)}
    ${scorecardProof}
  `;
}

function renderInsightOpportunityCard(scorecard) {
  const best = scorecard.best_current_opportunity || {};
  if (!hasDisplayValue(best) || !best.document_number) {
    return "";
  }
  const title = shortText(best.title || "Current opportunity", 150);
  const meta = [
    best.label,
    best.division,
    best.deadline ? `Due ${best.deadline}` : "",
    best.award_range
  ].filter(Boolean).join(" | ");
  const reason = best.decision_reason || "Top current item from the local bid-fitness engine.";
  return `
    <article class="scorecard-item wide insight-opportunity">
      <span>Best Current Opportunity</span>
      <strong>${escapeHtml(best.document_number)} - ${escapeHtml(title)}</strong>
      <p>${escapeHtml(meta || "Current scan top-ranked item")}</p>
      <ul class="proof-list">
        <li>${escapeHtml(shortText(reason, 190))}</li>
        ${firstItems(best.matched_terms || [], 3).map((term) => `<li>Matched: ${escapeHtml(term)}</li>`).join("")}
      </ul>
    </article>
  `;
}

function renderSimilarAwardsCard(scorecard) {
  const examples = firstItems(scorecard.similar_award_examples || [], 3);
  if (!examples.length) {
    return "";
  }
  const range = scorecard.similar_award_range || "Award range available from historical records";
  return `
    <article class="scorecard-item wide similar-awards-card">
      <span>Similar Awards</span>
      <strong>${escapeHtml(range)}</strong>
      <ul class="proof-list">
        ${examples.map((award) => {
    const value = award.award_value_label || (award.award_value ? formatMoney(award.award_value) : "value not listed");
    const descriptor = shortText(award.description || award.document_number || "Historical award", 120);
    const division = award.division ? ` / ${award.division}` : "";
    return `<li>${escapeHtml(value)}${escapeHtml(division)} - ${escapeHtml(descriptor)}</li>`;
  }).join("")}
      </ul>
    </article>
  `;
}

function renderFalsePositiveCategoriesCard(scorecard) {
  const categories = firstItems(scorecard.false_positive_categories || [], 5);
  if (!categories.length) {
    return "";
  }
  return `
    <article class="scorecard-item wide false-positive-card">
      <span>Rejected Keyword Traps</span>
      <strong>${number(scorecard.false_positives_skipped)} false-positive matches skipped</strong>
      <ul class="proof-list">
        ${categories.map((category) => {
    const label = `${category.category || "Uncategorized"} / ${category.blocker || "weak evidence"}`;
    return `<li>${escapeHtml(label)}: ${number(category.count)} skipped</li>`;
  }).join("")}
      </ul>
    </article>
  `;
}

function renderCapacityReviewCard(scorecard) {
  const examples = firstItems(scorecard.capacity_examples || [], 3);
  const reasons = firstItems(scorecard.capacity_downgrade_reasons || [], 3);
  if (!examples.length && !reasons.length) {
    return "";
  }
  const lines = reasons.length
    ? reasons.map((item) => `${item.reason || "Owner review required"} (${number(item.count)})`)
    : examples.map((item) => `${item.document_number || "Opportunity"}: ${firstItems(item.capacity_warnings || item.reasons || [], 1)[0] || item.recommended_action || "owner review required"}`);
  return `
    <article class="scorecard-item wide capacity-card">
      <span>Capacity Review</span>
      <strong>${number(scorecard.capacity_downgrades)} pursue decisions held for review</strong>
      <ul class="proof-list">
        ${firstItems(lines, 4).map((line) => `<li>${escapeHtml(shortText(line, 180))}</li>`).join("")}
      </ul>
    </article>
  `;
}

function renderBidFitnessTrace(item, requirements) {
  if (!item) {
    return `
      <article class="bid-fitness-trace empty-trace">
        <div class="trace-header">
          <div>
            <p class="eyebrow">Bid Fitness Trace</p>
            <h4>No opportunity selected</h4>
            <span>Run a scan or select a row to inspect blockers, signals, rules, and rationale.</span>
          </div>
          <span class="count-pill">Waiting</span>
        </div>
      </article>
    `;
  }

  const trace = normalizedBidFitnessTrace(item, requirements);
  const label = decisionLabel(item.label);
  const subtitle = label === "Skip"
    ? "Skipped false-positive proof"
    : "Selected opportunity proof";

  return `
    <article class="bid-fitness-trace">
      <div class="trace-header">
        <div>
          <p class="eyebrow">Bid Fitness Trace</p>
          <h4>${escapeHtml(getTitle(item))}</h4>
          <span>${escapeHtml(subtitle)}</span>
        </div>
        <span class="count-pill">${trace.hasBackendTrace ? "Backend trace" : "Fallback evidence"}</span>
      </div>
      <div class="trace-grid">
        ${renderTraceBucket("Hard Blockers", trace.hardBlockers, "blocker", "No hard blocker reported.")}
        ${renderTraceBucket("Rules Triggered", trace.rulesTriggered, "rule", "No explicit rule trigger returned.")}
        ${renderTraceBucket("Soft Warnings", trace.softWarnings, "warning", "No soft warning reported.")}
        ${renderTraceBucket("Positive Signals", trace.positiveSignals, "positive", "No positive signal reported.")}
        ${renderTraceBucket("Requirement Signals", trace.requirementSignals, "requirement", "No requirement signal reported.")}
        ${renderTraceBucket("Capacity Gates", trace.capacityGates, "capacity", "No capacity gate reported.")}
        ${renderTraceBucket("Historical Analogs", trace.historicalAnalogs, "history", "No historical analog returned.")}
        ${renderTraceBucket("Scorecard Labels", trace.scorecardLabels, "scorecard", "No scorecard label returned.", 10)}
      </div>
      <div class="trace-rationale">
        <span>Final Rationale</span>
        <p>${escapeHtml(trace.finalRationale)}</p>
      </div>
    </article>
  `;
}

function renderTraceBucket(label, items, modifier, emptyText, limit = 6) {
  const safeItems = firstItems(uniqueTextItems(textItems(items)), limit);
  return `
    <section class="trace-bucket trace-${escapeHtml(modifier)}">
      <h5>${escapeHtml(label)}</h5>
      ${safeItems.length
    ? `<ul>${safeItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : `<p>${escapeHtml(emptyText)}</p>`}
    </section>
  `;
}

function normalizedBidFitnessTrace(item, requirements) {
  const raw = rawBidFitnessTrace(item);
  const hasBackendTrace = Object.keys(raw).some((key) => hasDisplayValue(raw[key]));
  const label = decisionLabel(item && item.label);
  const supporting = supportingLabels(item);
  const rawHardBlockers = textItems(raw.hard_blockers);
  const hardBlockers = uniqueTextItems(rawHardBlockers.length ? rawHardBlockers : [
    ...textItems(item && item.hard_blockers),
    ...(label === "Skip" ? textItems(item && item.rejection_reasons) : []),
    ...textItems(item && item.missing_requirements).map((requirement) => `Missing requirement: ${requirement}`)
  ]);
  const rulesFromBackend = uniqueTextItems([
    ...textItems(raw.rules_triggered),
    ...textItems(item && item.rules_triggered),
    ...textItems(item && item.rejection_rules),
    ...textItems(item && item.rule_hits)
  ]);
  const rulesTriggered = rulesFromBackend.length
    ? rulesFromBackend
    : label === "Skip"
      ? firstItems(hardBlockers, 3).map((blocker) => `Derived blocker rule: ${blocker}`)
      : [];
  const rawSoftWarnings = textItems(raw.soft_warnings);
  const softWarnings = uniqueTextItems(rawSoftWarnings.length ? rawSoftWarnings : [
    ...textItems(item && item.soft_warnings),
    ...textItems(item && item.risks),
    ...capacityWarningItems(item)
  ]);
  const rawPositiveSignals = textItems(raw.positive_signals);
  const positiveSignals = uniqueTextItems(rawPositiveSignals.length ? rawPositiveSignals : [
    ...textItems(item && item.positive_signals),
    ...(label !== "Skip" ? textItems(item && item.reasons) : []),
    ...firstItems(item && item.matched_terms, 4).map((term) => `Matched term: ${term}`)
  ]);
  const requirementSignals = uniqueTextItems([
    ...textItems(raw.requirement_signals),
    ...textItems(item && item.requirement_signals),
    ...requirementSignalItems(requirements),
    ...firstItems(item && item.matched_terms, 4).map((term) => `Matched term: ${term}`)
  ]);
  const rawCapacityGates = textItems(raw.capacity_gates);
  const capacityGates = uniqueTextItems(rawCapacityGates.length ? rawCapacityGates : [
    ...textItems(item && item.capacity_gates),
    ...capacityGateItems(item, requirements)
  ]);
  const rawHistoricalAnalogs = textItems(raw.historical_analogs);
  const historicalAnalogs = uniqueTextItems(rawHistoricalAnalogs.length ? rawHistoricalAnalogs : [
    ...textItems(item && item.historical_analogs),
    ...historicalAnalogItems(item)
  ]);
  const rawScorecardLabels = scorecardLabelItems(raw.scorecard_labels);
  const scorecardLabels = uniqueTextItems(rawScorecardLabels.length ? rawScorecardLabels : [
    ...scorecardLabelItems(item && item.scorecard_labels),
    ...fallbackScorecardLabels(supporting)
  ]);

  return {
    hasBackendTrace,
    hardBlockers,
    rulesTriggered,
    softWarnings,
    positiveSignals,
    requirementSignals,
    capacityGates,
    historicalAnalogs,
    scorecardLabels,
    finalRationale: singleText(raw.final_rationale)
      || singleText(item && item.final_rationale)
      || finalReason(item, requirements)
  };
}

function rawBidFitnessTrace(item) {
  const trace = item && item.bid_fitness_trace;
  return isPlainObject(trace) ? trace : {};
}

function requirementSignalItems(requirements) {
  if (!requirements || typeof requirements !== "object") {
    return [];
  }
  const fields = [
    ["services", "Services"],
    ["certifications", "Certifications"],
    ["documents", "Documents"],
    ["facility_signals", "Facility signals"],
    ["procurement_type", "Procurement type"]
  ];
  return fields.flatMap(([key, label]) => {
    const values = textItems(requirements[key]);
    return values.length ? [`${label}: ${values.join(", ")}`] : [];
  });
}

function capacityGateItems(item, requirements) {
  const assessment = getCapacityAssessment(item);
  const items = [];
  if (assessment) {
    if (assessment.pursuit_load) {
      items.push(`Pursuit load: ${assessment.pursuit_load}`);
    }
    if (assessment.response_capacity) {
      items.push(`Response capacity: ${assessment.response_capacity}`);
    }
    if (assessment.execution_capacity) {
      items.push(`Execution capacity: ${assessment.execution_capacity}`);
    }
    if (assessment.recommended_action) {
      items.push(`Recommended action: ${assessment.recommended_action}`);
    }
  }
  if (requirements) {
    items.push(...textItems(requirements.capacity_flags).map((flag) => `Capacity flag: ${flag}`));
  }
  items.push(...capacityWarningItems(item));
  return items;
}

function historicalAnalogItems(item) {
  if (!item) {
    return [];
  }
  const history = formatHistory(item.historical, item.label);
  return history ? [history] : [];
}

function scorecardLabelItems(labels) {
  if (!hasDisplayValue(labels)) {
    return [];
  }
  if (isPlainObject(labels)) {
    return Object.entries(labels).map(([key, value]) => (
      `${titleCase(humanizeToken(key))}: ${formatTraceValue(value)}`
    ));
  }
  return textItems(labels);
}

function fallbackScorecardLabels(supporting) {
  return Object.entries(supporting || {})
    .filter(([, value]) => hasDisplayValue(value))
    .map(([key, value]) => `${titleCase(humanizeToken(key))}: ${formatTraceValue(value)}`);
}

function renderScorecardProofArtifacts(result, scorecard) {
  const proofSpecs = [
    ["Usability Proof", firstPresent([
      scorecard.usability,
      scorecard.usability_proof,
      result.usability_proof
    ])],
    ["Technical Depth Proof", firstPresent([
      scorecard.technical_depth,
      scorecard.technical_depth_proof,
      result.technical_depth_proof
    ])],
    ["Baseline", firstPresent([
      scorecard.baseline,
      scorecard.baselines,
      scorecard.baseline_metrics,
      result.baseline,
      result.baselines
    ])],
    ["Benchmark", firstPresent([
      scorecard.benchmark,
      scorecard.benchmarks,
      scorecard.benchmark_metrics,
      result.benchmark,
      result.benchmarks
    ])]
  ];
  const knownKeys = new Set([
    "false_positives_skipped",
    "similar_awards_grounded",
    "estimated_bid_hours_saved",
    "realistic_historical_opportunities",
    "profile",
    "evaluated_count",
    "actionable_count",
    "capacity_downgrades",
    "capacity_downgrade_reasons",
    "false_positive_examples",
    "false_positive_categories",
    "capacity_examples",
    "best_current_opportunity",
    "buyer_division_pattern",
    "similar_award_range",
    "similar_award_examples",
    "top_insight",
    "usability",
    "usability_proof",
    "technical_depth",
    "technical_depth_proof",
    "baseline",
    "baselines",
    "baseline_metrics",
    "benchmark",
    "benchmarks",
    "benchmark_metrics"
  ]);
  const explicitProof = proofSpecs
    .map(([label, value]) => renderScorecardProofArticle(label, value))
    .join("");
  const extraProof = Object.keys(scorecard)
    .filter((key) => !knownKeys.has(key) && hasDisplayValue(scorecard[key]))
    .slice(0, 3)
    .map((key) => renderScorecardProofArticle(titleCase(humanizeToken(key)), scorecard[key]))
    .join("");
  return explicitProof + extraProof;
}

function renderScorecardProofArticle(label, value) {
  const lines = firstItems(scorecardProofLines(value), 6);
  if (!lines.length) {
    return "";
  }
  const [summary, ...details] = lines;
  return `
    <article class="scorecard-item wide proof-artifact">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(summary)}</strong>
      ${details.length
    ? `<ul class="proof-list">${details.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`
    : ""}
    </article>
  `;
}

function scorecardProofLines(value) {
  if (!hasDisplayValue(value)) {
    return [];
  }
  if (isPlainObject(value)) {
    return uniqueTextItems(Object.entries(value).map(([key, entry]) => (
      `${titleCase(humanizeToken(key))}: ${formatTraceValue(entry)}`
    )));
  }
  return uniqueTextItems(textItems(value));
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
        <strong>${escapeHtml(getCompactOpportunityTitle(item, 150))}</strong>
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
  const ownerReady = Boolean(packet.owner_ready);
  const requiresNemotron = Boolean(packet.requires_nemotron);
  const statusText = ownerReady
    ? "Owner-ready Nemotron packet approved. Simulated submission only."
    : requiresNemotron
      ? "Blocked until local Nemotron generates the owner-ready brief."
      : "Owner approval required.";
  container.innerHTML = `
    <div class="packet-grid">
      <div class="packet-card packet-primary">
        <strong>${escapeHtml(packet.title || "Bid packet")}</strong>
        <span>${escapeHtml(packet.summary || "Packet prepared from computed evidence.")}</span>
      </div>
      <div class="packet-card packet-status-card">
        <strong>Status</strong>
        <span>${escapeHtml(statusText)}</span>
        ${packet.simulated_receipt ? `<p>${escapeHtml(packet.simulated_receipt)}</p>` : ""}
      </div>
      <div class="packet-card">
        <strong>Checklist</strong>
        ${renderList(packet.checklist || [])}
      </div>
      <div class="packet-card">
        <strong>Buyer Questions</strong>
        ${renderList(packet.clarification_questions || [])}
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
  const canRun = hasActiveProfile();
  $("scanButton").disabled = isBusy || !canRun;
  $("simulateButton").disabled = isBusy || !canRun;
  $("approveButton").disabled = isBusy || !canApproveCurrent();
  if (isBusy && message) {
    showToast(message);
  }
}

function canApproveCurrent() {
  const selected = findSelectedOpportunity();
  return Boolean(selected && decisionLabel(selected.label) !== "Skip");
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

function renderEvidenceTags(container, items) {
  const safeItems = firstItems(items || [], 6);
  container.innerHTML = safeItems.length
    ? safeItems.map((item) => `<span class="tag">${escapeHtml(String(item))}</span>`).join("")
    : "<span class=\"tag muted-tag\">Not listed</span>";
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
  return getPlainOpportunitySummary(item)
    || solicitation.description
    || solicitation.document_number
    || "Untitled opportunity";
}

function getCompactOpportunityTitle(item, maxLength = 140) {
  const solicitation = (item && item.solicitation) || {};
  const requirements = getStructuredRequirements(item);
  const scopeTerms = firstItems(
    ((requirements && requirements.services) || item.matched_terms || [])
      .map((term) => String(term || "").trim())
      .filter((term) => term && term.length <= 44),
    3
  );
  if (scopeTerms.length) {
    const scope = `${scopeTerms.join(", ")}${solicitation.division ? ` / ${solicitation.division}` : ""}`;
    return shortText(scope, maxLength);
  }
  const title = String(getTitle(item) || "").trim();
  const firstClause = title.split(";")[0] || title;
  const cleaned = firstClause
    .replace(/^this is\s+/i, "")
    .replace(/\s+/g, " ")
    .replace(/\.$/, "")
    .trim();
  return shortText(cleaned || title, maxLength);
}

function shortText(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) {
    return text;
  }
  const clipped = text.slice(0, maxLength - 1);
  const lastSpace = clipped.lastIndexOf(" ");
  return `${clipped.slice(0, lastSpace > 60 ? lastSpace : clipped.length).trim()}...`;
}

function getPlainOpportunitySummary(item) {
  if (!item) {
    return "";
  }
  const brief = getOpportunityBrief(item);
  const briefSummary = String((brief && brief.owner_summary) || "").trim();
  if (briefSummary) {
    return briefSummary;
  }
  const requirements = getStructuredRequirements(item);
  const solicitation = item.solicitation || {};
  const officialDescription = String(solicitation.description || "").trim();
  const extractedSummary = String((requirements && requirements.summary) || "").trim();
  const extractedKey = extractedSummary.toLowerCase();
  const officialKey = officialDescription.toLowerCase();
  if (extractedSummary && (!officialKey || (extractedKey !== officialKey && !extractedKey.includes(officialKey)))) {
    return extractedSummary;
  }

  const services = firstItems((requirements && requirements.services) || item.matched_terms || [], 3);
  const division = String(solicitation.division || "").trim();
  if (services.length) {
    return `This is ${humanList(services)} work${division ? ` for ${division}` : ""}.`;
  }
  const category = String(solicitation.category || "").trim();
  if (category && division) {
    return `${category} opportunity from ${division}.`;
  }
  if (category) {
    return `${category} opportunity.`;
  }
  return "";
}

function getOpportunityBrief(item) {
  if (!item) {
    return null;
  }
  const brief = item.opportunity_brief || item.nemotron_brief;
  return brief && typeof brief === "object" ? brief : null;
}

function getMarketFit(item) {
  if (!item || !item.market_fit || typeof item.market_fit !== "object") {
    return null;
  }
  return item.market_fit;
}

function marketFitLabel(market) {
  if (!market) {
    return "Market not scored";
  }
  const confidence = market.confidence || "Market";
  const score = Number(market.score || 0);
  return `${confidence} market / ${Math.round(score * 100)}%`;
}

function marketFitLanguage(item) {
  const market = getMarketFit(item);
  if (!market) {
    return "Local award-history market score is pending.";
  }
  const evidence = firstItems(market.evidence || [], 2);
  if (evidence.length) {
    return evidence.join(" ");
  }
  return market.summary || marketFitLabel(market);
}

function briefSourceLabel(brief) {
  if (!brief || !brief.source) {
    return "Bid brief";
  }
  if (brief.source === "local_nim") {
    return "Nemotron bid brief";
  }
  if (brief.source === "deterministic_fallback") {
    return "Deterministic brief";
  }
  return `${titleCase(humanizeToken(brief.source))} brief`;
}

function getSourceLinks(item) {
  const solicitation = (item && item.solicitation) || {};
  return solicitation.source_links && typeof solicitation.source_links === "object"
    ? solicitation.source_links
    : null;
}

function renderSourceActions(source) {
  if (!source) {
    return "";
  }
  const documentNumber = source.document_number || "";
  const docLabel = documentNumber ? `Doc ${documentNumber}` : "Toronto source";
  const note = source.is_demo_record
    ? "Demo fallback record"
    : source.verification_note || "Official Toronto source";
  return `
    <div class="source-actions">
      <span class="source-doc">${escapeHtml(docLabel)}</span>
      <span class="source-note">${escapeHtml(note)}</span>
    </div>
  `;
}

function renderOpportunityBrief(brief) {
  if (!brief) {
    return "";
  }
  const summary = String(brief.owner_summary || "").trim();
  const fitReason = String(brief.fit_reason || "").trim();
  const documents = firstItems(brief.required_documents || [], 3);
  const blockers = firstItems(brief.blockers || brief.missing_items || [], 2);
  const nextSteps = firstItems(brief.next_steps || [], 2);
  const source = briefSourceLabel(brief);
  const body = summary || fitReason || nextSteps[0] || "";
  if (!body && !documents.length && !blockers.length) {
    return "";
  }
  return `
    <div class="brief-panel ${brief.source === "local_nim" ? "brief-nim" : "brief-fallback"}">
      <div class="brief-heading">
        <strong>${escapeHtml(source)}</strong>
        ${brief.source === "local_nim" ? "<span>Owner-ready</span>" : "<span>Packet blocked</span>"}
      </div>
      ${body ? `<p>${escapeHtml(body)}</p>` : ""}
      ${documents.length ? `<div class="brief-row"><span>Docs</span><em>${escapeHtml(documents.join(", "))}</em></div>` : ""}
      ${blockers.length ? `<div class="brief-row warning"><span>Review</span><em>${escapeHtml(blockers.join(", "))}</em></div>` : ""}
      ${nextSteps.length ? `<div class="brief-row"><span>Next</span><em>${escapeHtml(nextSteps[0])}</em></div>` : ""}
    </div>
  `;
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

function getSelectedProfileId() {
  const selected = document.querySelector('input[name="supportedProfile"]:checked');
  return selected ? selected.value : state.selectedProfileId;
}

function currentProfile() {
  return profileById(getSelectedProfileId()) || state.supportedProfiles[0] || LOADING_PROFILE;
}

function profileById(profileId) {
  return state.supportedProfiles.find((profile) => profile.profile_id === profileId) || null;
}

function profileWithSupportedEvidence(profile) {
  const supported = profileById(profile.profile_id);
  return supported ? { ...supported, ...profile } : profile;
}

function hasActiveProfile() {
  return Boolean(currentProfile().profile_id);
}

function supportedProfilesFromHealth(health) {
  const profiles = Array.isArray(health && health.supported_profiles)
    ? health.supported_profiles.filter((profile) => profile && profile.profile_id)
    : [];
  const byId = new Map(profiles.map((profile) => [profile.profile_id, profile]));
  const orderedDemoProfiles = DEMO_PROFILE_ORDER
    .map((profileId) => byId.get(profileId))
    .filter(Boolean);
  if (orderedDemoProfiles.length) {
    return orderedDemoProfiles;
  }
  return profiles.filter((profile) => profile.profile_id !== "building_mechanical");
}

function selectProfileId(candidateId) {
  if (profileById(candidateId)) {
    return candidateId;
  }
  if (profileById(DEFAULT_PROFILE_ID)) {
    return DEFAULT_PROFILE_ID;
  }
  return state.supportedProfiles[0] ? state.supportedProfiles[0].profile_id : "";
}

function profileLabel(profile) {
  return profile.label || profile.name || titleCase(humanizeToken(profile.profile_id)) || "Supported profile";
}

function compactProfileLabel(profile) {
  const labels = {
    road_civil_infrastructure: "Road/Civil",
    parks_landscape: "Parks",
    professional_engineering_design: "Engineering"
  };
  return labels[profile.profile_id] || profileLabel(profile);
}

function compactCompanyName(name) {
  return String(name || "")
    .replace(/\s+(Ltd\.?|Limited|Inc\.?|Corporation|Corp\.?)$/i, "")
    .trim();
}

function profileCapacityText(profile) {
  const parts = [];
  if (profile.max_sites_per_day) {
    parts.push(`${profile.max_sites_per_day} city sites/day`);
  }
  if (profile.max_contract_value) {
    parts.push(`up to ${formatMoney(profile.max_contract_value)}`);
  }
  return parts.length ? parts.join(", ") : "Not listed";
}

function profilePursuitsText(profile) {
  const active = profile.active_pursuit_count;
  const limit = profile.max_active_pursuits;
  if (active !== undefined && active !== null && limit !== undefined && limit !== null) {
    return `${active} active, limit ${limit}`;
  }
  return "Not listed";
}

function renderProfileEvidence(profile) {
  const evidence = $("profileEvidence");
  const divisions = $("profileDivisions");
  const goodFit = $("profileGoodFit");
  const badFit = $("profileBadFit");
  if (!evidence || !divisions || !goodFit || !badFit) {
    return;
  }

  evidence.innerHTML = `
    <div>
      <dt>Lane Basis</dt>
      <dd>${escapeHtml(profile.lane_basis || "Waiting for backend lane evidence")}</dd>
    </div>
    <div>
      <dt>2026 Solicitation Hits</dt>
      <dd>${profile.ytd_solicitation_hits === undefined ? "Not listed" : number(profile.ytd_solicitation_hits)}</dd>
    </div>
    <div>
      <dt>Exclusive Best-Fit Hits</dt>
      <dd>${profile.exclusive_best_fit_hits === undefined ? "Not listed" : number(profile.exclusive_best_fit_hits)}</dd>
    </div>
  `;
  renderEvidenceTags(divisions, profile.top_divisions || []);
  renderEvidenceTags(goodFit, profile.good_fit_examples || []);
  renderEvidenceTags(badFit, profile.bad_fit_examples || []);
}

function renderActiveProfileEvidence(profile) {
  const container = $("activeProfileEvidence");
  if (!container) {
    return;
  }
  const profileName = profileLabel(profile);
  const divisions = firstItems(profile.top_divisions || [], 4);
  container.innerHTML = `
    <div>
      <p class="eyebrow">Active Demo Persona</p>
      <h3>${escapeHtml(profileName)}</h3>
      <p>Based on 2026 Toronto solicitation patterns: ${escapeHtml(profile.lane_basis || "lane evidence loads from /api/health")}.</p>
    </div>
    <div class="active-profile-stats">
      <span><strong>${profile.ytd_solicitation_hits === undefined ? "0" : number(profile.ytd_solicitation_hits)}</strong> 2026 hits</span>
      <span><strong>${profile.exclusive_best_fit_hits === undefined ? "0" : number(profile.exclusive_best_fit_hits)}</strong> exclusive best-fit</span>
      <span>${escapeHtml(divisions.length ? divisions.join(", ") : "Top divisions pending")}</span>
    </div>
  `;
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

function nextActionSummary(item) {
  const trace = normalizedBidFitnessTrace(item, getStructuredRequirements(item));
  return {
    recommendation: decisionLabel(item.label),
    deadline: deadlinePressureText(item),
    task: ownerTaskText(item),
    fit: fitConfidenceText(item, trace)
  };
}

function deadlinePressureText(item) {
  const days = item && item.days_until_deadline;
  if (days === undefined || days === null || days === "") {
    return "Deadline unknown";
  }
  const numericDays = Number(days);
  if (!Number.isFinite(numericDays)) {
    return String(days);
  }
  if (numericDays < 0) {
    return "Closed";
  }
  if (numericDays === 0) {
    return "Due today";
  }
  if (numericDays === 1) {
    return "1 day left";
  }
  return `${numericDays} days left`;
}

function queueReason(item) {
  const requirements = getStructuredRequirements(item);
  const trace = normalizedBidFitnessTrace(item, requirements);
  const brief = getOpportunityBrief(item);
  const label = decisionLabel(item.label);
  const source = label === "Skip"
    ? blockerItems(item, trace, brief)
    : whyMatchedItems(item, trace, requirements);
  return shortText(source[0] || finalReason(item, requirements), 128);
}

function ownerTaskText(item) {
  const requirements = getStructuredRequirements(item);
  const brief = getOpportunityBrief(item);
  const trace = normalizedBidFitnessTrace(item, requirements);
  const label = decisionLabel(item.label);
  const blockers = blockerItems(item, trace, brief);
  const warnings = capacityWarningItems(item);
  const assessment = getCapacityAssessment(item);
  const days = item.days_until_deadline;

  if (label === "Skip") {
    return blockers.length ? `Do not bid: ${shortText(blockers[0], 96)}` : "Do not spend bid time on this file";
  }
  if (warnings.length || (assessment && assessment.recommended_action === "Pursue After Review")) {
    return "Review capacity risk before response";
  }
  if (Number(days) >= 0 && Number(days) <= 2) {
    return "Confirm response capacity today";
  }
  if (requirements && requirements.next_action) {
    return shortText(requirements.next_action, 110);
  }
  const nextSteps = textItems(brief && brief.next_steps);
  if (nextSteps.length) {
    return shortText(nextSteps[0], 110);
  }
  if (label === "Pursue") {
    return "Open source package and assign estimator";
  }
  if (label === "Review") {
    return "Resolve blocker before committing bid time";
  }
  return "Monitor for addenda or a stronger fit";
}

function fitConfidenceText(item, trace = null) {
  const label = decisionLabel(item.label);
  const activeTrace = trace || normalizedBidFitnessTrace(item, getStructuredRequirements(item));
  const score = Number(item.rank_score);
  if (label === "Skip") {
    return "Poor fit";
  }
  if (activeTrace.positiveSignals.length >= 2 || score >= 70) {
    return "Strong scope match";
  }
  if (label === "Review") {
    return "Good fit, risk flagged";
  }
  if (label === "Monitor") {
    return "Relevant watch";
  }
  return "Fit needs review";
}

function whyMatchedItems(item, trace, requirements) {
  return firstItems(uniqueTextItems([
    ...trace.positiveSignals,
    ...requirementSignalItems(requirements),
    ...textItems(item.reasons),
    ...firstItems(item.matched_terms, 4).map((term) => `Matched term: ${term}`)
  ]), 4);
}

function blockerItems(item, trace, brief) {
  return firstItems(uniqueTextItems([
    ...trace.hardBlockers,
    ...trace.softWarnings,
    ...capacityWarningItems(item),
    ...textItems(item.rejection_reasons),
    ...textItems(item.missing_requirements).map((requirement) => `Missing requirement: ${requirement}`),
    ...textItems(brief && (brief.blockers || brief.missing_items))
  ]), 5);
}

function documentItems(item, requirements, brief) {
  return firstItems(uniqueTextItems([
    ...textItems(brief && brief.required_documents),
    ...textItems(requirements && requirements.documents),
    ...textItems(item && item.required_documents)
  ]), 5);
}

function compactSentenceList(items, fallback, limit = 2, maxLength = 220) {
  const safeItems = firstItems(uniqueTextItems(textItems(items)), limit);
  if (!safeItems.length) {
    return fallback;
  }
  return shortText(safeItems.join("; "), maxLength);
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

function firstPresent(values) {
  return values.find((value) => hasDisplayValue(value));
}

function singleText(value) {
  return textItems(value)[0] || "";
}

function textItems(value) {
  if (!hasDisplayValue(value)) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => textItems(item));
  }
  if (isPlainObject(value)) {
    return Object.entries(value).map(([key, entry]) => (
      `${titleCase(humanizeToken(key))}: ${formatTraceValue(entry)}`
    ));
  }
  return [String(value).trim()].filter(Boolean);
}

function uniqueTextItems(items) {
  const seen = new Set();
  return textItems(items).filter((item) => {
    const key = item.toLowerCase();
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function hasDisplayValue(value) {
  if (value === undefined || value === null) {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item) => hasDisplayValue(item));
  }
  if (isPlainObject(value)) {
    return Object.values(value).some((item) => hasDisplayValue(item));
  }
  return String(value).trim() !== "";
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function formatTraceValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => formatTraceValue(item)).filter(Boolean).join(", ");
  }
  if (isPlainObject(value)) {
    return Object.entries(value)
      .map(([key, entry]) => `${titleCase(humanizeToken(key))}: ${formatTraceValue(entry)}`)
      .join("; ");
  }
  return String(value ?? "").trim();
}

function firstItems(items, limit) {
  if (Array.isArray(items)) {
    return items.filter(Boolean).slice(0, limit);
  }
  return items ? [items].slice(0, limit) : [];
}

function humanList(items) {
  const values = textItems(items);
  if (!values.length) {
    return "";
  }
  if (values.length === 1) {
    return values[0];
  }
  if (values.length === 2) {
    return `${values[0]} and ${values[1]}`;
  }
  return `${values.slice(0, -1).join(", ")}, and ${values[values.length - 1]}`;
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
      if (value.fallback === "none") {
        return value.mode;
      }
      return value.mode === value.fallback ? value.fallback : `${value.mode}, fallback ready`;
    }
    return value.status || value.mode || value.name || JSON.stringify(value);
  }
  return String(value);
}

function compactRuntimeStatus(value) {
  const formatted = formatStatus(value);
  const normalized = formatted.toLowerCase();
  if (normalized.includes("rapids ready")) {
    return "RAPIDS ready";
  }
  if (normalized.includes("cpu fallback")) {
    return "CPU fallback";
  }
  if (normalized.includes("fallback")) {
    return "fallback ready";
  }
  if (normalized.includes("local_nim")) {
    return "local NIM";
  }
  return shortText(formatted, 18);
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
