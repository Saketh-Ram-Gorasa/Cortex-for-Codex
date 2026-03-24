$ErrorActionPreference = "Stop"

Set-Location -Path (Join-Path $PSScriptRoot "..")

if (!(Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip

if (Test-Path "wheelhouse") {
    pip install --no-index --find-links ./wheelhouse -r requirements.txt
} else {
    pip install -r requirements.txt
}

if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item .env.example .env
}

$env:CHROMA_DB_PATH = "./chroma_db"
python main.py
