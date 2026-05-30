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
- Which risks or watchouts remain.

For a rejected bid, show:

- The strongest reason it was rejected.
- Any misleading keyword matches that were ignored.
- Why a human should not waste time on it.

This rejection evidence is important because it proves the system is filtering intelligently.

## Anti-ChatGPT Proof

The project must visibly prove that it is not just prompt-in, answer-out.

The backend should follow a real pipeline:

`Toronto Open Data -> Ingestion -> Cleaning -> Requirement Extraction -> Business Profile Matching -> Historical Award Comparison -> Risk Filter -> Bid/No-Bid Decision -> Explanation`

The model can help with extraction and wording, but the product intelligence comes from:

- Structured data ingestion.
- Deterministic filtering.
- Local scoring and rule checks.
- Historical award comparison.
- Rejection logic.
- Evidence-backed recommendations.
- Local DGX Spark/Nemotron processing where available.

If the model is unavailable, the system should still produce useful ranked decisions with deterministic fallbacks.

## Judge Evidence View

The judge-facing backend view should be visual, not just text.

Show a pipeline with each stage lighting up as a contract is processed:

`Open Data Feed -> Contract Parser -> Requirement Extractor -> Profile Matcher -> Award Comparator -> Risk Filter -> Recommendation`

Each stage should output business-readable evidence:

- **Parsed:** Contract type, buyer, deadline, procurement status.
- **Requirements Found:** HVAC maintenance, BAS controls, emergency response, municipal facility service.
- **Profile Match:** Core services align with the business profile.
- **Award History:** Similar facilities contracts found in past awards.
- **Risk Filter:** No obvious certification or capacity blockers.
- **Recommendation:** Pursue.

This is the visual proof for judges: the system is a decision engine with local AI inside it, not a chatbot interface wrapped around a prompt.

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
10. The judge evidence view shows how the recommendation was produced.

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

## DGX Spark Role

DGX Spark should strengthen the "local intelligence" story:

- Local data processing over live or cached procurement records.
- Local requirement extraction with Nemotron/NIM when available.
- Local enrichment of only the best candidate contracts.
- Business profile and bid strategy remain local.
- Deterministic fallback keeps the demo working if the local model path is unavailable.

Agents working on DGX Spark, Nemotron, local model integration, or acceleration should use the relevant guidance in `Resources.md`.

## End-Of-Day Definition Of Done

By the end of the day, the main demo should support:

- Business profile input or loading.
- Historical award analysis.
- Current open bid recommendations.
- Priority mode selection.
- Selective top recommendations.
- Rejected false-positive examples.
- Simulate-next-day flow using real extracted/open data.
- Judge evidence view with a visual pipeline.
- Local model path or deterministic fallback path.
- A demo script that clearly says this is not a chatbot wrapper.

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
- The system can say "no strong bids today."
- The user does not need to manually inspect long contract lists.
- The backend decision process looks serious and visual.
- The final experience feels like software a real business would pay for.

## Verification Targets

- `python -m unittest` passes.
- `node --check static/app.js` passes.
- API smoke test passes for scan, simulation, and approval packet generation.
- Browser QA passes for the local app.
- Live or cached scan can process current Toronto procurement records and fall back to sample data if Open Data is unavailable.
