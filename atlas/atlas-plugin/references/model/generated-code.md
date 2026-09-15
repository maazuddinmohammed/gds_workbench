# Generated Code records

Owns artifact and source-System assignment fields, identities and storage checks. [SQL generation](../code-generation/sql.md) owns artifact content and semantic checks; [Mapping documents](mapping-documents.md) owns the complete transformation specification; [Model Change Sets](change-sets.md) owns local writes/MCP discovery; [record state](../record-state.md) owns locks and lifecycle. The [Code Generation skill](../../skills/atlas-code-generation/SKILL.md) owns sequence and user choices.

## Identity and local files

Both datasets belong to Model section `code_generation`. Read the current Snapshot catalog and exact dataset schemas. The catalog requires applied `mapping`; active applied Binding and complete Mapping are workflow prerequisites. `successive_change_set_required: false` does not make unapproved local Mapping an applied input.

| Dataset | Natural key within the Model | Snapshot location |
|---|---|---|
| `generated_code` | `modeled_entity_type` + `modeled_entity_name` + `artifact_name` | `code_generation.artifacts` |
| `generated_code_source_system` | Artifact key + `source_system_code` | `code_generation.source_systems` |

Use shared Model key normalization for comparisons; preserve actual names. Write complete changed records as arrays in `model-change-set/generated_code.json` and `model-change-set/generated_code_source_system.json`. These are not patches or backend workflow candidate envelopes. Artifact identity belongs to one target Entity; a filename is not globally unique across the Model.

All fields below are required, non-null and have no record-schema defaults. Use `active` and unlocked for new completed records; preserve existing state.

## Artifact fields

The [first release](../release-scope.md) generates SQL only. Keep the complete existing storage enums below: existing Python artifacts must remain readable/preserved, and Process registration of a supported existing executable is separate from new generation. Future Python generation requires the consumer contract described below.

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; exact bound target Entity. |
| `artifact_name` | Nonblank string, 1–400 characters; filename only, with no leading/trailing whitespace, `/`, `\`, `.` or `..` as the entire name. Use the approved filename and extension; no directory path. |
| `artifact_type` | `sql_file`, `python_file` or `python_notebook`. These are accepted storage types, not proof that every authoring/execution consumer supports them. |
| `generated_code_content` | Complete nonblank text, not a filepath, Markdown fence or JSON-encoded content object. Characters below U+0020 are rejected except tab, LF and CR. Record schema does not parse SQL/Python or establish a per-record content maximum; transport limits still apply. |
| `generated_code_status` | `active`, `inactive` or `deprecated`. |
| `generated_code_is_locked` | Boolean. |

The schema does not require an extension to match `artifact_type`; check that locally. Python notebook encoding/entrypoint behavior is not established by this text field. Do not invent that contract from the enum.

## Source-System assignment fields

One row connects a target artifact to one contributing source System. Repeat the full artifact key; assignments are not nested inside the artifact.

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`; same as the artifact. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; same target Entity. |
| `artifact_name` | Nonblank string, 1–400 characters; exact parent artifact filename. Parent existence and filename validity must resolve. |
| `source_system_code` | Nonblank string, 1–100 characters; the originating System whose active Mapping this artifact implements, not the physical GDS placement System. |
| `generated_code_source_system_status` | `active`, `inactive` or `deprecated`. |
| `generated_code_source_system_is_locked` | Boolean. |

No outer `source_system_codes` array, dependency order, target physical keys, output path, `artifact_role`, Model/database IDs, run IDs, timestamps or digest fields are accepted. Physical target comes from Binding. Source-System provenance comes from Mapping and these assignments, not a fabricated ID in the record.

## Combined and separate files

- **One file per target:** one artifact and one assignment for every System it implements. All branches use the same mapped target shape and explicit reconciliation policy.
- **One file per target/System:** separate artifact names; each assignment points to the corresponding file. Each file is self-contained. Do not rely on a temporary view from another file/session.
- **Mixed grouping:** an artifact can own a subset of Systems if the approved layout needs it. Across the target, each active mapped System belongs to exactly one active transformation artifact.
- Dependency orders remain in `mapping_dependency` and `mapping_object`; assignment-array order and filenames do not schedule execution. Later Process Metadata represents orchestration placement. A combined artifact must preserve mapped dependencies without assuming arbitrary branch order satisfies them.
- Multiple artifacts for the same target/System cannot represent repeated executions through duplicate active assignments. Resolve repeated execution in the approved transformation/Process design; do not invent another Code key dimension.

The backend authoring candidate has `artifact_role: target_transformation|support` and a source-System array. Conversion produces these two datasets and does not retain `artifact_role`. A generic active artifact with no assignments is therefore not inherently invalid, but the reader cannot infer its intended role from a stored role field. Atlas transformation outputs must have explicit coverage; target-registration DDL stays in its separate, user-selected generation flow. Do not automatically add unassigned support artifacts to hide missing assignments.

## Eligibility, coverage and protection

- Every artifact requires its target Object Binding; active artifacts require active Binding. New/changed authoring requires an eligible active Silver target for Logical or Gold target for Dimensional. Apply resolves complete active Mapping for that Binding before storing Code.
- Every assignment requires its artifact and an active registered source System. An active assignment requires an active artifact and active Object Mapping for that target/System.
- During Code authoring for a target, every active mapped System must have exactly one active assignment. Duplicate assignments across active artifacts are rejected. Upstream Mapping may add a System while unchanged Code remains; missing assignments then indicate stale/incomplete Code rather than permission to omit the new branch.
- A partial selection of targets is valid. Within each selected target, reconcile the complete existing-plus-proposed assignment set; changing one file must not remove another System's coverage.
- Artifact and assignment locks are checked independently. Locked Code cannot change content/type/status/name; locked assignments cannot move or deactivate. No implicit parent-lock cascade is established by the generic model contract. Preserve the behavior of protected work and flag layout changes that conflict with it.
- Inactive/deprecated records retain their keys. Omitting them does not delete them. Review any deliberate replacement of an existing file layout, including superseded artifacts and assignments, before staging its lifecycle changes; never auto-unlock or rewrite preserved history.

## Content, freshness and Apply

The generic schema checks text and references, not transformation correctness. The current backend Code Generation workflow authors SQL only and its review/download queries filter `sql_file`; Python storage acceptance is not an end-to-end Python workflow. Keep Python entrypoint, packaging and consumer support explicitly unresolved until designed.

Backend SQL candidate validation parses Databricks SQL but also accepts DDL, DML and commands. It does **not** establish Atlas's narrower [SQL transformation contract](../code-generation/sql.md). Local/content review must enforce that contract. A syntax pass also cannot prove grain, joins, keys, null/cast behavior or business results.

Apply derives `code_input_digest` from current eligible Mapping/target context; the database derives `generated_code_digest` from content. Neither is supplied in these records. Snapshot artifact records contain neither digest, so their presence or a local timestamp cannot prove freshness. Use a supported governed freshness/context view when available; otherwise record the unresolved freshness check. Use `read_mapping_context` for a revision/digest-bound current view; do not manufacture server artifact digests.

Changing Mapping or target context can make Code stale without changing artifact text. Regenerate/review only affected artifacts against a complete consistent Mapping view. Stamping unchanged SQL with refreshed input context is not evidence that it still implements the new Mapping.

Resolve [existing work and update scope](../working-method.md#existing-work-and-update-scope) before authoring. A Snapshot includes saved content, not automatically synchronized source files; inspect pending/local edits as described in [saved Code](../snapshots/model.md#saved-code-and-local-files). A narrow selection still requires complete per-target System coverage and preservation of unselected valid artifacts.

Use the shared [review/Stage/Validate/Apply lifecycle](../change-set-lifecycle.md), including generated-Code transport handling. Both datasets can accumulate in one local batch. Store complete artifact text in `generated_code_content`; any reviewable local `.sql` copy must match that exact content. Apply stores records; it does not create a deployed file, run SQL, register a Process or execute a pipeline. Refresh the Model Snapshot after verified Apply.

## Code record checks

| Rule | Check / reason | Current coverage |
|---|---|---|
| `code.shape` | Exact 7/6 fields, canonical keys, enums, nonblank content and legal filenames. | Generic schema, duplicate-key checks and database constraints; assignment filename resolves through its parent. |
| `code.parents` | Real eligible target Binding, complete active Mapping and active assigned System. | Graph/eligibility checks and Apply context resolution. |
| `code.coverage` | Every selected target's mapped System assigned exactly once across active transformation artifacts. | Generic Code-authoring graph checks; backend candidate also checks its frozen target set. |
| `code.layout` | Approved filenames/grouping, no output-path collision, self-contained artifacts and compatible dependencies. | Additional workflow/local checks; no scheduling/path fields in record schema. |
| `code.protection` | Preserve independent Code/assignment locks, statuses and unaffected coverage. | Direct record locks checked; semantic consequences of assignment/layout changes need review. |
| `code.content` | Code type/extension, allowed statements, explicit ordered output, mapped semantics and no unresolved runtime contract. | Generic record does not parse content; backend SQL parser is broader than Atlas's transformation policy. |
| `code.freshness` | Current Mapping view and matching reviewed content; no stale upstream assumptions or forged digest. | Server derives input/content digests; `read_mapping_context` binds current inputs; compare with the reviewed local evidence. |

Additional checks here are Atlas requirements, not newly implemented runtime guarantees. Content checks do not execute SQL; optional execution must follow the saved SQL policy and actual authorization.

## Complete synthetic examples

Assume applied Customer Binding and complete CRM/ERP Mapping. The confirmed target grain/key is `(SourceSystemID, CustomerCode)`; input customer references are nonblank and unique within each System. Source code/name fields are STRING; names may be null. Both sources contain valid non-null BIGINT `source_system_id` values with disjoint System identities. They need no batch filter. The approved layout combines their disjoint branches; own CustomerID and the nine framework audit fields are omitted from the final projection. These examples are complete record arrays, not evidence that the fictional tables exist.

`model-change-set/generated_code.json`:

```json
[
  {
    "modeled_entity_type": "logical_entity",
    "modeled_entity_name": "Customer",
    "artifact_name": "Customer.sql",
    "artifact_type": "sql_file",
    "generated_code_content": "CREATE OR REPLACE TEMPORARY VIEW Customer_CRM AS\nSELECT c.customer_reference AS CustomerCode, NULLIF(TRIM(c.display_name), '') AS CustomerName, c.source_system_id AS SourceSystemID\nFROM bronze.crm_customer AS c;\nCREATE OR REPLACE TEMPORARY VIEW Customer_ERP AS\nSELECT e.customer_code AS CustomerCode, NULLIF(TRIM(e.customer_name), '') AS CustomerName, e.source_system_id AS SourceSystemID\nFROM bronze.erp_customer AS e;\nSELECT CustomerCode, CustomerName, SourceSystemID FROM Customer_CRM\nUNION ALL\nSELECT CustomerCode, CustomerName, SourceSystemID FROM Customer_ERP;",
    "generated_code_status": "active",
    "generated_code_is_locked": false
  }
]
```

`model-change-set/generated_code_source_system.json`:

```json
[
  {
    "modeled_entity_type": "logical_entity",
    "modeled_entity_name": "Customer",
    "artifact_name": "Customer.sql",
    "source_system_code": "CRM",
    "generated_code_source_system_status": "active",
    "generated_code_source_system_is_locked": false
  },
  {
    "modeled_entity_type": "logical_entity",
    "modeled_entity_name": "Customer",
    "artifact_name": "Customer.sql",
    "source_system_code": "ERP",
    "generated_code_source_system_status": "active",
    "generated_code_source_system_is_locked": false
  }
]
```

For approved separate files, create complete `CustomerCRM.sql` and `CustomerERP.sql` artifact records, each with its own preparation and final SELECT; point the CRM/ERP assignments to those respective names. Do not stage both layouts together as active coverage. Dimensional Code uses `dimensional_entity` and the actual bound Gold Entity/Mapping, with the same outer fields.

## Source pointers

Fields: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`GeneratedCodeRecord`, `GeneratedCodeSourceSystemRecord`); keys/sections: `domain/snapshots/model.py`; catalog prerequisites: `tools/snapshots/model/archive.py`; locks/coverage: `application/change_sets/model_validation.py`; Apply/digests: `application/change_sets/model_apply.py`, `database/10_workflow_code_validation.sql`, `database/11_workflow_eligibility.sql`.

Separate backend candidate/SQL checks and conversion: `web_app/backend/gds_workbench_api/features/code_generation/candidate.py`, `service.py`; SQL-only read/download behavior: `read_service.py`. Current GDS teaching examples and generation conventions: `plugins/v2/gds/skills/gds/references/workflows/code-generation.md`. Do not mistake internal backend candidate fields or helper functions for public MCP tools.
