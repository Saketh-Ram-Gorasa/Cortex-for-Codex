# HAX Release Checklist

- [ ] Confidence and limitations text shown in VS Code sidebar answers.
- [ ] Recovery actions shown for backend/network/retrieval failures.
- [ ] Source provenance shown for retrieval-grounded answers.
- [ ] Document ingestion provenance shown (`source_type=document`, source URI, confidence).
- [ ] Project scope visibility present in chat response context.
- [ ] Incident packet exposes contradiction visibility with evidence-linked context.
- [ ] Incident packet exposes disproof checks for every ranked hypothesis.
- [ ] Incident packet includes confidence decomposition and recovery option risk comparison.
- [ ] Negative tests for missing context and auth failures are passing.
- [ ] Document ingestion feature flags validated (`MCP_EXTERNAL_INGESTION_ENABLED`, `MCP_EXTERNAL_DOCUMENT_ENABLED`).