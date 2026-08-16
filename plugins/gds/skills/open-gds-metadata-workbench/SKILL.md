---
name: open-gds-metadata-workbench
description: Launch the bundled local GDS Data Workbench to browse or edit downloaded Metadata or Model Snapshot and Change Set files. Use only when the user explicitly asks to open the local table utility; do not use for MCP reads or server Change Set operations.
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
   datasets and edits only the 16 eligible Change Set datasets. Model exposes all
   19 Model Change Set datasets, including mapping.
4. The utility reuses or creates the matching `GDS/change-set` or
   `GDS/model-change-set` local draft. No Tenant Lock is needed for local drafting.
5. Ask the user to save inside the utility and tell you when finished. Do not
   assume that an interaction occurred or inspect all local rows afterward.

## Boundary

The utility only reads local Snapshot files and writes complete arrays to the
matching local Change Set. For Model work it can export a proposed aggregate Model
JSON with the baseline revision; that file is local and unapplied, not an immutable
server Snapshot. It never calls MCP, acquires a Tenant Lock, Stages, validates on the
server, Applies, or changes PostgreSQL.

For Metadata Stage or Apply, switch to `$manage-gds-metadata`. For Model Stage or
Apply, switch to the matching Model-building skill and its governed workflow. Both
paths must check the Tenant Lock, reconcile a resumed server draft, ask before Stage,
validate on the server, and ask separately before Apply. Use `get_model_snapshot`
when an authoritative immutable Model Snapshot is required.

Never claim that locally saved records are authorized, Staged, validated, or
applied.
