---
name: manage-gds-metadata
description: "Inspect or change GDS Tenant metadata with governed MCP tools and local helpers. Use when the user asks to read specific Tenant metadata, build or prepare a local Metadata Change Set, obtain or search a Metadata Snapshot, manage a Tenant Lock, or create, stage, validate, apply, or archive a server Metadata Change Set; do not use for general GDS explanations or merely opening the local table Workbench."
---

# Manage GDS metadata

Use only governed `gds-workbench` tools. Never use direct SQL except the
read/temporary-object-only `execute_databricks_sql` tool. Never expose foundational
CRUD, credentials, connection values, raw rows, or raw tool output.

## Choose the smallest path

Infer intent from the user's verbs and stop at the least-committed boundary:

- **Bounded read:** use the smallest Tenant, Object, Copy Group, or Process Group read
  tool. Do not create a Snapshot, lock, or Change Set.
- **Broad inspection:** obtain or reuse a Metadata Snapshot, inspect only relevant
  catalog entries/rows, answer, and stop. Reads need no lock.
- **Local draft:** copy or author only affected records in `GDS/change-set`. Reuse an
  already validated Snapshot when available. Do not lock, create a server draft,
  Stage, Validate, or Apply.
- **Server change:** inspect an existing draft with `get_metadata_change_set` and stop.
  Enter the governed write window only for explicit create, resume, local-to-server
  handoff, Stage, Validate, or Apply intent. Read-only inspection and archive-only work
  do not require a lock.

Do not ask whether the user wants to read or change when their request is clear.
Never advance beyond the requested boundary. Ask only for a missing value that changes
the selected records or boundary.

## Load context progressively

- For Tenant reads use `list_tenants` or `get_tenant_details`; for physical metadata
  use `list_objects`, `get_objects`, or `get_object_lineage`; for ingestion control use
  `list_copy_groups`, `get_copy_group`, `list_process_groups`, or `get_process_group`.
- For an unfamiliar MCP call, read [tools](references/tools.md) only around that call.
- For broad inspection, call `get_metadata_snapshot`, read
  [snapshot](references/snapshot.md), then
  [catalog navigation](references/catalog-navigation.md). Never load the whole archive.
- For a local draft, read [datasets](references/datasets.md) for the affected dataset
  and call `describe_metadata_dataset` only when its exact live schema is needed. Read
  [local workspace](references/local-workspace.md) only around the helper used.
- Before a server Stage, read [Change Sets](references/change-sets.md).

Run bundled helpers from this skill directory. Pass the resolved absolute `GDS` path.
Use `powershell.exe -NoProfile -File ".\scripts\<helper>.ps1"` on Windows or
`"./scripts/<helper>.sh"` on macOS.

There is no `build_metadata_change_set` MCP tool. Build locally with the Workbench or
`upsert-local-metadata-record`; use `remove-local-metadata-record` to undo one pending
record. After `create_metadata_change_set`, bind/adopt the local draft with
`initialize-metadata-change-set`, check it with `validate-local-change-set`, and build
the approval summary with `prepare-metadata-stage-review`. Choose the `.ps1` or `.sh`
variant for the platform.

## Prepare a local draft

Keep the Snapshot immutable. Use the Workbench or local upsert helper to place complete,
ID-free records in the local Change Set. For an existing natural key, hydrate from the
Snapshot or pending record and change only requested fields. For a new key, provide one
complete schema-valid record. Never invent fields or database IDs.

Load only the exact schema and rows needed. Preserve earlier pending records. A copied
but unchanged record is temporary working state; edit or remove it before handoff.
Local validation is useful but is not server validation.

Do not warn that a validated Snapshot may be stale during local-only work. Check
freshness when the user crosses into the server write window, because that is when a
stale baseline can affect governed state.

## Enter the server write window

1. For read-only server draft inspection, call `get_metadata_change_set`, answer, and
   stop without acquiring a lock.
2. For archive-only intent, inspect the latest draft revision, confirm the exact draft,
   call `archive_metadata_change_set` without acquiring a lock, and stop. Release a lock
   already owned by this workflow when safe.
3. Confirm the exact Tenant and intended affected datasets before another mutation.
4. Call `check_tenant_lock`. Ask before calling `acquire_tenant_lock`; never override
   another owner automatically.
5. Call `create_metadata_change_set` only for explicit create/resume or when the
   requested Stage operation has no draft. If it resumes the Principal's draft, call
   `get_metadata_change_set` for its summary and every nonempty server dataset,
   including unrelated pending work. Reconcile it locally before any Stage.
6. Validate the local draft and build a fresh Stage review. Resolve `no_change` records.
   Show compact action counts and natural keys, then ask once before staging.
7. Call `stage_metadata_change_set` once with one to 16 unique complete accumulated
   local dataset lists and the latest `draft_revision`. Record the returned revision.
8. Call `get_metadata_change_set` to compare server counts, then call
   `validate_metadata_change_set`. Repair the first failed phase, restage the complete
   affected list, and repeat.
9. Show the authoritative `action_review`, truncation state, and exact revision. Require
   explicit user confirmation immediately before Apply.
10. Call `apply_metadata_change_set` once, verify with focused reads, then call
   `release_tenant_lock`. For an abandoned server draft, confirm and call
   `archive_metadata_change_set` before releasing the owned lock. Release a lock this
   workflow acquired at any requested stopping boundary when no immediate governed
   write follows.

## Safety invariants

- Stage and Apply are separate approvals. Validation is not Apply approval.
- Every supplied Stage list replaces that dataset's complete pending list. Never send
  only the newest record when earlier pending records exist.
- Never Validate or Apply a reused draft until every nonempty server dataset is matched
  to the local record count.
- Never delete applied metadata. Use a complete record with `is_active=false` to
  deactivate. An empty staged list clears pending work only.
- Never retry an ambiguous non-idempotent result. Inspect current state first.
- Override only releases the old Tenant Lock; recheck and acquire separately.
- On conflict, reconcile the latest revision and repeat review when effects change.
- Archive abandoned server drafts rather than deleting them. Release owned locks when
  safe and report release failures.

## Report

Normally use no more than three bullets and 120 words: outcome, affected scope/counts,
and blocker or next boundary. Do not narrate routine tool calls or repeat schemas,
unchanged records, checklists, or raw output. Never omit conflicts, validation warnings,
truncation, or the authoritative pre-Apply review.
