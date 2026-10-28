# Atlas reference sources

Maintainer map from packaged Atlas references to the code that defines their
contracts. It is not packaged with the plugin: runtime agents read the references,
Snapshot schemas and tool contracts, never these source files. Update an entry when
its reference or source changes; code and numbered SQL stay authoritative.

## Shared web and Atlas modeling rules

The web workflow prompts in `database/seed/05_global_prompt_defaults.template.sql` and
the Atlas references are written for different agents, so their prose differs.
`tests/atlas/test_shared_modeling_rules.py` lists the rules both must state (GDS and
zone meanings, null semantics, Subject Areas as table choice only, Mapping row choice, SQL
placeholders and projection, degenerate dimensions) with a pattern for each side.
Change both sides and that table together. Making one text the single source would
mean rewording web prompts, which publishes new prompt versions; that is a separate
product decision.

## `references/code-generation/sql.md`

Atlas contracts: [Generated Code records](../../atlas/atlas-plugin/references/project/generated-code.md) and [Mapping documents](../../atlas/atlas-plugin/references/project/mapping-documents.md). Backend contracts: `mcp_server/gds_etl_workbench/domain/modeling_records.py`, `application/change_sets/project_validation.py`; workflow authoring: `web_app/backend/gds_workbench_api/features/workflows/authoring/`.

## `references/metadata/read-only/chunk-type.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:121,312`.
- `database/01_reference.sql:183`.
- `database/seed/01_metadata_snapshot_demo.sql:36`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:332,512`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:290`.

## `references/metadata/read-only/connection-type.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:77,97`.
- `database/01_reference.sql:54`.
- `database/seed/01_metadata_snapshot_demo.sql:12`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:288,301`.

## `references/metadata/read-only/connection.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:77`.
- `database/02_core.sql:80`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:157,277`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:397`.

## `references/metadata/read-only/data-operation.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:133,320`.
- `database/01_reference.sql:169`.
- `database/seed/01_metadata_snapshot_demo.sql:50`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:352,514`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:292`.

## `references/metadata/read-only/file-type.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:127,315`.
- `database/01_reference.sql:144`.
- `database/seed/01_metadata_snapshot_demo.sql:43`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:342,513`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:291`.

## `references/metadata/read-only/lane.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:35`.
- `database/02_core.sql:5,34`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:232,251`.
- `database/seed/01_metadata_snapshot_demo.sql:66`.

## `references/metadata/read-only/object-type.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:104,157`.
- `database/01_reference.sql:70`.
- `database/seed/01_metadata_snapshot_demo.sql:20`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:311,394`.

## `references/metadata/read-only/process-type.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:139,343`.
- `database/01_reference.sql:212`.
- `database/seed/01_metadata_snapshot_demo.sql:59`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:362,557`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:244`.

## `references/metadata/read-only/system-type.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:90`.
- `database/01_reference.sql:26`.
- `database/seed/01_metadata_snapshot_demo.sql:4`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:274,291`.

## `references/metadata/read-only/system.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:69`.
- `database/02_core.sql:43`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:265,393,465`.

## `references/metadata/read-only/tenant.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:42`.
- `CONTEXT.md:7,11,20,45`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:394`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:243`.

## `references/metadata/read-only/zone.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:111,158,333`.
- `database/01_reference.sql:40,267`.
- `database/seed/01_metadata_snapshot_demo.sql:28`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:374,531`.

## `references/metadata/tables/attribute.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,163,171,173`.
- `database/02_core.sql:199,206,215,223,225,230,516,517`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:159,415,416`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,270,354,474,533`.
- `database/16_mcp_metadata_apply.sql:140,226,270,445,469`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:45,194`.

## `references/metadata/tables/copy-group-control.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,284,290,291`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:74,79,84,204`.
- `database/02_core.sql:348,349,352,356,362,380,382`.
- `database/16_mcp_metadata_apply.sql:747,767,781`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:181,493,495`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,354,474,533`.

## `references/metadata/tables/copy-group.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,266`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:204`.
- `database/02_core.sql:303,309,315,352,518`.
- `database/16_mcp_metadata_apply.sql:656,673,686`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:160,465`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,354,474,533`.

## `references/metadata/tables/copy.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:26,29,296,311,315,319,324`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:89,94,100,126`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:180,500,508,509`.
- `database/02_core.sql:388,392,393,401,409,425,427`.
- `mcp_server/gds_etl_workbench/tools/ingestion/copy_groups.py:176`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,354,474,533`.
- `database/16_mcp_metadata_apply.sql:270,816,906,938`.

## `references/metadata/tables/ingestion-attribute-mapping.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,226,241`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:179,441,450`.
- `database/02_core.sql:263,274,275,292,298`.
- `database/16_mcp_metadata_apply.sql:593,639,649`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,474,533`.

## `references/metadata/tables/ingestion-object-mapping.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,189,190,203`.
- `CONTEXT.md:135`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:178,427,436`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,425,474,533`.
- `database/02_core.sql:237,246,250,258`.
- `database/16_mcp_metadata_apply.sql:507,550`.

## `references/metadata/tables/member-group.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,275,280`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:229`.
- `database/02_core.sql:326,332,338,371,524`.
- `mcp_server/gds_etl_workbench/tools/ingestion/copy_groups.py:188`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:161,479`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,474,533`.
- `database/16_mcp_metadata_apply.sql:709,722`.

## `references/metadata/tables/object.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,145,152,158`.
- `database/02_core.sql:166,176,185,510`.
- `database/16_mcp_metadata_apply.sql:140,305,344,345,377`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:158,390,404`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,270,451,474,533`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:68,132,397`.
- `database/14_application_workflow_execution.sql:796,848`.
- `web_app/backend/gds_workbench_api/features/analysis/validation_execution.py:434`.

Guidance correction for implementation: `domain/snapshots/metadata_guidance.py` currently says downstream ownership "differs" from physical Tenant. It should say "may differ"; equality is permitted under the configured-Connection rules above. No backend change is made by this document.

## `references/metadata/tables/process-group.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,333`.
- `database/02_core.sql:432,435,445,530`.
- `database/16_mcp_metadata_apply.sql:944,961,981`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:162,528`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,474,533`.

## `references/metadata/tables/process.md`

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,343,349`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:51,182,544`.
- `database/02_core.sql:465,479,487,490`.
- `database/16_mcp_metadata_apply.sql:1008,1043,1052,1059`.
- `mcp_server/gds_etl_workbench/tools/processing/process_groups.py:110`.
- `CONTEXT.md:442`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,474,533`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:249`.

## `references/methods/registration/target-definition.md`

Atlas target registration follows the complete-column and optional-output rules above. Field contracts: `mcp_server/gds_etl_workbench/domain/metadata_records.py`; owner placement: `application/change_sets/metadata_validation.py`; Connection discovery: `tools/tenants/get_tenant_details.py`; Modeled ownership: `domain/modeling_records.py`; registration remains a separate Metadata workflow.

## `references/project/analysis-result.md`

Current contract: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`AnalysisResultRecord`, `AnalysisValidationEvidence`); key in `domain/snapshots/project.py`; scope checks in `application/change_sets/project_validation.py`; database rules in `database/05_workflow_analysis.sql`. Atlas probe planning lives in `atlas/atlas-plugin/scripts/analysis.js`.

## `references/project/subject-areas.md`

Current field contracts: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`SubjectAreaRecord`, `SubjectAreaTableRecord`). Keys: `domain/snapshots/project.py`; scope/references/locks: `application/change_sets/project_validation.py`; upserts: `application/change_sets/project_apply.py`; database contracts: `database/06_workflow_subject_area.sql`. The grouping method mirrors the web Subject Area prompt in `database/seed/05_global_prompt_defaults.template.sql` and the answer checks in `web_app/backend/gds_workbench_api/features/subject_areas/candidate.py`.

## `references/project/dimensional.md`

Fields/nested validation: `mcp_server/gds_etl_workbench/domain/modeling_records.py`; canonical keys: `domain/snapshots/project.py`; current graph checks: `application/change_sets/project_validation.py`; Attribute-parent source requirement: `application/change_sets/project_apply.py` (`_find_entity_object_source`); database constraints: `database/08_workflow_dimensional.sql`; physical eligibility: `database/11_workflow_eligibility.sql`; catalog prerequisites: `tools/snapshots/project/archive.py`.

## `references/project/generated-code.md`

Fields: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`GeneratedCodeRecord`, `GeneratedCodeSourceSystemRecord`); keys/sections: `domain/snapshots/project.py`; catalog prerequisites: `tools/snapshots/project/archive.py`; locks/coverage: `application/change_sets/project_validation.py`; Apply/digests: `application/change_sets/project_apply.py`, `database/10_workflow_code_validation.sql`, `database/11_workflow_eligibility.sql`.

Separate backend candidate/SQL checks and conversion: `web_app/backend/gds_workbench_api/features/code_generation/candidate.py`, `service.py`; SQL-only read/download behavior: `read_service.py`. Atlas generation guidance is in `atlas/atlas-plugin/references/code-generation/sql.md`. Do not mistake internal backend candidate fields or helper functions for public MCP tools.

## `references/project/logical.md`

Field/source contracts: `mcp_server/gds_etl_workbench/domain/modeling_records.py`; canonical keys: `domain/snapshots/project.py`; graph checks: `application/change_sets/project_validation.py`; Attribute-parent source requirement: `application/change_sets/project_apply.py` (`_find_entity_object_source`); database rules: `database/07_workflow_logical.sql`. Shared catalog prerequisites are defined in `tools/snapshots/project/archive.py`.

## `references/project/mapping-documents.md`

Exact template: `database/seed/06_global_mapping_output_templates.template.sql`. Record contract: [Mapping records](mapping.md). Runtime/code conventions: [SQL generation](../code-generation/sql.md). Complete-context projection: `web_app/backend/gds_workbench_api/features/workflows/authoring/downstream_inputs.py`; underlying eligibility projections: `database/11_workflow_eligibility.sql`.

## `references/project/mapping.md`

Fields/JSON limits: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`MappingObjectRecord`, `MappingAttributeRecord`, `_json_size`); canonical keys/section: `domain/snapshots/project.py`; prerequisites: `tools/snapshots/project/archive.py`; active parents/coverage/locks/eligibility: `application/change_sets/project_validation.py`; active System catalog: `application/change_sets/project.py`; replacement/template resolution: `application/change_sets/project_apply.py`; database uniqueness/size: `database/09_workflow_mapping.sql`. Existing inner-template authority: `database/seed/06_global_mapping_output_templates.template.sql`.

## `references/project/profiling-profile.md`

Current contract: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`ProfilingProfileRecord`), `domain/snapshots/project.py` dataset key and `application/change_sets/project_validation.py` scope checks. Current SQL generation is in `mcp_server/gds_etl_workbench/application/profiling/execution.py`; MCP owns run execution and persistence.

## `references/snapshots/metadata.md`

- mcp_server/gds_etl_workbench/application/metadata_snapshot/archive.py
- mcp_server/gds_etl_workbench/domain/snapshots/metadata.py

## `references/snapshots/project.md`

- mcp_server/gds_etl_workbench/tools/snapshots/project/archive.py
- mcp_server/gds_etl_workbench/application/project_snapshot.py
- mcp_server/gds_etl_workbench/domain/snapshots/project.py
- mcp_server/gds_etl_workbench/domain/modeling_records.py
- mcp_server/gds_etl_workbench/application/change_sets/project.py

## `references/dimensional-build/history.md`

Default Type 2 names come from `web_app/backend/gds_workbench_api/features/workflows/authoring/gold_policy.py` (`_DEFAULT_TECHNICAL`); projection in `features/dimensional/policy.py`; storage fields in `mcp_server/gds_etl_workbench/domain/modeling_records.py`. Prompt-variable examples in `database/seed/04_application_reference.sql` still show older names and are examples only.

## `references/metadata/validation.md`

Eligibility/keys/uniqueness/references: `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py`; guidance: `domain/snapshots/metadata_guidance.py`; field contracts: `domain/metadata_records.py`; cross-field rules: `domain/portable_validation.py`; published schemas: `application/metadata_snapshot/archive.py`; describe tool: `tools/snapshots/metadata/describe_metadata_dataset.py`; backend validation: `application/change_sets/metadata_validation.py`; storage/Apply: `database/02_core.sql`, `database/16_mcp_metadata_apply.sql`; local mirrors: `atlas/atlas-plugin/workbench/validation/`.

## `references/project/change-sets.md`

`mcp_server/gds_etl_workbench/domain/modeling_records.py`, `domain/snapshots/project.py`, `application/change_sets/project.py`, `application/change_sets/project_validation.py`, `tools/snapshots/project/describe_project_dataset.py`; helper flags in `atlas/atlas-plugin/contracts/local-helper.json`. Dataset guidance text shown to agents lives in `domain/snapshots/project_guidance.py` and `metadata_guidance.py`; keep it consistent with these references.

## `references/project/context.md`

`mcp_server/gds_etl_workbench/domain/modeling_records.py` (`ContextTypeRecord`, `ContextGroupRecord`, `ContextRecord`, `ContextRecordReference`), `domain/context_safety.py`, `domain/snapshots/project.py`, `application/change_sets/project_validation.py`.

## `references/project/keys-and-audit.md`

Backend projection: `web_app/backend/gds_workbench_api/features/logical/policy.py`, `features/dimensional/policy.py`, `features/workflows/authoring/gold_policy.py` and `audit_policy.py`; records in `mcp_server/gds_etl_workbench/domain/modeling_records.py`.

## `references/project/validation.md`

- `mcp_server/gds_etl_workbench/domain/modeling_records.py`: `ValidationGroupRecord`, `ValidationCheckRecord`, literal checks and limits; `domain/snapshots/project.py`: canonical keys and section.
- `application/change_sets/project_validation.py`: ownership, active dependencies, independent locks and active SQL checks; `application/change_sets/project_apply.py`: Group/Check upserts and server-derived currentness.
- `domain/databricks_sql.py`: statement policy/qualification; `application/project_snapshot.py`: exported saved definitions. All four paths above are under `mcp_server/gds_etl_workbench/`.
- `database/10_workflow_code_validation.sql`: storage constraints and uniqueness, including scalar-literal shape.
- `web_app/backend/gds_workbench_api/features/validation/{context,candidate,service}.py`: applied/current authoring inputs, complete-ledger reconciliation and definition generation; not an external comparison executor.
- `docs/workflows.md` and `docs/architecture/decisions.md`: authoring/execution boundary and scalar consumer contract.

## `references/query-scope.md`

`mcp_server/gds_etl_workbench/tools/databricks/execute_sql.py`, `domain/databricks_sql.py`, `infrastructure/databricks_sql.py`; Object owner catalog in `database/14_application_workflow_execution.sql`; batch planning in `atlas/atlas-plugin/scripts/profiling.js` and `scripts/analysis.js`.

## `references/record-state.md`

Local/server protection rules: `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py`, `application/change_sets/project_validation.py`, `domain/modeling_records.py`; local mirrors in `atlas/atlas-plugin/workbench/validation/`.

## `references/metadata/enrichment-quality.md` design notes

The skill contains the sequence; this reference holds reusable quality rules and examples. Existing Snapshot readers and validators should be reused. Add deterministic helpers for repeated evidence/type checks only when their contracts are agreed. This follows [Agent Skills guidance](https://agentskills.io/skill-creation/best-practices) on concrete procedures, examples, progressive disclosure and validation loops. Outcome quality still needs evaluation with representative cases and the projects the plugin will support; structural validation is not an evaluation of writing quality.

Local provenance: metadata_records.py; current GDS metadata-enrichment.md; profiling.js; metadata-enrichment-type-evidence.sql. Legacy Attribute-Mapping-only Bronze inference, Project-required selection, scope caps and inferred-type fill-only policy are not adopted by this draft.

## `references/metadata/tables/copy.md` order contract

Repeated `copy_source_order` values: `database/02_core.sql`, `database/16_mcp_metadata_apply.sql`, `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py`, Metadata Snapshot contracts and disposable Metadata Apply tests. Existing installations need a reviewed upgrade; readiness rejects the obsolete `uq_copy_group_order` constraint.

## `references/release-scope.md` compatibility work

Track implementation beside its authoritative rules: Process Group order (`metadata/tables/process-group.md#dependency-order`), Copy order (`metadata/tables/copy.md#copy-order-and-default`), keys/audits (`project/keys-and-audit.md`), Entity ownership, Mapping consumer context (`project/mapping-documents.md`) and Validation SQL contracts (`project/validation.md`). Existing installations require an explicit backend upgrade and operator review of Process Group dependency orders; deliver compatibility checks and operator instructions separately from deployment.

# Metadata check implementation matrices

Cross-layer audit of where each Metadata check is enforced (database, MCP backend,
local validator). Packaged table guides show only who enforces each check.

## `references/metadata/tables/attribute.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `attribute.shape` | Exact Attribute fields; required type 1..100 chars; inferred type null/nonblank; ordinal 1..2147483647; explicit booleans. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `attribute.unique` | Object + normalized Attribute name unique across zone datasets. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `attribute.ordinal` | Ordinal must be positive and unique within its Object. Preserve unambiguous column order. | Positive CHECK; deferred unique constraint permits atomic reorder. | Positive bounded integer and effective uniqueness. | Schema integer limits and effective uniqueness. | Existing; not parity-tested |
| `attribute.references` | Parent Object natural key must resolve. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `attribute.scope` | Parent Object must belong to selected Tenant and permitted placement; Apply also requires active Connection Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `attribute.lock` | Do not change a locked Attribute or an Attribute under a locked Object. Respect independent and parent protection. | Apply checks touched Object/Attribute locks. | Object and Attribute lock phase. | Baseline lock validation. | Existing; not parity-tested |
| `attribute.physical-type` | Use platform-valid physical type spelling/precision/scale; preserve physical type when setting inferred type. Length alone does not validate a data type. | VARCHAR storage; no platform grammar check. | String shape; no platform grammar validation located. | String shape; platform-specific validation requires separate implementation. | Review |
| `attribute.custom-code` | For SQL Source/Bronze, check actual inputs, dialect, SELECT item, alias and required cast; constants need no source field. Source file copy ignores custom code; API use requires connector evidence. | Text storage only. | String/null shape; no expression-semantic check located. | Proposed applicability/expression/type check; runtime results require permitted evidence. | Proposed; user-confirmed consumer rule |
| `attribute.mapped-state` | Mapping-flag consistency intentionally deferred: is_mapped is currently unused. Do not reconcile it from mappings or block authoring over its value. | Boolean shape still applies. | No semantic reconciliation required. | No semantic reconciliation required. | Deferred by user; not a pending check |
| `attribute.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## `references/metadata/tables/copy-group-control.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `copy_group_control.shape` | Complete Copy Group key; nullable Member Group; date/time nullable; watermark null or nonblank. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `copy_group_control.unique` | Copy Group + Member Group unique; null Member Group counts as one group-level identity. Existing controls retain their keys regardless of parent activity. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `copy_group_control.references` | Copy Group and optional Member Group must share supplied Tenant/System. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `copy_group_control.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `copy_group_control.member-required` | Default null; set only for an explicitly requested Member filter. | Nullable FK; same Tenant/System as Copy Group. | Shape and reference validation apply. | Preserve existing configuration. | Consumer applies filtering. |
| `copy_group_control.watermark` | New controls use null; framework maintains subsequent values. For explicit corrections, verify extraction-specific serialization; nonblank alone does not prove validity. | Nonblank CHECK; no extraction-specific semantics. | Nonblank shape only. | Nonblank shape; semantic review only when supplying/correcting a value. | Review |
| `copy_group_control.timestamp-offset` | Use an explicit offset for last-run timestamps. Avoid timezone-dependent interpretation. | TIMESTAMPTZ accepts offset-free input using session timezone. | datetime accepts naive values; offset requirement not located. | Date-time parser permits missing offset. | Review |
| `copy_group_control.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## `references/metadata/tables/copy-group.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `copy_group.shape` | Tenant/System/name required; name nonblank <=200; description nullable; two explicit booleans. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `copy_group.unique` | Tenant + System + normalized Copy Group name unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `copy_group.references` | Tenant and System must exist. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `copy_group.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `copy_group.member-required` | Default false; enable only for an explicitly requested Member filter. Preserve existing true values. | Boolean default false. | Boolean shape applies. | Verify intended Member Group and same Tenant/System control link. | Consumer handles runtime filtering. |
| `copy_group.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## `references/metadata/tables/copy.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `copy.shape` | Complete group/endpoint keys; nullable copy settings; explicit operations/order/active; delimiter <=20. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `copy.unique` | Copy Group + Ingestion Object Mapping unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `copy.order` | Positive sorting value, default 1 for new rows; repeated values allowed. No runtime sequencing guarantee. | INTEGER, positive CHECK, new-row default; group/order uniqueness removed. | Positive int32; Copy natural-key uniqueness preserved. | Published schema/effective keys; preserve unrelated values. | Implemented; disposable database tests |
| `copy.references` | Copy Group and Object Mapping exist; optional Chunk/File Types resolve; source/target Operations resolve. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `copy.chunking` | New/changed chunking requires the user's large-table request and a registered technique applicable to this table/System. Preserve unrelated existing settings. | Optional reference only. | Registered reference validation; no intent/applicability check located. | Proposed applicability check; request scope belongs to the workflow. | Proposed; user-confirmed authoring rule |
| `copy.target-operation` | Target function must match requested loading behavior. Copy Into appends; Override/custom scope comes from description. Source reference remains required but unused. | Required references only. | Reference checks; no target-behavior check located. | Proposed behavior review from registered descriptions. | Proposed; user-confirmed consumer rule |
| `copy.filters` | Nonblank initial/incremental fragments must include WHERE, a valid source condition and any confirmed placeholders. Blank is allowed and adds nothing; the framework adds no WHERE keyword. | Nullable text storage. | String/null shape; no filter-semantic check located. | Proposed dialect/assembly check; confirm dynamic placeholder rules when needed. | Proposed; user-confirmed consumer rule |
| `copy.scope` | Copy Group belongs to selected Tenant; endpoint Objects owned by it and on permitted Connections. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `copy.record-limit` | Chunk numeric parameter is null or a signed decimal string within BIGINT range. Preserve precision; do not impose a universal positive-only rule or row-cap meaning. | BIGINT conversion. | Pydantic pattern and range validator. | Pattern plus BigInt portable rule. | Existing; not parity-tested |
| `copy.limit-attribute` | Check parameter usage against selected chunk logic. Require a real source Attribute only if that logic expects one; apply function-specific ranges/defaults to numeric input. | Nullable text; no Attribute FK. | Shape only; selected-function semantics not checked. | Proposed chunk-contract check; no universal membership rule. | Proposed; user-confirmed consumer rule |
| `copy.landing-naming` | Filename/pattern must agree with the landing writer and Bronze reader. Validate only the confirmed combination/placeholders; do not treat them as source-selection filters. | Nullable text fields only. | Naming semantics not checked. | Proposed writer/reader compatibility check using descriptions/code. | Proposed; user-confirmed consumer rule |
| `copy.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |
| `copy.record-limit-contract-alignment` | Align signed authoring/DB limit with nonnegative inspect_metadata CopyDetails response; do not invent a positive-only authoring rule. A valid signed authoring value may not satisfy the current read-response contract. | BIGINT accepts negative values; no nonnegative CHECK located. | Authoring permits signed range; CopyDetails response requires ge=0. | Portable authoring validator accepts signed BIGINT range. | Review |

## `references/metadata/tables/ingestion-attribute-mapping.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `ingestion_attribute_mapping.shape` | Complete source/target Object and Attribute keys; required is_active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `ingestion_attribute_mapping.unique` | Parent Object Mapping + source Attribute + target Attribute unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `ingestion_attribute_mapping.references` | Parent Object Mapping exists; each Attribute belongs to its stated endpoint Object. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `ingestion_attribute_mapping.distinct` | Source and target Attribute must differ after key normalization. Prevent a self-Attribute mapping. | source_attribute_id <> target_attribute_id CHECK. | Pydantic model validator. | Portable ingestion_attribute_endpoints rule. | Existing; not parity-tested |
| `ingestion_attribute_mapping.scope` | Both endpoint Objects belong to selected Tenant; Connections owned or configured GDS. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `ingestion_attribute_mapping.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## `references/metadata/tables/ingestion-object-mapping.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `ingestion_object_mapping.shape` | Complete source and target Object keys; required is_active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `ingestion_object_mapping.unique` | Source Object + target Object pair unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `ingestion_object_mapping.references` | Both Object endpoints must resolve. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `ingestion_object_mapping.distinct` | Source and target Object must differ after key normalization. Prevent a self-copy mapping. | source_object_id <> target_object_id CHECK. | Pydantic model validator. | Portable ingestion_object_endpoints rule. | Existing; not parity-tested |
| `ingestion_object_mapping.scope` | Both Objects must belong to selected Tenant; Connections must be owned or configured GDS. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `ingestion_object_mapping.selection` | Copy Group, Copy and Object Mapping must all be active to pass selection. Explain which flag causes skipping; intentional inactivity is valid metadata. | Boolean storage; no cross-record activation constraint required. | Metadata validation does not prove external selection. | Proposed readiness explanation, not an inactive-record error. | Proposed; user-confirmed consumer rule |
| `ingestion_object_mapping.target-shape` | Each incoming dataset must support the Bronze fields/expressions actually used. Allow extra source columns, shared targets, and constants; identify missing inputs or incompatible outputs. | No physical payload/expression compatibility constraint. | Compatibility check not located. | Proposed per-input check using definitions and permitted evidence. | Proposed; user-confirmed consumer rule |
| `ingestion_object_mapping.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## `references/metadata/tables/member-group.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `member_group.shape` | Tenant/System/name required; name nonblank <=200; optional date/description; explicit active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `member_group.unique` | Tenant + System + normalized Member Group name unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `member_group.references` | Tenant and System must exist. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `member_group.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `member_group.date` | Initial load date is a valid calendar date or null. Avoid ambiguous or impossible dates. | DATE column. | Pydantic date. | Published date schema and calendar check. | Existing; not parity-tested |
| `member_group.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## `references/metadata/tables/object.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `object.shape` | Exact Object fields; required codes/names; schema/name <=400; explicit booleans; nullable optional fields. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `object.unique` | Connection + normalized schema/name unique across all four zone datasets; owner and zone are not key fields. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `object.references` | Connection, owner Tenant, Object Type and Zone must resolve. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `object.placement` | Owner is selected Tenant; source uses owned non-GDS Connection; bronze/silver/gold use configured GDS Connection. Separate metadata ownership from physical placement. | Apply checks owner, configured Connection and is_global_data_store. | Owner/configured membership checked; GDS-flag parity review. | Owner/configured membership checked; GDS-flag parity review. | Review |
| `object.zone` | zone_code is source/bronze/silver/gold and matches dataset. Avoid writing the row into the wrong zone document. | Zone FK; Apply zone placement branches. | Record enum and fixed dataset values. | Published enum/fixed schema values. | Existing; not parity-tested |
| `object.lock` | Do not stage a locked existing Object or any of its Attributes. Preserve governed record protection. | Apply locks and checks touched Object rows. | Object/Attribute lock phase. | Baseline lock check; live recheck still required. | Existing; not parity-tested |
| `object.batch-attribute` | Non-null batch_attribute_name should resolve within this Object. Analysis batch filtering additionally requires an active Attribute and supported scalar type. | No storage FK; analysis endpoint resolution checks active same-Object membership. | Metadata-authoring membership check not located; analysis validates the scalar type. | Metadata-authoring membership check not located. | Review: authoring coverage gap |
| `object.foreign-catalog` | When source profiling is needed, resolve foreign catalog plus exact foreign schema/Object/Attribute names. Do not invent physical source names. | Nullable text columns; no complete-catalog check here. | Workflow prerequisite; not unconditional shape requirement. | Check as prerequisite from snapshot/evidence; not a blanket required field. | Review |
| `object.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## `references/metadata/tables/process-group.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `process_group.shape` | Tenant/System/Zone/name and Copy Group required; name nonblank <=200; nullable description; active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `process_group.unique` | Tenant + System + Zone + normalized Process Group name unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `process_group.references` | Tenant/System/Zone exist; Copy Group matches the same Tenant/System. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `process_group.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `process_group.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |
| `process_group.dependency-order` | Required positive int32; default 1 for new groups; outside natural key; repeated levels allowed. | Non-null INTEGER, positive CHECK, new-row default. | Strict required field, Apply/read/Snapshot projection and compatibility readiness. | Published schema enforces range/presence; preserve existing orders. | Implemented; disposable database round trip tested |

## `references/metadata/tables/process.md` check matrix

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `process.shape` | Complete Process Group/Object keys; positive int32 order; nonblank location/executable; Process Type; active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `process.unique` | Process Group + order + exact location + exact executable unique; order alone need not be unique. Same executable at different orders is valid. Existing key changes follow the manual database-change rule. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `process.references` | Process Group and Type exist; Object belongs to specified Connection. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `process.scope` | Process belongs to selected Tenant; referenced Object owner matches and placement is permitted. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `process.executable-semantics` | Confirmed convention: SQL/.sql or Python/.python, path plus actual filename. Preserve actual registered type and file spelling; no new global enum or extension rejection rule. | Nonblank CHECKs and Process Type FK. | Text shape and reference checks only. | Show the actual values; runtime artifact existence not proved. | Review; consumer convention, not new enforcement |
| `process.zone-alignment` | Same Object/Process Group Zone is the normal convention; cross-Zone references remain allowed. Group Zone determines execution phase. | No equality constraint. | Keep group/Object references and ownership checks; no Zone-equality rule. | No Zone-equality warning, error or automatic rewrite. | Deferred by user; equality intentionally unenforced |
| `process.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |
| `process.shared-execution` | Reuse applies within one Zone phase, dependency level and Process order in one run. Intentional repetition at later stages is valid; preserve all registrations. | No global executable uniqueness constraint. | Metadata checks must allow distinct keys at different orders; runtime owns reuse. | May preview stages; do not reject repeated executables or claim runtime enforcement. | Runtime-only; not an authoring rejection |
