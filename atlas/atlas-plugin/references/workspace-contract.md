# Workspace file contract

File contract for the [working method](working-method.md), enforced by shared workspace helpers and the extension. Model-derived Metadata work may use several owner-specific drafts inside the same working directory.

## Minimal layout

```text
<working-directory>/
  .atlas/
    session.json
    tasks/
      <task-id>.json
      <task-id>.evidence/
    temp/
  metadata/metadata-snapshot/
  model/model-snapshot/
  metadata-change-set/
  model-change-set/
  code/
  metadata-owners/tenant-<id>/       # only for additional Metadata owners
    metadata/metadata-snapshot/
    metadata-change-set/
```

Create only what is used. Task IDs are helper-generated opaque identifiers. Evidence folders appear only when there is evidence to retain. The existing Snapshot guides own their internal archive layout; do not move those files into `.atlas`.

## Model-derived Metadata owners

Keep the primary Tenant and single active Model fixed. When Model-derived work changes Metadata belonging to another authorized owner, register that owner in `metadata_owners` and use its own subtree. No additional session, Model Snapshot or working directory is required.

- The primary Metadata owner uses root `.`; another owner uses `metadata-owners/tenant-<verified-id>`. IDs are verified positive integers, not user-supplied path fragments.
- Both roots contain the same `metadata/metadata-snapshot` and `metadata-change-set` structure. Snapshot internals remain unchanged. Primary examples elsewhere use root `.`; helpers resolve the selected owner root before accessing Metadata.
- Ownership comes from `source_tenant_code` and verified Tenant identity. Physical GDS Connection placement is not ownership and does not alone create another subtree.
- Fetch/install the appropriate owner's Snapshot before authoring its draft. Read-only context may include other owners, but each effective Metadata write graph, local digest, validation report and Stage manifest contains one owning Tenant's permitted changes.
- Keep server Change Sets, locks, revisions, approvals and receipts independent per owner. Workbench can navigate owners; it must never combine their files into one Stage request or imply atomic Apply.
- If owner Snapshots disagree about a shared physical record, resolve its authoritative ownership/version before using it. Never select a winner by folder or overlay order.
- The same task can reference several owner batches. Approval may be collected together if each reviewed owner/digest is explicit, but partial success stays visible. Dependent work waits for every required upstream Apply.
- Model-derived selection does not grant another Tenant's write access or broader Binding eligibility. Missing authorization leaves that owner unresolved while independent work can continue.

## Session

| Field | Shape and meaning |
|---|---|
| `schema_version` | String `"1.0"`; workspace file format, unrelated to Snapshot format or server revision. |
| `tenant` | Verified primary `{id, code}` plus optional display `name`. Positive numeric ID and nonempty code; identity comes from authorized context, not the directory name. The primary Tenant does not change when selecting another Metadata owner. |
| `model` | Verified `{id, name}` or `null`; at most one active Model. |
| `metadata_owners` | Optional map keyed by verified Tenant ID as a string. Each value is `{id, code, root}` with optional display `name`; include the primary owner with root `.` when Metadata is used. Additional owners use the subtree above. |
| `sql` | Optional `{policy, environment}`. Policy is `never`, `essential` or `proactive`; environment is `dev`, `qa`, `stg` or `prod` when relevant. Stores resolved choices, not authorization. |
| `active_task` | Task ID or `null`; navigation and resumption only. |
| `refresh_required` | Optional list of `{area, owner_tenant_id, reason, evidence}`. Helper-maintained known invalidations; for Model the owner is its Tenant. Absence does not prove remote freshness. |
| `operations` | Optional object: `metadata` maps owner Tenant IDs to current operation-evidence paths; `model` points to the current Model operation. Starting another task or selecting an owner must not hide a staged, failed or uncertain operation. |

Session does not duplicate Snapshot versions, server revisions, approval flags or task status lists. The selected filesystem root is the working directory; do not persist an authoritative absolute path that breaks when the directory moves. Display names never replace identity checks.

## Task

Each task has `schema_version:"1.0"` and the five agreed sections. Only `outcome` is required beyond the version; add other sections when useful.

| Section | Shape and ownership |
|---|---|
| `outcome` | Short string describing the requested result. Agent/user editable. |
| `inputs` | Object containing workflow, selected scope, relevant files and optional `snapshots` bindings. Scope prose remains flexible; helpers capture verified technical bindings. |
| `work` | List of `{path, purpose}` for workspace-relative outputs. No copied output contents. |
| `progress` | Free-form string; concise notes, decisions, optional plan, blockers and next action. No mandatory stage enum. |
| `evidence` | List of `{path, purpose}` pointing to retained reports and operation records. References do not themselves prove success. |

Each `inputs.snapshots` entry identifies `area`, `owner_tenant_id`, relative `manifest_path`, `snapshot_id`, `manifest_sha256`, and Model `model_revision` where applicable. Capture from verified installed files; never invent a Metadata revision. Include all inputs actually used, including a Model Snapshot that selected a Metadata enrichment scope. Several owner snapshots remain distinct entries.

Plain Markdown lists can be used inside progress text. A simple explanation needs no task. Helper identity/evidence fields are never hand-edited to manufacture a successful operation.

## Durable operation evidence

Keep each reviewed batch's operation record under `.atlas/tasks/<task-id>.evidence/<operation-id>.json`, with referenced reports and manifests beside it. Operation IDs are helper-generated. Update that operation's verified checkpoints through expected-content checks; preserve earlier reviewed versions and uncertain attempts when beginning another operation.

Common bindings: format version, operation/task IDs, Metadata/Model area, actual owner identity, safe configured backend identity, Snapshot inputs and local digest. Keep referenced report/manifest paths and digests. Never store connection values, credentials, raw tool dumps or raw user acknowledgements.

| Checkpoint | Evidence to retain when reached |
|---|---|
| Local validation | Validator/rules version, checks performed, actual outcome and bounded report, bound to all inputs and content. |
| Local acknowledgement | Acknowledgement source/time plus the exact reviewed local digest/report bindings; no raw conversation text. |
| Server draft | Actual Change Set ID and observed revision/status. |
| Stage | Bounded receipt with accepted digest, resulting draft revision and verified server fingerprint; attempt/idempotency references when returned. |
| Server validation | Actual result for the exact draft revision, including returned candidate digest/fingerprint where available. |
| Apply approval | Separate acknowledgement bound to the complete server action review and validated revision/content. |
| Apply | Actual bounded result/receipt, including resulting revision when returned. Unknown remains unknown until checked. |

Retain actual supported result fields; do not manufacture identifiers or compare local digests, server fingerprints and validation candidate digests as interchangeable values. Helpers/extension maintain these checkpoints. Editable progress and `approved:true` flags cannot grant permission or replace missing proof.

## Consistency rules

- Paths stored in task/session references are workspace-relative. Resolve and validate them within the chosen root; Stage's public manifest-path argument remains the verified absolute path required by its tool contract.
- Metadata drafts belong to their owner root; the Model draft belongs to the primary workspace. Neither belongs exclusively to an individual task. A batch may include earlier tasks' edits; review its complete contents. A task/owner switch does not transfer approval or clear an operation pointer.
- Write evidence before updating a pointer to it. Detect external edits before replacing state; never claim a multi-file update is atomic. A recoverable interrupted write must leave enough evidence to inspect its actual outcome.
- Content/input changes invalidate matching validation/review checkpoints. Preserve the records as history without presenting them as current approval.
- `.atlas/temp/` contains disposable material only. Required reports, approved manifests and recovery evidence stay durable. Same-directory temporary files needed for safe replacement may sit beside their destination.
- The [Change Set lifecycle](change-set-lifecycle.md) owns transition and approval rules. This contract only owns storage and bindings; backend authorization and validation remain authoritative.
