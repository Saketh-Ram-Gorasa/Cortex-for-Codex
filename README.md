# SecondCortex

SecondCortex is an AI-powered developer memory system that captures coding context, protects sensitive data locally, and helps you resume complex work quickly.

It consists of:
- A VS Code extension for capture, chat, and workspace resurrection.
- A FastAPI backend with multi-agent orchestration.
- A Next.js frontend for graph and dashboard experiences.

## Why SecondCortex

- Preserve development context across long breaks.
- Reconstruct workspace state (branch, open files, terminal intent).
- Ask natural-language questions about prior work.
- Apply privacy-first redaction before data leaves your machine.

## Monorepo Structure

- `secondcortex-vscode/`: VS Code extension (TypeScript)
- `secondcortex-backend/`: FastAPI backend (Python)
- `secondcortex-web/`: Next.js web app (TypeScript)
- `docker-compose.yml`: local container orchestration (backend + frontend)
- `DEMO_READY.md`: demo playbook

## Core Features

- Workspace Resurrection Engine
- Live Context Capture with debounce/noise filtering
- Semantic Firewall for local redaction
- Sidebar Chat with session history and new chat
- Shadow Graph visualization panel
- Secure auth token handling via VS Code SecretStorage
- Command Palette + CLI-style workflows

## Architecture (High Level)

1. VS Code extension captures editor and terminal context.
2. Semantic Firewall redacts sensitive values locally.
3. Sanitized snapshots are sent to backend APIs.
4. Backend retrieval/planning/execution agents process context and queries.
5. Results are shown in extension chat and web graph experiences.

## Tech Stack

- Extension: TypeScript, VS Code API
- Backend: FastAPI, Pydantic, ChromaDB, multi-agent services
- Frontend: Next.js App Router, React
- Deployment: Docker, Azure App Service

## Prerequisites

- Node.js 20+
- npm 9+
- Python 3.11+
- Git
- Optional: Docker Desktop

## Environment Variables

Backend configuration is loaded from `secondcortex-backend/config.py`.

Minimum useful variables:

```env
# Choose provider
LLM_PROVIDER=github_models

# GitHub Models
GITHUB_TOKEN=your_token
GITHUB_MODELS_ENDPOINT=https://models.inference.ai.azure.com
GITHUB_MODELS_CHAT_MODEL=gpt-4o
GITHUB_MODELS_EMBEDDING_MODEL=text-embedding-3-small

# Groq (optional but recommended for fast tasks)
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.1-8b-instant
GROQ_ENDPOINT=https://api.groq.com/openai/v1

# JWT
JWT_SECRET=change_me

# Storage
CHROMA_DB_PATH=./chroma_db

# Server
HOST=0.0.0.0
PORT=8000
```

Frontend variable:

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Extension runtime settings are exposed in VS Code under `secondcortex.*` configuration.

## Quick Start (Local, No Docker)

### 1. Start backend

```bash
cd secondcortex-backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Backend runs on `http://localhost:8000` by default.

### 2. Start frontend

```bash
cd secondcortex-web
npm install
npm run dev
```

Frontend runs on `http://localhost:3001`.

### 3. Run extension in VS Code

```bash
cd secondcortex-vscode
npm install
npm run compile
```

Then open this folder in VS Code and press `F5` to launch an Extension Development Host.

## Quick Start (Docker)

From repository root:

```bash
docker compose up --build
```

Services:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

Stop:

```bash
docker compose down
```

## Important API Endpoints

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `POST /api/v1/snapshot`
- `POST /api/v1/query`
- `POST /api/v1/resurrect`
- `GET /api/v1/events`
- `GET /api/v1/snapshots/timeline`
- `GET /api/v1/chat/history`
- `GET /health`

## VS Code Extension Packaging and Publishing

From `secondcortex-vscode/`:

```bash
npm run compile
npm run vsix
```

Generated artifact example:
- `secondcortex-0.1.7.vsix`

Recommended release flow:
1. Bump version in `secondcortex-vscode/package.json`.
2. Build a new VSIX.
3. Upload VSIX from Marketplace publisher portal.
4. Verify listing update (README/icon can take a few minutes to propagate).

## Privacy and Security

- Semantic Firewall performs local redaction before sync.
- Authentication tokens are stored in VS Code SecretStorage.
- Avoid committing secrets or PATs; keep them in ignored env files or terminal session variables.

## Development Notes

- Extension activation is currently broad (`*`), so bundle/optimize before larger scale distribution.
- VSIX currently includes many dependency files; tune `.vscodeignore` and bundle to reduce package size.

## Troubleshooting

### Marketplace shows old README/icon

- Confirm you published a higher version.
- Hard refresh listing after publish.
- Wait for Marketplace CDN propagation.

### Backend starts but query fails

- Verify `GITHUB_TOKEN` and/or `GROQ_API_KEY`.
- Check backend logs for 429 or auth errors.

### Extension appears idle

- Ensure `secondcortex.captureEnabled=true`.
- Verify backend URL in extension settings.

## Additional Docs

- Extension README: `secondcortex-vscode/README.md`
- Demo guide: `DEMO_READY.md`

## License

MIT (see `secondcortex-vscode/LICENSE`).
