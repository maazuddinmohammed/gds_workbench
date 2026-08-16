---
name: manage-gds-metadata
description: Inspect or change GDS Tenant metadata with the governed GDS Workbench MCP tools and local Change Set helpers. Use when the user asks to read specific Tenant metadata, obtain or search a Metadata Snapshot, manage a Tenant Lock, or create, stage, validate, apply, or archive a Metadata Change Set; do not use for general GDS explanations or merely opening the local table Workbench.
---

# Manage GDS metadata

Use only the governed `gds-workbench` MCP tools. Never use direct SQL except the
read/temporary-object-only `execute_databricks_sql` tool. Never use table writes,
foundational/reference mutation, arbitrary CRUD, or lock-table updates.

## Run local helpers

Resolve this `SKILL.md` source and use its parent directory as the process
working directory for every bundled helper. Pass the user's `GDS` path as an
absolute path. Reference commands therefore use `./scripts` or `.\scripts` and
must never expose an unresolved plugin-path placeholder.

- Windows: run `powershell.exe -NoProfile -File ".\scripts\<helper>.ps1"` in
  Windows PowerShell 5.1.
- macOS: run `"./scripts/<helper>.sh"` with the system shell.

## Choose the path

- For a small read, use the bounded Tenant/Object/Copy Group/Process Group read
  tools. Do not create a lock or Change Set.
- For Databricks data analysis that needs SQL, use `execute_databricks_sql` only
  with an active global Connection ID. Never request or handle its credentials.
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
2. Recommend a fresh `get_metadata_snapshot` for changes. No lock is required
   to create or read a Snapshot. If the user insists on an existing Snapshot,
   warn it may be outdated and record their acceptance later when binding the
   draft. Never expose its SAS URL. Ask the user to download and extract it
   under `GDS/metadata-snapshot`, then follow the Snapshot validator.
3. Follow catalog navigation. Search only affected dataset search files; load
   an exact full row and schema only when needed. Never load the whole archive.
4. Offer two local editing paths: work with the agent using the local helpers,
   or invoke `open-gds-metadata-workbench` for the browser table utility. A
   local-only draft needs no Tenant Lock and may have server status `local`.
   Never describe it as authorized, Staged, validated, or applied.
5. Use the dataset guide to restate the change as records and natural keys. Ask
   only questions that change records. Use the extracted dataset schema; if it
   is unavailable or uncertain, call `describe_metadata_dataset` for only that
   dataset. Rows are ID-free; Tenant and Change Set IDs remain valid tool
   control inputs.
6. Use the local upsert helper. For an update/deactivation, provide only the
   exact natural key and changed fields; the helper hydrates the full Snapshot
   or pending row locally. For an insert, provide one complete record. Never
   hand-append, invent fields, or use database IDs.
7. When the user wants to move the local draft to the server, call
   `check_tenant_lock`.

   - Unlocked: ask before calling `acquire_tenant_lock`.
   - Owned by the current user: continue; renew before it expires.
   - Owned by another Principal: stop and tell the user who owns it. Do not
     override automatically.
8. Call `create_metadata_change_set`. If it returns an existing draft, ask
   whether to reuse it. If yes, fetch its summary, then fetch and import every
   dataset whose server count is nonzero, including datasets outside the new
   request. If no, offer Archive with separate confirmation, then create anew.
   Keep the returned Change Set ID and `draft_revision`.
9. Follow [references/local-workspace.md](references/local-workspace.md). Run
   the platform-specific Change Set initializer. It creates a bound local
   Change Set or safely adopts the Workbench's matching unbound local draft.
   When resuming a server draft, adopt and review all of its nonempty datasets
   before Stage.
10. Run local validation, prepare the Stage review, and require it to be fresh.
   Resolve no-change items with the local removal helper. Show action counts and
   affected natural keys, then ask once before staging. Call
   `stage_metadata_change_set` once with one to 16 unique complete dataset lists
   in dependency order. Record its one returned revision against every reviewed
   dataset hash with one local state update.
11. Call `get_metadata_change_set` without a dataset to compare counts. Request
    one dataset only when reconciling a conflict or uncertain server state.
12. Require every local dataset to show staged, then call server validation at
   the latest revision. Fix the first failed phase, restage the complete
   affected dataset set in one call, record the revision, and repeat. Any
   restage invalidates prior validation.
13. Treat a successful validation response's `action_review` as authoritative.
   Show the user a compact review: Tenant, Change Set ID, datasets/counts,
   natural keys, intended insert/update/deactivation results, truncation state,
   and validation status. Obtain explicit confirmation immediately before
   `apply_metadata_change_set`.
14. Apply with the latest revision. Apply revalidates and commits all datasets
    atomically. Report the server result; do not claim success from local state.
15. Verify the Change Set status, then release the Tenant Lock. If work is
    abandoned, confirm when needed, archive the draft, and release the lock.

## Hard safety rules

- Require explicit user direction and a reason immediately before
  `override_tenant_lock`. Override only releases the old lock; recheck and
  acquire separately.
- Require explicit user confirmation immediately before Apply.
- A generated Stage review is not approval. Never Stage until the user approves
  its exact Tenant, datasets, actions, and counts.
- Never apply on a revision conflict. Fetch and reconcile; repeat review if the intended result changed.
- Never restage an existing or conflicted dataset until its current server list
  has been fetched and merged into the complete local list.
- Never validate or Apply a reused server Change Set until every nonempty server
  dataset has been imported, reviewed, and matched to the local record count.
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
