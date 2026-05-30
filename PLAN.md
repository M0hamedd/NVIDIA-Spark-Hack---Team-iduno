# Live Contract Radar

## Core Message

This is not a chatbot. It is a local bid intelligence engine for businesses that want government contracts.

The product watches Toronto procurement data, compares new opportunities against a company's real capabilities and past award patterns, then tells the business which bids are worth pursuing the moment they appear. The user should not have to manually search, read, and interpret complex contract listings every day.

## What Judges Should Remember

> A business no longer searches government contracts manually. Live Contract Radar watches public procurement data locally, filters out poor fits, and only surfaces opportunities the business can realistically pursue.

The important story is precision over volume. The system is impressive because it can say both:

- "This is worth pursuing."
- "There are no strong bids for you today."

That restraint is what makes it feel like serious business software instead of a generic AI wrapper.

## Target Customer And Pain

The target customer is a professional service business, contractor, or local vendor that wants public-sector work but does not have time to constantly monitor procurement portals.

Their pain:

- Contracts are hard to search and easy to miss.
- Procurement language is dense.
- Small businesses waste time on bids they are unlikely to win.
- Good opportunities can appear and close quickly.
- Owners need a bid/no-bid decision, not a long chat response.

## Demo Business

Use a commercial HVAC and building automation contractor as the primary demo business.

`GTA Mechanical & Controls Ltd.` is a Toronto-area contractor specializing in municipal and commercial building systems.

- **Services:** HVAC maintenance, building automation systems, boiler and chiller service, emergency repairs, preventative maintenance, energy retrofit support.
- **Strengths:** Certified technicians, 24/7 service, experience with schools, libraries, recreation centers, and municipal facilities.
- **Good-fit contracts:** Facilities maintenance, HVAC service, BAS controls, mechanical repairs, public building retrofits.
- **Bad-fit contracts:** Road paving, legal services, pure software, landscaping, food supply, major design/build construction.
- **Why this demo works:** The system can show intelligent acceptance and rejection because the matches are specific, practical, and easy for judges to understand.

## Product Promise

The user gives the system a business profile once. After that, the system monitors procurement data and produces a short list of strong opportunities.

The software should feel like:

- A daily contract radar.
- A bid/no-bid advisor.
- A procurement analyst that runs locally.
- A selective recommendation engine, not a search page.

## User Priority Modes

Let the user choose what "best" means for their business.

- **Best Win Chance:** Default mode. Prioritizes realistic opportunities based on similar past awards, scope match, buyer history, eligibility, and manageable risk.
- **Best Fit:** Prioritizes the closest match to the company's stated services, skills, certifications, and capacity.
- **Highest Value:** Prioritizes larger contracts while still filtering out bad fits and unrealistic pursuits.

The default should be **Best Win Chance** because the core promise is not to show the biggest contracts. It is to show the contracts worth spending time on.

## Decision Language

Avoid AI-looking percentages. Use procurement decision language that business users recognize.

Primary recommendation labels:

- **Pursue:** Strong opportunity and worth immediate attention.
- **Review:** Potentially good, but one or more risks need human judgment.
- **Monitor:** Relevant, but not urgent or not yet strong enough.
- **Skip:** Poor fit, likely waste of time, or clear mismatch.

Supporting labels:

- **Core Fit:** Strong, Partial, Weak.
- **Eligibility:** Clear, Needs Review, Blocked.
- **Competition:** Low, Moderate, High, Unknown.
- **Pursuit Effort:** Low, Medium, High.
- **Deadline Risk:** Manageable, Tight, Critical.
- **Strategic Value:** High, Medium, Low.

Final recommendation should read like a bid/no-bid decision, not an AI confidence score.

## Decision Evidence

Each recommendation needs evidence that proves the system did real work.

For a recommended bid, show:

- Why this contract matches the business.
- Which services, requirements, or phrases triggered the match.
- Whether similar contracts were awarded in the past.
- Whether the contract size and scope look realistic.
- Whether the deadline leaves enough time.
- Whether the business already has too many active pursuits for its team size and response capacity.
- Which risks or watchouts remain.

For a rejected bid, show:

- The strongest reason it was rejected.
- Any misleading keyword matches that were ignored.
- Why a human should not waste time on it.

This rejection evidence is important because it proves the system is filtering intelligently.

## Requirement Extraction And False-Positive Rejection

The system should extract procurement requirements into structured fields before it ranks an opportunity. The model may help convert dense procurement text into JSON, but deterministic validation and bid-fit rules must decide the final recommendation.

Target extracted fields:

- Services required.
- Certifications, insurance, WSIB, bonding, or vendor eligibility requirements.
- Site count, facility type, emergency response language, and service window.
- Contract type, deadline, buyer/division, and procurement status.
- Risk flags such as design/build scope, major construction, pure software implementation, road paving, food supply, or unclear eligibility.

This extraction should feed custom logic, not replace it. A good judge-facing example is:

> "The word maintenance appeared in this solicitation, but the extracted requirement was road maintenance, not HVAC maintenance, so the engine skipped it."

False-positive rejection is part of the product, not a side effect. The system should explicitly show misleading matches it ignored.

## Capacity-Aware Bid Warnings

The system should behave like a practical bid advisor, not just a matching engine. A strong contract can still be a bad idea if the business is too small, already pursuing too many bids, or lacks enough time to respond well.

For each business profile, track or estimate:

- Team size.
- Maximum sites per day.
- Preferred contract size.
- Response days available.
- Active pursuits already in progress.
- Current `Pursue` and `Review` recommendations in the monitoring window.

Use that context to produce smart warnings:

- **Pursuit Load:** Clear, Busy, Overloaded.
- **Response Capacity:** Enough Time, Tight, At Risk.
- **Execution Capacity:** Fits Team, Needs Scheduling Review, Likely Too Large.
- **Recommended Action:** Pursue Now, Pursue After Review, Monitor, Skip For Capacity.

Example judge/demo moment:

> "This HVAC contract is a strong fit, but GTA Mechanical is already pursuing three bids this week. Because the deadline is tight and the team is limited, the system marks this as Review instead of Pursue."

This feature is especially important for small businesses. It proves the system is not blindly recommending every relevant contract; it is thinking about whether the owner can realistically chase and deliver the work.

## Anti-ChatGPT Proof

The project must visibly prove that it is not just prompt-in, answer-out.

The backend should follow a real pipeline:

`Toronto Open Data -> Ingestion -> Cleaning -> Requirement Extraction -> Business Profile Matching -> Historical Award Comparison -> Risk Filter -> Bid/No-Bid Decision -> Explanation`

The model can help with extraction and wording, but the product intelligence comes from:

- Structured data ingestion.
- Structured requirement extraction with deterministic schema validation.
- Deterministic filtering.
- A custom Bid Fitness Engine with local scoring and rule checks.
- Historical award comparison.
- Historical award retrieval over similar past contracts.
- Capacity-aware risk gates.
- False-positive rejection logic.
- Evidence-backed recommendations.
- Local DGX Spark/Nemotron processing where available.

If the model is unavailable, the system should still produce useful ranked decisions with deterministic fallbacks.

The decision flow should be:

`Solicitation -> Requirement Extraction -> Capability Match -> Historical Award Retrieval -> Capacity/Risk Gates -> Bid Fitness Decision -> Evidence Summary`

Nemotron/NIM should not be the final decision-maker. It should extract, enrich, or summarize from computed evidence. The custom bid-fitness logic owns `Pursue`, `Review`, `Monitor`, and `Skip`.

## Judge Evidence View

The judge-facing backend view should be visual, not just text.

Show a pipeline with each stage lighting up as a contract is processed:

`Open Data Feed -> Contract Parser -> Requirement Extractor -> Profile Matcher -> Award Comparator -> Risk Filter -> Recommendation`

Each stage should output business-readable evidence:

- **Parsed:** Contract type, buyer, deadline, procurement status.
- **Requirements Found:** HVAC maintenance, BAS controls, emergency response, municipal facility service, required documents, and risk flags.
- **Profile Match:** Core services align with the business profile.
- **Award History:** Similar facilities contracts retrieved from past awards.
- **Risk Filter:** No obvious certification, deadline, bonding, or capacity blockers.
- **False Positive Check:** Misleading keyword matches ignored or rejected.
- **Recommendation:** Pursue.

This is the visual proof for judges: the system is a decision engine with local AI inside it, not a chatbot interface wrapped around a prompt.

Add a compact technical-depth panel for judges that shows records scanned, similar awards retrieved, rules triggered, skipped false positives, model/fallback mode, and runtime. This should make the engineering visible without exposing AI-looking confidence percentages.

## Readable Modern UI Direction

The UI needs to look like real procurement operations software, not a basic demo page or a chatbot skin. It should be readable first, modern second, and flashy only where the visual proof helps judges understand the system.

Use current open-source UI patterns as inspiration:

- **Tailwind CSS:** Use utility-first styling, responsive layouts, and design tokens for spacing, type, color, and states.
- **shadcn/ui style components:** Prefer clean, copy-owned components for buttons, badges, tabs, tables, sheets/drawers, tooltips, skeleton loaders, empty states, and forms.
- **Radix UI principles:** Use accessible primitives or equivalent accessible behavior for dialogs, selects, tabs, tooltips, drawers, focus management, and keyboard navigation.
- **Tremor-style dashboard patterns:** Use restrained metric cards, status badges, simple charts, and data-dense dashboard composition where useful.
- **TanStack Table-style behavior:** If the frontend moves to React, use a real table/data-grid approach for sorting, filtering, pagination, column visibility, row detail expansion, and sticky headers.
- **Government design-system lessons:** Tables, forms, status messages, and filters should prioritize accessibility, contrast, plain language, and scanability.

Do not rely on remote CDN assets for the Spark demo. If Tailwind or an open-source component system is used, the CSS and dependencies must be locally installable or compiled into checked-in static assets so the app works offline.

Target layout for the MVP:

- **Left rail:** Business profile, priority mode, active pursuits/capacity, and scan controls.
- **Center workspace:** Opportunity queue with `Pursue`, `Review`, `Monitor`, and `Skip` rows; sortable columns for buyer, deadline, effort, value, and decision.
- **Right inspector:** Selected opportunity details, bid/no-bid decision, evidence, historical awards, risks, and approval packet action.
- **Judge Evidence View:** A visual pipeline with stages, rule traces, extracted requirements, skipped false positives, and runtime/model mode.

Readable UI requirements:

- Use tables for comparison-heavy data instead of only stacked cards.
- Use status badges and decision chips, not AI confidence numbers.
- Make primary actions obvious: `Live Scan`, `Simulate Next Day`, `Approve Packet`.
- Use lucide or equivalent open-source icons for actions and pipeline stages.
- Use compact typography, clear hierarchy, and stable spacing so long contract names do not break the layout.
- Include loading, empty, error, and no-strong-bids states that look intentional.
- Make the app usable at desktop demo size and laptop/mobile widths without overlapping text or hidden controls.
- Keep the first screen as the working app, not a marketing hero.

The goal is for a judge to understand within five seconds:

> "This is a serious contract dashboard that scans real procurement data, filters intelligently, and explains bid decisions with evidence."

## 5-Minute Demo Spine And Feature Creep Guardrails

The next implementation focus is **AI proof first**. The five-minute demo should make the system's decision pipeline obvious, even if the UI is still a lightweight static app.

The demo spine:

1. Load `GTA Mechanical & Controls Ltd.`
2. Run a live Toronto Open Data scan, automatically falling back to cached real records if live fetch fails.
3. Show records scanned, awards compared, and rejected opportunities.
4. Open one `Pursue` or `Review` opportunity.
5. Show extracted requirements, similar historical awards, false-positive rejection, and capacity warning evidence.
6. Show Nemotron/local fallback status as technical proof.
7. End with approval packet generation only as an optional final action.

The one new feature allowed before demo polish freeze is **capacity warnings**:

- Track `active_pursuit_count` and `max_active_pursuits` on the business profile.
- Add capacity evidence to each evaluated opportunity:
  `Pursuit Load`, `Response Capacity`, `Execution Capacity`, `Recommended Action`, and warning text.
- Downgrade a strong `Pursue` to `Review` only when overload is paired with deadline pressure or execution-size risk.
- Otherwise, keep the opportunity visible and show the warning as business evidence.

Feature creep for the MVP:

- **Cut:** more procurement sources, full React/Vite migration, full shadcn rebuild, ranker/fine-tuning, complex table sorting/filtering, deep backtest, automatic submission, and full SAP Ariba integration.
- **Keep only if demo-supporting:** readable static UI polish, Nemotron extraction/fallback status, approval packet, and simulate-next-day.
- **Rule:** any new task must answer, "Will this make the 5-minute demo more obviously not a chatbot?"

## Bid Intelligence Moat

The current system is already more than a chatbot because the bid/no-bid decision works deterministically without a model. The next moat is to make that engine deeper and more visible.

MVP moat work:

- **Structured Rule Trace:** every opportunity should expose a `bid_fitness_trace` showing hard blockers, positive fit signals, historical evidence, capacity gates, deadline gates, false-positive checks, and the final decision rationale.
- **Bid Fitness Scorecard:** show business labels instead of percentages:
  `Core Fit`, `Scope Fit`, `Buyer History`, `Capacity`, `Deadline`, `Competition`, `Pursuit Effort`, and `Decision`.
- **Hard Blockers vs Soft Warnings:** separate reasons that force `Skip` from warnings that allow `Review` or `Monitor`.
- **Historical Analog Retrieval:** every recommended or reviewed opportunity should show similar past awards and why those awards are relevant.
- **Compact Backtest Summary:** show how the same engine would have handled historical Toronto records, such as realistic HVAC opportunities surfaced, poor fits rejected, and common false-positive categories skipped.

The moat story for judges:

> "The model can extract requirements, but the proprietary value is the local bid-fitness engine: hard blockers, soft warnings, historical analogs, capacity gates, and a backtestable decision trace."

Feature-creep boundary:

- The moat is not a full ML ranker yet.
- The moat is not more data sources yet.
- The moat is not a prettier explanation layer on top of weak logic.
- A learned ranker is only allowed after the deterministic trace and backtest make the current engine measurable.

## Demo Flow

1. Enter or load the demo business profile for `GTA Mechanical & Controls Ltd.`
2. The system analyzes historical Toronto awards and reports how many past contracts the business could realistically have pursued.
3. The user chooses a priority mode: **Best Win Chance**, **Best Fit**, or **Highest Value**.
4. The user asks for current open bids.
5. The system returns only a small number of strong recommendations, ideally the top 3 to 5.
6. The system also shows skipped examples so judges can see false positives being rejected.
7. The user clicks **Simulate Next Day**.
8. The simulation advances through real open-data records until a relevant contract appears.
9. The matching contract enters the pipeline and receives a bid/no-bid decision.
10. The judge evidence view shows requirements extracted, similar awards retrieved, rules triggered, false positives skipped, and how the recommendation was produced.
11. If available, the technical-depth panel shows a historical backtest summary: how many past records would have been surfaced or skipped by the same engine.

The dramatic demo moment is when the user does not search. A relevant contract appears because the system is watching for them.

## Smallest Impressive Version

The smallest impressive version is:

- User enters what their business does.
- System uses real Toronto procurement data.
- System returns a short list of highly relevant contracts.
- System rejects obvious false positives.
- System explains the decision with evidence.
- Everything runs locally or has local deterministic fallback behavior.

The impressive part is not the number of matches. It is accuracy, selectivity, and proof.

## Core Datasets

- `Toronto Bids Solicitations`
- `Toronto Bids Awarded Contracts`
- `Toronto Bids Non-Competitive Contracts`
- `Procurement Pipeline`
- `Business Licences and Permits`
- `Business Improvement Areas`
- `Business Incubation`

V1 should focus on `Toronto Bids Solicitations` and `Toronto Bids Awarded Contracts`. Additional datasets can support future business profiling and geographic matching.

## Later Source Expansion

Do not expand sources until the Toronto Open Data demo is excellent. The first priority is making one source feel intelligent, selective, and trustworthy.

Later, the product can increase live opportunity coverage by adding:

- **Toronto Bids Portal / SAP Ariba:** Treat as the source-of-truth path for City of Toronto opportunities beyond the open-data export.
- **CanadaBuys:** Add federal tender opportunities and federal award history.
- **Ontario Tenders Portal:** Add Ontario government and broader public-sector opportunities.
- **TTC / MERX:** Add Toronto transit solicitations, results, and awarded solicitations that are posted through MERX.
- **Nearby municipalities:** Add Mississauga, Brampton, Vaughan, Markham, Richmond Hill, Peel, York, Durham, Halton, Hamilton, and other GTA buyers.
- **bids&tenders / Link2Build:** Add construction-heavy and municipal Ontario opportunities.

The expansion story should be: V1 proves the intelligence engine on Toronto Open Data; later versions connect more procurement feeds into the same bid/no-bid pipeline.

## DGX Spark Role

DGX Spark should strengthen the "local intelligence" story:

- Local data processing over live or cached procurement records.
- Local requirement extraction with Nemotron/NIM when available.
- Local enrichment of only the best candidate contracts.
- Local retrieval over historical awards before any model summary is generated.
- Local custom bid-fitness scoring and capacity/risk gates.
- Business profile and bid strategy remain local.
- Deterministic fallback keeps the demo working if the local model path is unavailable.

## NVIDIA Scoring Commitment

The judged Spark demo must visibly prove at least one active NVIDIA path:

- **NIM/Nemotron:** Local structured requirement extraction for shortlisted contracts.
- **RAPIDS/cuDF:** Local accelerated filtering of raw procurement records before Python model objects are built.

Fallback behavior is required for reliability, but fallback alone is not the scoring story. `/api/health`, scan metrics, the benchmark script, and Evidence View should report:

- Active NVIDIA tool(s), model/library version where available, and fallback state.
- Whether RAPIDS/cuDF, local NIM, or deterministic fallback handled the run.
- What work was performed locally: record filtering, shortlist reduction, structured extraction, historical retrieval, and bid-fitness scoring.
- Model calls avoided because deterministic filtering reduced raw records to a small shortlist.
- NIM preflight/circuit-breaker status so an unavailable local model does not stall the demo.

Agents working on DGX Spark, Nemotron, local model integration, or acceleration should use the relevant guidance in `Resources.md`.

Fine-tuning should only be added if it can be evaluated. A full LLM fine-tune is not required for the MVP. The stronger hackathon story is either:

- A small local bid-fit ranker trained from positive and negative historical examples.
- Or a prompt/schema extraction path with measured agreement against deterministic labels.

Do not claim fine-tuning unless the demo can show before/after evaluation or backtest evidence.

## End-Of-Day Definition Of Done

By the end of the day, the main demo should support:

- Business profile input or loading.
- Historical award analysis.
- Current open bid recommendations.
- Priority mode selection.
- Selective top recommendations.
- Rejected false-positive examples.
- Structured requirement extraction or deterministic extraction fallback.
- Custom bid-fitness rule trace for every top and skipped opportunity.
- Bid Fitness Scorecard with business labels instead of percentages.
- Hard blockers and soft warnings shown separately.
- Capacity-aware warnings when a small business is overloaded or already pursuing too many bids.
- Historical award retrieval for recommended opportunities.
- Compact backtest summary proving the deterministic engine can be evaluated.
- NVIDIA/Spark proof metrics: active path, RAPIDS mode, NIM mode, records/sec, shortlist reduction, and model calls avoided.
- Benchmark script output for offline fallback and Spark/NVIDIA demo runs.
- Simulate-next-day flow using real extracted/open data.
- Judge evidence view with a visual pipeline.
- Local model path or deterministic fallback path.
- A demo script that clearly says this is not a chatbot wrapper.

## Immediate MVP Agent Split

The current codebase was built against the older KitchenCare plan. The first agent wave should modify that existing implementation rather than starting over. The goal is to get a credible MVP running on DGX Spark as soon as possible.

Shared rules for all agents:

- Keep V1 focused on Toronto Open Data only.
- Do not add CanadaBuys, Ontario Tenders, MERX, or other portals yet.
- Preserve the existing working app shape: `python app.py`, static frontend, local cache, deterministic fallback.
- Use the existing modules unless a small new helper clearly avoids file conflicts.
- Prefer visible judge evidence over hidden cleverness.
- Do not expose AI-looking percentages in the UI.
- Technical-depth work must change the decision process or evidence quality, not just add a cosmetic feature.
- Every completed workstream must have a command, screen, or test that proves it works.
- UI work should improve readability, trust, and judge comprehension. Use modern open-source UI systems only if they keep the Spark demo runnable offline.

### Agent 0: Spark MVP Runner And Integration Gate

**Mission:** Make sure there is always a runnable demo on DGX Spark.

**Owns:** `app.py`, `README.md`, run instructions, smoke-test commands, environment notes.

**Work:**

- Verify `python app.py` runs locally with cached data.
- Document the fastest Spark run path: environment variables, cache behavior, NIM optional mode, and expected URL.
- Add or document an API smoke check for `/api/health`, `/api/scan`, `/api/simulate`, and `/api/approve`.
- Confirm the app still works when Nemotron/NIM is unavailable.
- Confirm the app can use cached Toronto data without internet.

**MVP done when:** the user can run one command on DGX Spark, open the app, scan opportunities, and see deterministic fallback evidence if local NIM is not ready.

### Agent 0A: NVIDIA Stack And Performance Proof

**Mission:** Make the NVIDIA/Spark and performance story measurable, not just narrative.

**Owns:** RAPIDS/NIM status, benchmark script, performance metrics, Evidence View metric fields, related tests.

**Likely files:** `contract_radar/data.py`, `contract_radar/gpu.py`, `contract_radar/nemotron.py`, `contract_radar/service.py`, `scripts/benchmark_pipeline.py`, `static/app.js`, `tests/`.

**Work:**

- Implement a real RAPIDS/cuDF preprocessing path when `cudf` is installed, with Python parity fallback.
- Add NIM availability preflight and a circuit breaker so missing local NIM fast-fails into deterministic extraction.
- Extend `/api/health` with `nvidia_stack_active`, `active_nvidia_tools`, `rapids_cudf_available`, `rapids_mode`, `nim_mode`, and `spark_story`.
- Extend scan metrics with records/sec, shortlist reduction, model calls attempted, model calls avoided, RAPIDS mode, NIM mode, and active NVIDIA stack.
- Add `scripts/benchmark_pipeline.py --offline --repeat 100` to report runtime, throughput, rejected count, shortlist reduction, model calls avoided, and active NVIDIA path.
- Add tests proving offline benchmark output exists, unavailable NIM fast-fails, and RAPIDS/cuDF preserves labels when RAPIDS is available.

**MVP done when:** judges can see a benchmark or Evidence View proving what NVIDIA path ran, how fast the scan was, and how many model calls were avoided by local deterministic filtering.

### Agent 1: Demo Business Retarget

**Mission:** Replace the old `Leslieville KitchenCare` story with the HVAC/building automation contractor.

**Owns:** default business profile, fallback sample data, demo copy, related tests.

**Likely files:** `contract_radar/models.py`, `contract_radar/sample_data.py`, `tests/test_data.py`, `tests/test_nemotron_fallback.py`, frontend default profile copy.

**Work:**

- Change the default profile to `GTA Mechanical & Controls Ltd.`
- Use HVAC, BAS controls, boiler/chiller service, emergency repair, preventative maintenance, public building experience.
- Replace kitchen-equipment fallback records with HVAC/facilities records.
- Include obvious false positives: road paving, legal services, pure software, landscaping, food supply, oversized design/build construction.
- Update tests that still expect KitchenCare terms.

**MVP done when:** the first screen and fallback scan tell the HVAC story without any KitchenCare leftovers.

### Agent 2: Decision Labels And Priority Modes

**Mission:** Make the system feel like procurement software, not generic AI.

**Owns:** matching labels, priority-mode behavior, service response buckets, matcher tests.

**Likely files:** `contract_radar/matcher.py`, `contract_radar/service.py`, `contract_radar/simulator.py`, `tests/test_matcher.py`, `tests/test_simulator.py`.

**Work:**

- Replace old labels with `Pursue`, `Review`, `Monitor`, and `Skip`.
- Add supporting evidence labels where possible: core fit, eligibility, competition, pursuit effort, deadline risk, strategic value.
- Add user priority mode input: `best_win_chance`, `best_fit`, `highest_value`.
- Default to `best_win_chance`.
- Make priority mode change ranking, not basic eligibility.
- Ensure the system can say "no strong bids today."
- Add capacity-aware warnings so small businesses are not pushed to pursue too many simultaneous bids.
- Use active pursuits, team size, response days, contract size, and deadline pressure to downgrade or warn on otherwise relevant contracts.

**MVP done when:** scan results use business decision language and priority modes affect ordering in a testable way.

### Agent 2A: Bid Fitness Engine And Requirement Extraction

**Mission:** Add the custom logic judges expect under the hood.

**Owns:** requirement extraction schema, bid-fitness rule trace, false-positive rejection logic, related tests.

**Likely files:** `contract_radar/matcher.py`, `contract_radar/nemotron.py`, `contract_radar/models.py`, possibly a small new `contract_radar/requirements.py`, `tests/test_matcher.py`, `tests/test_nemotron_fallback.py`.

**Work:**

- Extract structured requirements from each solicitation: services, certifications/documents, facility/site signals, deadline risk, procurement type, and risk flags.
- Use Nemotron/NIM for extraction when available, but validate the output against a deterministic schema and fallback extractor.
- Add a custom Bid Fitness Engine that combines capability match, extracted requirements, historical evidence, capacity gates, and hard blockers.
- Preserve plain decision labels while keeping an internal rule trace for judges.
- Add `bid_fitness_trace` for each evaluated opportunity with hard blockers, soft warnings, positive signals, historical analogs, capacity gates, deadline gates, false-positive checks, and final rationale.
- Add a Bid Fitness Scorecard with business labels only, not numeric confidence percentages.
- Separate hard blockers from soft warnings so the user can tell why a bid was skipped versus why it needs review.
- Make false-positive rejection visible, especially misleading terms like road maintenance, software maintenance, legal services, food supply, landscaping, and oversized construction.
- Add tests showing that misleading keyword matches are skipped even when they share generic terms with the profile.

**MVP done when:** each top or skipped opportunity can show extracted requirements, hard blockers, soft warnings, rules triggered, scorecard labels, and the strongest reason for the final bid/no-bid decision.

### Agent 3: Historical Opportunity Evidence

**Mission:** Prove the system learns from past awards and can tell a business what it missed.

**Owns:** historical award analysis, past-fit count, historical retrieval, award evidence wording.

**Likely files:** `contract_radar/history.py`, `contract_radar/service.py`, `tests/test_matcher.py` or a new focused history test.

**Work:**

- Use awarded contracts to estimate how many past contracts the demo business could realistically have pursued.
- Return a concise historical summary in the scan response.
- Retrieve the most similar past awards for each open solicitation and attach them as grounded evidence.
- Include examples of past similar awards, realistic award ranges, buyer/division patterns, and why they matter.
- Add a compact backtest summary that replays the deterministic engine over historical records and reports surfaced realistic opportunities, rejected poor fits, and common false-positive categories.
- Fetch/use the full awarded-contract dataset when practical instead of stopping at 5,000 rows.
- Keep retrieval lightweight and local for MVP: deterministic term/category matching is acceptable; vector embeddings are a stretch only if they improve evidence quality.

**MVP done when:** the demo can say, "Based on public award history, this business could have pursued X similar contracts," each recommended bid shows the similar awards that grounded the decision, and the engine has a small backtest summary judges can inspect.

### Agent 4: Readable UI And Judge Evidence Pipeline

**Mission:** Make the app look like credible business software and turn the evidence view into visual proof that this is not a chatbot wrapper.

**Owns:** frontend layout, readability, visual hierarchy, evidence UI, and frontend pipeline rendering.

**Likely files:** `static/index.html`, `static/app.js`, `static/styles.css`.

**Work:**

- Upgrade the UI from basic styling to a modern procurement dashboard style.
- Use Tailwind CSS or a Tailwind-inspired local design-token system for consistent spacing, color, typography, shadows, borders, and responsive behavior.
- If the frontend is migrated to React/Vite, use shadcn/ui, Radix UI primitives, Tremor dashboard patterns, TanStack Table, and lucide icons where they speed up a professional result.
- If the static frontend stays for MVP speed, borrow those patterns without adding a fragile build step.
- Replace card-only result browsing with a readable opportunity queue/table plus a detail inspector.
- Add sticky or persistent scan controls, priority mode controls, and selected-opportunity context.
- Replace the plain pipeline detail list with visible stages:
  `Open Data Feed -> Contract Parser -> Requirement Extractor -> Profile Matcher -> Award Comparator -> Risk Filter -> Recommendation`.
- Show stage outputs in business language, not percentages.
- Show skipped examples beside the pipeline so false-positive rejection is visible.
- Add a technical-depth panel with records scanned, similar awards retrieved, requirement fields extracted, hard blockers, soft warnings, rules triggered, model/fallback mode, backtest summary, and runtime.
- Add a compact judge scoreboard with active NVIDIA path, records/sec, model calls avoided, false positives skipped, historical opportunities found, and similar awards grounded.
- Add priority-mode controls in the UI.
- Add loading, empty, error, offline, and no-strong-bids states that feel intentional.
- Ensure long solicitation names, buyer names, and requirement lists wrap or truncate cleanly without overlapping.
- Verify keyboard focus, color contrast, button labels, and screen-reader-friendly status updates for core actions.
- Keep the first screen as the actual app, not a landing page.

**MVP done when:** a judge can look at the app and immediately understand both the opportunity queue and the multi-stage decision process, without the interface feeling like a generic AI chat page.

### Agent 5: Simulate Next Day Demo Moment

**Mission:** Make the simulation match the intended demo story.

**Owns:** monitoring simulation and timeline behavior.

**Likely files:** `contract_radar/simulator.py`, `contract_radar/service.py`, `static/app.js`, `tests/test_simulator.py`.

**Work:**

- Change the demo from generic 30-day simulation to a "Simulate Next Day" flow.
- Advance through real/cached solicitation records until a relevant opportunity appears.
- Make the event feel like the system was watching and surfaced the contract automatically.
- Add a historical backtest summary when practical: replay past awarded/open records and report how many realistic HVAC opportunities the same engine would have surfaced or skipped.
- Preserve deterministic fallback behavior so the demo is stable.

**MVP done when:** the user can click one simulation control and see a real or cached relevant contract appear as a daily alert, with optional backtest evidence if it is ready.

### Agent 5A: Backtest And Insight Scorecard

**Mission:** Turn value and insight quality into judge-visible evidence.

**Owns:** insight scorecard, backtest summary, bid-hours-saved estimate, related tests.

**Likely files:** `contract_radar/backtest.py`, `contract_radar/service.py`, `static/app.js`, `tests/`.

**Work:**

- Replay evaluated current/cached Toronto records to count actionable opportunities, skipped misleading matches, capacity downgrades, and similar awards used as grounding.
- Produce one judge-friendly non-obvious insight sentence, such as a buyer/division pattern, realistic award range, and capacity-aware recommendation for the HVAC/BAS profile.
- Estimate practical value with bid-review hours saved from skipped false positives.
- Surface scorecard output in `/api/scan`, Evidence View, benchmark output, and tests.
- Include at least one test covering a true HVAC/BAS fit, a misleading maintenance false positive, and a capacity downgrade.

**MVP done when:** the Evidence View can say what insight the engine discovered, how it was grounded, and how much owner time the filtering saved.

### Agent 6: Demo Script And Docs Alignment

**Mission:** Make the written story match the new app.

**Owns:** `DEMO_SCRIPT.md`, final README wording, plan consistency.

**Work:**

- Replace old KitchenCare and old label language.
- Emphasize "local bid intelligence engine," not chatbot.
- Explain Toronto Open Data limitations honestly: the open solicitation feed is public/open-data coverage, not every City bid ever.
- Keep later source expansion clearly marked as future work.
- Describe the Bid Fitness Engine, historical retrieval, false-positive rejection, and fallback behavior in judge-friendly language.
- Add a 20-second Evidence View beat: "N records became K shortlisted contracts before Nemotron; X false positives were skipped; Y similar awards grounded the decision; this ran locally on DGX Spark."
- Only mention fine-tuning if a ranker/backtest evaluation exists.
- Add exact demo steps for Spark MVP.

**MVP done when:** the docs, demo script, and app all tell the same HVAC/Toronto/Open Data/Spark story.

### Agent 7: Bid-Fit Ranker And Fine-Tuning Stretch

**Mission:** Add a proof-backed training story only if the core demo is already stable.

**Owns:** optional ranker training/evaluation script, labeled examples, evaluation summary.

**Likely files:** `scripts/`, `contract_radar/matcher.py`, `contract_radar/history.py`, `tests/`, docs only after evaluation exists.

**Work:**

- Build positive and negative examples from historical awards and curated false positives.
- Train a small local bid-fit ranker, such as logistic regression, XGBoost, or a compact embedding/reranking model.
- Use features like matched services, category overlap, solicitation type, historical award range, capacity fit, deadline risk, and blocker flags.
- Compare ranker output against deterministic labels in a backtest.
- Keep public UI labels as `Pursue`, `Review`, `Monitor`, and `Skip`; do not expose raw model probabilities.
- Do not replace deterministic hard blockers with a learned model.

**Stretch done when:** the team can show a simple before/after evaluation or backtest proving the ranker improved ordering or false-positive rejection.

## MVP Merge Order

Agents can work in parallel, but merge in this order to reduce conflicts:

1. **Agent 1** retargets the demo business and sample data.
2. **Agent 2** changes labels and priority modes.
3. **Agent 2A** adds requirement extraction, bid-fitness rules, and false-positive rejection traces.
4. **Agent 3** adds historical past-fit evidence and similar-award retrieval.
5. **Agent 0A** adds NVIDIA stack proof, metrics, and benchmark output.
6. **Agent 4** upgrades the evidence UI and technical-depth panel.
7. **Agent 5** changes the simulation flow and adds backtest evidence if ready.
8. **Agent 5A** adds the insight scorecard and backtest proof.
9. **Agent 6** aligns docs after the app behavior settles.
10. **Agent 7** adds the optional ranker/fine-tuning stretch only after the MVP is stable.
11. **Agent 0** runs the Spark MVP acceptance gate throughout and again at the end.

## Spark MVP Acceptance Gate

Before calling the MVP ready, Agent 0 or the integrator must verify:

- `python -m unittest` passes.
- `node --check static/app.js` passes.
- `python scripts/benchmark_pipeline.py --offline --repeat 100` reports runtime, throughput, shortlist reduction, model calls avoided, NVIDIA mode, and insight scorecard.
- `python app.py` starts successfully.
- `/api/health` reports the app, `nvidia_stack_active`, active NVIDIA tools, DGX/RAPIDS status, NIM mode, and Spark story.
- `/api/scan` works with cached Toronto data.
- The default profile is `GTA Mechanical & Controls Ltd.`
- The UI uses `Pursue`, `Review`, `Monitor`, and `Skip`.
- Priority mode selection exists and changes ranking behavior.
- Evidence View shows a visual multi-stage pipeline.
- Evidence View shows a judge scoreboard with active NVIDIA path, records/sec, model calls avoided, false positives skipped, realistic historical opportunities, and similar awards grounded.
- The UI reads as modern procurement/dashboard software, with a queue/table, detail inspector, clear controls, and no remote CDN dependency required for Spark.
- Browser QA checks desktop and laptop/mobile widths for readable text, visible controls, and no overlapping UI.
- Top and skipped opportunities include requirement extraction, `bid_fitness_trace`, hard blockers, soft warnings, scorecard labels, and false-positive evidence.
- Recommended opportunities include similar historical awards when available.
- The technical-depth panel includes a compact backtest summary of surfaced realistic opportunities, rejected poor fits, and false-positive categories.
- Missing local NIM fast-fails into deterministic extraction instead of stalling the scan.
- Any fine-tuning or learned ranker claim has a backtest/evaluation artifact.
- The app works without live internet and without local NIM.

## Agent Merge Readiness

An agent's work is ready to merge only when it can answer:

- What feature did I complete?
- What command, screen, or test proves it works?
- What input did I test with?
- What output did I get?
- What files did I touch?
- Does it use real local/open data?
- Does it support the judge demo directly?
- Does it make the app feel less like a chatbot and more like a bid intelligence system?
- If it touches DGX Spark, Nemotron, or local inference, did it use the relevant resources from `Resources.md`?

Nothing is merge-ready unless it improves the judge demo or the local DGX Spark story.

## Evaluation

The project is good if testing on DGX Spark shows:

- Recommendations are actually relevant.
- Bad matches are rejected.
- Misleading keyword matches are explicitly caught and explained.
- The system can say "no strong bids today."
- The user does not need to manually inspect long contract lists.
- Historical retrieval grounds recommendations in past awards.
- Bid decisions are explainable through hard blockers, soft warnings, scorecard labels, and a deterministic rule trace.
- A compact backtest proves the deterministic engine is measurable before any learned ranker is added.
- The NVIDIA path is provable through health output, benchmark output, and Evidence View, even when fallback mode is used for demo reliability.
- Performance is measurable through records/sec, shortlist reduction, model calls avoided, and NIM fast-fail behavior.
- Any learned ranker or fine-tuning claim is backed by measurable backtest evidence.
- The backend decision process looks serious and visual.
- The frontend looks readable, modern, and business-grade rather than basic.
- The final experience feels like software a real business would pay for.

## Verification Targets

- `python -m unittest` passes.
- `node --check static/app.js` passes.
- `python scripts/benchmark_pipeline.py --offline --repeat 100` passes and prints benchmark plus insight scorecard output.
- API smoke test passes for scan, simulation, and approval packet generation.
- Browser QA passes for the local app.
- Browser QA includes screenshots at desktop and laptop/mobile widths, checking readability, table/inspector layout, loading/error states, and no overlapping text.
- Live or cached scan can process current Toronto procurement records and fall back to sample data if Open Data is unavailable.
- Unit tests cover at least one true HVAC/BAS fit, one misleading keyword false positive, one capacity downgrade, unavailable-NIM fast-fail, RAPIDS/Python parity when RAPIDS is installed, one hard-blocker trace, one soft-warning trace, one scorecard label set, one historical retrieval example, and one compact backtest summary.
- If the ranker stretch is included, its evaluation command produces a readable before/after summary.
