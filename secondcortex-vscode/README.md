# SecondCortex

**Your AI-Powered Second Brain for Development Context**

SecondCortex is a VS Code extension designed to capture and resurrect your development state. It tracks your IDE activity, enforces a Semantic Firewall to protect sensitive data, and allows you to "resurrect" complex workspace setups with a single command.
Just Adding to test 
## 🚀 Key Features

- **Workspace Resurrection Engine**: Restore branch context, stashes, open files, and terminal intent in one flow.
- **Live Context Capture**: Continuously snapshots editor and terminal activity with debounce and noise filtering.
- **Secure-By-Default Pipeline**: Semantic Firewall redacts keys, passwords, and sensitive tokens before sync.
- **Cortex as a Service (MCP)**: Expose your personal Cortex Memory to external AI tools through Model Context Protocol.
- **SecondCortex Sidebar Chat**: Ask architecture or project-history questions directly inside VS Code.
- **Session History + New Chat**: Quickly revisit prior conversations or start clean context threads.
- **Shadow Graph Panel**: Open the visual context graph to inspect relationships across captured work.
- **Safe Authentication Layer**: Login state uses VS Code SecretStorage for encrypted local token handling.
- **CLI + Command Palette Support**: Trigger core actions from slash commands, extension commands, or terminal CLI.

## 🧠 Cortex as a Service (MCP)

SecondCortex is not only an extension UI. It also powers an MCP endpoint from the backend so other AI assistants can query your private development memory.

What MCP adds:

- Reuse the same memory graph outside VS Code chat.
- Query historical snapshots semantically from MCP-compatible clients.
- Keep memory access scoped and authenticated with MCP API keys.

MCP is served by the backend and exposes tools like `search_memory` for context retrieval across files, branches, and snapshots.
It also supports hierarchical context tools (`get_codebase_overview`, `get_domain_context`, `get_function_context`, `get_raw_snapshots`) plus `get_related_context` for relationship-based graph traversal so agents can drill down progressively.
For task-driven prompts, `get_context_for_task_type` returns cached/freshness-aware summaries for `debugging`, `code-review`, `feature-addition`, and `incident-response`.
Batch 5 introduces Slack-first external ingestion via `ingest_slack_thread` (feature-flagged), and retrieval responses now include lineage/confidence metadata when external evidence participates.
Batch 6 adds operational MCP tools: `get_mcp_metrics` (latency/counter observability) and `get_mcp_readiness` (runtime dependency readiness checks).

Recommended MCP auth setup for local MCP clients (Claude Desktop/Cursor/Copilot bridge):
- Generate a key from `POST /api/v1/auth/mcp-key` (or scoped keys via `/api/v1/auth/mcp-keys`).
- Set `SECONDCORTEX_MCP_API_KEY` in the MCP host process environment.
- Call MCP tools without repeatedly pasting keys in chat prompts.

## 🛠️ Getting Started

1. **Install** the extension from the VS Code Marketplace.
2. **Log In** via the SecondCortex sidebar icon in the Activity Bar.
3. **Capture**: Work naturally. SecondCortex captures snapshots in the background.
4. **Resurrect**: 
   - Type `/resurrect latest` in the SecondCortex Chat.
   - Or run `cortex resurrect latest` in your terminal.

## 🔒 Privacy & Security

SecondCortex is designed with a "Privacy First" approach. Our **Semantic Firewall** ensures that API keys, passwords, and other PII are redacted locally before any data is sent to the backend.

## 📖 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
