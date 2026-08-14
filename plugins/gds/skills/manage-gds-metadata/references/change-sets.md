# Metadata Change Sets

## Eligible datasets

Only these 16 operational datasets may be staged:

```text
source_object                 source_attribute
bronze_object                 bronze_attribute
silver_object                 silver_attribute
gold_object                   gold_attribute
ingestion_object_mapping      ingestion_attribute_mapping
copy_group                    member_group
copy_group_control            copy
process_group                 process
```

Foundational and reference snapshot rows are read-only through this workflow.

## Build and stage

There is no separate build or push MCP tool. Build the JSON arrays locally;
`stage_metadata_change_set` is the governed upload into the server-side draft.

Use the matching Snapshot schema for field definitions. The server and Snapshot
use the same record models. Do not copy field lists into prompts or this plugin.
Use the local upsert helper from `local-workspace.md`; it merges one full record
by the schema's canonical key and checks every resulting unique constraint.

Before Stage, run the local validator from `local-workspace.md` and review its
dataset counts/hashes. It checks the live Snapshot schema, required and unknown
fields, scalar types and limits, fixed values, and unique constraints. Server
validation remains authoritative for references, Tenant scope, and Object locks.

A stage call contains:

- Tenant ID and Change Set ID as control identifiers;
- `expected_draft_revision` as a concurrency fence; and
- one discriminated change containing a dataset name and a JSON list of full,
  ID-free records.

Stage **replaces the complete pending list for exactly one dataset**. Therefore:

- Keep the accumulated list locally.
- Merge a new edit into that list by canonical natural key.
- Restage the entire list, including earlier pending records.
- Never send only the newest item unless it is truly the dataset's only pending
  record.
- An empty list clears pending records for that dataset; it does not delete
  applied database rows.

Stage parents before children:

1. Zone Objects.
2. Zone Attributes.
3. Ingestion Object Mappings.
4. Ingestion Attribute Mappings.
5. Copy Groups and Member Groups.
6. Copy Group Controls and Copies.
7. Process Groups.
8. Processes.

Every successful stage increments one global `draft_revision` and returns the
new value. Immediately record the dataset's reviewed SHA/count and returned
revision with the local state updater before the next Stage. It also makes an
earlier validation stale.

## Revision conflicts

Never retry blindly. Call `get_metadata_change_set` for counts, then request
only the affected dataset. Reconcile the server list into the local complete
list, decide the intended result, set the latest revision locally, and restage.
If reconciliation changes the review, show it to the user again.

The state updater clears staged markers when synchronizing to a higher server
revision without recording a Stage. This is intentional: recheck server lists
and restage every affected local dataset before validation.

## Validate

Validation runs in this order and stops at the first failed phase:

```text
schema → locks → tenant_scope → uniqueness → references → complete
```

Fix the reported phase, update the complete local dataset, stage it, then run
validation again. The server returns at most 100 compact errors per run.
Before every server validation, run local validation with `RequireStaged`.

Current server caveat: the snapshot schema allows
`copy_group_control.member_group_name` to be null, but the current reference
validator rejects that null composite reference. If encountered, report the
schema/validator mismatch; do not invent a Member Group merely to pass it.

## Apply

Before Apply, show a compact record-level review and get explicit confirmation.
Apply rechecks authorization, lock ownership, revision, validation, candidate
digest, and Object locks. It resolves natural keys to database IDs and performs
natural-key upserts:

- Existing key: update the full record.
- New key: insert it.
- `is_active: false`: deactivate the record.
- No Change Set operation deletes an applied row.

All datasets apply inside one PostgreSQL transaction. A failure rolls back all
earlier writes.

## Lock and lifecycle

Create, stage, validate, and Apply require the caller's Tenant Lock. Renew it
during long local work. Another owner's lock is a stop condition. Override only
after explicit user direction and a supplied reason; override releases but does
not acquire.

`create_metadata_change_set` can return the caller's existing active/validated
draft instead of creating another. When `created=false`, get its summary first
and fetch every dataset you will edit before building the local accumulated
list. `archive_metadata_change_set` is for an abandoned draft. Release the
Tenant Lock after Apply or Archive; ask before releasing unfinished work.
