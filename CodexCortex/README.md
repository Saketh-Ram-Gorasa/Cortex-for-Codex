# CodexCortex

CodexCortex is a thin in-repo MCP adapter package that lets Codex read and write SecondCortex memory without forking or duplicating the SecondCortex backend.

It exposes a small Codex-friendly tool surface:

- `search_memory`: retrieve relevant prior memory before editing code.
- `get_decision_context`: inspect history/rationale for a file, symbol, snapshot, or decision target.
- `list_snapshots`: list recent snapshots, optionally filtered by file and time window.
- `store_decision`: persist Codex's task summary, reasoning, touched files, confidence, and parent/contradiction metadata.
- `get_mcp_readiness`: verify auth and vector-store readiness.

## Local Setup

From the repository root, create the shared Codex/SecondCortex Python environment:

```powershell
.\CodexCortex\scripts\setup_env.cmd
```

Point the adapter at the existing backend:

```powershell
$env:SECONDCORTEX_BACKEND_PATH = (Resolve-Path .\secondcortex-backend).Path
$env:SECONDCORTEX_MCP_API_KEY = "<your existing sc_mcp key>"
```

Run tests:

```powershell
.\CodexCortex\scripts\run_tests.cmd
```

## Codex Wiring

Copy the snippet from [.codex/config.toml.example](.codex/config.toml.example) into your Codex config when you want to switch Codex from the existing `secondcortex` server to this focused adapter.

The example uses the installed `codexcortex-mcp` console script from the repository `.venv`. Replace the `<repo-root>` placeholder in the config example with the absolute path to your clone. If you rebuild the environment, restart Codex before checking the MCP tool list.

Do not paste real MCP keys into the repo. Keep `SECONDCORTEX_MCP_API_KEY` in your shell/user environment or a local secret manager.

## Smoke Test

After wiring Codex to the MCP server:

1. Call `get_mcp_readiness`.
2. Call `search_memory` with a concrete task.
3. Complete a small code task.
4. Call `store_decision` with the task, reasoning, and modified files.
5. Call `search_memory` again and verify the new `codex_decision` record appears.

## Troubleshooting

- If `get_mcp_readiness` says the MCP key is invalid or revoked, rotate or re-export `SECONDCORTEX_MCP_API_KEY`. A key can be valid in your Codex config while a stale shell environment variable points at an older revoked key.
- After changing `~/.codex/config.toml`, restart Codex or open a fresh Codex session before checking the MCP tool list. Running sessions keep the tool registry they loaded at startup.
- If Windows reports `pywintypes` or Chroma/Numpy import errors, rebuild with `.\CodexCortex\scripts\setup_env.cmd` (or `.ps1` with `-ExecutionPolicy Bypass`). The repo prefers Python 3.13 because the current MCP/Chroma stack is not reliable under Python 3.14 on this machine.
- If local searches log Azure credential warnings, the adapter is still usable but SecondCortex will fall back when embedding generation is unavailable. Configure the same embedding credentials as the backend for true semantic retrieval.
