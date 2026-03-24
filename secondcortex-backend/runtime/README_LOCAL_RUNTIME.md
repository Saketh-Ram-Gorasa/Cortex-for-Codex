# SecondCortex Local Runtime

This folder is bundled into the published `secondcortex-local-runtime-<version>.zip` package.

## Quick start (Windows)

1. Extract the ZIP.
2. Open PowerShell in the extracted folder.
3. Run:
   - `./runtime/start-local-runtime.ps1`

## Quick start (macOS/Linux)

1. Extract the ZIP.
2. Open terminal in the extracted folder.
3. Run:
   - `chmod +x runtime/start-local-runtime.sh`
   - `./runtime/start-local-runtime.sh`

## Notes

- The script creates `.venv` on first run and installs dependencies.
- Runtime uses `CHROMA_DB_PATH=./chroma_db` by default.
- Backend health endpoint: `http://127.0.0.1:8000/health`
- If `wheelhouse/` is present (full ZIP), dependencies install fully offline.

## Build the stable full ZIP

From `secondcortex-backend/`:

- Full offline ZIP (recommended for website download):
   - `python create_local_runtime_zip.py --include-wheelhouse`
- Lightweight ZIP (source only):
   - `python create_local_runtime_zip.py --no-include-wheelhouse`

## One-click CI build (GitHub Actions)

- Open Actions → `Build Local Runtime ZIP`.
- Click `Run workflow`.
- Optional: set `upload_to_release=true` and provide `release_tag` (for example `v0.1.0`) to attach ZIP to an existing GitHub Release.
- Download artifact `secondcortex-local-runtime-full` from the workflow run.
