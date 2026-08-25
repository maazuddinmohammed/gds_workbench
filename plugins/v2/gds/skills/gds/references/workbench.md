# GDS Workbench contract

Workbench is a static, local utility for one existing session directory. It never calls MCP, uses network access, executes SQL, creates server Change Sets, stages, validates on the server, applies, archives, deploys, or writes outside the selected session.

## Filesystem authority

- Read `session.json`, one unzipped Metadata Snapshot, and one unzipped Model Snapshot.
- Treat every Snapshot as immutable; never writes a Snapshot.
- Write only one matching local Change Set dataset per Save, atomically.
- It may update the current task only for edit → `review`, accepted valid digest → `ready`, or explicitly accepted failing digest → `overridden`.
- It cannot create sessions, manifests, tasks, plans, or server-draft state.

## UI behavior

- Top navigation switches Metadata and Model without reconnecting.
- Refresh rereads session state, Snapshot manifest/catalog/member inventory, and local pending files while preserving the current area/dataset when still available.
- Before Save, compare the file’s current digest with the digest read at edit start. On mismatch show an external-edit conflict and do not write.
- Save requires syntactically valid JSON but may save a domain-invalid draft.
- Save, Validate, and Accept are disabled for a stale area. A dataset is writable only when its signed schema explicitly sets `x-gds-change-set-eligible: true`; this gate cannot be overridden.
- Validate is an explicit button; never validate on each keystroke.
- Validation reads the effective Snapshot-plus-pending graph in memory and creates no report file.
- Review groups Mapping by target, then source System, with Previous, Next, and All views.

Acceptance is bound to the exact local Change Set digest. Any edit cancels prior acceptance. Failed local rules may be overridden only through an explicit action and reason. Operational failures such as unreadable files, stale digests, unsafe paths, or permission denial cannot be overridden. Workbench can never override server validation.

Refresh and validation do not mutate user data. Display issues, counts, and affected canonical keys; do not silently repair records.
