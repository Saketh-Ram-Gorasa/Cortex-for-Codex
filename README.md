# SecondCortex

SecondCortex is an AI-powered developer memory system that captures coding context, protects sensitive data locally, and helps you resume complex work quickly.

It consists of:
- A VS Code extension for capture, chat, and workspace resurrection.
- A FastAPI backend with multi-agent orchestration.
- A Model Context Protocol (MCP) server that exposes Cortex Memory as a service.
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
- Cortex as a Service (MCP): query private developer memory from external AI clients
- Sidebar Chat with session history and new chat
- Shadow Graph visualization panel
- Shadow Graph timeline time-travel with snapshot lookup/restore workflow
- Decision Archaeology hover (function-level historical reasoning from git + snapshot context)
- Retro Git Ingestion (commits, diffs, comments, optional PR context)
- Activity Lookup fast-path ("what am I working on?" queries from latest snapshot)
- Secure auth token handling via VS Code SecretStorage
- Command Palette + CLI-style workflows

## Architecture (High Level)

1. VS Code extension captures editor and terminal context.
2. Semantic Firewall redacts sensitive values locally.
3. Sanitized snapshots are sent to backend APIs.
4. Backend retrieval/planning/execution agents process context and queries.
5. MCP exposes the same memory layer as a tool for external AI assistants.
6. Results are shown in extension chat and web graph experiences.

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
# Task-aware provider routing (global default + optional task overrides)
LLM_PROVIDER_DEFAULT=azure_openai
# LLM_PROVIDER_RETRIEVER=azure_openai
# LLM_PROVIDER_PLANNER=azure_openai
# LLM_PROVIDER_EXECUTOR=azure_openai
# LLM_PROVIDER_SIMULATOR=azure_openai
# LLM_PROVIDER_ARCHAEOLOGY=azure_openai
# LLM_PROVIDER_EMBEDDINGS=azure_openai

# Optional task fallback providers for safe cutover/rollback
# LLM_FALLBACK_PROVIDER_RETRIEVER=groq
# LLM_FALLBACK_PROVIDER_PLANNER=groq
# LLM_FALLBACK_PROVIDER_EXECUTOR=groq
# LLM_FALLBACK_PROVIDER_SIMULATOR=groq
# LLM_FALLBACK_PROVIDER_ARCHAEOLOGY=github_models
# LLM_FALLBACK_PROVIDER_EMBEDDINGS=github_models

# Azure OpenAI v1 (primary)
AZURE_OPENAI_BASE_URL=https://<resource>.openai.azure.com/openai/v1/
AZURE_OPENAI_AUTH_MODE=managed_identity_then_key
AZURE_OPENAI_CLIENT_ID=<user-assigned-mi-client-id>
AZURE_OPENAI_API_KEY=<fallback-key>
AZURE_OPENAI_TOKEN_SCOPE=https://ai.azure.com/.default

# Per-capability deployment names
AZURE_OPENAI_DEPLOYMENT_RETRIEVER=gpt-4o-retriever
AZURE_OPENAI_DEPLOYMENT_PLANNER=gpt-4o-planner
AZURE_OPENAI_DEPLOYMENT_EXECUTOR=gpt-4o-executor
AZURE_OPENAI_DEPLOYMENT_SIMULATOR=gpt-4o-simulator
AZURE_OPENAI_DEPLOYMENT_ARCHAEOLOGY=gpt-4o-archaeology
AZURE_OPENAI_DEPLOYMENT_EMBEDDINGS=text-embedding-3-small

# GitHub Models (rollback option)
GITHUB_TOKEN=your_token
GITHUB_MODELS_ENDPOINT=https://models.inference.ai.azure.com
GITHUB_MODELS_CHAT_MODEL=gpt-4o
GITHUB_MODELS_EMBEDDING_MODEL=text-embedding-3-small

# Groq (rollback option)
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.1-8b-instant
GROQ_ENDPOINT=https://api.groq.com/openai/v1

# Provider-aware rate limits
LLM_RATE_LIMIT_DEFAULT_PER_MINUTE=60
LLM_RATE_LIMIT_AZURE_OPENAI_PER_MINUTE=120
LLM_RATE_LIMIT_GITHUB_MODELS_PER_MINUTE=60
LLM_RATE_LIMIT_GROQ_PER_MINUTE=12
LLM_RATE_LIMIT_MAX_RETRIES=2

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
- `POST /api/v1/auth/mcp-key`
- `GET /api/v1/auth/mcp-key`
- `POST /api/v1/auth/mcp-keys`
- `GET /api/v1/auth/mcp-keys`
- `DELETE /api/v1/auth/mcp-keys/{key_id}`
- `POST /api/v1/snapshot`
- `POST /api/v1/ingest/git`
- `POST /api/v1/query`
- `POST /api/v1/resurrect`
- `POST /api/v1/decision-archaeology`
- `GET /api/v1/events`
- `GET /api/v1/snapshots/timeline`
- `GET /api/v1/snapshots/{snapshot_id}`
- `GET /api/v1/chat/history`
- `GET /api/v1/chat/sessions`
- `POST /api/v1/chat/sessions`
- `DELETE /api/v1/chat/history`
- `SSE /mcp` (MCP endpoint mount)
- `GET /health`

## MCP and Cortex as a Service

SecondCortex includes an MCP server (`secondcortex-backend/mcp_server.py`) mounted by the backend at `/mcp`.

What this enables:
- External AI clients can use your historical IDE context as a live tool.
- Cortex Memory is queryable with semantic search across snapshots.
- Access is user-scoped through MCP API key authentication.

Current MCP tool:
- `search_memory(query, api_key, top_k=5)`: returns relevant snapshots with summary, branch, file path, entities, and code context excerpts.

Hierarchical MCP tools:
- `get_codebase_overview(api_key?, max_items=8)`: ultra-compressed recent codebase orientation.
- `get_domain_context(domain, api_key?, top_k?)`: domain-level decisions and active streams.
- `get_function_context(file, function, api_key?, top_k?)`: function/file decision history and code context.
- `get_raw_snapshots(query, max_tokens=1000, api_key?, top_k?)`: budgeted raw snapshot retrieval for deeper agent control.
- `get_related_context(anchor, relationship_types?, depth=1, max_tokens=1000, api_key?, top_k?)`: graph-style related context traversal (`co-changed`, `co-debugged`, `causally-linked`) with bounded depth and budget.
- `get_context_for_task_type(domain, task_type, project_id?, max_tokens?, api_key?, top_k?)`: task-scoped summaries (`debugging`, `code-review`, `feature-addition`, `incident-response`) with freshness metadata and cache-aware fallback synthesis.
- `ingest_slack_thread(channel, thread_ts, messages, domain, project_id?, api_key?)`: feature-flagged Slack ingestion path using normalized provenance metadata and reconciliation before persistence.
- `get_mcp_metrics(api_key?)`: runtime observability summary (request counters, auth/rate-limit rejections, cache stats, graph fan-out, per-tool latency p50/p95/p99).
- `get_mcp_readiness(api_key?)`: readiness status for auth principal resolution, vector storage availability, and connector flags.

Lineage/confidence behavior:
- MCP retrieval output now includes source lineage fields (`source_type`, `source_uri`) and `confidence_score` when available.
- External-source context is merged into the same semantic retrieval surface as code snapshots for cross-source reasoning.

MCP client auth options:
- Legacy per-call key argument: pass `api_key` directly to `search_memory`.
- Recommended client integration: set `SECONDCORTEX_MCP_API_KEY` in the MCP host process (Claude Desktop/Cursor/Copilot bridge) so keys are not pasted into every chat.

This is the foundation for using SecondCortex not just as an extension, but as a developer memory service across tooling.

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


## Additional Docs

- Extension README: `secondcortex-vscode/README.md`
- Demo guide: `DEMO_READY.md`
- Azure OpenAI cutover runbook: `secondcortex-backend/AZURE_OPENAI_CUTOVER_RUNBOOK.md`

## License

MIT (see `secondcortex-vscode/LICENSE`).
