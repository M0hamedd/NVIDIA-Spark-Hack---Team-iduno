# Live Contract Radar

Live Contract Radar is a Toronto Open Data procurement agent for small businesses. It monitors current City of Toronto contract opportunities, filters out poor fits, compares realistic matches against historical awards, and prepares an approval-gated bid packet for the owner.

The V1 demo focuses on three data-backed 2026 YTD Toronto procurement lanes that the user can switch between live:

- **Road/Civil Infrastructure Contractor:** 45 multi-label solicitation hits; 29 exclusive best-fit hits.
- **Parks/Landscape Contractor:** 42 multi-label solicitation hits; 29 exclusive best-fit hits.
- **Professional Engineering/Design Firm:** 23 multi-label solicitation hits; 14 exclusive best-fit hits.

The goal is to show how a local contractor, vendor, or professional firm without a procurement team can still discover and act on realistic public revenue opportunities in the lanes where Toronto is repeatedly buying.

This is not a chatbot. It is a local bid intelligence engine: deterministic filtering, historical award comparison, scikit-learn award-history market scoring, a visual evidence pipeline, and Nemotron/NIM structured extraction for owner-ready bid briefs when a local model endpoint is available.

## Economic Systems Judging Fit

- **Insight Quality:** Small businesses often miss public contracts because of discovery friction, procurement language, deadline pressure, and capacity mismatch, not only because they lack the ability to do the work.
- **Usability:** The owner gets plain procurement decisions: `Pursue`, `Review`, `Monitor`, or `Skip`.
- **Creativity:** The system combines live/daily solicitations, historical awarded contracts, local award-history ML, business capacity, local structured requirement extraction, and an approval workflow.
- **Performance:** The pipeline scans procurement records locally first, trains/applies the award-history ranker without Nemotron, uses RAPIDS/cuDF when available for raw-record filtering, fast-fails unavailable NIM endpoints, rejects obvious bad fits quickly, and uses Nemotron/NIM only on shortlisted candidates.

## V1 Demo Flow

1. Start with the default **Road/Civil Infrastructure Contractor** profile.
2. Switch between the three data-backed demo lanes to show that matching behavior changes by business type.
3. Run a live scan of Toronto procurement data.
4. Review rejected opportunities to prove the system is filtering, not listing.
5. Open a top `Pursue` or `Review` opportunity.
6. Compare the opportunity to similar historical awards and capacity warnings.
7. Open the judge evidence view for records scanned, rejection counts, runtime, active NVIDIA path, model calls avoided, and backtest insight.
8. Approve the opportunity and generate a simulated bid packet.

## Spark/Local Fast Path

Install the local ranker dependencies before running the app or training proof:

```powershell
python -m pip install -r requirements.txt
```

`requirements.txt` is already included in the repo. Do not commit the installed `.venv` or Python packages; build them on the Spark so the wheels match Linux/CUDA/Python. After pulling the repo on DGX Spark/Linux, set up the Python environment with:

```bash
bash scripts/setup_spark.sh
```

```powershell
python app.py --without-nemotron
```

Then open the local URL printed by the server, usually:

```text
http://127.0.0.1:8080
```

To run the DGX Spark demo with local Nemotron, use the default app command:

```bash
python3 app.py
```

The first run builds `llama.cpp`, downloads the Q4 Nemotron GGUF model, starts an OpenAI-compatible model server on `http://127.0.0.1:30000/v1`, then launches the app on `http://127.0.0.1:8080`. Later runs reuse the downloaded model and built server. Runtime build files live outside the repo in `~/.contract-radar/nemotron`, model files default to `data/models/nemotron3-gguf`, and model-server logs are written to `~/.contract-radar/nemotron/llama-server.log`.

If you manually download the model, place it here before starting the app:

```bash
data/models/nemotron3-gguf/Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL.gguf
```

If you want to do the slow setup ahead of the demo:

```bash
python3 app.py --nemotron-setup-only
```

For the fastest deterministic DGX Spark/local smoke test, use the cached Toronto Open Data path:

```powershell
$env:CONTRACT_RADAR_CACHE_DIR="data/cache"
$env:CONTRACT_RADAR_OFFLINE="1"
python app.py --without-nemotron
```

In a second terminal:

```powershell
python scripts/smoke_api.py --base-url http://127.0.0.1:8080
```

The smoke command validates `/api/health`, `/api/scan`, `/api/simulate`, and `/api/approve` against the running app. Use `--help` to see optional flags, including `--refresh` for a live Toronto Open Data refresh when internet access is available. Demo scans refuse bundled sample solicitations unless `CONTRACT_RADAR_ALLOW_SAMPLE_DATA=1` is explicitly set for local tests.

To show the deterministic judging/performance proof without opening the UI:

```powershell
python scripts/benchmark_pipeline.py --offline --repeat 100
```

To allow live refresh/cache behavior at larger scale, omit `--offline`:

```powershell
python scripts/benchmark_pipeline.py --repeat 10 --json
```

For judged Spark readiness, require an active NVIDIA path:

```powershell
python scripts/benchmark_pipeline.py --repeat 1 --require-nvidia
```

The benchmark reports local records processed, runtime, records/sec, shortlist reduction, model calls avoided, active NVIDIA path, false positives skipped, similar awards grounded, and the top insight scorecard sentence. `--require-nvidia` intentionally fails in fallback mode so the team does not accidentally present fallback as NVIDIA acceleration.

To prove the bid engine beats naive keyword matching across all three personas:

```powershell
python scripts/evaluate_bid_engine.py --offline --profiles all
```

That evaluation reports naive keyword candidates, bid-engine actionable items, false positives skipped, shortlist reduction, top opportunity, and estimated bid-review hours saved.

To train and evaluate the local bid-fit and market rankers:

```powershell
python -m pip install -r requirements.txt
python scripts/train_bid_ranker.py --offline --profiles all
```

The scan now treats the award-history ranker as a required local capability, not a silent fallback. It trains and applies a local scikit-learn award-history market model during scan, while the training script also reports the evaluation proof. The ranker has two roles:

- A guarded bid-fit ranker over current evaluated opportunities and historical fit examples.
- A temporal award-history market model that trains on older awards, tests on recent awards, and uses supplier repeat history, market concentration, value accessibility, category/type, division, and profile-term fit signals.

That gives the demo a concrete procurement-intelligence layer: not just "does this text match our profile?", but "have similar contracts historically been accessible, who tends to win them, and does the recent market look worth chasing?" Deterministic hard blockers still own `Pursue`, `Review`, `Monitor`, and `Skip`; the ranker scores and orders safe candidates.

Cache behavior:

- By default, the app reads Toronto Open Data cache files from `data/cache` before trying live fetches.
- Successful live fetches write fresh cache files back to `data/cache`.
- If live/cache data is incomplete, the app fails loudly rather than showing fake postings.
- Set `CONTRACT_RADAR_OFFLINE=1` to use cached Toronto Open Data without a live fetch for a stable no-internet demo.
- `CONTRACT_RADAR_ALLOW_SAMPLE_DATA=1` unlocks bundled sample fixtures only for local tests; do not use it for demos.

## Environment Variables

These variables are optional for local development and demo reliability.

```powershell
$env:CONTRACT_RADAR_CACHE_DIR="data/cache"
$env:CONTRACT_RADAR_OFFLINE="0"
$env:CONTRACT_RADAR_ALLOW_SAMPLE_DATA="0"
$env:CONTRACT_RADAR_DISABLE_NEMOTRON="0"
$env:NIM_BASE_URL="http://localhost:8000/v1"
$env:NIM_MODEL="nvidia/llama-3.1-nemotron-70b-instruct"
$env:NIM_API_KEY=""
$env:NIM_PREFLIGHT_TIMEOUT_SECONDS="0.2"
$env:CONTRACT_RADAR_NEMOTRON_PORT="30000"
$env:CONTRACT_RADAR_NEMOTRON_HOME="$HOME/.contract-radar/nemotron"
$env:CONTRACT_RADAR_NEMOTRON_MODEL_DIR="data/models/nemotron3-gguf"
$env:CONTRACT_RADAR_NEMOTRON_MODEL_FILE="Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL.gguf"
```

- `CONTRACT_RADAR_CACHE_DIR`: directory for cached Toronto Open Data responses.
- `CONTRACT_RADAR_OFFLINE`: set to `1` to use cached Toronto Open Data without a live fetch for a stable demo.
- `CONTRACT_RADAR_ALLOW_SAMPLE_DATA`: set to `1` only for local tests that intentionally exercise bundled fixtures. Keep unset or `0` for demos.
- `CONTRACT_RADAR_DISABLE_NEMOTRON`: set to `1` when running local deterministic tests; `python app.py --without-nemotron` sets this automatically.
- `NIM_BASE_URL`: local NVIDIA NIM/OpenAI-compatible endpoint used for structured requirement extraction on shortlisted contracts.
- `NIM_MODEL`: local Nemotron model identifier served by NIM.
- `NIM_API_KEY`: optional key if the local NIM endpoint requires one.
- `NIM_PREFLIGHT_TIMEOUT_SECONDS`: fast preflight timeout before falling back to deterministic extraction.
- `CONTRACT_RADAR_NEMOTRON_PORT`: port used by the default managed Nemotron startup in `python3 app.py`.
- `CONTRACT_RADAR_NEMOTRON_HOME`: local directory for the managed llama.cpp build, Hugging Face CLI venv, and server log.
- `CONTRACT_RADAR_NEMOTRON_MODEL_DIR`: local directory for manually downloaded or managed GGUF model files.
- `CONTRACT_RADAR_NEMOTRON_MODEL_FILE`: GGUF model filename. Defaults to the smaller Q4 Nemotron file for demo speed.

NIM/Nemotron is no longer just a nice-to-have in the owner workflow. The app can still rank opportunities deterministically when local NIM is unavailable, but owner-ready packet drafting is blocked until Nemotron generates a validated bid brief. When `NIM_BASE_URL` is reachable, the app asks a local Nemotron model for structured fields, blockers, required documents, clarification questions, next steps, and grounded buyer-email wording for already-shortlisted opportunities. Nemotron does **not** make the final `Pursue`, `Review`, `Monitor`, or `Skip` decision; validated blockers can downgrade a `Pursue` recommendation to `Review` through the bid-fitness policy.

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
- The three supported profiles map to road/civil infrastructure, parks/landscape, and professional engineering/design lanes.
- Profile switching changes ranking behavior while keeping the same endpoints and decision labels.
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
