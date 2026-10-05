# Workspace state and evidence

Saved 0.1.x workflow labels are historical task context, not installed skill paths. Route their outcome to the current skill: Guided/Grill Me labels share the logical or dimensional skill, Custom investigations use investigate, physical enrichment uses metadata, and target/Process registration uses registration. Do not rewrite a saved task or reset drafts merely to rename a workflow.

## Workspace records

```text
<working-directory>/
  .atlas/
    session.json
    tasks/<task-id>.json
    tasks/<task-id>.evidence/
    temp/
  metadata/metadata-snapshot/
  model/model-snapshot/
  metadata-change-set/
  model-change-set/
  code/
  metadata-owners/tenant-<id>/      # additional Model-derived Metadata owners only
    metadata/metadata-snapshot/
    metadata-change-set/
```

Create only what the work needs. The [workspace file contract](../workspace-contract.md) defines session/task fields, owner roots and durable evidence bindings; the shared runtime validates these shapes.

- Session: Tenant identity, optional active Model identity, SQL selections where applicable, sub-agent policy, active task pointer, known refresh requirement. Model selection is unnecessary for work that does not need a Model.
- Task: outcome, inputs, work/artifact paths, progress, evidence. An optional plan is part of progress. Store precise input snapshot identities/revisions.
- Technical fields and verified operation results are maintained by helpers; task narrative remains concise and editable. Validation, approval and submission state must not depend on fixed task stages or editable progress text.
- Temporary archives/scripts/intermediates use `.atlas/temp/`. Material needed for resumption or approval must have durable storage before cleanup.
- A question or simple read need not create a task. Substantial authoring uses one task per meaningful outcome, not one per tool call.

Reuse this workspace across workflows and tasks for its primary Tenant/Model. Atlas Local Workbench opens the working-directory root, containing `.atlas` and the sibling data folders. Users and agents edit the same local Change Set files; Snapshot files remain immutable. Metadata owner selection resolves its subtree and independent operation evidence without changing the Model context. See the [Atlas Local Workbench guide](../../docs/usage-guide.md#atlas-local-workbench) for opening, resuming and handling concurrent local edits.

## Snapshot use

- Read the shared [Metadata Snapshot guide](../snapshots/metadata.md) or [Model Snapshot guide](../snapshots/model.md) for layout, targeted reads and local edits. Workflows select inputs; these references explain how to use them.
- Snapshot manifests identify installed data. Task inputs identify the version used for that work. Avoid manually copying version state into session fields.
- Fetch a fresh Metadata Snapshot when starting metadata authoring. Keep that baseline through the related local work, including additional tasks and edits within the same workflow; do not fetch once per task or edit. Other workflows declare their input freshness policy at entry.
- Logical and Dimensional skills reuse valid bound inputs. Show identities and known refresh requirements; fetch missing inputs and reconcile required refreshes before dependent work. Ask only when an actual conflict requires a choice; never replace the baseline beneath pending work. See [Logical context](../logical-build/context.md) and [Dimensional context](../dimensional-build/context.md).
- A resumed unfinished workflow retains its baseline and draft until any required refresh is reconciled. Never replace the baseline underneath pending work. A local file timestamp cannot prove freshness.
- Model revision can be compared with authoritative server state. Metadata has no Tenant-wide revision counter; retain existing freshness, Tenant Lock, and server-validation protections.
- An external change, revision conflict, completed manual correction or successful Apply can require a refresh before affected work continues. Preserve the draft and reconcile its base/current/proposed records rather than silently overwriting them.
- Snapshot files are immutable applied-state inputs. Local Change Set files hold complete proposed records. Read the effective result: pending records replace matching Snapshot records by canonical key, while untouched records remain.
- Read manifest/catalog first, the relevant dataset schemas next, and only the required records and dependencies. Helpers may scan complete files internally; return bounded context to the agent. Incomplete lookup rows and truncated selections do not establish complete coverage.

## Progress, review, and handoff

- Plans can change as evidence changes; changing plan text does not itself change approved data.
- Approval validity depends on the actual reviewed content and relevant evidence bindings. Helpers must determine validity; the [Change Set lifecycle](../change-set-lifecycle.md) defines review and receipt requirements.
- Preserve concise decisions with evidence references; omit raw prompts, raw physical rows, secret values/references, signed URLs, and raw tool dumps.
- Author against the effective Snapshot-plus-pending result. Backend authorization and validation remain authoritative.
- Generate resume/handoff summaries from current records and checks. Do not maintain a second independent checklist.
- Report the actual achieved state: drafted, validated, reviewed, staged, or applied. Required unresolved work prevents a claim of completion.
- Keep generated SQL/DDL separate from permission to execute it. Use governed submission/Apply capabilities and existing user authorization; initialization answers do not approve unseen mutations.
