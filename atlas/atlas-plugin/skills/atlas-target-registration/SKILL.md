---
name: atlas-target-registration
description: Register or update Silver or Gold target Object and Attribute metadata from an applied Logical or Dimensional model, and optionally prepare local Databricks creation DDL. Use before Entity Binding; registration does not deploy tables or author Mapping.
---

# Target registration

Verify available capabilities; do not invent commands or claim generated scripts were executed.

## Establish target context

1. Follow the [working method](../../references/working-method.md); resolve missing Tenant, absolute working directory, Model and **Silver or Gold** selection. Reuse supplied context and preserve pending work. SQL policy/environment matter only when evidence queries are needed, not for executing generated DDL.
2. **Ask target schema first:** "Which schema should contain these [Silver/Gold] targets? Use one schema for all selected Entities, or list Entity-specific overrides." Reuse an explicit answer; show the resolved default and complete override assignments. Do not choose a schema from a source Connection or guess unresolved splits.
3. Load the bound [Model](../../references/snapshots/model.md) and [Metadata](../../references/snapshots/metadata.md) Snapshots. Select active applied Logical Entities/Attributes for Silver, or active applied Dimensional Entities/Attributes for Gold. Unapplied modeling changes must complete their governed lifecycle before they become registration inputs.
4. Resolve the actual data/metadata owner for each target from its contributing source ownership. For single-origin targets, use that owner; **do not default to the Model Tenant**. Follow [Object ownership](../../references/metadata/tables/object.md#ownership-and-physical-identity) for explicitly shared/mixed targets. Ask for unresolved ownership of generated/standalone targets; never invent a source to resolve it.
5. Resolve each owner's configured active GDS Connection through the Metadata Tenant's complete configured Connection key. Verify the exact Connection and global-data-store flag. Silver/Gold placement is this GDS Connection, **not a contributing Source Connection**. Read [target definition](references/target-definition.md#resolve-placement-and-ownership) for the read-only MCP limitation.
6. Follow [record state](../../references/record-state.md); inspect existing target records, locks, activity and conflicts. Resolve [existing work and update scope](../../references/working-method.md#existing-work-and-update-scope) before authoring. Show new/affected targets and reuse unchanged registrations; do not interpret workflow entry as full regeneration. Start/reuse the local Workbench through its verified launcher.

## Choose DDL output

Ask only when unanswered: **"Generate creation DDL too? Choose: No DDL; All registration targets; Selected tables (list names); Entire model (current or model name)."** For a change-driven update, narrow these choices to **No DDL**, **Affected targets**, or **Selected affected targets**; do not offer unchanged tables unless the user explicitly asks for broader output. Reuse an explicit prior choice. For selected tables or a different Model, resolve exact Entity identities, layer and schema assignments before generation. Record the resolved scope with the task.

Follow [DDL scope](references/target-definition.md#choose-ddl-output): DDL is optional and its table selection is independent of Metadata registration. A broader DDL request does not expand Metadata changes or authorize Stage/Apply. Each selected table receives its complete definition, not selected columns.

## Prepare registration locally

1. Read [target definition](references/target-definition.md). Build one resolved target definition per selected Entity from its applied model. Produce complete Metadata records only for the registration scope, and local DDL only for the requested DDL scope. Keep the source provenance, owner, schema assignment and Model revision with the task evidence.
2. Use the shared [Object](../../references/metadata/tables/object.md) and [Attribute](../../references/metadata/tables/attribute.md) field contracts plus installed schemas. Follow [Metadata editing](../../references/metadata/editing.md), [naming](../../references/model/naming.md) and [keys/audit](../../references/model/keys-and-audit.md); do not duplicate or reinterpret their rules here.
3. Match exact existing targets before creating records. Reuse compatible targets and make supported compatible updates to unlocked Metadata in this workflow. Preserve unrelated fields, inactive identities and existing locks. Present incompatible definitions or actual-table changes for manual resolution; never generate a destructive replacement or rename workaround.
4. Save complete affected arrays in `metadata-change-set/silver_object.json` / `silver_attribute.json` or the Gold equivalents, under the appropriate owner context. Keep requested DDL local; report **not requested** when declined. Follow the target-definition projection/checks; do not infer completion from a generated file.
5. Run [local validation](../../references/local-validation.md), shared [Metadata checks](../../references/metadata/validation.md) and the [registration checks](references/target-definition.md#registration-checks). Repair affected failures before dependent work. Record unsupported checks as pending, not passed.
6. Complete the related local batch, then follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) for Workbench review, extension staging, server validation and separate Apply approval of Metadata changes. Skip that lifecycle when the request produces only local DDL and no Metadata changes. Check input freshness before handoff/Apply; if a fresh Snapshot is required, reconcile it with pending work rather than replacing the draft blindly.
7. After **verified Metadata Apply**, fetch/install a fresh Metadata Snapshot in the affected owner context and verify the registered targets. Report local DDL separately from registration status. Stop before [Entity Binding](../atlas-entity-binding/SKILL.md), Mapping, Process registration or Code Generation.

## Gotchas

- Current Model Binding requires target ownership to equal the Model Tenant. A correctly registered target with another owner may therefore be unbindable today. Surface this before preparing a downstream-ready result; never change true ownership to satisfy that limitation.
- Multiple owners require separate Metadata Change Sets and their governed authorization/locks. They do not form one atomic Apply.
- Applying Metadata does not create or alter a Databricks table. `execute_databricks_sql` cannot execute persistent target DDL; generated DDL remains a user handoff artifact.
- Schema/Connection/name changes to existing metadata keys follow the shared manual-change procedure. A new default schema is not permission to move or recreate existing targets.
- Existing physical-table structure may differ from registered Metadata. State the known baseline and unresolved differences; `CREATE TABLE IF NOT EXISTS` does not reconcile them.
