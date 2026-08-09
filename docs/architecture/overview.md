# Release 1 architecture

GDS ETL Workbench Release 1 has two deployment shapes and one authoritative
database:

```text
developer MCP client -------- /mcp -------------------+
human workflow operator ----- /workflow-control/v1 --+--> Easy Auth v2
                                                      |        |
Databricks workload --------- /mcp -------------------+        v
                                               one modular App Service
                                                        |
                                                        v
                                                  PostgreSQL 16
```

PostgreSQL is authoritative for applied Models, drafts, grants, workflow runs,
profiling attempts, receipts, and transactional audit. The MCP process owns
identity mapping, authorization, compilation, validation, idempotency, and
transaction orchestration. It keeps only a bounded reconstructible snapshot
cache in process memory. Jobs use MCP only; they never import server internals or
connect to metadata PostgreSQL.

## App Service modular monolith

MCP runs as one process with one PostgreSQL pool. It is a feature-first modular
monolith. It does not use microservices, internal HTTP, a command bus, or an
event bus.

```text
gds_etl_workbench/
    runtime.py             composition and process lifecycle
    access.py              shared principal and Workflow Grant checks
    adapters/mcp/          exact 22-tool actor-filtered transport bindings
    adapters/workflow_control/  three fixed human control routes
    adapters/health/       liveness and readiness HTTP routes
    application/           typed ports, shared compiler, and RuntimeReadiness
    catalog/               CatalogFeature
    model_context/         ModelContextFeature
    change_sets/           ChangeSetsFeature
    mapping/               MappingFeature
    profiling_runs/        ProfilingRunsFeature
    workflow_runs/         WorkflowRunsFeature
    infrastructure/        one PostgresRepository adapter and snapshot output
```

Each tool binds directly to one feature. There is no generic central service or
`application/service.py` facade. The exact ownership is:

| Feature | Tool count | Tools |
|---|---:|---|
| `CatalogFeature` | 3 | `list_tenants`, `list_objects`, `get_objects` |
| `ModelContextFeature` | 6 | `list_models`, `get_model`, `get_modeling_evidence`, `check_model_readiness`, `get_model_snapshot`, `get_model_dbml` |
| `ChangeSetsFeature` | 5 | `get_model_change_set`, `create_model_change_set`, `put_model_change_set_section`, `validate_model_change_set`, `apply_model_change_set` |
| `MappingFeature` | 1 | `get_mapping_materialization` |
| `ProfilingRunsFeature` | 3 | `get_profiling_run`, `create_profiling_run`, `complete_profiling_run` |
| `WorkflowRunsFeature` | 4 | `get_workflow_run_contract`, `activate_workflow_run`, `complete_workflow_no_op`, `complete_dbml_export` |

`WorkflowRunsFeature` also serves the non-MCP authorize, revoke, and safe-status
control operations through the dedicated workflow-control adapter. They do not
enter the MCP registry or tool bindings.

## Actor-separated MCP surface

The authenticated claims are resolved to a server-owned `ActorKind` before MCP
discovery or dispatch. The exact MCP audience partitions are:

| Audience | Count | Tools |
|---|---:|---|
| Human-only | 5 | `list_tenants`, `list_objects`, `get_objects`, `list_models`, `get_modeling_evidence` |
| Shared | 9 | `get_model`, `check_model_readiness`, `get_model_snapshot`, `get_model_dbml`, `get_model_change_set`, `create_model_change_set`, `put_model_change_set_section`, `validate_model_change_set`, `apply_model_change_set` |
| Workload-only | 8 | `get_mapping_materialization`, `get_profiling_run`, `get_workflow_run_contract`, `complete_workflow_no_op`, `complete_dbml_export`, `activate_workflow_run`, `create_profiling_run`, `complete_profiling_run` |

A promoted human sees the five human-only plus nine shared tools (14); the
exact configured workload sees the nine shared plus eight workload-only tools
(17). Without verified mutation promotion, mutating tools are removed globally,
leaving ten human and eight workload reads. The same per-request projection
governs tool discovery, direct calls, capabilities, registry, and tool-schema
resources. Hidden names fail before schema validation with the generic
unregistered response used for an unknown name, including when a client reuses
a cached inventory from another principal.

The human control surface is exactly JSON-only
`POST /workflow-control/v1/authorize`,
`POST /workflow-control/v1/revoke`, and
`POST /workflow-control/v1/status`. Authorize and revoke require the same
process-start `VerifiedMutationPromotion` as mutating MCP registration. Status
is read-only and remains registered without promotion. It accepts the exact
Workflow Run/Grant UUID pair and returns bounded scalar state and aggregate
counts only. Manual Databricks launch is outside the service: authorization
returns safe handles, an operator starts the predefined task, and the workload
activates and reads its immutable contract through MCP.

All six features use the shared `AccessControl` checks and the typed
`StateRepository` application port. `PostgresRepository` is the one production
adapter for that port. It owns the PostgreSQL pool and transaction mechanics.
Features do not expose raw SQL, connection objects, or generic CRUD tools.
PostgreSQL owns relational integrity. Python does not repeat a fixed shape check
after a raw request becomes a trusted typed request. Authorization, grant state,
expiry, locks, revisions, digests, and idempotent replay can change. The feature
and repository recheck these values in the transaction.

`RuntimeReadiness` is separate from the six tool features. It checks database
access, the least-privilege posture, and schema version. Runtime configuration
and the seven workflow deployment definitions are validated before the process
constructs the features. `RuntimeReadiness` does not own a public MCP tool.

Authentication, request limits, MCP translation, the fixed workflow-control
routes, and health endpoints are outer adapters. Domain code does not import
Starlette, MCP, Azure, Databricks, or provider SDKs. Production source contains
no fake repository, test identity, recorded response, or test-only dispatch
path.

## Databricks source modules

The jobs source has a portable typed core and seven workflow modules. The seven
notebooks add one fixed, versioned workspace parent to `sys.path`. They own and
compile their Notebook Definition once. The source does not require Databricks
globals during import. Jobs do not import `gds_etl_workbench`; the server does
not import `gds_etl_jobs`.

The shared interface is contract v1: typed requests/responses, canonical JSON
rules, and generated public JSON Schemas/examples. There is no shared generated
workflow, phase, profile, or package-identity registry. The fixed workspace and
job configuration plus safe release and Notebook Definition audit values bind a
run to the expected source.

Model Snapshot archives are human-readable modeling inputs, not MCP transport
bundles. Their contract subtree is assembled from an explicit transport-neutral
allowlist of common schemas, generic examples, and the source/Mapping contract
documents. It excludes MCP capabilities, the MCP registry, the schema catalog,
and all MCP tool request/result DTO schemas.

DBML export is a separate immutable, revision-bound read resource. A caller
selects `conceptual`, `logical`, or `both`; Logical output can be one `complete`
view or a `bundle` containing the complete and Submodel views plus an optional
default view for Entities with no Submodel; and colors can be enabled or
disabled. `get_model_dbml` returns a typed manifest and
ZIP resource URI. The App Service never receives or dereferences an output
directory: the MCP client downloads or extracts the ZIP into its own current or
chosen directory.

## Mutation path

1. Inspect capabilities/readiness and bounded catalog/Model context.
2. Create one Model Change Set.
3. Replace complete section documents with global draft-revision CAS.
4. Compile and validate the complete future graph without effective writes.
5. Apply only the sealed candidate with Model revision, context digest, lock,
   principal/grant, and idempotency rechecks in one Model-serialized transaction.
6. Reconstruct immutable snapshots from durable PostgreSQL state.

Omission means unchanged. Automation never deletes effective modeling rows.
Database-generated identifiers are returned in the apply receipt and resolve
stable local references within the candidate.

## Deployment boundaries

- `database/01_*.sql` through `13_*.sql` are one canonical fresh-install schema.
  They are applied by a separate deployment identity, never at server startup.
- `mcp_server/` builds one allowlisted Azure App Service ZIP. It contains the
  production monolith source and locked runtime dependencies. It contains no
  tests, notebooks, jobs source, or test support.
- `jobs/` publishes an allowlisted first-party source tree to one immutable,
  versioned Databricks workspace folder. It does not build or install a
  first-party wheel.
- `jobs/notebooks/` contains seven separate notebooks. Each contains its fixed
  source parent path and its editable Notebook Definition. Widgets contain only
  `WorkflowRunID` and `WorkflowGrantID`.
- All tests and test support live under root folders
  `tests/contracts/{mcp,workflows}`,
  `tests/mcp/{auth,application,configuration,foundation,infrastructure}`,
  `tests/workflows/{unit,adapters,spark,containers}`, `tests/database`,
  `tests/acceptance/{appservice,workflows,release}`, and `tests/support`.
  Neither deployment allowlist copies `tests/`.
- Physical Silver/Gold registration and generated-code execution remain owned
  external gates. The workbench records readiness; it does not fabricate them.

Detailed database, contract, and jobs designs are in this directory. Operations
and recovery procedures are under `docs/runbooks/` and `docs/operations/`.
