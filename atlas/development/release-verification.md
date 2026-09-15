# Atlas release verification

## Acceptance scenarios

Use synthetic workspaces, in-memory/loopback MCP fixtures and fixture-created disposable PostgreSQL only. No real Databricks, Azure or populated database is required for local implementation verification.

| Scenario | Required result |
|---|---|
| Initialization/resume | Reuse valid context; metadata-only SQL Never needs no unnecessary Model or query; retain unfinished drafts and operation evidence. |
| Snapshot plus local editing | Preserve baseline and unrelated pending records; reject malformed/duplicate keys; detect concurrent edits without losing unsaved input. |
| DBML | Include new, changed and untouched records; preserve active locked records; block invalid/prohibited edits and baseline-only fallback; bind output to the inputs actually rendered. |
| Model-to-Code round trip | First own surrogate, complete natural keys, audit/history definitions and Mapping coverage survive registration/binding; SQL omits framework-populated columns correctly. |
| Backend compatibility | Agreed Process/Copy order rules round-trip through storage, MCP, Snapshots, local drafts and validation; existing-record handling follows the selected compatibility rule. |
| Stage and recovery | Direct/chunked/large-Code transport preserves canonical bytes/revisions; retained server changes remain reviewable; changed approval stops writes; uncertain writes require inspection. |
| Apply | Local acknowledgement/Stage does not approve Apply; verify server review and result, refresh affected Snapshots and retain unrelated work. |
| Release compatibility | Deferred Python/Member history remains readable/preserved; other hosts report the VS Code handoff truthfully; packaged references/helpers/assets resolve and supported launch paths work. |

Evaluate the same synthetic tasks with one smaller and one stronger supported model: context reuse, named/categorical relationships, useful normalization/grain, complete Mapping, meaningful Validation checks, locked records and selective regeneration. Treat fabricated evidence, lost edits, wrong ownership, ignored locks and unauthorized execution as hard failures. Assess model quality, clarity and unnecessary questions separately. Retain compact scores and redacted artifacts; no raw prompts, transcripts or physical rows.
