# Workbench

Workbench edits one local session. It never uses the network, calls MCP, runs SQL, or mutates server Change Sets. Local validation only compiles files.

- Open once at session creation; later ask the user to Refresh.
- Signed Snapshot catalogs and schemas define sheets, keys, fields, forms, and editability.
- Snapshot is read-only. **Add to Change Set** copies a complete record into the sparse draft.
- Only Change Set records are editable. **Save changes** writes immediately and rejects edit-start digest conflicts.
- Stale areas and schemas without `x-gds-change-set-eligible: true` are read-only.
- Each sheet has at most three useful multi-select filters.
- Mapping documents, generated SQL, and Validation SQL open through **Show details**, not in the ledger.
- **Validate locally** writes the shared digest-bound `reports/local-validation/<area>.json` report.
- **Generate DBML** is user-initiated. DBML generation never runs automatically after a Model edit.

The Workbench has no approval button or review ceremony. Users may edit, ask the agent to edit, or acknowledge in chat. Edits make prior reports stale. The agent reruns validation for the exact digest before reconciliation; server validation remains authoritative.
