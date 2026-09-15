---
name: atlas-code-generation
description: Generate framework transformation files from applied Logical or Dimensional Mapping. Choose target/System file grouping, translate complete Mapping instructions into SQL, preserve source assignments and validate locally before the shared review and Apply process.
---

# Code Generation

Generate the requested transformation artifacts from approved Mapping. Registration DDL, Process configuration and Validation authoring have separate workflows.

## Establish inputs and output

1. Follow the [working method](../../references/working-method.md). Reuse Tenant, working directory, Model, Logical/Silver or Dimensional/Gold route and requested targets. Resolve SQL policy/environment only for optional execution-based evidence; writing SQL does not execute it.
2. Require active applied Mapping and Binding. Follow [Model Snapshot](../../references/snapshots/model.md) freshness rules and preserve pending work. Load each selected target's [complete Mapping view](../../references/model/mapping-documents.md#complete-context-for-coding-and-validation), current Code and source-System assignments. Do not reconstruct missing transformation decisions from upstream models.
3. Check [record state](../../references/record-state.md) and the [Code record contract](../../references/model/generated-code.md). Read saved code from the Snapshot plus pending/local edits, then resolve [existing work and update scope](../../references/working-method.md#existing-work-and-update-scope). Show new/missing and affected artifacts/Systems; ask the contextual selection question unless already answered. Preserve locked/unchanged artifacts and assignments. Read full existing content before updating it; resolve input changes or stale code rather than treating an old file as current.
4. **Ask for file grouping; do not assume a default.** "One file per target containing its Systems, or separate files per System and target? Any target-specific exceptions?" Reuse an explicit choice already supplied for this work. Show concrete filenames and contributing Systems. No separate file per source table is implied when several sources form one target branch.
5. **Generate SQL in the first release.** Follow [release scope](../../references/release-scope.md). Preserve existing Python artifacts/assignments without converting them; new Python generation is deferred until its consumer contract is established. Explain that limitation for an explicit Python request and continue independently requested SQL work. Do not offer unsupported generation or routinely ask for a language selection.
6. Show the proposed artifact list and a small representative structure. Reuse prior decisions; ask only about unresolved choices or material exceptions. This preview does not replace review of the final content in the already open Workbench before Stage/Apply.

## Generate and check locally

1. Follow [SQL generation](../../references/code-generation/sql.md). Translate Object steps into coherent preparation/join/projection stages and apply Attribute expressions at the correct stage. Each artifact contains its own prerequisites and ends with one target's explicit runtime projection. A Python request does not authorize a silent SQL substitution.
2. Preserve Mapping grain, joins, predicates, filter placement, keys, casts, null/invalid behavior, runtime parameters and cross-System policy. Missing or contradictory rules return to Mapping for correction and governed Apply; do not hide a design change inside code. Continue unaffected targets where possible.
3. Apply the chosen layout without changing semantics. Combined files align all assigned branches and implement the specified reconciliation. Separate files remain self-contained and must be valid under Mapping's collision and dependency rules. If a requested split cannot preserve those rules, explain the concrete conflict and resolve the layout or Mapping before authoring affected files.
4. Save reviewed source files under the workspace's `code/` output area with collision-safe placement. Store only a filename in `artifact_name`; local folders are not artifact identity fields. Serialize the exact intended file content into complete `generated_code` records and maintain `generated_code_source_system` records. Do not invent role/path/digest fields or assume edits to a file automatically update the Change Set.
5. Verify that every active mapped System for an authored target has exactly one active artifact assignment. Combined files have several assignments; separate files have disjoint assignments. Preserve valid unaffected files when regenerating a subset. Never discard protected assignments or silently strand a mapped System when regrouping files.
6. Run [local validation](../../references/local-validation.md), Code record checks and the [SQL content checks](../../references/code-generation/sql.md#local-content-checks). Compare file text with record content. Static parsing and semantic review are required checks; optional Databricks probes follow the SQL guide and saved policy. Report unsupported checks as unverified.
7. Review the complete related local batch: artifact names, assigned Systems, Mapping changes addressed, final output columns and check results. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md); do not Stage/Apply per file. After verified Apply, refresh the Model Snapshot and confirm saved content/assignments and authoritative freshness state.

Code Apply stores artifacts; it does not deploy or execute them. Report authored, validated and applied states separately. Continue to Validation or Process metadata only when requested or already part of the agreed journey; Gold modeling is not required before validating Logical code.

## Targeted exceptions

- Existing code is locked: preserve it and report the affected work; no duplicate filename or alternate artifact to bypass the lock.
- Multiple files need the same source System: the current assignment contract cannot represent that as independent active artifacts for one target. Resolve a supported self-contained artifact layout; no unassigned helper file workaround.
- A runtime placeholder or cross-catalog access rule is unknown: request the relevant consumer contract/code. Do not invent parameters or grant access. New Python generation follows the deferred first-release boundary.
- Mapping and code disagree: fix accidental translation errors here; intentional transformation changes belong in Mapping first.

## Preserve edited and locked artifacts

A lock on a selected Code artifact blocks every content change to that artifact; a lock on an unrelated artifact does not block the selected target. Attribute/Mapping locks preserve their governed field semantics. Read Snapshot, pending Code and the existing file before updating: retain manual changes compatible with the applied Mapping, and resolve conflicting manual-versus-Mapping intent with the user before replacement. Never silently choose generated content over a differing local file.
