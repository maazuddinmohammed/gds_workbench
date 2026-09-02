# Workbench

Workbench is a static local viewer/editor for one existing session. It never uses the network, calls MCP, executes SQL, or creates, stages, validates, applies, or archives server Change Sets.

- Open it once when the session is created. Later ask the user to Refresh.
- It discovers datasets, fields, canonical keys, editability, and forms from signed Snapshot catalogs and JSON Schemas.
- It reads Snapshots without modifying them and saves only complete local Change Set arrays.
- A save compares the edit-start digest and refuses external-edit conflicts.
- Stale areas and datasets without `x-gds-change-set-eligible: true` are read-only.
- Table and JSON text stay compact for dense review.

The Workbench has no approval button or review ceremony. The user may edit locally, ask the agent to edit, or acknowledge in chat. The agent always reruns internal local validation against the exact digest before reconciliation. Server validation remains authoritative.
