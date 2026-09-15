---
name: atlas-metadata-authoring
description: Create or update an existing Tenant's editable physical metadata, ingestion mappings, Copy configuration, and Process configuration. Use for focused metadata corrections or broader registration requests. Business-meaning investigation and description enrichment use metadata enrichment.
---

# Metadata authoring

Produce the metadata changes needed for the user's outcome. A request to change one Copy setting does not require a complete ingestion setup. Preserve explicit scope and existing authorization.

Focused Process corrections can stay here. For registering applied generated artifacts with their runtime locations and dependencies, use [Process metadata](../atlas-process-metadata/SKILL.md); both workflows share the same table/editing contracts.

## Establish context

1. Follow the [working method](../../references/working-method.md) when starting or resuming work; reuse it if already loaded. Resolve the Tenant and absolute working directory. Consult [atlas terminology](../../references/terminology.md) when a domain term is unclear.
2. Metadata authoring requires a Metadata Snapshot, not a Model by default. Use the shared [Snapshot guide](../../references/snapshots/metadata.md). Fetch fresh context when starting this workflow, then reuse the baseline and local Change Set through its related tasks and edits. Preserve unfinished work on resume; require Model context only when the request needs it.
3. Use [intake and examples](references/intake-and-examples.md) for missing authoring decisions. Ask related questions together. SQL policy/environment are needed only when SQL evidence access is relevant.
4. Connect the resolved working directory in the Workbench opened at startup. If launch or directory access failed, report that limitation.

## Select the relevant references

Use the [table index](../../references/metadata/index.md) to find affected tables. Read their pages for keys, fields, dependencies, change behavior, and checks.

Validate related Snapshot records, but open their documentation only to resolve a new/changed relationship, unclear meaning, or validation failure. Links describe relationships; they are not instructions to load every linked page recursively. Foundational and lookup tables are read-only inputs.

## Author the requested change

1. Follow [editing rules](../../references/metadata/editing.md). Identify records by their complete normalized natural keys and distinguish owning Tenant from physical placement.
2. Use the installed Snapshot catalog and affected dataset schemas for the bound contract. Use local description helpers where available; request `describe_metadata_dataset` only when needed to resolve missing or mismatched contract information. Resolve mismatches before writing.
3. Read complete effective records and relevant dependencies, including pending changes already made locally. Preserve unrelated supported fields and earlier edits; do not copy a baseline row over its pending version. Construct new records from verified definitions and registered references; never invent lookup values or caller-supplied database IDs.
   For framework-dependent fields, propose defaults using [confirmed conventions](../../references/metadata/editing.md#framework-dependent-values). Request relevant orchestration code when custom behavior, ambiguity or conflicting evidence requires it; names alone do not define execution.
4. Keep an optional, revisable plan in the task. Record material decisions and unresolved evidence. A task may touch several datasets; proposed references can target other records in that same change set.
5. Follow [local validation](../../references/local-validation.md), using the [Metadata checks](../../references/metadata/validation.md) and affected tables' checklists. Fix failures and rerun affected checks. If blocked by missing facts or capabilities, preserve the draft and report the blocker. Separate actual passes, review items, and checks awaiting the server; a checklist is not an executable validator.
6. Complete the related local edits, then follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md): Workbench review, extension staging, verified server validation and separate Apply approval. Submit at a meaningful completion/dependency boundary, not after each edit or task.
7. Record verified results and receipts as that procedure requires. Report whether the requested outcome is drafted, locally validated, reviewed, staged, server-validated or applied; do not infer completion from plan checkboxes.

## Gotchas

- Natural-key changes to existing records are manual database work by the user. Provide [manual-change instructions](../../references/metadata/editing.md#manual-natural-key-changes); never execute the change or simulate it through new records and deactivation. This includes Process execution order, which is a key field.
- Follow [record state](../../references/record-state.md): an existing locked Object protects itself and its Attributes, including proposed additions. Inactive history is preserved.
- Do not execute generated DDL, run ingestion, deploy, or schedule a Process merely because its metadata was authored.
- Keep business-meaning inference and enrichment separate. Supplied corrections to descriptions can remain ordinary authoring.
- Preserve useful task findings in durable evidence. Promote general rules into plugin references only after confirming their applicability.
