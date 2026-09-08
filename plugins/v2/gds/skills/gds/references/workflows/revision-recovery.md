# Model Revision Recovery

Use when authoritative Model revision differs from the installed Snapshot. Metadata has no tenant-wide revision; it uses a non-stale Snapshot, Tenant Lock, and server validation. Metadata Enrichment also uses this recovery for its scope Model.

Never install over unapplied pending files: the helper rejects it. Preserve the acknowledged digest and task ID, then check `status` for a cached server draft. If one exists, stop for its explicit disposition; never clear, archive or reset it automatically. Run recovery before draft creation whenever possible.

With no cached draft:

1. If the affected area has local pending work, run `task-stash --session <session> --task <ID> --expected-digest <digest>`. It safely removes live files and machine acceptance while retaining the draft. For enrichment, also stash its Metadata task before reassessing changed scope.
2. Create/download the fresh Model Snapshot and run `snapshot-install` with exact returned ID, size and SHA-256. Never repeat/store the signed URL. Never edit a Snapshot or discard a draft to enable installation.
3. Run `task-restore --session <session> --task <ID> --expected-digest <digest>` for stashed work; it returns to `doing`. A restore/schema mismatch stops recovery with the stash retained.
4. Re-run readiness and reassess the effective graph against fresh evidence. Never merge or repair automatically. Report conflicts; make requested corrections only within authorized scope.
5. Validate. If bytes remain identical and reassessment passes, retain the user's previous acknowledgement: set `task-state --state review`, then `accept --digest <digest>` to bind it to the new Snapshot. Include `--session` and `--task` where required by `command-contract`. The old acceptance file does not survive stash.
6. If content changes, rerun the affected functional review/validation, notify the user to Refresh Workbench, and obtain acknowledgement of the new digest before acceptance.

Conflicting server-draft records require explicit resolution by canonical key. A newer local copy does not authorize overwriting them. After Apply, normal `snapshot-install` reconciles exact applied records; do not use the unapplied-work stash sequence for that case.
