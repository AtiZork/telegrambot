#!/usr/bin/env bash
# Run the Divergence Alert microservice (after venv and DB are set up).
set -e
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
