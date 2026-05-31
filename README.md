# SoBid

SoBid is a local procurement intelligence app for small businesses pursuing City of Toronto work. It scans Toronto Open Data solicitations, compares current listings against historical awards, filters poor fits, ranks realistic opportunities for a selected business profile, and prepares bid notes only after owner approval.

The demo is built for the **NVIDIA DGX Spark Hackathon, Economic Systems track**. It is not a chatbot: the core bid/no-bid decision comes from deterministic business gates, historical award evidence, local scikit-learn models, pricing/revenue simulation, and portfolio capacity checks. Local Nemotron/NIM is used selectively for structured owner-facing bid briefs after the system has already shortlisted opportunities.

## Current Demo

The app ships with three data-backed 2026 Toronto procurement lanes:

| Profile ID | UI Label | 2026 matching listings | Strong matches |
| --- | --- | ---: | ---: |
| `road_civil_infrastructure` | Road/Civil Infrastructure Contractor | 45 | 29 |
| `parks_landscape` | Parks/Landscape Contractor | 42 | 29 |
| `professional_engineering_design` | Professional Engineering/Design Firm | 23 | 14 |

The UI opens on the **Inbox** view, auto-runs the first profile-specific scan, and lets the user:

- switch business type;
- choose a demo month from January through May 2026;
- inspect `Pursue`, `Review`, `Monitor`, and `Skip` recommendations;
- open the **Proof** view for source status, runtime, records/sec, model calls avoided, NVIDIA path, pricing stats, validation, and skipped examples;
- prepare bid notes with the **Prepare Bid Notes** button.

Owner-ready packets are gated: if a listing was not enriched by local Nemotron/NIM, approval returns a blocked packet with instructions to start local Nemotron, rerun the scan, and approve again. Deterministic fallback still ranks opportunities and shows basic structured requirements, but it does not generate the final owner-ready packet or simulated receipt.

## Quick Start: Local Development

In this workspace, run local smoke tests and UI checks without managed Nemotron:

```powershell
python -m pip install -r requirements.txt
python app.py --without-nemotron
```

Open the URL printed by the server, usually:

```text
http://127.0.0.1:8080
```

For a stable no-internet local run against cached Toronto Open Data:

```powershell
$env:CONTRACT_RADAR_CACHE_DIR="data/cache"
$env:CONTRACT_RADAR_OFFLINE="1"
python app.py --without-nemotron
```

Do not use the removed `--with-nemotron` flag.

## DGX Spark Demo Run

On DGX Spark, the intended demo command is:

```bash
python app.py
```

The default command starts managed local Nemotron before launching the web app. On first run it:

- builds `llama.cpp` with CUDA support;
- downloads `unsloth/Nemotron-3-Nano-30B-A3B-GGUF`;
- serves `Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL.gguf` through an OpenAI-compatible endpoint;
- sets `NIM_BASE_URL` to `http://127.0.0.1:30000/v1`;
- starts SoBid at `http://127.0.0.1:8080`.

Runtime build files live under `~/.contract-radar/nemotron`. Model files default to `data/models/nemotron3-gguf`, and model-server logs are written to `~/.contract-radar/nemotron/llama-server.log`.

Set up the Spark Python environment with:

```bash
bash scripts/setup_spark.sh
source .venv/bin/activate
python app.py
```

If the model is already downloaded manually, place it here:

```text
data/models/nemotron3-gguf/Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL.gguf
```

To build/download the managed Nemotron runtime before demo time:

```bash
python app.py --nemotron-setup-only
```

To skip the DGX Spark cuOpt bootstrap check:

```bash
python app.py --skip-cuopt-install
```

## API

The app is a small Python HTTP server with static frontend assets and JSON/NDJSON API routes.

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | GET | Frontend app |
| `/api/health` | GET | Runtime status, supported profiles, NVIDIA/NIM/ranker state |
| `/api/scan-stream` | POST | Streaming NDJSON scan progress plus final result |
| `/api/scan` | POST | Non-streaming scan result |
| `/api/simulate` | POST | Scan plus month timeline simulation |
| `/api/approve` | POST | Approval-gated bid packet or Nemotron-required block |

Useful payload fields:

- `profile_id`: one of the three supported profile IDs.
- `business_profile`: optional profile override object.
- `priority_mode`: `best_win_chance`, `best_fit`, or `highest_value`.
- `as_of`: ISO date used for demo month/deadline logic.
- `refresh`: set `true` to refresh Toronto Open Data.
- `days`: simulation window for `/api/simulate`.
- `approved` and `opportunity_id`: used by `/api/approve`.

## Verification Commands

With the app running:

```powershell
python scripts/smoke_api.py --base-url http://127.0.0.1:8080
```

The smoke test validates `/api/health`, `/api/scan`, `/api/simulate`, and `/api/approve`, and rejects bundled dev fixtures unless sample data was explicitly enabled.

Run the unit tests:

```powershell
python -m unittest
```

Run the local pipeline benchmark:

```powershell
python scripts/benchmark_pipeline.py --offline --repeat 100
```

Run the DGX/NVIDIA readiness gate:

```powershell
python scripts/benchmark_pipeline.py --repeat 1 --require-nvidia
```

`--require-nvidia` intentionally fails if the last scan used only fallback paths. Omit it for deterministic local demos.

Run the naive-keyword baseline comparison:

```powershell
python scripts/evaluate_bid_engine.py --offline --profiles all
```

Train and evaluate the local ranker/value proof:

```powershell
python scripts/train_bid_ranker.py --offline --profiles all
```

Optionally write a JSON model artifact:

```powershell
python scripts/train_bid_ranker.py --offline --profiles all --output data/output/bid_ranker_model.json
```

## Pipeline

Each scan runs this local pipeline:

1. Load Toronto Bids solicitations and awarded contracts from cache or live CKAN.
2. Filter records locally, using RAPIDS/cuDF when available and Python fallback otherwise.
3. Apply deterministic profile fit gates for category, deadline, scope, capacity, missing capabilities, and bid effort.
4. Attach historical-award RAG evidence for realistic analogs.
5. Train/apply local scikit-learn award-history market and value models.
6. Estimate bid range, win probability, expected profit, and bid prep cost.
7. Simulate revenue outcomes.
8. Optimize the bid portfolio with cuOpt MILP when available, otherwise deterministic greedy fallback.
9. Enrich only shortlisted candidates with local Nemotron/NIM structured requirements and owner brief fields.
10. Return the owner inbox plus the proof metrics judges can inspect.

The model explains and drafts from computed evidence; it does not replace the local bid-fitness engine.

## Data and Caching

Core V1 data sources:

- [Toronto Bids Solicitations](https://open.toronto.ca/dataset/tobids-all-open-solicitations/) for current/open City opportunities.
- [Toronto Bids Awarded Contracts](https://open.toronto.ca/dataset/tobids-awarded-contracts/) for historical award comparison.

Cache behavior:

- The app reads `data/cache/toronto_bids_solicitations.json` and `data/cache/toronto_bids_awarded_contracts.json` before live fetches unless `refresh=true`.
- Successful live fetches write fresh cache files back to `data/cache`.
- `CONTRACT_RADAR_OFFLINE=1` forces cached Toronto Open Data only.
- If live/cache data is incomplete, the app fails loudly rather than showing fake demo postings.
- `CONTRACT_RADAR_ALLOW_SAMPLE_DATA=1` unlocks bundled fixtures only for local tests. Do not use it for judged demos.

During a normal app run, scans also use in-process caches:

- shared data bundles and historical retrievers across same-lane variants;
- listing-level Nemotron extraction cache keyed by the solicitation;
- exact scan-result cache for identical profile/date/priority runs unless `refresh=true`.

## Precomputed Scan Replay

To generate replayable scan JSON:

```bash
python scripts/precompute_scan_cache.py --offline
```

The precompute script does not start managed Nemotron by itself; it uses the configured `NIM_BASE_URL`. On Spark, make sure the local Nemotron endpoint is already reachable and omit `--without-nemotron` so replay files can include local Nemotron briefs. For local deterministic replay generation:

```powershell
python scripts/precompute_scan_cache.py --offline --without-nemotron
```

Replay generated scans:

```bash
export CONTRACT_RADAR_OFFLINE=1
export CONTRACT_RADAR_USE_PRECOMPUTED_SCAN=1
python app.py --without-nemotron
```

Precomputed scans live under `data/precomputed/scans`. Leave `CONTRACT_RADAR_USE_PRECOMPUTED_SCAN` unset when you want to prove the full live pipeline.

## NVIDIA Story

SoBid uses DGX Spark as the local AI/data workstation:

- business profile, capacity, procurement strategy, and scan results stay local;
- RAPIDS/cuDF accelerates raw-record filtering when installed;
- cuOpt selects an owner-capacity-aware bid portfolio when its Python MILP API is available;
- Nemotron/NIM extracts structured requirements and owner-ready bid brief text only for shortlisted opportunities;
- metrics expose active NVIDIA tools, records/sec, shortlist reduction, model calls avoided, cuOpt mode, Nemotron mode, and market-model proof.

If NVIDIA components are unavailable, the deterministic local path remains usable and the UI names the fallback state explicitly.

## Environment Variables

Common local/demo variables:

```powershell
$env:HOST="127.0.0.1"
$env:PORT="8080"
$env:CONTRACT_RADAR_CACHE_DIR="data/cache"
$env:CONTRACT_RADAR_OFFLINE="0"
$env:CONTRACT_RADAR_REFRESH="0"
$env:CONTRACT_RADAR_ROW_LIMIT="10000"
$env:CONTRACT_RADAR_ALLOW_SAMPLE_DATA="0"
$env:CONTRACT_RADAR_DISABLE_NEMOTRON="0"
$env:CONTRACT_RADAR_USE_PRECOMPUTED_SCAN="0"
$env:CONTRACT_RADAR_PRECOMPUTED_DIR="data/precomputed"
$env:CONTRACT_RADAR_DISABLE_SCAN_RESULT_CACHE="0"
```

Nemotron/NIM variables:

```powershell
$env:NIM_BASE_URL="http://localhost:8000/v1"
$env:NIM_MODEL="nvidia/llama-3.1-nemotron-70b-instruct"
$env:NIM_API_KEY=""
$env:NIM_PREFLIGHT_TIMEOUT_SECONDS="2"
$env:NIM_TIMEOUT_SECONDS="45"
$env:NIM_PREFLIGHT_CACHE_SECONDS="30"
$env:CONTRACT_RADAR_NIM_SHORTLIST_LIMIT="3"
```

Managed DGX Spark Nemotron variables:

```powershell
$env:CONTRACT_RADAR_NEMOTRON_PORT="30000"
$env:CONTRACT_RADAR_NEMOTRON_BASE_URL="http://127.0.0.1:30000/v1"
$env:CONTRACT_RADAR_NEMOTRON_HOME="$HOME/.contract-radar/nemotron"
$env:CONTRACT_RADAR_NEMOTRON_MODEL_REPO="unsloth/Nemotron-3-Nano-30B-A3B-GGUF"
$env:CONTRACT_RADAR_NEMOTRON_MODEL_DIR="data/models/nemotron3-gguf"
$env:CONTRACT_RADAR_NEMOTRON_MODEL_FILE="Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL.gguf"
$env:CONTRACT_RADAR_NEMOTRON_MODEL_NAME="nemotron"
$env:CONTRACT_RADAR_NEMOTRON_GPU_LAYERS="99"
$env:CONTRACT_RADAR_NEMOTRON_CTX_SIZE="8192"
$env:CONTRACT_RADAR_NEMOTRON_THREADS="8"
$env:CONTRACT_RADAR_NEMOTRON_READY_TIMEOUT_SECONDS="900"
```

cuOpt variables:

```powershell
$env:CONTRACT_RADAR_AUTO_INSTALL_CUOPT="1"
$env:CONTRACT_RADAR_CUDA_MAJOR="13"
$env:CONTRACT_RADAR_CUOPT_PACKAGE="cuopt-cu13"
$env:CONTRACT_RADAR_CUOPT_VERSION="26.4.*"
```

`requirements.txt` uses NVIDIA CUDA 13 RAPIDS/cuDF and cuOpt packages on Linux. If the Spark image is CUDA 12, swap `cudf-cu13`/`cuopt-cu13` for the matching CUDA 12 package names before installing.

## Repository Layout

```text
app.py                         HTTP server and CLI flags
static/                        SoBid frontend
contract_radar/                procurement engine, models, data, ranking, NIM, portfolio logic
scripts/smoke_api.py           running-app API smoke test
scripts/benchmark_pipeline.py  performance and NVIDIA readiness proof
scripts/evaluate_bid_engine.py naive keyword baseline comparison
scripts/train_bid_ranker.py    local ranker/value-model evaluation
scripts/precompute_scan_cache.py replay JSON generation
scripts/setup_spark.sh         DGX Spark Python environment setup
tests/                         unit tests
```

Ignored/generated paths include `.venv`, `data/cache`, `data/output`, GGUF model files, Python caches, and local app-server PID files.

## Later Source Expansion

V1 proves the local intelligence engine on Toronto Open Data. Future source connectors can feed the same bid/no-bid pipeline:

- Toronto Bids Portal / SAP Ariba packages beyond the open-data export;
- CanadaBuys;
- Ontario Tenders Portal;
- TTC / MERX;
- nearby municipalities in the GTA;
- bids&tenders / Link2Build for construction-heavy Ontario opportunities.
