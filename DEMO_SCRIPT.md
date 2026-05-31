# Live Contract Radar Demo Script

Target length: **3-5 minutes**.

Demo goal: show judges that this is a live/daily procurement monitoring and decision system, not a generic chatbot.

## 0:00-0:25 - Hook

Narration:

> Small businesses can do real work for the City, but they usually do not have a procurement team watching Toronto Bids every morning. They miss opportunities because the language is dense, deadlines are easy to miss, and many contracts are too large or the wrong fit.

Click:

- Open the app.
- Point to the default business profile: **Road/Civil Infrastructure Contractor**.
- Show that the profile switcher also includes **Parks/Landscape Contractor** and **Professional Engineering/Design Firm**.

## 0:25-0:55 - Data-Backed Profile Switcher

Narration:

> The demo is not built around one hand-picked company. We found three recurring 2026 Toronto procurement lanes and turned them into switchable business profiles: road and civil infrastructure, parks and landscape work, and professional engineering or design services. The counts beside each profile show the dataset basis: 45 and 29 for road/civil, 42 and 29 for parks/landscape, and 23 and 14 for engineering/design.

Click:

- Show the three profile options.
- Highlight that the user can switch lanes during the demo and rerun the scan.
- For road/civil, highlight fit signals like road rehabilitation, sidewalks, sewer/stormwater, traffic control, and municipal construction capacity.
- For parks/landscape, highlight park renewal, planting, turf, trails, playground-adjacent site work, and seasonal maintenance.
- For engineering/design, highlight professional services, design, studies, inspections, contract administration, and licensed engineering requirements.

## 0:55-1:35 - Live Scan

Narration:

> Now we scan public Toronto Open Data procurement records and compare them against historical awarded contracts. This V1 feed is honest open-data coverage, not every possible live City bid source. The first pass is deterministic and fast: remove expired items, reject wrong categories, reject oversized work, and keep only candidates worth deeper analysis.

Click:

- Click **Run Live Scan**.
- Show timestamp and source status.
- Show record counts:
  - solicitations scanned
  - awards compared
  - opportunities rejected
  - viable candidates

Judge emphasis:

> The LLM is not looking at every record. DGX Spark does the local filtering first, then Nemotron/NIM extracts structured requirements only from shortlisted contracts.

## 1:35-2:15 - Rejections Prove Selectivity

Narration:

> A search tool would just show anything with loose keyword overlap. We intentionally show the rejections because they prove the system is making business decisions.

Click:

- Open the rejection breakdown.
- Point to examples:
  - `Skip`: wrong lane for the selected profile
  - `Skip`: too large or outside scope for the selected business
  - `Review`: relevant work, but capacity or credential gap
  - `Monitor`: relevant but not ready to act on

Judge emphasis:

> The useful insight is knowing what not to waste time on.

## 2:15-3:05 - Top Opportunity + Historical Awards

Narration:

> Here is the opportunity the system recommends. It is not just a keyword match. It matches the business capabilities, has enough time before closing, fits the contract type, and similar past awards are in a realistic range.

Click:

- Open the top `Pursue` or `Review` card.
- Show:
  - matched capabilities
  - missing requirements
  - capacity warning or clear pursuit load
  - deadline
  - buyer/division
  - similar historical award range or insufficient-history notice

Judge emphasis:

> Nemotron turns dense contract language into a usable owner brief: requirements, blockers, required documents, clarification questions, next steps, and draft outreach. The deterministic bid engine still owns the final Pursue, Review, Monitor, or Skip decision, but validated Nemotron blockers can downgrade a Pursue into Review.

## 3:05-3:45 - Judge Evidence View

Narration:

> The business owner sees a simple alert. For judges, we expose the system evidence so you can see the pipeline underneath.

Click:

- Switch to **Evidence View**.
- Show:
  - live/cache/fallback source status
  - records scanned
  - rejection counts
  - runtime
  - active NVIDIA path
  - cuOpt portfolio mode
  - records per second
  - model calls avoided
  - matched terms
  - historical award comparison
  - false positives skipped
  - similar awards grounded
  - insight scorecard sentence
  - visual stages from open data feed to recommendation
  - DGX/Nemotron status
  - structured extraction fallback status

20-second scoreboard beat:

> The important scoring proof is here: the system turned N raw records into K shortlisted contracts before Nemotron, avoided unnecessary model calls, skipped misleading false positives, grounded this decision in similar awards, and kept the business profile local on DGX Spark. The Bid Fitness Trace shows the hard blockers, soft warnings, rules triggered, capacity gates, and final rationale. If RAPIDS or local NIM is active, the active NVIDIA path is shown here; if not, the fallback reason is explicit.

Optional baseline proof line:

> We also compare this against naive keyword search. On the offline demo set, naive matching surfaces 8 to 9 candidates per persona, while the bid engine cuts that down to 2 to 3 actionable items and skips the misleading lookalikes.

Judge emphasis:

> This is where the performance and execution story lives: fast local scan, deterministic filtering, historical award comparison, selective structured extraction, model-call avoidance, and clear evidence.

## 3:45-4:30 - Approval-Gated Packet

Narration:

> The agent does not submit anything on its own. The owner approves first. After approval, local Nemotron prepares the owner-ready packet: plain-English summary, checklist, missing requirements, clarification questions, SAP Ariba next steps, and a draft buyer email.

Click:

- Click **Approve Draft**.
- Show generated packet.
- Point to simulated receipt/status.

Judge emphasis:

> The product is action-oriented but safe: it prepares the owner to apply, and the submission is simulated for the demo.

## 4:30-5:00 - Close

Narration:

> Live Contract Radar helps small businesses see which City opportunities are actually worth their time. It turns Toronto Open Data into a daily revenue signal: pursue, review, monitor, or skip.

Final line:

> A chatbot can explain a contract if you paste one in. This system monitors the procurement stream, filters it against a real business profile, compares historical awards, shows the evidence pipeline, and prepares the next action after approval.

## Spark MVP Run Path

Start the app:

```powershell
python app.py
```

For local agent smoke tests away from DGX Spark, use `python app.py --without-nemotron` so the deterministic fallback path starts immediately.

For a stable no-internet demo with real cached Toronto Open Data:

```powershell
$env:CONTRACT_RADAR_CACHE_DIR="data/cache"
$env:CONTRACT_RADAR_OFFLINE="1"
python app.py
```

Do not set `CONTRACT_RADAR_ALLOW_SAMPLE_DATA` during the demo. If cache/live data is unavailable, the app should fail rather than showing bundled fixture postings.

In a second terminal, verify the API:

```powershell
python scripts/smoke_api.py --base-url http://127.0.0.1:8080
```

Run the benchmark proof:

```powershell
python scripts/benchmark_pipeline.py --offline --repeat 100
```

Run the cached-record scale proof:

```powershell
python scripts/benchmark_pipeline.py --repeat 10 --json
```

Run the naive-baseline proof:

```powershell
python scripts/evaluate_bid_engine.py --offline --profiles all
```

Run the local ranker proof:

```powershell
python -m pip install -r requirements.txt
python scripts/train_bid_ranker.py --offline --profiles all
```

Run the judged Spark readiness gate:

```powershell
python scripts/benchmark_pipeline.py --repeat 1 --require-nvidia
```

The smoke test checks `/api/health`, `/api/scan`, `/api/simulate`, and `/api/approve`. The benchmark reports local records processed, runtime, records/sec, shortlist reduction, model calls avoided, owner briefs generated, NVIDIA mode, false positives skipped, similar awards grounded, market-model examples, precision@10, top-decile lift, and the top insight sentence. The baseline proof reports how many naive keyword candidates were removed by the bid engine. The ranker proof trains two local scikit-learn models: a guarded bid-fit ranker over current/historical structured features and a temporal award-history market model that trains on older awards, tests on recent awards, and reports precision@10, top-decile lift, supplier concentration, false-positive pressure, and top feature weights. Nemotron/NIM is optional for deterministic ranking reliability, but owner-ready packet drafting requires active local NIM. `--require-nvidia` intentionally fails if neither NVIDIA path is active. When available, Nemotron extracts requirements and bid briefs from shortlisted contracts; the deterministic bid engine owns `Pursue`, `Review`, `Monitor`, and `Skip`, while the market model scores and orders safe candidates.

## Future Source Expansion

V1 proves the intelligence engine on Toronto Open Data. Later versions can connect more procurement feeds into the same bid/no-bid pipeline:

- Toronto Bids Portal / SAP Ariba
- CanadaBuys
- Ontario Tenders
- TTC / MERX
- Nearby municipalities
- bids&tenders / Link2Build
