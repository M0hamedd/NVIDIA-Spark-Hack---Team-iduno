const DEMO_PROFILE_ORDER = [
  "road_civil_infrastructure",
  "parks_landscape",
  "professional_engineering_design"
];

const DEFAULT_PROFILE_ID = DEMO_PROFILE_ORDER[0];

const DEMO_MONTHS_2026 = [
  { value: "2026-01-31", label: "January", days: 30 },
  { value: "2026-02-28", label: "February", days: 30 },
  { value: "2026-03-31", label: "March", days: 30 },
  { value: "2026-04-30", label: "April", days: 30 },
  { value: "2026-05-30", label: "May", days: 30 }
];

const DEFAULT_DEMO_MONTH = DEMO_MONTHS_2026[DEMO_MONTHS_2026.length - 1].value;

const LOADING_PROFILE = {
  profile_id: "",
  label: "Loading business types",
  name: "Loading supported business types",
  business_type: "Waiting for city listings",
  base_location: "Toronto",
  skills: [],
  ready_documents: [],
  top_divisions: [],
  good_fit_examples: [],
  bad_fit_examples: []
};

const PRIORITY_LABELS = {
  best_win_chance: "Best Chance",
  best_fit: "Best Fit",
  highest_value: "Best Value"
};

const state = {
  health: null,
  supportedProfiles: [],
  scan: null,
  selectedOpportunityId: "",
  activeView: "owner",
  priorityMode: "best_win_chance",
  selectedProfileId: DEFAULT_PROFILE_ID,
  selectedDemoMonth: DEFAULT_DEMO_MONTH,
  scanRequestId: 0,
  autoScanDone: false
};

const $ = (id) => document.getElementById(id);

document.addEventListener("DOMContentLoaded", () => {
  renderProfileSelector();
  renderProfile(currentProfile());
  syncMonthSelector();
  bindEvents();
  resetWorkspace("Loading business types from City of Toronto data. First decision pass will run automatically.");
  setBusy(false);
  checkHealth();
});

function bindEvents() {
  $("scanButton").addEventListener("click", () => runScan(false));
  $("monthSelector").addEventListener("change", (event) => {
    state.selectedDemoMonth = event.target.value;
    updateSnapshotLabel();
    runSimulation();
  });
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
      resetWorkspace(`${profileLabel(profile)} selected. Re-ranking Toronto contracts for this lane.`);
      runScan(false, {
        busyMessage: `Re-ranking ${profileLabel(profile)}`,
        doneMessage: `${profileLabel(profile)} matches ready`,
        toast: false
      });
    }
  });
  document.querySelectorAll('input[name="priorityMode"]').forEach((input) => {
    input.addEventListener("change", () => {
      state.priorityMode = getPriorityMode();
      if (state.scan) {
        $("lastRun").textContent = `Re-ranking for ${PRIORITY_LABELS[state.priorityMode]}`;
        runScan(false, {
          busyMessage: `Re-ranking for ${PRIORITY_LABELS[state.priorityMode]}`,
          doneMessage: `${PRIORITY_LABELS[state.priorityMode]} queue ready`,
          toast: false
        });
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
      resetWorkspace(`${profileLabel(currentProfile())} loaded. Find Toronto contracts that fit.`);
    }
    $("healthStatus").textContent = "City listings ready";
    $("healthStatus").className = "status-pill ok";
    $("gpuStatus").textContent = `Local: ${compactRuntimeStatus(health.gpu)}`;
    $("nemotronStatus").textContent = `Brief: ${compactRuntimeStatus(health.nemotron)}`;
    if (!state.supportedProfiles.length) {
      setBusy(false);
      showToast("No supported business types were returned.");
      return;
    }
    if (!state.scan && !state.autoScanDone) {
      state.autoScanDone = true;
      await runScan(false, {
        busyMessage: `Ranking ${selectedDemoMonth().label} Toronto contracts`,
        doneMessage: `${selectedDemoMonth().label} decision queue ready`,
        toast: false
      });
      return;
    }
    setBusy(false);
  } catch (error) {
    $("healthStatus").textContent = "City listings unavailable";
    $("healthStatus").className = "status-pill error";
    $("gpuStatus").textContent = "Local processing: unknown";
    $("nemotronStatus").textContent = "Bid brief: unknown";
    state.supportedProfiles = [];
    renderProfileSelector();
    renderProfile(currentProfile());
    setBusy(false);
    showToast(error.message);
  }
}

async function runScan(refresh = false, options = {}) {
  const profile = currentProfile();
  const month = selectedDemoMonth();
  if (!profile.profile_id) {
    showToast("Business types are still loading.");
    return;
  }
  const requestId = ++state.scanRequestId;
  setBusy(true, options.busyMessage || `Finding ${month.label} contract matches`);
  try {
    const result = await apiPost("/api/scan", {
      profile_id: profile.profile_id,
      business_profile: profile,
      priority_mode: getPriorityMode(),
      as_of: month.value,
      refresh
    });
    if (requestId !== state.scanRequestId || profile.profile_id !== state.selectedProfileId) {
      return;
    }
    ingestResult(result, options.doneMessage || `${month.label} matches ready`, {
      toast: options.toast !== false
    });
  } catch (error) {
    showToast(error.message);
  } finally {
    if (requestId === state.scanRequestId) {
      setBusy(false);
    }
  }
}

async function runSimulation(options = {}) {
  const profile = currentProfile();
  const month = selectedDemoMonth();
  if (!profile.profile_id) {
    showToast("Business types are still loading.");
    return;
  }
  const requestId = ++state.scanRequestId;
  setBusy(true, options.busyMessage || `Refreshing ${month.label} matches`);
  try {
    const result = await apiPost("/api/simulate", {
      profile_id: profile.profile_id,
      business_profile: profile,
      priority_mode: getPriorityMode(),
      as_of: month.value,
      days: month.days
    });
    if (requestId !== state.scanRequestId || profile.profile_id !== state.selectedProfileId) {
      return;
    }
    ingestResult(result, options.doneMessage || `${month.label} matches ready`, {
      toast: options.toast !== false
    });
  } catch (error) {
    showToast(error.message);
  } finally {
    if (requestId === state.scanRequestId) {
      setBusy(false);
    }
  }
}

async function approveDraft() {
  if (!state.selectedOpportunityId) {
    showToast("Select a city listing first.");
    return;
  }

  setBusy(true, `Preparing ${approvalArtifactNoun()}`);
  try {
    const profile = currentProfile();
    const result = await apiPost("/api/approve", {
      profile_id: profile.profile_id,
      business_profile: profile,
      approved: true,
      opportunity_id: state.selectedOpportunityId
    });
    renderPacket(result.packet, result.approved);
    $("packetStatus").textContent = result.approved ? "Prepared" : "Needs a closer look";
    showToast(`${approvalArtifactTitle()} prepared`);
  } catch (error) {
    showToast(error.message);
  } finally {
    setBusy(false);
  }
}

function ingestResult(result, message, options = {}) {
  state.scan = result;
  const resultMonth = demoMonthForDate(result.as_of);
  if (resultMonth) {
    state.selectedDemoMonth = resultMonth.value;
    syncMonthSelector();
  }
  state.selectedProfileId = selectProfileId(
    (result.business_profile && result.business_profile.profile_id) || state.selectedProfileId
  );
  const top = result.top_opportunities || [];
  const watch = result.watchlist || [];
  const selected = top[0] || watch[0] || null;
  state.selectedOpportunityId = selected ? getOpportunityId(selected) : "";

  renderProfileSelector();
  renderProfile(result.business_profile || currentProfile());
  updateSnapshotLabel();
  renderOwner(result);
  renderEvidence(result);
  $("approveButton").disabled = !canApproveCurrent();
  if (options.toast !== false) {
    showToast(message);
  }
}

function renderProfileSelector() {
  const container = $("profileOptions");
  if (!container) {
    return;
  }
  const profiles = state.supportedProfiles;
  if (!profiles.length) {
    container.innerHTML = "<p class=\"profile-loading\">Loading business types...</p>";
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
}

function resetWorkspace(message) {
  updateSnapshotLabel();
  $("decisionHeadline").textContent = "Preparing procurement decision queue";
  $("lastRun").textContent = message || "No search yet";
  $("summaryRecommendation").textContent = "Waiting";
  $("summaryDeadline").textContent = "Not checked";
  $("summaryTask").textContent = "Ranking current listings";
  $("summaryFit").textContent = "No signal yet";
  $("topCount").textContent = "0";
  $("watchCount").textContent = "0";
  $("timelineCount").textContent = "0";
  $("topOpportunities").className = "docket-list empty-list";
  $("topOpportunities").innerHTML = "<p>The first profile-specific scan will rank listings into pursue, review, monitor, and pass.</p>";
  $("watchlist").className = "docket-list empty-list";
  $("watchlist").innerHTML = "<p>Listings to keep an eye on will appear here.</p>";
  $("selectedOpportunityDetail").className = "selected-detail empty-list";
  $("selectedOpportunityDetail").innerHTML = "<p>Select a city listing to see what it is, why it matched, and what to do next.</p>";
  $("gateStatus").textContent = "Waiting";
  $("decisionGateChecklist").className = "gate-checklist empty-list";
  $("decisionGateChecklist").innerHTML = "<p>Find matches to see whether this looks ready to bid.</p>";
  $("timeline").hidden = true;
  $("timeline").className = "timeline empty-list";
  $("timeline").innerHTML = "<p>Pick a month to see deadline reminders and next steps.</p>";
  $("packetStatus").textContent = "Not ready";
  $("packetOutput").hidden = true;
  $("packetOutput").className = "packet-output empty-list";
  $("packetOutput").innerHTML = `<p>Select a listing and prepare ${approvalArtifactNoun()} when the ready check passes.</p>`;
  $("metricSolicitations").textContent = "0";
  $("metricAwards").textContent = "0";
  $("metricRejected").textContent = "0";
  $("metricRuntime").textContent = "0 ms";
  $("metricRecordsPerSecond").textContent = "0";
  $("metricModelCallsAvoided").textContent = "0";
  $("metricNvidiaPath").textContent = "Pending";
  $("metricBacktestInsight").textContent = "0";
  $("engineLabel").textContent = "Python";
  $("skipCount").textContent = "0";
  $("evaluatedCount").textContent = "0";
  $("pipelineDetails").className = "pipeline-list empty-list";
  $("pipelineDetails").innerHTML = "<p>Details appear after you find matches.</p>";
  $("skippedExamples").className = "docket-list empty-list";
  $("skippedExamples").innerHTML = "<p>Listings we passed on will show why they are probably not worth your time.</p>";
  $("scorecardStatus").textContent = "Waiting";
  $("scorecardDetails").className = "scorecard-grid empty-list";
  $("scorecardDetails").innerHTML = "<p>Find matches to see the validation details behind the recommendations.</p>";
  $("evaluatedStream").className = "table-list empty-list";
  $("evaluatedStream").innerHTML = "<p>Find matches to inspect every listing that was checked.</p>";
  $("approveButton").disabled = true;
}

function renderOwner(result) {
  updateSnapshotLabel();
  const top = result.top_opportunities || [];
  const watch = result.watchlist || [];
  const inboxItems = [...top, ...watch];
  const timeline = result.timeline || [];
  const metrics = result.metrics || {};
  const topDecision = top[0] || watch[0];
  const selected = findSelectedOpportunity() || topDecision;
  const summary = selected ? nextActionSummary(selected) : null;

  $("decisionHeadline").textContent = selected
    ? `${summary.recommendation}: ${summary.deadline}; ${shortText(summary.task, 78)}`
    : "No strong match found today";
  $("lastRun").textContent = result.as_of
    ? `As of ${result.as_of} / ${PRIORITY_LABELS[getPriorityMode()]}`
    : `Latest check / ${PRIORITY_LABELS[getPriorityMode()]}`;
  $("summaryRecommendation").textContent = summary ? summary.recommendation : "No strong match";
  $("summaryDeadline").textContent = summary ? summary.deadline : "No active listing";
  $("summaryTask").textContent = summary ? summary.task : "See why we passed";
  $("summaryFit").textContent = summary ? summary.fit : "No strong match";

  $("topCount").textContent = String(inboxItems.length);
  $("watchCount").textContent = "0";
  $("timelineCount").textContent = String(timeline.length);

  renderOpportunityList($("topOpportunities"), inboxItems, "No good matches found.");
  renderOpportunityList($("watchlist"), [], "No listings to keep watching yet.");
  renderSelectedOpportunityDetail(selected);
  renderDecisionGate(selected, result);
  renderTimeline(timeline);

  if (!metrics || Object.keys(metrics).length === 0) {
    $("packetStatus").textContent = "Not ready";
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
  const internalLabel = decisionLabel(item.label);
  const displayLabel = ownerDecisionLabel(item.label);
  const decisionClass = `decision-${internalLabel.toLowerCase()}`;
  const reason = queueReason(item);
  const score = item.rank_score === undefined || item.rank_score === null ? "" : `Fit ${item.rank_score}`;
  const bidLabel = bidRecommendationLabel(item);

  return `
    <article class="opportunity-card ${decisionClass}${selected}" data-id="${escapeHtml(id)}" tabindex="0" role="button" aria-pressed="${selected ? "true" : "false"}">
      <div class="docket-main">
        <div class="card-topline">
          <h4 class="card-title">${escapeHtml(getCompactOpportunityTitle(item, 120))}</h4>
          <div class="card-badges">
            <span class="label-pill ${labelClass(internalLabel)}">${escapeHtml(displayLabel)}</span>
            ${score ? `<span class="docket-score">${escapeHtml(score)}</span>` : ""}
          </div>
        </div>
        <div class="card-meta">
          <span>Listing ${escapeHtml(id || "pending")}</span>
          <span>Due ${escapeHtml(deadline)}</span>
          <span>${escapeHtml(dayText)}</span>
          ${bidLabel ? `<span>${escapeHtml(bidLabel)}</span>` : ""}
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
    container.innerHTML = "<p>No listing selected. Find matches or choose a city listing.</p>";
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
  const whatThisIs = cleanDisplayText(
    getPlainOpportunitySummary(item) || officialDescription || "Official scope summary is not listed in the feed."
  );
  const blockers = blockerItems(item, trace, brief);
  const blockerText = fullSentenceList(
    blockers,
    "No clear deal-breaker surfaced. Confirm the city listing before spending estimating time.",
    4
  );
  const bidRecommendation = getBidRecommendation(item);
  const bidAmount = bidRecommendation && bidRecommendation.recommended_bid
    ? formatMoney(bidRecommendation.recommended_bid)
    : "Not enough history";
  const bidRange = bidRangeLabel(bidRecommendation);
  const nextStep = ownerTaskText(item);
  const fit = fitConfidenceText(item, trace);
  const decision = ownerDecisionLabel(item.label);
  const internalLabel = decisionLabel(item.label);
  const sourceLabel = briefSourceLabel(brief);
  const whyUs = fitNarrative(item, trace, requirements, brief);
  const scope = scopeNarrative(item, requirements, brief, whatThisIs);
  const documents = documentItems(item, requirements, brief);
  const documentText = documents.length
    ? humanList(documents)
    : "Confirm the official Toronto package before assigning estimating time.";
  const buyerText = buyer || "Toronto contact not listed";
  const title = getCompactOpportunityTitle(item, 190);

  container.className = "selected-detail";
  container.innerHTML = `
    <article class="selected-detail-card contract-reader">
      <section class="contract-hero decision-${escapeHtml(internalLabel.toLowerCase())}">
        <div class="contract-hero-copy">
          <span class="label-pill ${labelClass(internalLabel)}">${escapeHtml(decision)}</span>
          <h4>${escapeHtml(title)}</h4>
          <p>${escapeHtml(shortText(scope, 220))}</p>
        </div>
        <div class="contract-next-step">
          <span>Next step</span>
          <strong>${escapeHtml(cleanDisplayText(nextStep))}</strong>
          <em>${escapeHtml(sourceLabel)}</em>
        </div>
      </section>

      <dl class="hero-facts">
        ${renderHeroFact("Due Date", deadline, dayText, "deadline")}
        ${renderHeroFact("Document #", getOpportunityId(item) || "Not listed", solicitation.solicitation_type || "Toronto listing")}
        ${renderHeroFact("Estimated Bid", bidAmount, bidRange || "Historical award guidance")}
        ${renderHeroFact("Fit", fit, buyerText, "fit")}
      </dl>

      <div class="quick-read-grid">
        ${renderDecisionBriefBlock("Why Us", whyUs, "primary wide")}
        ${renderDecisionBriefBlock("Scope", whatThisIs)}
        ${renderDecisionBriefBlock("Bid Value", bidRecommendationLanguage(item))}
        ${renderDecisionBriefBlock("Documents", documentText)}
        ${renderDecisionBriefBlock("What To Check", blockerText, blockers.length ? "warning" : "")}
      </div>
    </article>
  `;
}

function renderHeroFact(label, value, note = "", modifier = "") {
  return `
    <div class="${modifier ? `hero-fact-${escapeHtml(modifier)}` : ""}">
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value)}</dd>
      ${note ? `<small>${escapeHtml(cleanDisplayText(note))}</small>` : ""}
    </div>
  `;
}

function renderDecisionBriefBlock(label, body, tone = "") {
  const toneClass = String(tone || "")
    .split(/\s+/)
    .filter(Boolean)
    .map((token) => `brief-${token}`)
    .join(" ");
  return `
    <section class="brief-block ${escapeHtml(toneClass)}">
      <span class="selected-detail-label">${escapeHtml(label)}</span>
      <p>${escapeHtml(cleanDisplayText(body))}</p>
    </section>
  `;
}

function bidRangeLabel(recommendation) {
  if (!recommendation) {
    return "";
  }
  if (recommendation.low_bid && recommendation.high_bid && recommendation.low_bid !== recommendation.high_bid) {
    return `${formatMoney(recommendation.low_bid)}-${formatMoney(recommendation.high_bid)}`;
  }
  if (recommendation.confidence) {
    return `${recommendation.confidence} confidence`;
  }
  return "";
}

function fitNarrative(item, trace, requirements, brief) {
  const briefFit = cleanDisplayText(String((brief && brief.fit_reason) || "").trim());
  if (briefFit && briefFit.length > 36) {
    return briefFit;
  }

  const profile = currentProfile();
  const services = firstItems((requirements && requirements.services) || item.matched_terms || [], 4);
  const history = item.historical || {};
  const assessment = getCapacityAssessment(item);
  const parts = [];
  if (services.length) {
    parts.push(`${compactCompanyName(profile.name) || "This business"} already works in ${humanList(services)}, which matches the core scope in this listing.`);
  } else {
    parts.push(`${compactCompanyName(profile.name) || "This business"} matches the selected ${compactProfileLabel(profile)} lane for this listing.`);
  }
  if (history.similar_count) {
    const median = history.award_median ? ` with a typical award around ${formatMoney(history.award_median)}` : "";
    parts.push(`The system found ${number(history.similar_count)} similar Toronto award(s)${median}, so this is grounded in real purchasing history rather than keyword overlap.`);
  }
  if (assessment) {
    parts.push(`Capacity check: ${assessment.pursuit_load} pursuit load, ${String(assessment.response_capacity || "").toLowerCase()}, and ${String(assessment.execution_capacity || "").toLowerCase()}.`);
  }
  const positive = firstItems((trace && trace.positiveSignals) || [], 1)[0];
  if (positive) {
    parts.push(ownerText(positive));
  }
  return cleanDisplayText(parts.join(" "));
}

function scopeNarrative(item, requirements, brief, fallback) {
  const summary = cleanDisplayText(String((brief && brief.owner_summary) || "").trim());
  if (summary) {
    return summary;
  }
  const services = firstItems((requirements && requirements.services) || item.matched_terms || [], 4);
  const solicitation = item.solicitation || {};
  if (services.length) {
    return `City work involving ${humanList(services)}${solicitation.division ? ` for ${solicitation.division}` : ""}.`;
  }
  return fallback;
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
    checklist.innerHTML = "<p>Find matches to see whether this looks ready to bid.</p>";
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
  const deadlineReady = item.days_until_deadline === undefined || item.days_until_deadline === null
    ? false
    : item.days_until_deadline >= 0;
  const checks = [
    ["Deadline", deadlineReady ? deadlinePressureText(item) : "Deadline missing or expired", deadlineReady],
    ["Team Capacity", capacityReady ? (assessment && assessment.recommended_action ? cleanDisplayText(assessment.recommended_action) : "No capacity problem found") : shortText(cleanDisplayText(capacityWarnings[0]), 110), capacityReady],
    ["City Listing", documentsReady ? shortText(documents.length ? documents.slice(0, 2).map(cleanDisplayText).join(", ") : "Listing page available", 110) : "Open the city listing before bid work", documentsReady]
  ];
  const approvedChecks = checks.filter(([, , ok]) => ok).length;
  gateStatus.textContent = `${approvedChecks}/${checks.length} ready`;
  gateStatus.className = `count-pill ${approvedChecks === checks.length ? "gate-ready" : "gate-review"}`;
  checklist.className = "gate-checklist";
  checklist.innerHTML = `
    <div class="gate-owner-task">
      <span>Next step</span>
      <strong>${escapeHtml(cleanDisplayText(ownerTaskText(item)))}</strong>
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
  const candidates = [
    ...((state.scan && state.scan.top_opportunities) || []),
    ...((state.scan && state.scan.watchlist) || [])
  ];
  const items = candidates.length ? candidates : [findSelectedOpportunity() || firstDecisionOpportunity()].filter(Boolean);
  const warnings = firstItems(metrics.warnings || [], 1);
  const summary = metrics.solicitations_loaded
    ? `Checked ${number(metrics.solicitations_loaded)} current listings and ${number(metrics.awards_loaded)} past awards, then kept the contracts worth owner attention.`
    : "Decision reasons appear after contracts are checked.";

  $("pipelineDetails").className = "pipeline-list decision-proof-list";
  if (!items.length) {
    $("pipelineDetails").innerHTML = `<p>${escapeHtml(summary)}</p>`;
    return;
  }

  $("pipelineDetails").innerHTML = `
    <article class="decision-proof-summary">
      <strong>Why These Decisions</strong>
      <p>${escapeHtml(ownerText(summary))}</p>
      ${warnings.length ? `<span>${escapeHtml(ownerText(warnings[0]))}</span>` : ""}
    </article>
    ${items.map((item) => renderDecisionProofCard(item)).join("")}
  `;
}

function renderDecisionProofCard(item) {
  const requirements = getStructuredRequirements(item);
  const trace = normalizedBidFitnessTrace(item, requirements);
  const brief = getOpportunityBrief(item);
  const solicitation = item.solicitation || {};
  const internalLabel = decisionLabel(item.label);
  const decision = ownerDecisionLabel(item.label);
  const title = getCompactOpportunityTitle(item, 120);
  const bidLabel = bidRecommendationLabel(item) || "Bid value not estimated";
  const why = internalLabel === "Skip"
    ? fullSentenceList(blockerItems(item, trace, brief), "This listing is probably not worth bid time.", 3)
    : fitNarrative(item, trace, requirements, brief);
  const check = internalLabel === "Pursue"
    ? ownerTaskText(item)
    : fullSentenceList(blockerItems(item, trace, brief), ownerTaskText(item), 2);
  return `
    <article class="decision-proof-card decision-${escapeHtml(internalLabel.toLowerCase())}">
      <div class="decision-proof-head">
        <div>
          <span class="label-pill ${labelClass(internalLabel)}">${escapeHtml(decision)}</span>
          <h4>${escapeHtml(title)}</h4>
        </div>
        <strong>${escapeHtml(bidLabel)}</strong>
      </div>
      <dl class="decision-proof-meta">
        <div><dt>Document</dt><dd>${escapeHtml(getOpportunityId(item) || "Not listed")}</dd></div>
        <div><dt>Due</dt><dd>${escapeHtml(solicitation.submission_deadline || "Not listed")}</dd></div>
        <div><dt>Status</dt><dd>${escapeHtml(deadlinePressureText(item))}</dd></div>
      </dl>
      <section>
        <span>Why this decision</span>
        <p>${escapeHtml(cleanDisplayText(why))}</p>
      </section>
      <section>
        <span>What to check next</span>
        <p>${escapeHtml(cleanDisplayText(check))}</p>
      </section>
    </article>
  `;
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
    container.innerHTML = "<p>Find matches to see the validation details behind the recommendations.</p>";
    return;
  }

  container.className = "scorecard-grid";
  const activeNvidia = nvidiaPathLabel(metrics);
  const reduction = Number(metrics.shortlist_reduction_ratio || 0);
  const reductionText = `${Math.round(reduction * 100)}% shortlist reduction`;
  container.innerHTML = `
    <article class="scorecard-item">
      <span>Local Processing</span>
      <strong>${escapeHtml(activeNvidia)}</strong>
      <p>${escapeHtml(runtimePathDetail(metrics))}</p>
    </article>
    <article class="scorecard-item">
      <span>Checks Saved</span>
      <strong>${number(metrics.model_calls_avoided)} avoided</strong>
      <p>${number(metrics.model_calls_attempted)} deep checks attempted | ${number(metrics.model_calls_successful)} successful | ${number(metrics.briefs_generated)} brief(s) | ${escapeHtml(reductionText)}</p>
    </article>
    <article class="scorecard-item">
      <span>Safety Check</span>
      <strong>${number(metrics.label_changes_after_extraction)} changed</strong>
      <p>A bid brief can move a listing from "Recommended Bid" to "check first" before a checklist is made.</p>
    </article>
    <article class="scorecard-item">
      <span>Past-Winner Signal</span>
      <strong>${escapeHtml(metrics.market_model_mode || "not scored")}</strong>
      <p>${number(metrics.market_model_examples)} examples | precision@10 ${number(metrics.market_model_precision_at_10)} | lift ${number(metrics.market_model_top_decile_lift)}x</p>
    </article>
    <article class="scorecard-item">
      <span>Time Saved</span>
      <strong>${number(scorecard.false_positives_skipped)} skipped</strong>
      <p>${number(scorecard.similar_awards_grounded)} similar awards grounded | ${number(scorecard.estimated_bid_hours_saved)} bid-review hours saved</p>
    </article>
    <article class="scorecard-item wide">
      <span>Validation Insight</span>
      <strong>${number(scorecard.realistic_historical_opportunities)} realistic historical opportunities</strong>
      <p>${escapeHtml(ownerText(scorecard.top_insight || "Historical and false-positive evidence will appear after you find matches."))}</p>
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
  const title = shortText(best.title || "Current city listing", 150);
  const meta = [
    ownerDecisionLabel(best.label),
    best.division,
    best.deadline ? `Due ${best.deadline}` : "",
    best.award_range
  ].filter(Boolean).join(" | ");
  const reason = best.decision_reason || "Top current listing from the local fit check.";
  return `
    <article class="scorecard-item wide insight-opportunity">
      <span>Best Current Match</span>
      <strong>${escapeHtml(best.document_number)} - ${escapeHtml(title)}</strong>
      <p>${escapeHtml(meta || "Top listing from this search")}</p>
      <ul class="proof-list">
        <li>${escapeHtml(shortText(ownerText(reason), 190))}</li>
        ${firstItems(best.matched_terms || [], 3).map((term) => `<li>Matched: ${escapeHtml(ownerText(term))}</li>`).join("")}
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
      <span>Similar Past Awards</span>
      <strong>${escapeHtml(range)}</strong>
      <ul class="proof-list">
        ${examples.map((award) => {
    const value = award.award_value_label || (award.award_value ? formatMoney(award.award_value) : "value not listed");
    const descriptor = shortText(award.description || award.document_number || "Historical award", 120);
    const division = award.division ? ` / ${award.division}` : "";
    return `<li>${escapeHtml(value)}${escapeHtml(division)} - ${escapeHtml(ownerText(descriptor))}</li>`;
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
      <span>Listings We Passed On</span>
      <strong>${number(scorecard.false_positives_skipped)} misleading matches skipped</strong>
      <ul class="proof-list">
        ${categories.map((category) => {
    const label = `${category.category || "Uncategorized"} / ${category.blocker || "weak evidence"}`;
    return `<li>${escapeHtml(ownerText(label))}: ${number(category.count)} skipped</li>`;
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
    ? reasons.map((item) => `${ownerText(item.reason || "Needs a closer look")} (${number(item.count)})`)
    : examples.map((item) => `${item.document_number || "Listing"}: ${ownerText(firstItems(item.capacity_warnings || item.reasons || [], 1)[0] || item.recommended_action || "needs a closer look")}`);
  return `
    <article class="scorecard-item wide capacity-card">
      <span>Team Capacity</span>
      <strong>${number(scorecard.capacity_downgrades)} listings held for a closer look</strong>
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
            <p class="eyebrow">Why This Decision</p>
            <h4>No listing selected</h4>
            <span>Find matches or select a row to see why it was recommended or passed over.</span>
          </div>
          <span class="count-pill">Waiting</span>
        </div>
      </article>
    `;
  }

  const trace = normalizedBidFitnessTrace(item, requirements);
  const label = decisionLabel(item.label);
  const subtitle = label === "Skip"
    ? "Why we passed on this listing"
    : "Why this listing is shown";

  return `
    <article class="bid-fitness-trace">
      <div class="trace-header">
        <div>
          <p class="eyebrow">Why This Decision</p>
          <h4>${escapeHtml(getTitle(item))}</h4>
          <span>${escapeHtml(subtitle)}</span>
        </div>
        <span class="count-pill">${trace.hasBackendTrace ? "Checked details" : "Basic evidence"}</span>
      </div>
      <div class="trace-grid">
        ${renderTraceBucket("Deal Breakers", trace.hardBlockers, "blocker", "No deal-breaker reported.")}
        ${renderTraceBucket("Checks Used", trace.rulesTriggered, "rule", "No specific check returned.")}
        ${renderTraceBucket("Things To Confirm", trace.softWarnings, "warning", "No warning reported.")}
        ${renderTraceBucket("Why It Looks Good", trace.positiveSignals, "positive", "No positive signal reported.")}
        ${renderTraceBucket("Documents / Requirements", trace.requirementSignals, "requirement", "No requirement signal reported.")}
        ${renderTraceBucket("Team Capacity", trace.capacityGates, "capacity", "No capacity issue reported.")}
        ${renderTraceBucket("Similar Past Awards", trace.historicalAnalogs, "history", "No similar past award returned.")}
        ${renderTraceBucket("Summary Labels", trace.scorecardLabels, "scorecard", "No summary label returned.", 10)}
      </div>
      <div class="trace-rationale">
        <span>Bottom Line</span>
        <p>${escapeHtml(ownerText(trace.finalRationale))}</p>
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
    ? `<ul>${safeItems.map((item) => `<li>${escapeHtml(ownerText(item))}</li>`).join("")}</ul>`
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
    ["procurement_type", "Buying process"]
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
      items.push(`Current bid load: ${assessment.pursuit_load}`);
    }
    if (assessment.response_capacity) {
      items.push(`Time to respond: ${assessment.response_capacity}`);
    }
    if (assessment.execution_capacity) {
      items.push(`Team capacity: ${assessment.execution_capacity}`);
    }
    if (assessment.recommended_action) {
      items.push(`Suggested next step: ${ownerText(assessment.recommended_action)}`);
    }
  }
  if (requirements) {
    items.push(...textItems(requirements.capacity_flags).map((flag) => `Capacity note: ${flag}`));
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
    container.innerHTML = "<p>No checked listings yet.</p>";
    return;
  }

  container.innerHTML = items.map((item) => {
    const solicitation = item.solicitation || {};
    return `
      <div class="stream-row">
        <strong>${escapeHtml(getCompactOpportunityTitle(item, 150))}</strong>
        <span class="label-pill ${labelClass(item.label)}">${escapeHtml(ownerDecisionLabel(item.label))}</span>
        <span>${escapeHtml(solicitation.submission_deadline || "No deadline")}</span>
      </div>
    `;
  }).join("");
}

function renderTimeline(items) {
  const container = $("timeline");
  if (!container) {
    return;
  }
  container.className = items.length ? "timeline" : "timeline empty-list";
  if (!items.length) {
    container.innerHTML = "<p>Pick a month to see deadline reminders and next steps.</p>";
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
          <strong>${escapeHtml(ownerText(String(title)))}</strong>
          <span>${escapeHtml(ownerText(String(body)))}</span>
        </div>
      </div>
    `;
  }).join("");
}

function renderPacket(packet, approved) {
  const container = $("packetOutput");
  if (!container) {
    return;
  }
  if (!packet) {
    container.className = "packet-output empty-list";
    container.innerHTML = `<p>No ${approvalArtifactNoun()} returned.</p>`;
    container.hidden = false;
    return;
  }

  container.className = "packet-output";
  container.hidden = false;
  const contact = packet.buyer_contact || {};
  const ownerReady = Boolean(packet.owner_ready);
  const requiresNemotron = Boolean(packet.requires_nemotron);
  const statusText = ownerReady
    ? `${approvalArtifactTitle()} are ready for owner review. Submission is not sent from this workspace.`
    : requiresNemotron
      ? "Needs the local bid brief before it is ready to use."
      : "Choose a listing first.";
  const checklist = firstItems(packet.checklist || [], 3).map(cleanDisplayText);
  const questions = firstItems(packet.clarification_questions || [], 2).map(cleanDisplayText);
  const contactLines = [contact.name, contact.email, contact.phone].filter(Boolean);
  container.innerHTML = `
    <div class="packet-result-title">
      <span>Prepared ${escapeHtml(approvalArtifactTitle())}</span>
      <strong>${escapeHtml(ownerReady ? "Ready" : "Review first")}</strong>
    </div>
    <div class="packet-grid">
      <div class="packet-card packet-primary">
        <strong>${escapeHtml(shortText(cleanDisplayText(packet.title || `Prepared ${approvalArtifactNoun()}`), 120))}</strong>
        <span>${escapeHtml(shortText(cleanDisplayText(packet.summary || `${approvalArtifactTitle()} prepared from the match details.`), 240))}</span>
      </div>
      <div class="packet-card packet-status-card">
        <strong>Status</strong>
        <span>${escapeHtml(statusText)}</span>
        ${packet.simulated_receipt ? `<p>${escapeHtml(packet.simulated_receipt)}</p>` : ""}
      </div>
      <div class="packet-card">
        <strong>Next Steps</strong>
        ${renderList(checklist)}
      </div>
      ${questions.length ? `
        <div class="packet-card">
          <strong>Buyer Questions</strong>
          ${renderList(questions)}
        </div>
      ` : ""}
      <div class="packet-card">
        <strong>Buyer Contact</strong>
        ${renderList(contactLines)}
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
  const scanButton = $("scanButton");
  const approveButton = $("approveButton");
  scanButton.disabled = isBusy || !canRun;
  scanButton.textContent = isBusy ? "Scanning..." : (state.scan ? "Refresh Matches" : "Find Matches");
  $("monthSelector").disabled = isBusy || !canRun;
  approveButton.disabled = isBusy || !canApproveCurrent();
  if (isBusy && message.toLowerCase().includes("bid notes")) {
    approveButton.textContent = "Preparing...";
  } else {
    approveButton.innerHTML = "<span>Prepare Bid Notes</span>";
  }
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
    || "Untitled city listing";
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
    return `${category} city listing from ${division}.`;
  }
  if (category) {
    return `${category} city listing.`;
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

function getBidRecommendation(item) {
  if (!item || !item.bid_recommendation || typeof item.bid_recommendation !== "object") {
    return null;
  }
  const recommendation = item.bid_recommendation;
  return recommendation.recommended_bid ? recommendation : null;
}

function bidRecommendationLabel(item) {
  const recommendation = getBidRecommendation(item);
  if (!recommendation) {
    return "";
  }
  return `Bid ${formatMoney(recommendation.recommended_bid)}`;
}

function bidRecommendationLanguage(item) {
  const recommendation = getBidRecommendation(item);
  if (!item) {
    return "Bid guidance appears after a city listing is checked.";
  }
  if (!recommendation) {
    return "Not enough historical award value evidence to suggest a bid amount.";
  }
  const amount = formatMoney(recommendation.recommended_bid);
  const range = recommendation.low_bid && recommendation.high_bid && recommendation.low_bid !== recommendation.high_bid
    ? ` Suggested range ${formatMoney(recommendation.low_bid)} to ${formatMoney(recommendation.high_bid)}.`
    : "";
  const evidence = firstItems(recommendation.evidence || [], 1)[0] || "";
  return `Bid around ${amount}. ${range} ${evidence}`.replace(/\s+/g, " ").trim();
}

function simulationLanguage(item) {
  const simulation = item && item.simulation_summary;
  if (!simulation || !simulation.iterations) {
    return "Revenue scenarios appear after the value model scores this listing.";
  }
  const range = `${formatMoney(simulation.likely_low)} to ${formatMoney(simulation.likely_high)}`;
  const downside = simulation.downside_case ? ` Downside ${formatMoney(simulation.downside_case)}.` : "";
  const driver = firstItems(simulation.drivers || [], 1)[0] || "";
  return `Likely revenue range ${range} (${simulation.confidence || "directional"} confidence).${downside} ${driver}`.replace(/\s+/g, " ").trim();
}

function portfolioLanguage(item) {
  const decision = item && item.portfolio_decision;
  if (!decision || !decision.decision) {
    return "Portfolio optimizer runs after revenue scoring and capacity checks.";
  }
  const value = decision.expected_value ? ` Expected value ${formatMoney(decision.expected_value)}.` : "";
  const effort = decision.estimator_hours ? ` Estimator effort ${number(decision.estimator_hours)} hours.` : "";
  const reason = firstItems(decision.reasons || [], 1)[0] || "";
  return `${decision.decision}.${value}${effort} ${reason}`.replace(/\s+/g, " ").trim();
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
    return "Local Nemotron brief";
  }
  if (brief.source === "deterministic_fallback") {
    return "Basic local brief";
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
  const docLabel = documentNumber ? `Listing ${documentNumber}` : "Toronto listing";
  const note = source.is_demo_record
    ? "Sample fallback record"
    : source.verification_note || "Official Toronto listing";
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
        ${brief.source === "local_nim" ? "<span>Ready</span>" : "<span>Needs bid brief</span>"}
      </div>
      ${body ? `<p>${escapeHtml(body)}</p>` : ""}
      ${documents.length ? `<div class="brief-row"><span>Docs</span><em>${escapeHtml(documents.join(", "))}</em></div>` : ""}
      ${blockers.length ? `<div class="brief-row warning"><span>Check</span><em>${escapeHtml(ownerText(blockers.join(", ")))}</em></div>` : ""}
      ${nextSteps.length ? `<div class="brief-row"><span>Next</span><em>${escapeHtml(nextSteps[0])}</em></div>` : ""}
    </div>
  `;
}

function briefReasonItems(brief) {
  if (!brief || typeof brief !== "object") {
    return [];
  }
  return uniqueTextItems([
    brief.fit_reason
  ]);
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

function ownerDecisionLabel(label) {
  const labels = {
    Pursue: "Recommended Bid",
    Review: "Check First",
    Monitor: "Keep Watching",
    Skip: "Pass"
  };
  return labels[decisionLabel(label)] || "Keep Watching";
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

function approvalArtifactNoun() {
  return "bid notes";
}

function approvalArtifactTitle() {
  return "Bid Notes";
}

function ownerText(value) {
  return String(value || "")
    .replace(/\bPursue Now\b/g, "Worth reviewing today")
    .replace(/\bPursue After Review\b/g, "Check first, then decide")
    .replace(/\bReview risks\b/gi, "Check risks")
    .replace(/\bReview the\b/gi, "Check the")
    .replace(/\bReview whether\b/gi, "Check whether")
    .replace(/\bReview all\b/gi, "Check all")
    .replace(/\bPursue\b/g, "Recommended Bid")
    .replace(/\bReview\b/g, "Check First")
    .replace(/\bMonitor\b/g, "Keep Watching")
    .replace(/\bSkip\b/g, "Pass")
    .replace(/\bsolicitations\b/gi, "city listings")
    .replace(/\bsolicitation\b/gi, "city listing")
    .replace(/\bsource package\b/gi, "city listing")
    .replace(/\bsource file\b/gi, "city listing")
    .replace(/\bsources\b/gi, "city listings")
    .replace(/\bsource\b/gi, "city listing")
    .replace(/\bapproval packet\b/gi, approvalArtifactNoun())
    .replace(/\bowner-ready packet\b/gi, `ready-to-use ${approvalArtifactNoun()}`)
    .replace(/\bpacket\b/gi, approvalArtifactNoun())
    .replace(/\bready-to-use bid notes blocked\b/gi, `${approvalArtifactTitle()} need the local bid brief`)
    .replace(/\bmodel call\(s\)\b/gi, "deep check(s)")
    .replace(/\bmodel calls\b/gi, "deep checks")
    .replace(/\bdeterministic\b/gi, "rule-based")
    .replace(/\bfalse-positive\b/gi, "misleading")
    .replace(/\bfalse positive\b/gi, "misleading")
    .replace(/\bblocker\b/gi, "concern")
    .replace(/\bblockers\b/gi, "concerns")
    .replace(/\bcapacity gate\b/gi, "capacity check")
    .replace(/\bowner review\b/gi, "a closer look")
    .replace(/\bprocurement\b/gi, "city buying")
    .replace(/\bopportunity\b/gi, "listing")
    .replace(/\bopportunities\b/gi, "listings");
}

function cleanDisplayText(value) {
  return ownerText(value)
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/\.;/g, ".")
    .replace(/;\./g, ".")
    .replace(/,;/g, ";")
    .replace(/([;:])(?=\S)/g, "$1 ")
    .replace(/,([^\s\d])/g, ", $1")
    .replace(/([.;:!?])\s+\1+/g, "$1")
    .trim();
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

function selectedDemoMonth() {
  return DEMO_MONTHS_2026.find((month) => month.value === state.selectedDemoMonth)
    || DEMO_MONTHS_2026[DEMO_MONTHS_2026.length - 1];
}

function demoMonthForDate(value) {
  const yearMonth = String(value || "").slice(0, 7);
  if (!yearMonth) {
    return null;
  }
  return DEMO_MONTHS_2026.find((month) => month.value.slice(0, 7) === yearMonth) || null;
}

function syncMonthSelector() {
  const selector = $("monthSelector");
  if (selector) {
    selector.value = selectedDemoMonth().value;
  }
  updateSnapshotLabel();
}

function updateSnapshotLabel() {
  const label = $("snapshotEyebrow");
  if (label) {
    label.textContent = `${selectedDemoMonth().label} 2026`;
  }
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
      <dt>Why This Type</dt>
      <dd>${escapeHtml(ownerText(profile.lane_basis || "Waiting for city listing evidence"))}</dd>
    </div>
    <div>
      <dt>2026 Matching Listings</dt>
      <dd>${profile.ytd_solicitation_hits === undefined ? "Not listed" : number(profile.ytd_solicitation_hits)}</dd>
    </div>
    <div>
      <dt>Strong Matches</dt>
      <dd>${profile.exclusive_best_fit_hits === undefined ? "Not listed" : number(profile.exclusive_best_fit_hits)}</dd>
    </div>
  `;
  renderEvidenceTags(divisions, profile.top_divisions || []);
  renderEvidenceTags(goodFit, profile.good_fit_examples || []);
  renderEvidenceTags(badFit, profile.bad_fit_examples || []);
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
    local_nim: "local bid brief",
    deterministic_fallback: "basic rule check"
  };
  const source = sourceLabels[requirements.source] || humanizeToken(requirements.source);
  return `Brief from: ${source}`;
}

function requirementExtractionLanguage(item, requirements, fallbackTerms, solicitation) {
  if (!item) {
    return "Requirements will appear after a listing is checked.";
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
      parts.push(`Buying process: ${procurementType}`);
    }
    if (parts.length) {
      return parts.join(". ") + ".";
    }
  }
  if (fallbackTerms.length) {
    return `Found scope signals: ${fallbackTerms.join(", ")}.`;
  }
  return `Used category and description to identify ${solicitation.category || "the type of work"}.`;
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
    return "Eligibility, deadline, and team capacity will be checked after you find matches.";
  }
  const parts = [];
  const riskFlags = requirements ? firstItems(requirements.risk_flags, 3) : [];
  const capacityFlags = requirements ? firstItems(requirements.capacity_flags, 3) : [];
  const assessment = getCapacityAssessment(item);
  const assessmentWarnings = capacityWarningItems(item);
  const rejectionReasons = item ? firstItems(item.rejection_reasons, 3) : [];
  const deadlineRisk = (requirements && requirements.deadline_risk) || supporting.deadlineRisk;

  if (riskFlags.length) {
    parts.push(`Risks to check: ${riskFlags.join(", ")}`);
  }
  if (capacityFlags.length) {
    parts.push(`Capacity notes: ${capacityFlags.join(", ")}`);
  }
  if (rejectionReasons.length) {
    parts.push(`Reasons to pass: ${rejectionReasons.join(", ")}`);
  }
  if (assessment) {
    parts.push(
      `Current bid load: ${assessment.pursuit_load}`,
      `Time to respond: ${assessment.response_capacity}`,
      `Team capacity: ${assessment.execution_capacity}`,
      `Suggested next step: ${ownerText(assessment.recommended_action)}`
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
    parts.push(`Bid effort: ${supporting.pursuitEffort}`);
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
    recommendation: ownerDecisionLabel(item.label),
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
    : whyMatchedItems(item, trace, requirements, brief);
  return cleanDisplayText(ownerText(source[0] || finalReason(item, requirements)));
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
    return blockers.length ? `Pass for now: ${shortText(ownerText(blockers[0]), 96)}` : "Do not spend bid time on this listing";
  }
  if (warnings.length || (assessment && assessment.recommended_action === "Pursue After Review")) {
    return "Check team capacity before deciding";
  }
  if (Number(days) >= 0 && Number(days) <= 2) {
    return "Confirm today whether you can respond in time";
  }
  if (requirements && requirements.next_action) {
    return shortText(ownerText(requirements.next_action), 110);
  }
  const nextSteps = textItems(brief && brief.next_steps);
  if (nextSteps.length) {
    return shortText(ownerText(nextSteps[0]), 110);
  }
  if (label === "Pursue") {
    return "Open the city listing and assign an estimator";
  }
  if (label === "Review") {
    return "Check the concern before spending bid time";
  }
  return "Keep an eye on it for updates or a better fit";
}

function fitConfidenceText(item, trace = null) {
  const label = decisionLabel(item.label);
  const activeTrace = trace || normalizedBidFitnessTrace(item, getStructuredRequirements(item));
  const score = Number(item.rank_score);
  if (label === "Skip") {
    return "Not a fit";
  }
  if (activeTrace.positiveSignals.length >= 2 || score >= 70) {
    return "Strong scope match";
  }
  if (label === "Review") {
    return "Good fit, check first";
  }
  if (label === "Monitor") {
    return "Relevant, not urgent";
  }
  return "Needs a closer look";
}

function whyMatchedItems(item, trace, requirements, brief = null) {
  return firstItems(uniqueTextItems([
    ...briefReasonItems(brief),
    ...requirementSignalItems(requirements),
    ...trace.positiveSignals,
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
  const safeItems = firstItems(uniqueTextItems(textItems(items).map(cleanDisplayText)), limit);
  if (!safeItems.length) {
    return fallback;
  }
  return shortText(cleanDisplayText(safeItems.join("; ")), maxLength);
}

function fullSentenceList(items, fallback, limit = 4) {
  const safeItems = firstItems(uniqueTextItems(textItems(items).map(cleanDisplayText)), limit);
  return safeItems.length ? cleanDisplayText(safeItems.join("; ")) : fallback;
}

function finalReason(item, requirements) {
  const assessment = getCapacityAssessment(item);
  const rejectionReasons = firstItems(item.rejection_reasons, 2);
  if (decisionLabel(item.label) === "Skip" && rejectionReasons.length) {
    return `Reason to pass: ${rejectionReasons.join(", ")}`;
  }
  if (assessment && assessment.recommended_action === "Pursue After Review") {
    return `Capacity check: ${ownerText(assessment.recommended_action)}`;
  }
  if (requirements && requirements.next_action) {
    return `Next step: ${requirements.next_action}`;
  }
  const reasons = item.reasons || item.rejection_reasons || [];
  if (reasons.length) {
    return reasons[0];
  }
  const label = decisionLabel(item.label);
  if (label === "Pursue") {
    return "Strong enough to look at today.";
  }
  if (label === "Review") {
    return "Potential fit, but check one concern first.";
  }
  if (label === "Skip") {
    return "Probably not worth your bid time.";
  }
  return "Relevant, but not urgent enough for today.";
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
  if (!metrics) {
    return "Pending";
  }
  if (!metrics.nvidia_stack_active) {
    return "CPU local path";
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

function runtimePathDetail(metrics) {
  const rapidsMode = (metrics && metrics.rapids_mode) || "python_fallback";
  const nimMode = (metrics && metrics.nemotron_mode) || "deterministic_fallback";
  if (metrics && metrics.nvidia_stack_active) {
    return `Active local acceleration: RAPIDS ${rapidsMode}; NIM ${nimMode}.`;
  }
  return `CPU local run; RAPIDS ${rapidsMode}; NIM ${nimMode}; DGX Spark hooks ready.`;
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
    return "CPU local";
  }
  if (normalized.includes("fallback")) {
    return "local fallback";
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
