# Atlas backend compatibility

> Historical verification record. The interactive notebook runtime was retired
> by [ADR 007](adr/007-web-owned-workflows-and-notebook-retirement.md); notebook checks below describe the earlier release.

Local implementation. Deployment and changes to populated installations require separate operator approval. Fresh-install SQL remains a fresh-install sequence; no migration or backfill helper is provided.

## Contract and review index

| Rule | Behavior | Code | Tests |
|---|---|---|---|
| `process-group.order` | Required positive INTEGER; new database rows default to 1; mutable outside the natural key. Equal levels are valid. | `database/02_core.sql`, `16_mcp_metadata_apply.sql`; `domain/metadata_records.py`; Snapshot SQL/projection | Metadata snapshot contracts, database Metadata Change Set round trip |
| `copy.order` | Positive order defaults to 1 for new database rows. Repeated values allowed; no Copy Group/order uniqueness. | `02_core.sql`; `domain/snapshots/metadata.py` | Metadata contracts, database Metadata Apply |
| `binding.reassignment` | Existing modeled assignments cannot retarget through physical-key Apply upserts. A parent retarget also reports a locked child's changed physical identity. | `application/change_sets/model_validation.py::_validate_binding_reassignment` | Model Change Set validation |
| `binding.reserved-target` | Inactive/deprecated assignments retain physical Object/Attribute uniqueness. | `application/change_sets/model_validation.py::_validate_bindings` | Model validation and database round trip |
| `logical.key` | New active tables get one own BIGINT surrogate first; preserve business identifiers. Existing table identities stay unchanged. | Backend `features/logical/policy.py` | Logical policy/executor |
| `dimensional.key` | New dimensions, facts and bridges get an own surrogate first; use the configured Gold key template. FK projection preserves it. | Backend `features/dimensional/policy.py` | Dimensional policy/executor/idempotence |
| `audit.provenance` | Preserve SourceSystemID physical lineage and Logical key flags. Other configured framework audit fields have no physical lineage. | Logical/Dimensional policy modules | Logical provenance test, policy tests |
| `mapping.context` | One shared projection supplies five target-oriented components; preserve physical coordinates, batch declaration, registered types/flags, configured population and System value. | `application/mapping_context.py`; `database/11_workflow_eligibility.sql` | Mapping projection/page tests; downstream prompt contracts |
| `mapping.scope` | Include Mapping-named inputs only when current Model eligibility permits them. Reader checks every actual owner; descriptions never grant access. | Eligibility SQL; `tools/modeling/read_mapping_context.py` | Installed Mapping context, Model round trip, tool schema |
| `mapping.currentness` | HMAC cursor binds Model revision, complete context digest, target, component, System selection and page size. Caller pins both revision and digest across components. | Mapping reader | Metadata drift, cursor and governed reader tests |
| `mapping.completeness` | Missing physical coordinates, batch column, named Objects/Attributes or target/System coverage yields `complete=false` with compact rule codes. No inferred repair. | `application/mapping_context.py::mapping_context_issues` | Missing-reference and coverage tests |
| `validation.sql` | Existing governed SQL validation remains authoritative: qualified persistent relations; reads/unqualified temporary objects only; no persistent DDL or DML. | `domain/databricks_sql.py`; Model validation; backend Validation candidate | Existing SQL/Validation suites |

Paths beginning `application/`, `domain/` or `tools/` are under `mcp_server/gds_etl_workbench/`. Backend feature paths are under `web_app/backend/gds_workbench_api/`.

## Existing installation review

1. Record the installed backend/database release and retain a backup under the operator's established process.
2. Have the operator review every existing Process Group's dependency level. No historical group is silently assigned 1. Review Copy ordering semantics and framework consumption together.
3. Prepare and review the installation-specific upgrade separately. It must add the non-null positive Process Group field, align Apply/read/Snapshot routines, and remove Copy order uniqueness while retaining Copy identity uniqueness.
4. Upgrade the Mapping consumer SQL projection and backend together. The reader requires `consumer_context_version="atlas-1"` and rejects older projections.
5. Readiness checks reject a missing Process Group column or the obsolete Copy order unique constraint. Run the fresh-install verification only for a fixture-created fresh installation; it is not an upgrade script.
6. Refresh affected Snapshots and review pending changes against their new schemas. The new field is required in payloads; no server-side historical default is inferred from a missing field.

Model-derived metadata in one workspace does not widen Binding ownership. Silver/Gold Binding targets still require the Model Tenant's source ownership. No orchestration pipeline is deployed or executed by this change; its engine must consume the reviewed dependency metadata under its own release process.

## Mapping reader

`read_mapping_context` is a Tenant-read MCP tool. Read each target separately; select its modeled layer/name and optional originating System codes. It executes fixed metadata SELECTs only, never Databricks SQL.

Synthetic first request:

```json
{
  "model_id": 42,
  "modeled_entity_type": "logical_entity",
  "modeled_entity_name": "Customer",
  "component": "target_metadata",
  "page_size": 50
}
```

Response fields: `schema_version`, `model_id`, `model_revision`, `context_digest`, `component`, `records`, `complete`, `issues`, `next_cursor`.

Read the remaining components `source_metadata`, `source_systems`, `object_transformations`, `attribute_transformations`. Send the returned `model_revision` as `expected_model_revision` and `context_digest` as `expected_context_digest` on every further request. Continue each component's `next_cursor` until null. A changed context invalidates its cursor; restart the complete view, never splice pages from different versions.

`source_systems` exposes the registered numeric provenance as `source_system_value`, beside the System code/dependency order. It is context for the Mapping's actual SourceSystemID rule, not permission to replace a mapped expression with a guessed constant. `target_metadata.attributes[].population` is `database`, `framework` or `mapping`, resolved from registered surrogate flags and configured audit/history templates. Existing frozen workflow contexts without these new flags remain readable.

Limits: 100 records per request, 256 KiB per page/record, 10 MiB complete target context. An oversized record is rejected rather than truncated; this reader does not promise independent Code Generation for a context it cannot deliver. Preserve local work and resolve the bounded-reader limitation explicitly. `complete` certifies the listed structural checks only; business grain, joins and transformation semantics still require review.

No secrets, connection values, SQL results or raw rows are added to the consumer view. Internal storage IDs are removed from instructions. Audit retains only safe Model/component/page metadata.

## Validation evidence

- Focused disposable PostgreSQL suite: 155 passed, including fresh installation, Metadata Apply, Model round trip, runtime readiness and installed Mapping stages.
- Complete MCP/backend suite: 2,552 passed after correcting the Process Group web read projection. Additional Mapping coordinate checks: 4 passed.
- Both Python source trees pass Ruff formatting/lint and Pyright. Three extracted notebook artifact probes pass on Python 3.12; the notebook artifact excludes MCP transport readers and retains the shared Mapping projector.
- Deployment packaging suite: 61 passed. Strengthened Metadata Apply fixture confirms two different Object Mappings in one Copy Group both persist at order 1.
- Native PowerShell 7 profiling/analysis safety scenarios and end-to-end plan manifest/SQL parity: 2 passed. Windows PowerShell 5.1 remains a CI verification target; it was not available on this macOS host.
- MCP source artifact: `mcp_server/dist/gds-mcp-appservice-atlas-0.1.0.zip`. Built locally; not deployed.

Tests use fixture-created disposable PostgreSQL with random credentials, database and sentinel. The sandbox initially denied its Docker socket; the approved escalated test command accesses that same fixture path. No existing database, DSN, Azure or Databricks execution was substituted.
