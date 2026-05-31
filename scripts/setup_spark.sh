#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

mkdir -p data/models/nemotron3-gguf

MODEL_PATH="data/models/nemotron3-gguf/Nemotron-3-Nano-30B-A3B-UD-Q4_K_XL.gguf"

echo
echo "Spark Python environment is ready."
if [[ -f "$MODEL_PATH" ]]; then
  ls -lh "$MODEL_PATH"
else
  echo "Model file still needed at:"
  echo "  $MODEL_PATH"
fi
echo
echo "Run the demo with:"
echo "  source .venv/bin/activate"
echo "  python app.py"
