# Process metadata

Connect selected transformation artifacts to the framework's Process metadata. Reuse the existing [Process](../../metadata/tables/process.md), [Process Group](../../metadata/tables/process-group.md) and [Copy Group](../../metadata/tables/copy-group.md) contracts; this skill defines their workflow, not new fields or scheduling rules.

## Establish context and scope

1. Follow the [working method](../../working-method.md). Reuse Tenant, working directory, Model, selected layer/targets and artifact choices. SQL execution is normally unnecessary. Start/reuse Atlas Local Workbench through its verified launcher.
2. Follow [Metadata Snapshot](../../snapshots/metadata.md) freshness rules, preserving unfinished local work. For registration from generated files, also load current applied [Model Snapshot](../../snapshots/model.md) Code, source-System assignments and Mapping; separately resolve registered runtime targets. Pending Code is not applied context. A focused correction to existing Process metadata can use [Metadata authoring](../../../skills/atlas-metadata/SKILL.md) without requiring a Model or regenerating code.
3. Inspect existing Process Groups/Processes, actual Copy Groups, registered Process Types and earlier local edits. Use the Metadata Snapshot for complete Process identities; current Process read tools omit location/executable. Follow [existing work and update scope](../change-impact.md); reuse explicit selection and preserve unrelated/manual work. A change to code text alone does not require a new Process record when its registration and invocation contract are unchanged.

## Resolve the artifact-to-Process plan

Derive known values from applied records and explicit prior decisions. Ask one consolidated question for missing facts; do not make the user re-enter information already available.

| Detail | How to resolve it |
|---|---|
| Target | Resolve the selected artifact's schema-qualified Entity against the separately registered runtime Object. Verify its complete physical Object key and compatible columns before Process authoring. Its GDS placement System can differ from the Process Group's originating System. |
| Owning Tenant | Process ownership must match the target Object's source owner, and its physical Connection must be permitted for that owner. Code source-System assignments do not carry a Tenant. Resolve the actual owning Tenant/Copy Group rather than substituting the physical GDS Tenant; report a mismatch with the selected Metadata owner/Change Set Tenant. |
| Contributing Systems | Read active Code source-System assignments and Mapping. Preserve the approved combined/separate file layout; this workflow does not regroup code. |
| Process Group and Copy Group | Reuse the actual applicable group per Tenant/System/Zone and its ingestion Copy Group. Preserve split Copy Groups. If several could apply, ask which ingestion should trigger the processing; never invent a stored "all" or "default" group. Propose a new group only when needed for the requested registration. |
| Executable and type | Preserve the artifact's exact filename and resolve the corresponding active registered Process Type. Follow the [SQL/Python consumer convention](../../metadata/read-only/process-type.md); an accepted Code storage type alone does not establish runtime support. |
| Runtime location | Reuse a confirmed applicable framework path convention or ask for the actual path and any System/target exceptions. A local `code/` folder, Snapshot path or downloadable artifact URL is not automatically its runtime location. |
| Process execution order | Use verified Mapping dependencies, existing schedule and explicit repeated invocations to explain a proposed sequence. Mapping allows zero; Process order must be positive. No mechanical conversion is established: resolve the intended positive stages rather than copy, offset or renumber blindly. Ask only where the dependency/placement is unresolved. |
| Process Group dependency order | Follow the [agreed group-order design](../../metadata/tables/process-group.md#dependency-order), including new-group default 1. Process Groups own this runtime ordering; Mapping has no separate System order. Existing installations need operator upgrade and historical order review. |

Example missing-details question: "For [files], what runtime location should each use? Which Copy Group should trigger [ambiguous group]? Should [unresolved process] run before or after [dependency]?" Include only unresolved items, with actual names and concrete options where known. Do not ask this entire list on every entry.

Show one compact plan: **System → Copy Group → Process Group/Zone → dependency level → Process order → runtime location/file → target**. Identify values derived from current records versus unresolved/proposed values. Resolve uncertain assignments or sequencing with the user before completing the affected records; reuse explicit prior choices and unambiguous existing assignments. The complete authored content is reviewed through the shared lifecycle before Stage/Apply.

## Check scheduling meaning

1. Follow [pipeline selection](../../metadata/tables/copy-group.md#pipeline-selection) and [Process execution behavior](../../metadata/tables/process.md#execution-behavior). Check that selected ingestion makes each required Process Group eligible and that producers finish before dependent consumers. Splitting groups can change which work is selected; missing prerequisites must remain visible.
2. Combined files may have Process registrations under several originating Systems. Preserve those registrations and the confirmed layout. Verify invocation context when a single-System/Copy-Group trigger selects a combined artifact; do not assume it automatically filters the artifact's other branches. Resolve unclear behavior from the actual framework/Mapping contract.
3. Preserve intentional repeated execution at different stages, such as an initial insert followed by a later self-lookup. Runtime handles same-artifact reuse within a stage; do not delete repeated registrations or invent global executable uniqueness.
4. Compare complete Process keys. Two proposed registrations with the same Group/order/location/file cannot represent two different targets: the target is not part of the key. Resolve placement or invocation intent instead of silently overwriting one target. Equal order alone is allowed for distinct executable keys.
5. Group Zone normally matches the target's Zone, but cross-Zone references remain allowed under the table contract. Keep the agreed phase behavior; no new equality restriction. Defaults and activation never silently reactivate existing groups or their parents.

## Author and finish locally

1. Follow [record state](../../record-state.md), [Metadata editing](../../metadata/editing.md) and the installed dataset schemas. Write complete changed records to `metadata-change-set/process_group.json` and `metadata-change-set/process.json`, preserving earlier pending changes. Current Group/Process records have no lock flag; do not invent one or confuse this with Tenant Lock authorization. Required new Copy Group metadata may join the same batch only when its creation is part of the resolved scope; do not fabricate a placeholder parent.
2. Apply [manual natural-key change rules](../../metadata/editing.md#manual-natural-key-changes) to existing Process order/location/file and group identity changes. Give the user the required correction instructions; do not stage a replacement or create/deactivate workaround. An explicitly additional invocation at another stage is a new record, not a rename.
3. Validate the complete effective Metadata using [local validation](../../local-validation.md), [Metadata checks](../../metadata/validation.md) and the affected table checklists. Verify ownership, complete target/parent/type references, key collisions, intended sequence and preserved state. Schema acceptance does not prove runtime file existence or correct framework scheduling.
4. Review the complete related batch in Atlas Local Workbench and follow the shared [Change Set lifecycle](../../change-set-lifecycle.md) for Metadata. Do not submit per Process. After verified Apply, refresh Metadata context and confirm the saved assignments. Model Code remains a separate applied artifact; there is no stored Code-to-Process foreign key or automatic synchronization to rely on.

Report registered versus unresolved work and any runtime prerequisites. Metadata Apply does not upload files, deploy code, create triggers, schedule runs or execute the pipeline. Do not claim the proposed dependency-level behavior is implemented while its field is absent.
