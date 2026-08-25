---
name: open-gds-metadata-workbench
description: Launch the bundled GDS Data Workbench to browse or edit a local Metadata or Model Snapshot or Change Set. Use when the user asks to open the utility, inspect local tables, select or copy Snapshot rows, edit a local draft, or save local changes; do not use for MCP reads or server Change Set operations.
---

# Open GDS Data Workbench

Open the bundled static utility in the default browser. It has no server,
Python, Node, network, or MCP dependency.

## Launch

Use this skill directory as the process working directory. On Windows
PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\open-gds-metadata-workbench.ps1"
```

On macOS:

```sh
"./scripts/open-gds-metadata-workbench.sh"
```

Require `ok=true` and `opened=true`. The utility opens the default browser.
Direct folder editing requires current Chrome or Edge. If the default browser
does not support it, ask the user to open the same bundled
`assets/workbench/index.html` in Chrome or Edge.

## Hand control to the user

1. Ask the user to choose either the current project folder or its exact `GDS`
   folder. Browser permission is always explicit.
2. Require `GDS/metadata-snapshot` or `GDS/model-snapshot`. If both exist, ask the
   user which one to open. The utility verifies each opened member against its
   `manifest.json` before displaying it.
3. Explain that Snapshot rows are immutable. Metadata exposes all 29 Snapshot
   datasets and permits copying only the 16 eligible datasets. Model exposes all
   19 Model Change Set datasets, including mapping.
4. In Snapshot, select one or more eligible rows and choose **Copy to Change Set**.
   The utility preserves existing pending edits and switches to the matching local
   Change Set. Edit only there.
5. The utility reuses or creates `GDS/change-set` or `GDS/model-change-set`. Save
   remains in the top draft bar. Copied unchanged rows must be edited or removed
   before handoff. No Tenant Lock is needed for local drafting.
6. Do not assume that a user interaction occurred or inspect all local rows afterward.

## Boundary

The utility only reads local Snapshot files and writes complete arrays to the
matching local Change Set. For Model work it can export a proposed aggregate Model
JSON with the baseline revision; that file is local and unapplied, not an immutable
server Snapshot. It never calls MCP, acquires a Tenant Lock, Stages, validates on the
server, Applies, or changes PostgreSQL.

For Metadata Stage or Apply, switch to `$manage-gds-metadata`. For Model Stage or
Apply, switch to `$manage-gds-model`. Both
paths must check the Tenant Lock, reconcile a resumed server draft, ask before Stage,
validate on the server, and ask separately before Apply. Use `get_model_snapshot`
when an authoritative immutable Model Snapshot is required.

Never claim that locally saved records are authorized, Staged, validated, or
applied.
