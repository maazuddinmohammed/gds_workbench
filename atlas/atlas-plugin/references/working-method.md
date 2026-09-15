# atlas working method

Shared operating rules. Use the [Atlas runtime guide](../docs/runtime-guide.md) for concrete commands; workflow references own domain decisions.

## Initialize or resume

1. Resolve Tenant name/code. Offer MCP `list_tenants` when the user asks for accessible choices.
2. Resolve an absolute working directory before setup. Reuse a valid saved directory unless the user selects another. If neither a supplied nor valid saved directory is available, state that the actual current directory will be used and continue. An invalid supplied path requires correction, not silent fallback.
3. Show relevant existing atlas context and unfinished work. Follow a clear request; ask "Resume this task or start new work?" only when existing unfinished work makes intent unclear. Preserve unfinished artifacts.
4. Resolve the workflow before asking for Model or SQL selections. Reuse valid saved choices.
5. Ask for a Model only when the workflow/request needs it; list applicable choices when requested. A working directory has one primary Tenant and at most one active Model. Model-derived Metadata changes for other owners stay in that directory in [separate owner subtrees](workspace-contract.md#model-derived-metadata-owners). A different primary Tenant or Model uses another working directory; never silently replace existing identity or drafts.
6. When evidence queries are relevant, resolve SQL policy: Never, Essential, Proactive. Essential resolves blocking gaps; Proactive also permits useful investigation. When needed, use selected environment or `dev`; choices are `dev`, `qa`, `stg`, `prod`.
7. The workflow identifies its required snapshots. Prepare current inputs without replacing snapshots beneath pending work. For authoring/review or an explicit request, open/reuse the local Workbench after readiness checks using a supported launcher. A simple read-only explanation can proceed without launching it.

The [Atlas entry skill](../skills/atlas/SKILL.md) routes metadata authoring, metadata enrichment, logical build, target registration, entity binding, mapping, Gold build, code generation, validation, process metadata, and [Custom](../skills/atlas-custom/SKILL.md). Custom derives its requirements from the requested outcome; it does not expand tool permissions.

## Current initialization capabilities

The shared procedure above owns question order and choices; the governed MCP contracts below resolve verified identity.

| Capability | Exact current contract / use |
|---|---|
| `list_tenants` | `schema_version:"1.0"`, `page_size` 1–200 (default 50), optional `cursor`. Returns active authorized Tenant IDs/codes/names and `next_cursor`; follow pages when needed. |
| `get_tenant_details` | Positive `tenant_id`, `schema_version:"1.0"`; details include at most 200 relevant Connections. Respect `connections_truncated`; this list has no pagination. |
| `list_models` | Positive `tenant_id`, `schema_version:"1.0"`, `page_size` 1–200 (default 200), optional `cursor`. Returns active Model IDs/names/revisions/policies/templates; follow `next_cursor` with unchanged Tenant/page size. |
| Supplied names/codes | Reuse verified identity context or resolve through authorized listings. No direct name resolver or `get_model_details` tool is established. A lookup does not require showing an unsolicited menu. |
| Atlas command discovery | `node scripts/atlas-local.js command-contract --command <name>` from the installed plugin directory. |
| Atlas `session-init` | `--root <absolute-directory> --tenant <verified-code> --tenant-id <verified-id>` creates `.atlas` in that directory or reuses the same identity. Optional Model arguments bind the first Model. |
| Atlas `status` | `--session <working-directory>` reads saved context and flexible tasks. `task-select` resumes a task; `model-select` attaches the first Model. |
| Atlas Workbench | `bash scripts/open-workbench.sh` or `scripts/open-workbench.ps1`, no arguments; opens bundled HTML. Select the working-directory root through browser directory access. No server or port is needed. |

Set saved SQL choices with `sql-policy --session <path> --policy never|essential|proactive [--environment dev|qa|stg|prod]`. The selected skill still owns its Snapshot, scope and prerequisite checks. The [runtime guide](../docs/runtime-guide.md) describes owner registration, input binding and actual helper limits.

Open Workbench once for new authoring context and reuse it. Workbench Refresh rereads local files, not remote snapshots. Report an unavailable launcher or incompatible workspace format without claiming initialization succeeded; independent read-only discussion can continue.

Sources: `mcp_server/gds_etl_workbench/tools/tenants/{list_tenants,get_tenant_details}.py`, `tools/modeling/model_details.py`; GDS `contracts/local-helper.json`, `scripts/gds-local.js`, `scripts/open-workbench.sh` and `workbench/workspace.js`.

## Build workflow routing

For Logical Build or Gold (Dimensional) Build, use the requested approach. If missing, ask: "How do you want to build this model?" Options: **Guided** — follow the defined phases; **Grill Me** — develop the model through discussion. These select separate workflow skills, not branches inside one build skill.

| Build | Guided | Grill Me |
|---|---|---|
| Logical | [atlas-logical-build-guided](../skills/atlas-logical-build-guided/SKILL.md) | [atlas-logical-build-grill-me](../skills/atlas-logical-build-grill-me/SKILL.md) |
| Dimensional / Gold | [atlas-dimensional-build-guided](../skills/atlas-dimensional-build-guided/SKILL.md) | [atlas-dimensional-build-grill-me](../skills/atlas-dimensional-build-grill-me/SKILL.md) |

Atlas's entry skill resolves the selection, then loads the selected workflow's instructions and passes the existing context. This is instruction routing, not an assumed portable skill-calling API. Direct selection is also valid. Shared references supply domain rules; Guided does not load interview instructions. Legacy "custom logical build" wording means Grill Me here; top-level Custom remains a different workflow. Dimensional skills share their own design rules and eligible Silver context; do not substitute Logical normalization or Input Scope rules. 

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

Create only what the work needs. The [workspace file contract](workspace-contract.md) defines session/task fields, owner roots and durable evidence bindings; the shared runtime validates these shapes.

- Session: Tenant identity, optional active Model identity, SQL selections where applicable, active task pointer, known refresh requirement. Model selection is unnecessary for work that does not need a Model.
- Task: outcome, inputs, work/artifact paths, progress, evidence. An optional plan is part of progress. Store precise input snapshot identities/revisions.
- Technical fields and verified operation results are maintained by helpers; task narrative remains concise and editable. Validation, approval and submission state must not depend on fixed task stages or editable progress text.
- Temporary archives/scripts/intermediates use `.atlas/temp/`. Material needed for resumption or approval must have durable storage before cleanup.
- A question or simple read need not create a task. Substantial authoring uses one task per meaningful outcome, not one per tool call.

Reuse this workspace across workflows and tasks for its primary Tenant/Model. Workbench opens the working-directory root, containing `.atlas` and the sibling data folders. Users and agents edit the same local Change Set files; Snapshot files remain immutable. Metadata owner selection resolves its subtree and independent operation evidence without changing the Model context. See the [Workbench workspace design](../docs/workbench-design.md) for opening, resuming and handling concurrent local edits.

## Snapshot use

- Read the shared [Metadata Snapshot guide](snapshots/metadata.md) or [Model Snapshot guide](snapshots/model.md) for layout, targeted reads and local edits. Workflows select inputs; these references explain how to use them.
- Snapshot manifests identify installed data. Task inputs identify the version used for that work. Avoid manually copying version state into session fields.
- Fetch a fresh Metadata Snapshot when starting metadata authoring. Keep that baseline through the related local work, including additional tasks and edits within the same workflow; do not fetch once per task or edit. Other workflows declare their input freshness policy at entry.
- Logical and Dimensional Build skills offer fresh or existing required Snapshots when suitable inputs are available. Show identities and known refresh requirements; follow the user's choice without replacing the baseline beneath pending work. See [Logical context](logical-build/context.md) and [Dimensional context](dimensional-build/context.md).
- A resumed unfinished workflow retains its baseline and draft until any required refresh is reconciled. Never replace the baseline underneath pending work. A local file timestamp cannot prove freshness.
- Model revision can be compared with authoritative server state. Metadata has no Tenant-wide revision counter; retain existing freshness, Tenant Lock, and server-validation protections.
- An external change, revision conflict, completed manual correction or successful Apply can require a refresh before affected work continues. Preserve the draft and reconcile its base/current/proposed records rather than silently overwriting them.
- Snapshot files are immutable applied-state inputs. Local Change Set files hold complete proposed records. Read the effective result: pending records replace matching Snapshot records by canonical key, while untouched records remain.
- Read manifest/catalog first, the relevant dataset schemas next, and only the required records and dependencies. Helpers may scan complete files internally; return bounded context to the agent. Incomplete lookup rows and truncated selections do not establish complete coverage.

## Existing work and update scope

Before Dimensional Build, Target Registration, Entity Binding, Mapping, Code Generation, Validation authoring or Process metadata, always inspect existing outputs and resolve what to create, reuse or update. Each workflow follows this shared rule; it does not assume entry means rebuild everything.

1. Read current Snapshot records, pending changes and relevant local files. Use task decisions, known Change Set results, retained input versions and authoritative freshness information where available. Establish what changed by identity/content and actual dependencies; conversation/history helps locate changes but does not replace current state. A Model revision change or file timestamp alone does not prove every output changed.
2. Identify **new/missing**, **changed/affected**, **unchanged reusable**, and **unresolved/protected** items. Show a compact list of names and reasons, scoped to the current workflow/Model/layer. Trace relevant bindings, source references, target columns, Mapping branches, lookup dependencies and file/System assignments. Distinguish definite effects from possible effects needing review; missing history is unknown, not proof that everything is unchanged.
3. Resolve the selection before authoring. Follow an explicit instruction such as "regenerate Customer and Order" or "update only what changed"; state the resolved items and reuse that answer. Otherwise ask the appropriate question below. Ask once for the related batch, not for each column or file. If a new dependency changes the agreed scope, show it and resolve that addition before changing it.
4. Update only the selected items and necessary agreed dependencies. Reuse valid unchanged work, preserve manual edits and locks, and retain unselected/blocked work explicitly. A selected target may require complete per-System Mapping/Binding coverage or rewriting a whole shared Code artifact while preserving its unaffected branches. Explain that consequence; never silently widen to unrelated targets.
5. Save the selection, evidence/basis and affected artifact paths in the existing task's inputs/progress/evidence. No separate handoff ledger or full snapshot-history archive is required. Run the workflow's checks against the complete effective graph; a narrow edit scope does not permit broken references or incomplete target coverage. Selecting work does not approve Stage/Apply or execute SQL.

| Context | Exact question / behavior |
|---|---|
| Known model/data-contract changes or newly added items | "New or affected: [names and short reasons]. Update these items, or select a subset from this list?" Offer **Update affected** and **Choose affected items**. Do not offer a blanket rebuild of unchanged work here. Follow a broader explicit user request if supplied. |
| Existing work, no specific change-driven request | "Existing [workflow outputs] are available. Reuse them, update selected items, or rebuild all in this [Model/layer] scope?" Options: **Reuse existing**, **Selected items**, **All in scope**. Show missing items separately. |
| No applicable outputs yet | "Create [workflow outputs] for all [named requested targets], or selected targets?" Options: **All listed targets**, **Selected targets**. Reuse an already explicit selection. |
| Scope already clear from the conversation | State "I'll update [resolved list] and preserve [unaffected work]." Do not ask the same selection again. |
| Impact cannot be established reliably | Show the known changes and uncertain dependencies; ask the user to identify targets or broaden the review. Do not claim the affected list is exhaustive or regenerate everything automatically. |

"All" means the named workflow/Model/layer scope, never all Tenants or unrelated work. Rebuild means review/regenerate permitted local content; it never means dropping/recreating database tables, deleting history or unlocking records.

| Workflow | Impact to resolve |
|---|---|
| Dimensional Build | Selected analytical processes and affected facts, dimensions, bridges, Attributes/relationships. Trace effects of shared dimensions across processes; preserve unrelated designs and agreed grain/history decisions. |
| Target Registration | New/changed target definitions and their Object/Attribute records. DDL remains optional with its own selected table scope; regenerate only requested complete table definitions. |
| Entity Binding | New/missing or affected Entity/Attribute matches. Reuse valid assignments; a broader selection does not enable unsupported rebinding. |
| Mapping | Affected target/System branches, Attribute rules, grain/key/lookup effects and dependencies. Inspect complete target coverage while preserving unchanged rules. |
| Code Generation | Artifacts that implement affected Mapping or target contracts, plus source-System assignments. A combined file can be affected by one branch; unrelated files remain reusable. |
| Validation authoring | Checks/groups whose tested fields, Mapping behavior, output contract or code changed, plus missing required coverage. Regenerating definitions is separate from executing checks. |
| Process metadata | Missing/affected artifact-to-Process assignments, runtime locations, Group/Copy Group links and invocation dependencies. Code text changes alone do not require new registration; existing natural-key changes remain manual database work. |

Example: adding Customer.Email can affect Customer registration, Binding, relevant Mapping branches, Customer code and checks for that field. It does not automatically require regenerating unrelated Order transformations. A changed Customer key or lookup contract may affect Order too; follow actual dependencies rather than names alone. Do not run later workflows automatically merely because their outputs may be affected.

## Complete related work locally

Before authoring in any workflow, read [record state](record-state.md): locked records stay unchanged, unlocked records still require eligibility, and inactive/deprecated history is preserved. Workflow entry does not reset those protections.

1. Accumulate all changes needed for the current outcome in the local Change Set, using the effective result for further authoring. After each authored phase's local batch, follow [local validation](local-validation.md) and repair failures before dependent work. A new task or local edit does not trigger submission or refresh.
2. When the complete related batch is ready, follow the shared [Change Set lifecycle](change-set-lifecycle.md): local validation, Workbench review, extension staging, server validation and separate Apply approval. Transport may use several bounded requests; they still represent one logical Change Set.
3. After verified Apply, mark affected snapshots stale and install fresh applied context before dependent work. Preserve receipts/evidence and retire only pending records confirmed as applied.
4. Each downstream workflow states whether it can work from the local effective result or requires applied inputs. Complete and Apply upstream changes before a stage that requires them; do not mistake pending records for applied state.

Metadata and Model changes retain their separate governed Change Sets and ownership/revision boundaries. Local batching does not combine them into a single transaction. Starting another workflow does not silently publish unfinished work.

## Progress, review, and handoff

- Plans can change as evidence changes; changing plan text does not itself change approved data.
- Approval validity depends on the actual reviewed content and relevant evidence bindings. Helpers must determine validity; the [Change Set lifecycle](change-set-lifecycle.md) defines review and receipt requirements.
- Preserve concise decisions with evidence references; omit raw prompts, raw physical rows, secret values/references, signed URLs, and raw tool dumps.
- Author against the effective Snapshot-plus-pending result. Backend authorization and validation remain authoritative.
- Generate resume/handoff summaries from current records and checks. Do not maintain a second independent checklist.
- Report the actual achieved state: drafted, validated, reviewed, staged, or applied. Required unresolved work prevents a claim of completion.
- Keep generated SQL/DDL separate from permission to execute it. Use governed submission/Apply capabilities and existing user authorization; initialization answers do not approve unseen mutations.

## Reference ownership

Each topic has one maintained rule source. Skills route to it; repeated reminders do not define another policy.

| Change needed | Authoritative home |
|---|---|
| Entry selection and build-skill routing | This working method; [Atlas entry](../skills/atlas/SKILL.md) follows it. Current identity/launcher contracts live in [initialization capabilities](#current-initialization-capabilities). |
| First-release host, backend and feature scope | [Release scope](release-scope.md). |
| Session/task field shapes and durable operation evidence | [Workspace file contract](workspace-contract.md). |
| Workflow sequence or user questions | The selected workflow's SKILL.md; shared interview technique lives in [modeling interview](modeling-interview.md). |
| Existing output reuse, affected-item detection and regeneration selection | [Existing work and update scope](#existing-work-and-update-scope). |
| Modeling method, candidate discovery or SQL preparation | The relevant topic guide, such as [profiling](logical-build/profiling.md) or [finding relationships](logical-build/find-relationships.md). |
| Dimensional grain, conformance, measures and historical lookups | [Dimensional design](dimensional-build/design.md) and [history](dimensional-build/history.md); [Dimensional records](model/dimensional.md) owns field/lineage contracts. |
| Batch selection, query coordinates, SQL-tool contract | [Query scope](query-scope.md). |
| Owner versus physical Tenant or mixed-target ownership | [Object ownership](metadata/tables/object.md#ownership-and-physical-identity). |
| Locked/unlocked/inactive records and read versus change eligibility | [Record state](record-state.md). |
| Local validation sequence, endpoint/scope checks and finding classification | [Local validation](local-validation.md). |
| Model local authoring and current helper calls | [Model Change Sets](model/change-sets.md). |
| Mapping template, concise transformation instructions and complete consumer context | [Mapping documents](model/mapping-documents.md); field contracts remain in [Mapping records](model/mapping.md). |
| Generated SQL structure and translation checks | [SQL generation](code-generation/sql.md); artifact/assignment fields remain in [Code records](model/generated-code.md). |
| Validation coverage, independent expectations and tested population | [Check design](validation/check-design.md); Group/Check fields and comparator contract remain in [Validation records](model/validation.md). |
| Artifact-to-Process assignment and intake | [Process metadata workflow](../skills/atlas-process-metadata/SKILL.md); [Process](metadata/tables/process.md) and [Process Group](metadata/tables/process-group.md) own fields, keys and scheduling meaning. |
| Modeled naming, surrogate keys or audit columns | [Naming](model/naming.md) and [keys/audit](model/keys-and-audit.md). |
| Record fields, keys, value meanings or metric formulas | The affected dataset guide: [Profile](model/profiling-profile.md), [Analysis](model/analysis-result.md), [Conceptual](model/conceptual.md), [Logical](model/logical.md), [Dimensional](model/dimensional.md), [Assertions](model/assertions.md), [Binding](model/binding.md), [Mapping](model/mapping.md), [Code](model/generated-code.md), [Validation](model/validation.md), or a Metadata table page. |
| Review, Stage, server validation and Apply | [Change Set lifecycle](change-set-lifecycle.md). |
| Workbench folder access, workspace context, resume and local editing behavior | [Workbench design](../docs/workbench-design.md); this working method owns workspace identity and record placement. |
| Extension module boundaries and behavior-preserving refactor | [Extension design](../docs/extension-design.md); invocation and submission rules remain in the Change Set lifecycle. |

The backend's shared record schemas remain the machine contract. Dataset guides document that contract and its meaning; schema changes require updating/checking the affected guide and consumers. These guides are maintained alongside the code; they are not automatically generated. Resolve known implementation/guidance conflicts explicitly rather than copying competing advice into each skill.
