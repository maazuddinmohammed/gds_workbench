---
name: manage-gds-metadata
description: Inspect or change GDS Tenant metadata through the GDS Workbench MCP server. Use for metadata snapshots, Objects and Attributes, mappings, Copy Groups and Copies, Process Groups and Processes, Tenant Locks, or Metadata Change Sets.
---

# Manage GDS metadata

Use only the governed `gds-workbench` MCP tools. Never use direct SQL, table
writes, foundational/reference mutation, arbitrary CRUD, or lock-table updates.

## Choose the path

- For a small read, use the bounded Tenant/Object/Copy Group/Process Group read
  tools. Do not create a lock or Change Set.
- For broad discovery, use a metadata snapshot and read it selectively.
- For any metadata change, follow the complete workflow below.

Read [references/tools.md](references/tools.md) before unfamiliar tool calls.
For Snapshots, follow [references/snapshot.md](references/snapshot.md), then
[references/catalog-navigation.md](references/catalog-navigation.md). Use
[references/datasets.md](references/datasets.md) to map requirements to datasets.
Read [references/change-sets.md](references/change-sets.md) before staging.

## Change workflow

1. Ask whether the user wants to read/analyze or change metadata. Identify the
   exact Tenant; never infer it from a name fragment. Reads need no lock.
2. Call `check_tenant_lock`.
   - Unlocked: ask before calling `acquire_tenant_lock`.
   - Owned by the current user: continue; renew before it expires.
   - Owned by another Principal: stop and tell the user who owns it. Do not
     override automatically.
3. Recommend a fresh `get_metadata_snapshot` after owning the lock. If the user
   insists on an existing Snapshot, warn it may be outdated and record their
   acceptance. Never expose its SAS URL. Ask the user to download and extract
   it under `gds-workspace/metadata-snapshot`, then follow the Snapshot validator.
4. Follow catalog navigation. Search only affected dataset search files; load
   an exact full row and schema only when needed. Never load the whole archive.
5. Use the dataset guide to restate the change as records and natural keys. Ask
   only questions that change records. Rows are ID-free; Tenant and Change Set
   IDs remain valid tool control inputs.
6. Call `create_metadata_change_set`. If it returns an existing draft, ask
   whether to reuse it. If yes, fetch its summary and every dataset being
   edited. If no, offer Archive with separate confirmation, then create anew.
   Keep the returned Change Set ID and `draft_revision`.
7. Create a local Change Set outside the immutable snapshot. Follow
   [references/local-workspace.md](references/local-workspace.md) and use its
   platform-specific initializer. Keep one complete JSON array per affected
   dataset.
8. Build every item as a complete record from the matching Snapshot schema.
   For an update/deactivation, start from the exact existing full row. Use the
   local upsert helper to merge by canonical key; never hand-append blindly.
   Do not invent fields or database IDs.
9. Run the schema-aware local validator. Show all reviewed dataset names/counts
   and ask once before staging. Stage in dependency order with complete lists;
   record each returned revision and reviewed hash with the local state updater.
10. Call `get_metadata_change_set` without a dataset to compare counts. Request
    one dataset only when reconciling a conflict or uncertain server state.
11. Require every local dataset to show staged, then call server validation at
    the latest revision. Fix the first failed phase, restage its complete list,
    record the revision, and repeat. Any restage invalidates prior validation.
12. Show the user a compact review: Tenant, Change Set ID, datasets/counts,
    natural keys, intended insert/update/deactivation results, and validation
    status. Obtain explicit confirmation immediately before
    `apply_metadata_change_set`.
13. Apply with the latest revision. Apply revalidates and commits all datasets
    atomically. Report the server result; do not claim success from local state.
14. Verify the Change Set status, then release the Tenant Lock. If work is
    abandoned, confirm when needed, archive the draft, and release the lock.

## Hard safety rules

- Require explicit user direction and a reason immediately before
  `override_tenant_lock`. Override only releases the old lock; recheck and
  acquire separately.
- Require explicit user confirmation immediately before Apply.
- Never apply on a revision conflict. Fetch and reconcile; repeat review if the intended result changed.
- Never restage an existing or conflicted dataset until its current server list
  has been fetched and merged into the complete local list.
- Never delete applied metadata. An empty staged list clears only that pending
  dataset. To deactivate, stage the complete record with `is_active: false`.
- Existing natural key means update; a new natural key means insert.
- A locked Object blocks changes to it and its Attributes. Let validation and
  Apply enforce the server rule.
- Never commit snapshots, local drafts, SAS URLs, credentials, raw tool output,
  or raw physical rows.
- Do not paste large tool or file output into chat. Summarize counts and natural
  keys instead.

## Context limits

- Keep `catalog.json`, not the entire snapshot, as navigation context.
- Use lookup lines for wide datasets; read the pointed `rows.jsonl` line only.
- Read schemas only for datasets currently being edited.
- Request only one staged dataset when record-level reconciliation is needed.
- Keep full working records in local JSON files, not repeated chat messages.
