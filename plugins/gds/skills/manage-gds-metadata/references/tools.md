# GDS MCP tool reference

Use the tool schema advertised by the connected MCP server as the contract. Do not
invent record fields. Unless noted, `schema_version` is optional and defaults to
`"1.0"`; `tenant_id` and other database IDs are positive integers.

## Authentication and safety

- The MCP client performs server authentication. The server derives Principal,
  Tenant access, role, and lock ownership. Never supply or infer them in tool input.
- This plugin stores no credential. Never request, paste, log, or save a bearer token,
  connection value, Snapshot download URL, secret, or raw unredacted tool dump.
- On `authentication_required`, pause for the user to complete the MCP client's sign-in,
  then retry. On `authorization_denied`, stop; do not seek a bypass.
- Ask for explicit user approval immediately before
  `apply_metadata_change_set` or `override_tenant_lock`. Validation is not approval.
- `override_tenant_lock` only releases another Principal's lock. It never acquires a
  replacement. Check again and acquire normally before continuing.
- Treat opaque cursors and UUIDs as values. Send SQL only to
  `execute_databricks_sql`; every other tool exposes a fixed governed operation.

## Read and discover

### `list_tenants`

**Purpose:** Find active Tenants visible to the authenticated Principal.
**Inputs:** Optional `page_size` 1-200 (default 50) and opaque `cursor`.
**Returns:** Bounded Tenant summaries with `tenant_id`, code, name, visibility,
server-derived effective role, and `next_cursor`.
**Safe/error:** Follow `next_cursor` without modifying it. Empty results are valid.
Stop on authentication or authorization errors.

### `get_tenant_details`

**Purpose:** Read one authorized Tenant plus Connection-grain System/type details and
active Source/Bronze/Silver/Gold Object counts.
**Inputs:** `tenant_id`.
**Returns:** Tenant header, `connection_count`, at most 200 Connection summaries, and
`connections_truncated`.
**Safe/error:** If truncated, use the narrower catalog tools; do not assume omitted
Connections are absent. Stop on `tenant_not_found` or `authorization_denied`.

### `get_model`

**Purpose:** Read active Model headers and naming/audit policy templates for one Tenant.
**Inputs:** `tenant_id`; optional `page_size` 1–200 (default 200) and opaque `cursor`.
**Returns:** Up to 200 Models with IDs, names, descriptions, revisions, policy templates,
Model Scope Object counts, complete count, truncation flag, and `next_cursor`.
**Safe/error:** Follow the cursor unchanged until the requested scope is complete.
Created/updated audit fields are intentionally omitted.

### `get_model_scope`

**Purpose:** Read active physical Objects currently included in one Model Scope.
**Inputs:** `model_id` returned by `get_model`; optional `page_size` 1–2,000 (default
2,000) and opaque `cursor`.
**Returns:** Up to 2,000 Scope Objects with Model Scope/Object IDs plus expanded Tenant,
System, Connection, Object Type, Zone, lock state, physical names, and `next_cursor`.
**Safe/error:** Only active Scope and catalog records are returned. Follow the cursor
unchanged. Use Model Change Sets for add/reactivate/archive; there is no direct Model
Scope mutation tool.

### `list_objects`

**Purpose:** Discover authorized physical Objects in one exact Zone.
**Inputs:** `tenant_id`, `zone` (`source|bronze|silver|gold`); optional positive
`connection_id`, `active_state` (`active|inactive|all`, default `active`), `page_size`
1-200, and opaque `cursor`.
**Returns:** Object summaries, inclusion flags, mapping presence, Attribute counts, and
`next_cursor`.
**Safe/error:** Preserve all filters when following the cursor. Use returned IDs with
`get_objects`; do not guess IDs.

### `get_objects`

**Purpose:** Read full bounded Object and Attribute details.
**Inputs:** `tenant_id`; `object_ids`, 1-25 unique positive IDs discovered by
`list_objects`.
**Returns:** Objects in requested order with type, Zone, Connection/System, lock/activity,
and ordered Attributes.
**Safe/error:** One missing/invisible Object fails the batch. Split a rejected batch to
locate the bad ID. If details exceed the 2,000-Attribute bound, request fewer Objects.

### `get_object_lineage`

**Purpose:** Read direct configured ingestion lineage, not observed runtime flow.
**Inputs:** `tenant_id`, `object_id`; optional `direction`
(`upstream|downstream|both`, default `both`).
**Returns:** Up to 500 mapping edges with source/target Objects, direction, Attribute
mapping count, Copy count, activity, and `mappings_truncated`.
**Safe/error:** A missing/invisible Object returns `invalid_request`. If truncated, state
that the result is incomplete; the tool has no pagination.

### `list_copy_groups`

**Purpose:** Discover Copy Groups owned by one Tenant.
**Inputs:** `tenant_id`; optional positive `system_id`, `active_state`
(`active|inactive|all`), `page_size` 1-200, and opaque `cursor`.
**Returns:** Copy Group summaries and counts for Copies, Controls, and Process Groups,
plus `next_cursor`.
**Safe/error:** Preserve filters across pages. Empty results are valid; do not turn them
into a change request without confirming the user's requirement.

### `get_copy_group`

**Purpose:** Read one Tenant-owned Copy Group with bounded Copies and Controls.
**Inputs:** `tenant_id`, `copy_group_id` from `list_copy_groups`.
**Returns:** Group summary, at most 200 Copies, at most 200 Controls, and truncation flags.
SQL scripts and raw checkpoint values are not returned.
**Safe/error:** Stop on `invalid_request` when not found. If either list is truncated,
report incomplete evidence; do not reconstruct omitted values.

### `list_process_groups`

**Purpose:** Discover Process Groups reached through the Tenant's Copy Groups.
**Inputs:** `tenant_id`; optional positive `system_id`, Zone filter, `active_state`
(`active|inactive|all`), `page_size` 1-200, and opaque `cursor`.
**Returns:** Process Group summaries, declared Zone, Copy Group/System, Process count,
and `next_cursor`.
**Safe/error:** Preserve filters across pages. Use returned IDs; never infer a Process
Group from similar names.

### `get_process_group`

**Purpose:** Read one Process Group and its ordered Process/Object associations.
**Inputs:** `tenant_id`, `process_group_id` from `list_process_groups`.
**Returns:** Group summary, up to 500 ordered Processes, referenced Objects/Connections,
and `processes_truncated`. Executable names and locations are not returned.
**Safe/error:** Stop on `invalid_request` when not found. A truncated response is
incomplete evidence and must be reported as such.

### `get_metadata_snapshot`

**Purpose:** Create an immutable, ID-free 29-dataset Metadata Snapshot for local analysis.
**Inputs:** `tenant_id`; `schema_version` is `"2.0"` (default `"2.0"`).
**Returns:** Snapshot UUID, temporary read-only ZIP URL and expiry, byte size, SHA-256,
and content type. Rows never enter the MCP response.
**Safe/error:** Treat the URL as sensitive and short-lived: download once without echoing
it, verify byte size and SHA-256, then read `catalog.json` first. Search only needed
lookup/row files and open schemas on demand; never load the whole ZIP into chat. Create a
new Snapshot if the URL expires. Stop on `payload_too_large` or
`dependency_unavailable`; do not weaken bounds.

### `execute_databricks_sql`

**Purpose:** Run governed analysis SQL using the source Tenant's configured GDS
Connection for one Environment.
**Inputs:** Positive source `connection_id`; active `environment_code`; `sql`
containing 1-25 semicolon-separated statements and at most 100,000 characters.
**Returns:** Columns and at most 50 rows from only the final statement, plus
statement count and row/cell truncation flags.
**Safe/error:** Fully qualify physical relations as `catalog.schema.table`. Use
reads or unqualified `CREATE [OR REPLACE] TEMP VIEW/TABLE` only. Never send
INSERT, UPDATE, DELETE, MERGE, COPY, persistent DDL, secrets, or
connection values. The complete submitted SQL is retained in the append-only
tool-call audit log, so never place credentials in SQL. Secret-returning SQL
functions are rejected. Statements share one session and run in order; a failure
stops the batch. Do not claim rollback of earlier temporary DDL. Report safe
connection/configuration/statement error codes without seeking credentials or
exposing raw connector details.

### `describe_metadata_dataset`

**Purpose:** Read the current contract for one Snapshot dataset without reading rows.
**Inputs:** Exact dataset name from `catalog.json`.
**Returns:** Section, Change Set eligibility, natural key, references, dependencies, and
the exact JSON Schema generated from the same server contract used by Snapshot creation
and Stage validation.
**Safe/error:** Call it only for a dataset you need to edit when its extracted Snapshot
schema is unavailable or uncertain. Do not request all dataset schemas preemptively.

## Tenant Lock

### `check_tenant_lock`

**Purpose:** Read current lock state before metadata mutation.
**Inputs:** `tenant_id`.
**Returns:** `is_locked` and bounded owner display, caller-ownership flag, purpose, and
timestamps when locked.
**Safe/error:** If unlocked, acquire normally. If owned by the caller, reuse/renew it. If
owned by another Principal, stop and report the owner; override requires explicit approval.

### `acquire_tenant_lock`

**Purpose:** Acquire an unlocked Tenant for the current Principal.
**Inputs:** `tenant_id`; optional `duration_minutes` 1-240 (default 60) and optional
nonblank `purpose` up to 500 characters.
**Returns:** `acquired=true` and caller-owned lock details.
**Safe/error:** Any active lock fails, including the caller's. On `tenant_locked`, check
state and wait or renew if already owner; do not override automatically.

### `renew_tenant_lock`

**Purpose:** Extend the current Principal's active lock.
**Inputs:** `tenant_id`; optional `duration_minutes` 1-240 (default 60).
**Returns:** `renewed=true` and updated lock details.
**Safe/error:** Only the owner can renew. On `tenant_lock_required` or `tenant_locked`,
check state and stop/reacquire as appropriate; never claim ownership from stale state.

### `release_tenant_lock`

**Purpose:** Release the current Principal's active lock after work or safe abandonment.
**Inputs:** `tenant_id`.
**Returns:** `released=true`, `is_locked=false`.
**Safe/error:** Only release a caller-owned lock. If work is abandoned, archive its active
or validated Change Set first when appropriate. On failure, check lock state; do not force
release through another path.

### `override_tenant_lock`

**Purpose:** Force-release another Principal's active lock under governed authorization.
**Inputs:** `tenant_id`; nonblank audit `reason` up to 2,000 characters.
**Returns:** `overridden=true`, `is_locked=false`, and bounded previous-lock details.
**Safe/error:** Obtain explicit user approval immediately before this call. It is valid
only for another Principal's active lock. It releases only and never acquires a new lock;
call `check_tenant_lock`, then `acquire_tenant_lock` separately if approved work continues.

## Metadata Change Sets

The 16 stageable dataset names are:

```text
source_object, source_attribute, bronze_object, bronze_attribute,
silver_object, silver_attribute, gold_object, gold_attribute,
ingestion_object_mapping, ingestion_attribute_mapping, copy_group,
member_group, copy_group_control, copy, process_group, process
```

Use complete ID-free records from the extracted Snapshot schema or
`describe_metadata_dataset`. The Stage input stays intentionally generic to keep the MCP
tool list small; the server still validates every record against that exact contract.
Reference relationships by natural keys, never database IDs.

### `create_metadata_change_set`

**Purpose:** Create or resume the caller's one ongoing Change Set for a locked Tenant.
**Inputs:** `tenant_id`.
**Returns:** Change Set UUID, `created` flag, `active|validated` status, current
`draft_revision`, and timestamps.
**Safe/error:** Requires the caller-owned lock. `created=false` means an existing draft
was returned; inspect it before staging. On a lock error, check state rather than retrying
blindly.

### `stage_metadata_change_set`

**Purpose:** Atomically replace one to 16 complete pending dataset lists in the
Change Set.
**Inputs:** `tenant_id`, `metadata_change_set_id`, latest positive
`expected_draft_revision`, and `changes=[{"dataset": <name>, "records": [...]}, ...]`
with one to 16 unique dataset names. Maximum 50,000 full records per entry and
16 MiB serialized for the call.
**Returns:** Every supplied dataset/count, one incremented `draft_revision`, `active`
status, and expiry.
**Safe/error:** Use one entry for one dataset and one atomic call for multiple approved
datasets. Each entry is replacement, not append or patch. Keep each complete candidate
list locally. An empty list clears only that pending dataset; it does not delete applied
metadata. Use full records with `is_active=false` for lifecycle changes. On
`draft_revision_conflict`, get the Change Set and reconcile before retrying.

### `get_metadata_change_set`

**Purpose:** Inspect the caller-owned Change Set without requiring a current lock.
**Inputs:** `tenant_id`, `metadata_change_set_id`; optional one dataset name.
**Returns:** Status, revision, digest/validation outcome, 16 dataset counts, timestamps,
and either no records or only the selected dataset records.
**Safe/error:** Omit dataset for a cheap counts/status check. Request one dataset at a
time; never load all documents into chat. Not-found also protects ownership, so stop rather
than probing.

### `validate_metadata_change_set`

**Purpose:** Validate the complete pending future state against Snapshot schemas, Tenant
scope, natural keys, uniqueness, references, and Object locks.
**Inputs:** `tenant_id`, `metadata_change_set_id`, latest positive
`expected_draft_revision`.
**Returns:** `valid`, validation phase, `active|validated` status, revision, candidate
digest when valid, staged count, bounded structured errors, validation time, expiry, and
authoritative `action_review` when validation completes. Review entries contain complete
action counts, up to 100 natural keys across the response, and `keys_truncated`.
**Safe/error:** `valid=false` is a normal result and writes no effective metadata. Fix the
reported phase locally, restage complete affected lists, use the new revision, and validate
again. On `object_locked`, do not alter that Object or its Attributes. On revision conflict,
re-read and reconcile.

### `apply_metadata_change_set`

**Purpose:** Revalidate and atomically upsert all 16 pending datasets by resolving natural
keys to PostgreSQL IDs.
**Inputs:** `tenant_id`, `metadata_change_set_id`, latest positive
`expected_draft_revision`.
**Returns:** `valid`, `applied`, phase, `active|applied` status, digest, staged/action/error
counts, structured errors, revalidated `action_review`, and applied time.
**Safe/error:** First show the user the validated revision, digest, dataset counts, and
planned effect; obtain explicit approval immediately before calling. Apply revalidates in
the same transaction. If invalid, it returns `applied=false` and performs no effective
write. On digest/revision conflict, stop, re-read, revalidate, and request fresh approval.

### `archive_metadata_change_set`

**Purpose:** End and retain an abandoned active or validated Change Set; it is not deleted.
**Inputs:** `tenant_id`, `metadata_change_set_id`, latest positive
`expected_draft_revision`.
**Returns:** `archived=true`, terminal status/revision, and archive time.
**Safe/error:** No current lock is required, but creator ownership is. On revision conflict,
re-read before archiving. Never describe archive as rollback or deletion; it does not undo
an applied Change Set.

## Common failure branches

- `invalid_request`: correct only the bounded input named by the server/tool schema.
- `tenant_not_found`: stop and confirm the Tenant selected through `list_tenants`.
- `tenant_lock_required` / `tenant_locked`: call `check_tenant_lock`; never bypass.
- `metadata_change_set_not_found` / `metadata_change_set_not_active`: stop and create or
  resume through the governed lifecycle; never fabricate an ID.
- `draft_revision_conflict` / `candidate_digest_conflict`: re-read, reconcile, revalidate;
  apply then needs fresh explicit approval.
- `dependency_unavailable` / `internal_error`: report the safe code, preserve local work,
  and retry only when the dependency/server is healthy. Never expose raw exception output.
- `databricks_connection_*`: confirm the selected global Connection or ask an
  administrator to correct its stored values; never request those values.
- `databricks_statement_failed`: report the returned statement index and correct
  only the SQL. Never expose or infer credentials.
