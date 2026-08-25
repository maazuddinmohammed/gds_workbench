# Local GDS workspace

The local workspace separates the immutable metadata Snapshot from the editable
Change Set. Keep it in the user's current project, not inside this plugin.

Commands below assume this skill directory is the process working directory.
Resolve `<absolute-GDS-path>` to the user's absolute project `GDS` directory
before execution; never pass that token literally.

## Layout

```text
GDS/
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
powershell.exe -NoProfile -File ".\scripts\initialize-gds-workspace.ps1" -Root "<absolute-GDS-path>"
```

On macOS:

```sh
"./scripts/initialize-gds-workspace.sh" "<absolute-GDS-path>"
```

Completion criterion: output starts with `ok=true`, and `workspace` is the
absolute expected path. Do not recommend weakening PowerShell execution policy.

If `metadata_snapshot_exists=true` or `change_set_exists=true`, stop and ask
whether the user wants to reuse it. If not, ask the user to remove it or rename
it clearly, then wait. Never perform that operation for the user.

## Unbound local draft

The bundled Metadata Workbench may create `change-set` before a Tenant Lock or
server Change Set exists. This is only a local draft:

```json
{
  "format_version": "1.0",
  "tenant": { "tenant_id": null, "tenant_code": "DEMO" },
  "snapshot": {
    "snapshot_id": "<uuid>",
    "path": "../metadata-snapshot",
    "usage": "local",
    "outdated_snapshot_warning_acknowledged": false
  },
  "server_change_set": {
    "metadata_change_set_id": null,
    "draft_revision": null,
    "status": "local"
  },
  "datasets": {}
}
```

Dataset files may be built and saved in this state. Local status does not mean
authorized, Staged, server-validated, or applied. Do not call Stage until the
draft is bound.

## Bind or create a local Change Set

After the user approves the Tenant Lock and the server returns the Metadata
Change Set ID, status, and revision, run the initializer below. It creates a
new bound local Change Set when none exists. When a matching unbound Workbench
draft exists, it atomically replaces only `change-set.json` and preserves every
`datasets/*.json` file. It refuses an existing bound or mismatched draft.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\initialize-metadata-change-set.ps1" `
    -WorkspacePath "<absolute-GDS-path>" `
    -TenantId <tenant-id> -TenantCode "<tenant-code>" `
    -SnapshotId "<snapshot-id>" -SnapshotUsage "fresh" `
    -MetadataChangeSetId "<change-set-id>" `
    -ServerStatus "<active-or-validated>" -DraftRevision <revision>
```

macOS:

```sh
"./scripts/initialize-metadata-change-set.sh" \
  --workspace "<absolute-GDS-path>" \
  --tenant-id <tenant-id> --tenant-code "<tenant-code>" \
  --snapshot-id "<snapshot-id>" --snapshot-usage fresh \
  --change-set-id "<change-set-id>" \
  --server-status "<active-or-validated>" --draft-revision <revision>
```

Completion criterion: `ok=true`; the Tenant, Snapshot, Change Set ID, revision,
and status match the MCP results; and `adopted_local_draft` reports whether the
unbound draft was bound. For a user-approved reused Snapshot,
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
the bundled Metadata Workbench. Do not duplicate Snapshot schemas or business
definitions in the Change Set; read them from the Snapshot and skill references.

## Update or deactivate an existing record

Read `schemas/<dataset>.schema.json` before authoring. Use `properties` and
`required` for the complete shape, `x-gds-canonical-key` for merge identity,
`x-gds-unique-constraints` for conflicts, `x-gds-fixed-values` for constants,
and `x-gds-references` to identify parents.

Put exactly the canonical-key fields in `GDS/record-key.json`. Put only the
user-approved non-key fields in `GDS/record-changes.json`. The helper finds the
exact Snapshot row, uses an existing pending row as its base when present,
applies the fields, validates the complete record and accumulated dataset, then
writes atomically. It never prints the key, changes, or hydrated row.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\upsert-local-metadata-record.ps1" `
    -ChangeSetPath "<absolute-GDS-path>\change-set" `
    -Dataset "source_object" `
    -KeyPath "<absolute-GDS-path>\record-key.json" `
    -ChangesPath "<absolute-GDS-path>\record-changes.json"
```

macOS:

```sh
"./scripts/upsert-local-metadata-record.sh" \
  --change-set "<absolute-GDS-path>/change-set" \
  --dataset "source_object" \
  --key-file "<absolute-GDS-path>/record-key.json" \
  --changes-file "<absolute-GDS-path>/record-changes.json"
```

Completion criterion: `ok=true`, `mode=field-edit`, the expected dataset/action,
and `review_stale=true` when bytes changed. `action=no_change` leaves bytes
unchanged. It never stages anything.

## Insert one complete record

For a new natural key, provide every required field with its correct JSON type.
Never invent reference codes; select existing parents from the Snapshot. Keep
the object temporarily in `GDS/record-input.json`, then run the same helper with
`-RecordPath` on PowerShell or `--record-file` on macOS.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\upsert-local-metadata-record.ps1" `
    -ChangeSetPath "<absolute-GDS-path>\change-set" `
    -Dataset "source_object" `
    -RecordPath "<absolute-GDS-path>\record-input.json"
```

macOS:

```sh
"./scripts/upsert-local-metadata-record.sh" \
  --change-set "<absolute-GDS-path>/change-set" \
  --dataset "source_object" \
  --record-file "<absolute-GDS-path>/record-input.json"
```

Completion requires `mode=full-record` and `action=inserted`. Matching and
uniqueness use the exact `x-gds-key-normalization` rules from the Snapshot
schema.

Direct editors, including the bundled Metadata Workbench, may write the complete
`datasets/<dataset>.json` array instead. They must not patch only part of a row;
run the same local validator afterward.

## Remove one local pending record

Use this only to remove one record from a local accumulated dataset. Put exactly
the canonical-key fields from the live schema in `GDS/record-key.json`.
The helper rejects missing, extra, invalid, or unmatched keys.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\remove-local-metadata-record.ps1" `
    -ChangeSetPath "<absolute-GDS-path>\change-set" `
    -Dataset "source_object" `
    -KeyPath "<absolute-GDS-path>\record-key.json"
```

macOS:

```sh
"./scripts/remove-local-metadata-record.sh" \
  --change-set "<absolute-GDS-path>/change-set" \
  --dataset "source_object" \
  --key-file "<absolute-GDS-path>/record-key.json"
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
powershell.exe -NoProfile -File ".\scripts\validate-local-change-set.ps1" -ChangeSetPath "<absolute-GDS-path>\change-set" -ExpectedMetadataChangeSetId "<change-set-id>" -ExpectedDraftRevision <revision>
```

macOS:

```sh
"./scripts/validate-local-change-set.sh" "<absolute-GDS-path>/change-set" "<change-set-id>" "<revision>"
```

Completion criterion: `ok=true`, matching control identity, and one compact
`dataset=name|record-count|bytes|sha256|staged|staged-revision` line per local dataset. The validator
rejects unknown datasets, incomplete or unknown fields, wrong scalar types,
fixed-value violations, duplicate unique constraints, database ID fields, more
than 50,000 records, and files over the 16 MiB Stage limit. It never prints
record contents.

A Stage call accepts one to 16 unique dataset changes. Each entry replaces that
dataset's complete pending server list, so send each complete accumulated local
array. The whole call is atomic and increments the revision once. An empty
array clears only that pending dataset; it does not delete applied metadata.
Any edit after review requires another local validation and review.

## Prepare a large dataset Stage Batch

Use this only after local validation/review and only when one complete dataset cannot
fit a normal Stage request. Run from the `manage-gds-metadata` skill directory. The
output must be a new ignored directory directly under `GDS`, not inside `change-set`:

```sh
node ../../scripts/prepare-stage-batch.js \
  --kind metadata \
  --dataset-file "<absolute-GDS-path>/change-set/datasets/source_object.json" \
  --dataset source_object \
  --output "<absolute-GDS-path>/metadata-source-object-stage-batch"
```

Require `ok=true`. Read `manifest.json`, then each named chunk only when calling
`put_metadata_stage_chunk`; never print chunk bodies. Use manifest counts/digest with
`begin_metadata_stage_batch`, upload all ordered chunks, then call
`commit_metadata_stage_batch` at the original revision. The helper never calls MCP,
changes local records, or grants Stage approval. It refuses to overwrite output.

## Prepare the Stage review

Run this after local validation and before asking for Stage approval.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\prepare-metadata-stage-review.ps1" `
    -ChangeSetPath "<absolute-GDS-path>\change-set" `
    -MetadataChangeSetId "<change-set-id>" `
    -ExpectedDraftRevision <revision>
```

macOS:

```sh
"./scripts/prepare-metadata-stage-review.sh" \
  --change-set "<absolute-GDS-path>/change-set" \
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

A successful expected Stage changes the global revision once but does not
change approved dataset hashes. A conflict, reconciliation, local edit, or
changed intended result requires a new review and approval.

## Record successful Stage results

Immediately after a successful Stage, compare every returned dataset/count with
the approved call, then record its one returned revision against every exact
SHA-256 from the fresh local review. For one dataset, PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\update-local-change-set-state.ps1" -ChangeSetPath "<absolute-GDS-path>\change-set" -MetadataChangeSetId "<change-set-id>" -ExpectedCurrentRevision <sent-revision> -ServerRevision <returned-revision> -ServerStatus "active" -StagedDataset "<dataset>" -StagedSha256 "<reviewed-sha256>"
```

macOS:

```sh
"./scripts/update-local-change-set-state.sh" \
  --change-set "<absolute-GDS-path>/change-set" \
  --change-set-id "<change-set-id>" \
  --expected-current-revision <sent-revision> \
  --server-revision <returned-revision> --server-status active \
  --staged-dataset "<dataset>" --staged-sha256 "<reviewed-sha256>"
```

For multiple datasets, pass all pairs to one updater invocation. PowerShell 5.1
uses one comma-delimited `dataset=sha256` value:

```powershell
powershell.exe -NoProfile -File ".\scripts\update-local-change-set-state.ps1" `
    -ChangeSetPath "<absolute-GDS-path>\change-set" `
    -MetadataChangeSetId "<change-set-id>" `
    -ExpectedCurrentRevision <sent-revision> `
    -ServerRevision <returned-revision> -ServerStatus "active" `
    -StagedPairs "source_object=<reviewed-sha256>,source_attribute=<reviewed-sha256>"
```

macOS uses one repeated `--staged-pair` per dataset:

```sh
"./scripts/update-local-change-set-state.sh" \
  --change-set "<absolute-GDS-path>/change-set" \
  --change-set-id "<change-set-id>" \
  --expected-current-revision <sent-revision> \
  --server-revision <returned-revision> --server-status active \
  --staged-pair "source_object=<reviewed-sha256>" \
  --staged-pair "source_attribute=<reviewed-sha256>"
```

Completion criterion: `stage_recorded=true`, `staged_dataset_count` equals the
Stage result, every compact `staged_dataset=name|count|sha256` line matches the
fresh review, and the local revision equals the Stage result. The helper checks
all files first and writes all staged markers atomically at the same revision.
It fails if any file changed after review or the Stage revision did not
increment by exactly one.

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
