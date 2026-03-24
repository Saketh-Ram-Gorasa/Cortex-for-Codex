#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip

if [ -d "wheelhouse" ]; then
  pip install --no-index --find-links ./wheelhouse -r requirements.txt
else
  pip install -r requirements.txt
fi

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp .env.example .env
fi

export CHROMA_DB_PATH="./chroma_db"
python main.py
