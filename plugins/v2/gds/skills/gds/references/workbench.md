# GDS Workbench contract

Workbench is a static local utility for one existing session. It never calls MCP, uses the network,
executes SQL, creates/stages/validates/applies/archives server Change Sets, deploys, or writes outside the selected session.

## Authority

- Read `session.json` and one unzipped Metadata/Model Snapshot each; it never writes a Snapshot.
- Save one matching local Change Set dataset atomically.
- Update the current task only for edit→`review`, accepted valid digest→`ready`, or explicitly
  accepted failing digest→`overridden`.
- Never create sessions, manifests, tasks, plans, or server-draft state.

## UI behavior

- Navigation switches areas without reconnecting. Refresh rereads state, inventories, and pending
  files while preserving valid selection.
- Before Save, compare current file digest to its edit-start digest. Mismatch is an external-edit
  conflict; do not write. Save requires valid JSON but may save a domain-invalid draft.
- Disable Save, Validate, and Accept for stale areas. Write only datasets whose signed schema has
  `x-gds-change-set-eligible: true`; this cannot be overridden.
- Validate only on explicit click. Read the effective graph in memory; create no report file.
- Review Mapping by target then source System, with Previous, Next, and All views.

Acceptance binds the exact local Change Set digest; edits cancel it. Only domain-rule failures may
be explicitly overridden with a reason. Unreadable files, stale digests, unsafe paths, and permission
denial cannot. Workbench can never override server validation. Refresh/validation do not mutate user
data; display issues, counts, and canonical keys without silent repair.
