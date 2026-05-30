# SparkTerritory AI

SparkTerritory AI is a DGX Spark-powered local market expansion agent for Toronto service businesses. The v1 demo focuses on a 2-person window washing company and turns Toronto Open Data into ranked, evidence-backed neighbourhood recommendations.

## Why It Fits The Hackathon

- **Track:** Economic Systems
- **Technical system:** raw Toronto Open Data -> local processing -> scoring engine -> Nemotron-grounded recommendations -> web app
- **NVIDIA story:** DGX Spark runs local RAPIDS/cuDF data processing and local Nemotron/NIM inference. No GPT/OpenAI API calls are required for the judged demo.

## Run Locally

```powershell
python app.py
```

Open `http://localhost:8080`.

On PowerShell, use `$env:PORT=8090` and then `python app.py` if port `8080` is already taken.

The first recommendation request downloads and caches Toronto Open Data under `data/cache/`. If downloads fail, the app falls back to a tiny embedded demo dataset and clearly reports that fallback in the UI.

## Run On DGX Spark

Install/enable RAPIDS and start a local Nemotron NIM endpoint, then run:

```bash
export NIM_BASE_URL=http://localhost:8000/v1
export NIM_MODEL=nvidia/llama-3.1-nemotron-70b-instruct
python app.py
```

Optional environment variables:

- `SPARKTERRITORY_CACHE_DIR`: dataset cache directory, default `data/cache`
- `SPARKTERRITORY_ROW_LIMIT`: optional CKAN row cap for fast dev runs, default full datasets
- `SPARKTERRITORY_REFRESH=1`: redownload cached datasets
- `SPARKTERRITORY_OFFLINE=1`: skip downloads and use the embedded smoke-test dataset
- `NIM_BASE_URL`: OpenAI-compatible local NIM URL, default `http://localhost:8000/v1`
- `NIM_MODEL`: local Nemotron model name exposed by NIM
- `NIM_API_KEY`: optional bearer token if your endpoint requires one

## Test

```powershell
python -m unittest
```
