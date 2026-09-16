# Atlas user guide

Atlas helps you author metadata and data models, review local changes in Workbench, and submit them through the companion Stage Runner extension.

## Start or resume

```text
Start atlas.
```

Workbench opens immediately, even before you select a workflow. Atlas reuses saved choices and asks only for missing information:

| Choice | What to provide |
|---|---|
| Tenant | Name/code, or say “List the tenants I can access.” |
| Working directory | An absolute path. If no path or valid saved directory is available, Atlas announces the current directory and uses it. An invalid supplied path needs correction. |
| Workflow | Select a workflow below, or describe your request. |
| Model | Name/ID when the workflow needs one; ask for available Models if needed. |
| SQL policy | **Never**: no execution. **Essential**: resolve blocking evidence gaps. **Proactive**: also investigate useful questions. |
| Environment | When needed: `dev` (default), `qa`, `stg`, or `prod`. |

Provide known choices together:

```text
Start atlas.
Tenant: [tenant name or code]
Working directory: [absolute path]
Workflow: Logical build — Guided
Model: [model name]
SQL policy: Essential
Environment: dev
```

To resume: `Resume atlas in [absolute path].` If unfinished work leaves your intent unclear, Atlas asks **Resume this task** or **Start new work**. Starting new work preserves existing drafts.

## Choose a workflow

These are the choices shown by the starter skill. Build modes are explicit:

| Workflow | Use it for |
|---|---|
| [Metadata authoring](../skills/atlas-metadata-authoring/SKILL.md) | Add/change physical metadata, Copy configuration and focused Process settings. |
| [Metadata enrichment](../skills/atlas-metadata-enrichment/SKILL.md) | Improve Object/Attribute descriptions and inferred types. |
| [Logical build — Guided](../skills/atlas-logical-build-guided/SKILL.md) | Follow Profiling → Analysis → Conceptual → Logical. |
| [Logical build — Grill Me](../skills/atlas-logical-build-grill-me/SKILL.md) | Develop the logical model with an interview grounded in existing scope. |
| [Dimensional / Gold build — Guided](../skills/atlas-dimensional-build-guided/SKILL.md) | Establish analytical purpose, grain, dimensions, facts and history. |
| [Dimensional / Gold build — Grill Me](../skills/atlas-dimensional-build-grill-me/SKILL.md) | Discuss analytical choices and build agreed parts together. |
| [Target registration](../skills/atlas-target-registration/SKILL.md) | Register Silver/Gold targets; optionally generate creation DDL. |
| [Entity binding](../skills/atlas-entity-binding/SKILL.md) | Match model Entities/Attributes to registered targets. |
| [Mapping](../skills/atlas-mapping/SKILL.md) | Define concise transformation instructions for each target and contributing System. |
| [Code generation](../skills/atlas-code-generation/SKILL.md) | Generate transformation SQL from applied Mapping. |
| [Validation](../skills/atlas-validation/SKILL.md) | Author meaningful technical and functional checks. |
| [Process metadata](../skills/atlas-process-metadata/SKILL.md) | Register applied transformation files, locations and execution dependencies. |
| [Custom](../skills/atlas-custom/SKILL.md) | Debug supplied code, explain a model, reverse engineer logic or investigate other questions. |

**Guided** follows defined phases. **Grill Me** inspects evidence, recommends answers and works through consequential decisions with you. “Drill me” is accepted as an alias for Grill Me. Switching modes preserves work; it does not restart the model. For registration, binding, mapping, code and validation, specify **Logical/Silver** or **Dimensional/Gold** when context does not make it clear.

## Useful requests

```text
Use atlas for metadata enrichment.
Tenant: [tenant code]
Working directory: [absolute path]
System: [system name]
Zone: bronze
Objects: [object names]
Fill missing descriptions and inferred types. SQL policy: Essential.
```

Enrichment fills missing values by default; request replacement explicitly. Physical data types stay unchanged. You can instead select active Objects through a Model's Input Scope.

```text
Use atlas for Logical build — Grill Me.
Model: [model name]
Start with Orders and Order Lines. Inspect the scope first.
Recommend grain and identity, challenge the design with examples,
and build each agreed part locally. Preserve unrelated work.
```

```text
Use atlas for Dimensional / Gold build — Guided.
Model: [model name]
Design sales reporting by customer, product and sale date.
Reuse the applied Silver contributions and existing shared dimensions.
```

```text
Generate transformation SQL for [selected targets].
Use separate files per System and target. Preserve unaffected files.
```

Atlas asks whether to use one file per target or separate files per System/target unless already specified. This release generates SQL and preserves existing Python; [release scope](../references/release-scope.md) describes the limits.

For targeted regeneration: `Update only the entities and downstream artifacts affected by [change].` Atlas shows affected items and lets you narrow them. General requests with existing output offer reuse, selected items or all in scope. Locks and unrelated/manual edits remain protected.

## Workbench

Choose **Open working directory** and select the folder containing `.atlas`, not `.atlas` itself. Chrome/Edge may ask for directory access. Once selected:

- **Save local changes** saves a proposal; it does not Stage or Apply.
- **Reload local files** picks up agent edits; it does not download a fresh Snapshot.
- **Validate locally** shows findings to correct and recheck.
- **Generate DBML** is your Workbench-only export: complete Model Snapshot plus saved changes, regardless of filters or paging. Resolve unsaved edits first. Agents work with Model records and do not generate or read this export.

If another window or the agent changed a file, Workbench asks you to resolve the conflict before saving. Snapshots remain the applied baseline. One directory holds one active Model; Model-derived Metadata can have separate owner folders within it. Each owner's review and submission remain separate.

## Review, Stage and Apply

1. Atlas completes related edits locally and validates the whole proposed batch.
2. Review/edit the batch in Workbench, then acknowledge it in the conversation.
3. Atlas prepares the manifest and uses Stage Runner to send the approved files to the server draft.
4. Atlas validates that draft on the server and shows its complete action review.
5. Approve **Apply** separately. Atlas verifies the result and refreshes affected Snapshots before dependent work.

You do not need to copy digests or prepare evidence JSON. Changed content requires renewed checks and review. Stage sends a draft; Apply persists it. Neither deploys generated code, runs a pipeline or commits to Git.

## Setup and limits

Install the Atlas plugin in a compatible agent host. For Stage, install the matching VSIX in VS Code and configure its backend connection; the MCP and extension connections are separate. **Atlas: Check Stage Runner** checks readiness without staging. Other hosts can prepare local work, then continue submission in a supported VS Code host.

Local helpers use Node.js 20+; Snapshot installation also uses Python 3.12+. Windows PowerShell 5.1 is the native fallback. [Runtime guide](runtime-guide.md) covers commands and troubleshooting.

SQL evidence uses the selected policy and fully qualified `catalog.schema.table` names. Atlas resolves target catalog from the physical owning Tenant's `tenant_catalog`; it does not guess from the schema or SQL environment. For batched Objects, supply batch IDs by System or Object; missing choices never become an all-batches query. [Query rules](../references/query-scope.md) describe access and scope.

Existing natural-key renames require your manual database correction; Atlas provides instructions. Generated DDL is supplied for review, not executed. Locked records remain protected, and local validation cannot replace server authorization.

For detail, use the [metadata table index](../references/metadata/index.md), [terminology](../references/terminology.md), [working method](../references/working-method.md), or [submission procedure](../references/change-set-lifecycle.md). Do not put credentials or raw data in prompts or task notes.
