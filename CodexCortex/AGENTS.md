# CodexCortex Agent Rules

You are working in the CodexCortex adapter package inside the SecondCortex-for-Codex monorepo. Keep this package small and focused: it should connect Codex to an existing SecondCortex backend, not copy the backend.

Before substantial edits, call `search_memory` with the task you are about to perform.

Before changing existing behavior, call `get_decision_context` for the relevant file, function, symbol, or decision target.

After completing a task, call `store_decision` with:

- the original task prompt,
- the implementation reasoning,
- the files modified,
- confidence,
- useful tags,
- `parent_snapshot_id` when extending a prior decision,
- `contradictions` when overriding prior memory.

Never commit real MCP API keys. Use `SECONDCORTEX_MCP_API_KEY` from the environment.

Keep backend MCP changes modular and coordinated with teammates: adapter-only changes belong under `CodexCortex/`; shared MCP storage/search changes belong under `secondcortex-backend/`.
