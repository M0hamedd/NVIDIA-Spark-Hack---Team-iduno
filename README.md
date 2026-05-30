# Live Contract Radar

Live Contract Radar is a Toronto Open Data procurement agent for small businesses. It monitors current City of Toronto contract opportunities, filters out poor fits, compares realistic matches against historical awards, and prepares an approval-gated bid packet for the owner.

The V1 demo focuses on **GTA Mechanical & Controls Ltd.**, a Toronto-area commercial HVAC and building automation contractor. The goal is to show how a local service business that does not have a procurement team can still discover and act on realistic public revenue opportunities.

This is not a chatbot. It is a local bid intelligence engine: deterministic filtering, historical award comparison, a visual evidence pipeline, and optional Nemotron/NIM structured extraction when a local model endpoint is available.

## Economic Systems Judging Fit

- **Insight Quality:** Small businesses often miss public contracts because of discovery friction, procurement language, deadline pressure, and capacity mismatch, not only because they lack the ability to do the work.
- **Usability:** The owner gets plain procurement decisions: `Pursue`, `Review`, `Monitor`, or `Skip`.
- **Creativity:** The system combines live/daily solicitations, historical awarded contracts, business capacity, local structured requirement extraction, and an approval workflow.
- **Performance:** The pipeline scans procurement records locally first, uses RAPIDS/cuDF when available for raw-record filtering, fast-fails unavailable NIM endpoints, rejects obvious bad fits quickly, and uses Nemotron/NIM only on shortlisted candidates.

## V1 Demo Flow

1. Enter or use the default GTA Mechanical & Controls Ltd. business profile.
2. Run a live scan of Toronto procurement data.
3. Review rejected opportunities to prove the system is filtering, not listing.
4. Open a top `Pursue` or `Review` opportunity.
5. Compare the opportunity to similar historical awards and capacity warnings.
6. Open the judge evidence view for records scanned, rejection counts, runtime, active NVIDIA path, model calls avoided, and backtest insight.
7. Approve the opportunity and generate a simulated bid packet.

## Spark/Local Fast Path

```powershell
python app.py
```

Then open the local URL printed by the server, usually:

```text
http://127.0.0.1:8080
```

For the fastest deterministic DGX Spark/local smoke test, use the cached or fallback data path:

```powershell
$env:CONTRACT_RADAR_CACHE_DIR="data/cache"
$env:CONTRACT_RADAR_OFFLINE="1"
python app.py
```

In a second terminal:

```powershell
python scripts/smoke_api.py --base-url http://127.0.0.1:8080
```

The smoke command validates `/api/health`, `/api/scan`, `/api/simulate`, and `/api/approve` against the running app. Use `--help` to see optional flags, including `--refresh` for a live Toronto Open Data refresh when internet access is available.

To show the judging/performance proof without opening the UI:

```powershell
python scripts/benchmark_pipeline.py --offline --repeat 100
```

The benchmark reports runtime, records/sec, shortlist reduction, model calls avoided, active NVIDIA path, false positives skipped, similar awards grounded, and the top insight scorecard sentence.

Cache behavior:

- By default, the app reads Toronto Open Data cache files from `data/cache` before trying live fetches.
- Successful live fetches write fresh cache files back to `data/cache`.
- If live/cache data is incomplete, the app falls back to built-in deterministic sample data.
- Set `CONTRACT_RADAR_OFFLINE=1` to force the deterministic fallback/sample data path for a stable no-internet demo.

## Environment Variables

These variables are optional for local development and demo reliability.

```powershell
$env:CONTRACT_RADAR_CACHE_DIR="data/cache"
$env:CONTRACT_RADAR_OFFLINE="0"
$env:NIM_BASE_URL="http://localhost:8000/v1"
$env:NIM_MODEL="nvidia/llama-3.1-nemotron-70b-instruct"
$env:NIM_API_KEY=""
$env:NIM_PREFLIGHT_TIMEOUT_SECONDS="0.2"
```

- `CONTRACT_RADAR_CACHE_DIR`: directory for cached Toronto Open Data responses.
- `CONTRACT_RADAR_OFFLINE`: set to `1` to force fallback/sample data for a stable demo.
- `NIM_BASE_URL`: local NVIDIA NIM/OpenAI-compatible endpoint used for structured requirement extraction on shortlisted contracts.
- `NIM_MODEL`: local Nemotron model identifier served by NIM.
- `NIM_API_KEY`: optional key if the local NIM endpoint requires one.
- `NIM_PREFLIGHT_TIMEOUT_SECONDS`: fast preflight timeout before falling back to deterministic extraction.

NIM/Nemotron is optional for local reliability but should be active during the judged Spark run if RAPIDS is not the active NVIDIA path. When `NIM_BASE_URL` is reachable, the app asks a local Nemotron model for structured fields such as requirements, credentials, scope clues, deadlines, and concise evidence wording for already-shortlisted opportunities. Nemotron does **not** make the final `Pursue`, `Review`, `Monitor`, or `Skip` decision. If the endpoint is missing, offline, or returns an unusable response, the app fast-fails to deterministic extraction, ranking, evidence, and fallback summary wording.

## DGX Spark / NVIDIA Story

DGX Spark is used as the local AI and data processing workstation:

- Scan current solicitations and historical award records locally.
- Keep the business profile, capacity limits, and bid strategy on-device.
- Warn when an otherwise relevant opportunity collides with active pursuits, deadline pressure, or execution capacity.
- Use RAPIDS/cuDF for raw-record filtering when available, with Python parity fallback.
- Use fast deterministic filtering before model calls and report how many model calls were avoided.
- Use local Nemotron/NIM only for high-value language tasks after deterministic shortlisting: extracting procurement requirements into structured fields and helping draft evidence-backed owner-facing wording.
- Show the active NVIDIA path, records/sec, model calls avoided, and insight scorecard in Evidence View and benchmark output.

The demo message is: **the model explains and drafts from computed evidence; it does not guess from vibes.**

## Tests

```powershell
python -m unittest
```

Expected V1 coverage:

- Live or fallback data loads successfully.
- Irrelevant, expired, oversized, or wrong-category opportunities are rejected.
- Strong matches are labeled `Pursue` or `Review`.
- Historical award values parse into a range or return insufficient history.
- Approval packet generation requires explicit owner approval.
- Nemotron fallback works when no local NIM endpoint is running.
- The benchmark script reports model efficiency and the insight scorecard.
- Unavailable NIM fast-fails instead of stalling scans.

## Toronto Open Data Datasets

V1 uses public Toronto Open Data procurement feeds. That is enough to prove the local bid intelligence pipeline, but it is not every possible live City bid source and should not be represented as full coverage of all Toronto procurement activity.

Core V1:

- [Toronto Bids Solicitations](https://open.toronto.ca/dataset/tobids-all-open-solicitations/) - current/open City procurement opportunities.
- [Toronto Bids Awarded Contracts](https://open.toronto.ca/dataset/tobids-awarded-contracts/) - historical contract awards for similar-opportunity comparison.

Strong stretch:

- [Toronto Bids Non-Competitive Contracts](https://open.toronto.ca/dataset/tobids-non-competitive-contracts/) - additional purchasing pattern evidence.
- [Procurement Pipeline](https://open.toronto.ca/dataset/procurement-pipeline/) - future opportunities before they become active solicitations.

Economic expansion:

- [Municipal Licensing and Standards - Business Licences and Permits](https://open.toronto.ca/dataset/municipal-licensing-and-standards-business-licences-and-permits/) - business categories and local vendor landscape.
- [Business Improvement Areas](https://open.toronto.ca/dataset/business-improvement-areas/) - local business corridors and future BIA alerting.
- [Business Incubation](https://open.toronto.ca/dataset/business-incubation/) - support programs for businesses that are not yet bid-ready.

Later procurement source expansion:

- Toronto Bids Portal / SAP Ariba for City opportunities beyond the open-data export.
- CanadaBuys for federal tenders and award history.
- Ontario Tenders Portal for Ontario government and broader public-sector opportunities.
- TTC / MERX for Toronto transit solicitations, results, and awards posted through MERX.
- Nearby municipalities including Mississauga, Brampton, Vaughan, Markham, Richmond Hill, Peel, York, Durham, Halton, Hamilton, and other GTA buyers.
- bids&tenders / Link2Build for construction-heavy and municipal Ontario opportunities.
