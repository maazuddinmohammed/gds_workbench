# Local GDS workspace

The local workspace separates the immutable metadata Snapshot from the editable
Change Set. Keep it in the user's current project, not inside this plugin.

## Layout

```text
gds-workspace/
├── .gitignore
├── record-input.json       # optional reusable full-record input
├── record-key.json         # optional reusable canonical-key input
├── metadata-snapshot/
│   ├── manifest.json
│   ├── catalog.json
│   ├── schemas/
│   └── data/
└── change-set/
    ├── change-set.json
    ├── review.json          # generated pre-Stage review
    └── datasets/<dataset>.json
```

Normally, neither managed directory exists when work begins. Initialize only
the ignored root. The initializer reports whether either managed directory is
already present; it never deletes, renames, or replaces one.

## Initialize safely

Resolve the script from this skill's `scripts` directory. On Windows PowerShell
5.1:

```powershell
powershell.exe -NoProfile -File "<plugin>\skills\manage-gds-metadata\scripts\initialize-gds-workspace.ps1" -Root "$((Get-Location).Path)\gds-workspace"
```

On macOS:

```sh
"<plugin>/skills/manage-gds-metadata/scripts/initialize-gds-workspace.sh" "$PWD/gds-workspace"
```

Completion criterion: output starts with `ok=true`, and `workspace` is the
absolute expected path. Do not recommend weakening PowerShell execution policy.

If `metadata_snapshot_exists=true` or `change_set_exists=true`, stop and ask
whether the user wants to reuse it. If not, ask the user to remove it or rename
it clearly, then wait. Never perform that operation for the user.

## Create a local Change Set

Create this only after the validated Snapshot is present and the server returns
the Metadata Change Set ID, status, and current revision. The initializer
refuses an existing local `change-set`.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File "<plugin>\skills\manage-gds-metadata\scripts\initialize-metadata-change-set.ps1" `
    -WorkspacePath "$((Get-Location).Path)\gds-workspace" `
    -TenantId <tenant-id> -TenantCode "<tenant-code>" `
    -SnapshotId "<snapshot-id>" -SnapshotUsage "fresh" `
    -MetadataChangeSetId "<change-set-id>" `
    -ServerStatus "<active-or-validated>" -DraftRevision <revision>
```

macOS:

```sh
"<plugin>/skills/manage-gds-metadata/scripts/initialize-metadata-change-set.sh" \
  --workspace "$PWD/gds-workspace" \
  --tenant-id <tenant-id> --tenant-code "<tenant-code>" \
  --snapshot-id "<snapshot-id>" --snapshot-usage fresh \
  --change-set-id "<change-set-id>" \
  --server-status "<active-or-validated>" --draft-revision <revision>
```

Completion criterion: `ok=true` and the Tenant, Snapshot, Change Set ID,
revision, and status match the MCP results. For a user-approved reused Snapshot,
set usage to `reused` and add `-AcknowledgeOutdatedSnapshot` on PowerShell or
`--acknowledge-outdated-snapshot` on macOS.

The initializer writes this control shape:

```json
{
  "format_version": "1.0",
  "tenant": {
    "tenant_id": 1,
    "tenant_code": "DEMO"
  },
  "snapshot": {
    "snapshot_id": "<uuid>",
    "path": "../metadata-snapshot",
    "usage": "fresh",
    "outdated_snapshot_warning_acknowledged": false
  },
  "server_change_set": {
    "metadata_change_set_id": "<uuid>",
    "draft_revision": 1,
    "status": "active"
  },
  "datasets": {}
}
```

Do not hand-edit Tenant, Snapshot, or server identifiers. `datasets` is local
workflow state; dataset records remain in separate files.

## Dataset files

Each `datasets/<dataset>.json` is the complete local pending JSON array for one
of the 16 change-eligible datasets. It is the shared format for agent edits and
the future HTML utility. Do not duplicate Snapshot schemas or business
definitions in the Change Set; read them from the Snapshot and skill references.

## Build and merge one full record

Read `schemas/<dataset>.schema.json` before authoring. Use `properties` and
`required` for the complete shape, `x-gds-canonical-key` for merge identity,
`x-gds-unique-constraints` for conflicts, `x-gds-fixed-values` for constants,
and `x-gds-references` to identify parents.

- Update or deactivate: copy the exact existing full Snapshot/server row, then
  change only the user-approved fields. Preserve every other field.
- Insert: provide every required field with its correct JSON type. Never invent
  reference codes; select existing parents from the Snapshot.
- Keep one full object temporarily in `gds-workspace/record-input.json`. This
  path is ignored by Git. The helper never prints its values or deletes it.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File "<plugin>\skills\manage-gds-metadata\scripts\upsert-local-metadata-record.ps1" `
    -ChangeSetPath "$((Get-Location).Path)\gds-workspace\change-set" `
    -Dataset "source_object" `
    -RecordPath "$((Get-Location).Path)\gds-workspace\record-input.json"
```

macOS:

```sh
"<plugin>/skills/manage-gds-metadata/scripts/upsert-local-metadata-record.sh" \
  --change-set "$PWD/gds-workspace/change-set" \
  --dataset "source_object" \
  --record-file "$PWD/gds-workspace/record-input.json"
```

Completion criterion: `ok=true`, the expected dataset, `action=inserted` or
`action=replaced`, and the expected accumulated count. Matching strings in the
canonical key are trimmed and compared without case. The helper validates the
new full record, the previous accumulated list, and every resulting unique
constraint before writing atomically. It never stages anything.

Direct editors, including the future HTML utility, may write the complete
`datasets/<dataset>.json` array instead. They must not patch only part of a row;
run the same local validator afterward.

## Remove one local pending record

Use this only to remove one record from a local accumulated dataset. Put exactly
the canonical-key fields from the live schema in `gds-workspace/record-key.json`.
The helper rejects missing, extra, invalid, or unmatched keys.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File "<plugin>\skills\manage-gds-metadata\scripts\remove-local-metadata-record.ps1" `
    -ChangeSetPath "$((Get-Location).Path)\gds-workspace\change-set" `
    -Dataset "source_object" `
    -KeyPath "$((Get-Location).Path)\gds-workspace\record-key.json"
```

macOS:

```sh
"<plugin>/skills/manage-gds-metadata/scripts/remove-local-metadata-record.sh" \
  --change-set "$PWD/gds-workspace/change-set" \
  --dataset "source_object" \
  --key-file "$PWD/gds-workspace/record-key.json"
```

Completion criterion: `action=removed` and the expected remaining count. An
empty result remains as `[]`; it does not delete the dataset file. This never
calls MCP, never changes PostgreSQL, and never deletes applied metadata. Any
existing Stage review becomes stale; validate and prepare it again.

## Validate the local Change Set

Before staging, validate every dataset against its matching Snapshot schema.
This local check does not validate cross-dataset references, Tenant scope, or
Object locks; server validation remains required.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File "<plugin>\skills\manage-gds-metadata\scripts\validate-local-change-set.ps1" -ChangeSetPath "$((Get-Location).Path)\gds-workspace\change-set" -ExpectedMetadataChangeSetId "<change-set-id>" -ExpectedDraftRevision <revision>
```

macOS:

```sh
"<plugin>/skills/manage-gds-metadata/scripts/validate-local-change-set.sh" "$PWD/gds-workspace/change-set" "<change-set-id>" "<revision>"
```

Completion criterion: `ok=true`, matching control identity, and one compact
`dataset=name|record-count|bytes|sha256|staged|staged-revision` line per local dataset. The validator
rejects unknown datasets, incomplete or unknown fields, wrong scalar types,
fixed-value violations, duplicate unique constraints, database ID fields, more
than 50,000 records, and files over the 16 MiB Stage limit. It never prints
record contents.

A Stage call replaces that one pending server dataset, so send the complete
accumulated local array every time. An empty array clears that pending dataset;
it does not delete applied metadata. Any edit after review requires another
local validation and review.

## Prepare the Stage review

Run this after local validation and before asking for Stage approval.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File "<plugin>\skills\manage-gds-metadata\scripts\prepare-metadata-stage-review.ps1" `
    -ChangeSetPath "$((Get-Location).Path)\gds-workspace\change-set" `
    -MetadataChangeSetId "<change-set-id>" `
    -ExpectedDraftRevision <revision>
```

macOS:

```sh
"<plugin>/skills/manage-gds-metadata/scripts/prepare-metadata-stage-review.sh" \
  --change-set "$PWD/gds-workspace/change-set" \
  --change-set-id "<change-set-id>" \
  --expected-draft-revision <revision>
```

The command writes `review.json`. Chat output contains only dataset/action
counts and hashes. The local file contains action plus canonical-key values,
not full rows. Read it selectively; do not paste hundreds of keys into chat.

Run the local validator again with `-RequireReviewed` on PowerShell or append
`--require-reviewed` on macOS. Completion criterion: `reviewed=true`. Resolve
`no_change` items, regenerate after any edit, then show the compact review and
ask for explicit Stage approval. The script cannot grant or record approval.

A successful expected Stage changes the global revision but does not change the
approved dataset hashes. Continue the approved sequence using the latest Stage
revision. A conflict, reconciliation, local edit, or changed intended result
requires a new review and approval.

## Record successful Stage results

Immediately after each successful Stage, record the returned revision against
the exact reviewed SHA-256. PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File "<plugin>\skills\manage-gds-metadata\scripts\update-local-change-set-state.ps1" -ChangeSetPath "$((Get-Location).Path)\gds-workspace\change-set" -MetadataChangeSetId "<change-set-id>" -ExpectedCurrentRevision <sent-revision> -ServerRevision <returned-revision> -ServerStatus "active" -StagedDataset "<dataset>" -StagedSha256 "<reviewed-sha256>"
```

macOS:

```sh
"<plugin>/skills/manage-gds-metadata/scripts/update-local-change-set-state.sh" \
  --change-set "$PWD/gds-workspace/change-set" \
  --change-set-id "<change-set-id>" \
  --expected-current-revision <sent-revision> \
  --server-revision <returned-revision> --server-status active \
  --staged-dataset "<dataset>" --staged-sha256 "<reviewed-sha256>"
```

Completion criterion: `stage_recorded=true`, matching dataset/hash/count, and
the local revision equals the Stage result. The helper fails if the file changed
after review or the Stage revision did not increment by exactly one.

The helper owns each staged-state entry; do not hand-edit it:

```json
"source_object": {
  "file": "datasets/source_object.json",
  "record_count": 3,
  "staged_sha256": "<sha256>",
  "staged_revision": 2
}
```

Before server validation, rerun the local validator with `-RequireStaged` on
PowerShell or append `--require-staged` on macOS. Every dataset line must show
`staged=true`.

To record a server Validate/Get result without a Stage, call the same updater
without dataset/SHA arguments and pass the server revision/status. A same-revision
status update preserves staged markers. Moving to a higher reconciled revision
clears every marker conservatively; fetch/merge server datasets and restage.
