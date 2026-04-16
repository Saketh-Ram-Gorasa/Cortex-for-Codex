# CodexCortex Native Setup

CodexCortex is an in-repo Python package for the `SecondCortex-for-Codex` fork. It is intentionally thin: Codex-facing tools live in `CodexCortex/`, while shared memory, auth, vector search, and backend MCP behavior stay in `secondcortex-backend/`.

## Repository Alignment

Use `Saketh-Ram-Gorasa/SecondCortex-for-Codex` as the Codex fork remote:

```powershell
git remote add codex-fork https://github.com/Saketh-Ram-Gorasa/SecondCortex-for-Codex.git
git fetch codex-fork
```

Keep feature work on `codex/*` branches and stage only the intended paths. The current local checkout may also have older `origin` and `fork` remotes for `SecondCortex-Labs`; do not push CodexCortex work there unless the team explicitly asks.

## Python Environment

The local machine has Python 3.14 and 3.13 installed. Use Python 3.13 for now because the current MCP/Chroma/Numpy stack is not reliable under Python 3.14 here.

From the repository root:

```powershell
.\CodexCortex\scripts\setup_env.cmd
```

This script rebuilds `.venv`, installs backend requirements, installs `CodexCortex` in editable mode, and exposes the `codexcortex-mcp` console script.
If you prefer calling PowerShell directly, use `.\CodexCortex\scripts\setup_env.ps1` with `-ExecutionPolicy Bypass`.

## Codex MCP Wiring

Copy `CodexCortex/.codex/config.toml.example` into your Codex config and keep the real key in the environment:

```powershell
$env:SECONDCORTEX_MCP_API_KEY = "sc_mcp_..."
```

Restart Codex after changing MCP config. Existing sessions keep the MCP tool registry they loaded at startup.

## Test Scope

Run the CodexCortex adapter tests and the backend MCP contract tests:

```powershell
.\CodexCortex\scripts\run_tests.cmd
```

For faster backend-only MCP validation:

```powershell
.\CodexCortex\scripts\run_tests.cmd -BackendMcpOnly
```

## Ownership Boundaries

- `CodexCortex/`: Codex-native adapter, tool names, Codex setup docs, adapter tests.
- `secondcortex-backend/mcp_server.py`: shared MCP tools, auth hardening, response budgets, metrics.
- `secondcortex-backend/services/vector_db.py`: storage, retrieval, dedupe, fact/failure memory collections.
- `requirements-codex.txt`: local integrated environment for teammate MCP/Codex work.
