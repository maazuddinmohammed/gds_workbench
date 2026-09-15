# Logical build context

Shared entry for Guided and Grill Me. This page owns input readiness; each skill owns its sequence and interaction.

1. Follow the [working method](../working-method.md). Resolve missing Tenant, absolute working directory, SQL policy, applicable environment and Model. Reuse valid supplied/saved choices and the selected workflow; Atlas routes to a dedicated Guided or Grill Me skill.
2. Show existing session context and unfinished work. Ask "Continue this session or start new work?" unless already answered. Preserve unfinished drafts and their Tenant/Model bindings.
3. Show available Metadata/Model Snapshot identities, Model revision and known refresh requirements. Ask "Fetch fresh snapshots or use the existing snapshots?" unless already answered. Fetch missing required inputs before dependent work.
4. Follow the [Metadata](../snapshots/metadata.md) and [Model](../snapshots/model.md) guides for acquisition, placement and reading. Reconcile pending work before baseline replacement; reuse does not override identity or freshness conflicts.
5. Resolve requested Objects from applied Model Input Scope without changing membership. Follow catalog prerequisites. Connect the resolved directory in the already open Workbench.
6. Read [record-state rules](../record-state.md) before authoring. Identify protected and inactive records; locked active inputs may still be read and used.
7. At a new build, show effective [naming](../model/naming.md) and [key/audit policy](../model/keys-and-audit.md). Reuse approved choices; ask only about missing or conflicting settings. Missing audit types/nullability need the actual Model template, not guesses.

## Switching workflows

When the user switches between Guided and Grill Me, preserve session context, snapshots, evidence and pending records. Update the selected workflow in the existing task context. Load only the destination skill. Guided assesses its phases using the existing-result rules; switching alone never discards work or triggers a redo, Stage or Apply.
