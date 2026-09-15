# Editing metadata

Read before constructing metadata records, together with the shared [record-state rules](../record-state.md). The workflow owns intake, review, and submission; these rules govern record content.

| Operation | Rule |
|---|---|
| Match existing records | Use the complete normalized natural key from the current dataset contract. Resolve tool/Snapshot schema differences before writing. |
| Update a record | Start from its complete effective record, including earlier pending edits; preserve unrelated supported fields. An older template or baseline copy must not silently discard them. |
| Add a record | Populate required fields from verified definitions. Required nullable fields must be present; use `null` when permitted. Select reference values from registered records. |
| Set activation | Default is_active=true on every new editable record that has this field, unless the user requests otherwise. Write required fields explicitly; a default does not make omission valid. Preserve existing activation values during unrelated edits; adding a child does not reactivate its parents. |
| Change an existing key | Manual database work by the user. Give instructions; never execute the change or simulate it by creating a replacement and deactivating the original. |
| Change related records | Check relationships against Snapshot plus all pending records, including newly created parents. Inspect records whose validity the change could affect. |

Use the [affected table pages](index.md) for exact field rules and [validation](validation.md) to check the effective result. Keep changes bounded by the user's outcome.

Use the shared [Metadata Snapshot guide](../snapshots/metadata.md) for files, targeted reading and draft updates. Keep edits in the local Metadata Change Set and accumulate the related batch before submission; leave Snapshot files unchanged.

## Framework-dependent values

Field names and descriptions help navigation; applicable orchestration behavior determines how values are used. Current schemas still govern types, required fields, keys and references.

1. For standard requests, propose one default configuration from confirmed rules or verified working metadata for the same connector/framework. Explain its basis briefly; preserve unrelated existing values and runtime state.
2. For custom behavior, unclear descriptions or conflicting evidence, ask: “Please provide the relevant orchestration code or a working example showing how these fields are used.” Read only the relevant consumer code; users need not supply the whole framework.
3. Check where the fields are read, combined, substituted and passed to the next step. Resolve the values and interpretation for that framework version; do not assume behavior from names or stale descriptions.
4. Record the confirmed behavior and source/version with the task. Promote a reusable rule only after confirming its scope. If an essential detail remains unknown, keep the affected value proposed and continue independent work.

## Manual natural-key changes

User-confirmed Atlas rule: renaming or changing an existing record's natural-key fields requires the user to make the database correction manually. This includes Object/Attribute names, group names, mapping endpoints, and Process order/location/executable. New record creation remains ordinary authoring; Attribute ordinal is not a natural-key field.

When requested:

1. Identify the current and intended complete keys, affected records, and dependencies from verified schema and Snapshot evidence.
2. Give the user concise database-change instructions, including uniqueness/reference checks and how to verify the result. Identify missing facts instead of inventing SQL or assuming every reference needs rewriting.
3. Leave the affected change unstaged. Do not execute database updates, provide an automated rename helper, or substitute a create/deactivate sequence.
4. After the user confirms completion, obtain a fresh Snapshot and reconcile affected pending work before continuing. Preserve the earlier draft for review; do not submit it against the old identity.

## Context that must remain explicit

- Follow [Object ownership and physical identity](tables/object.md#ownership-and-physical-identity) for owner versus physical Tenant, Zone placement, mixed targets and mapping endpoint keys.
- Foundational/reference rows cannot be staged in Metadata Change Sets. Missing registrations require the existing operator workflow.
- Follow [record state](../record-state.md) for Object/Attribute protection, inactive history and read versus change eligibility.
- Local checks cannot certify current server state. Do not turn unavailable context into a pass.

## Reusable findings

- Keep request-specific decisions with the task.
- Reuse existing table explanations and helpers when semantics match.
- Add general terminology, consumer rules, or validation rules only after establishing their meaning and scope.
- Add a reusable script when a real repeated operation warrants it; do not create one wrapper for each field or validation ID.
