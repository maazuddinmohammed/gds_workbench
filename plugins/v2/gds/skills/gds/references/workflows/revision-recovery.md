# Revision Recovery

If the authoritative revision differs from the Snapshot revision used for the reviewed digest:

1. Stop before reconciliation or Stage.
2. Ask the user to download the fresh complete Snapshot from the MCP tool result and replace the affected Snapshot area. Never repeat its temporary signed URL in chat.
3. Re-run readiness and reassess every affected local record against it.
4. Never merge or repair automatically.
5. If the exact local bytes remain unchanged, keep the prior positive acknowledgement.
6. If any content changes, rerun local validation, notify the user to Refresh Workbench, and wait for another acknowledgement.

Conflicting server-draft records are resolved explicitly by canonical key. Never overwrite them because the local copy is newer.
