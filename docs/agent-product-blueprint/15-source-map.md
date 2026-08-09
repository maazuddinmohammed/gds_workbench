# Source map

Use this page to move from product intent to exact executable detail. Paths are
grouped by the question an agent is trying to answer.

## Authority and vocabulary

| Question | Primary sources |
|---|---|
| What is the execution contract? | [`IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| What words have exact domain meaning? | [`CONTEXT.md`](../../CONTEXT.md) |
| What safety rules apply to this workspace? | [`AGENTS.md`](../../AGENTS.md) |
| Where are exact DD-108–110 contracts approved? | [`RELEASE-1-DECISIONS.md`](../design/RELEASE-1-DECISIONS.md) |
| What changed the architecture? | [`docs/adr/`](../adr/) |
| What canonical accepted detail remains delegated? | [`reference_snapshot/docs/features/FEATURE-001.md`](../../reference_snapshot/docs/features/FEATURE-001.md) |
| How is that immutable evidence trusted? | [`reference_snapshot/MANIFEST.sha256`](../../reference_snapshot/MANIFEST.sha256), [`verify_bootstrap.sh`](../../scripts/verify_bootstrap.sh) |
| What has dated completion evidence? | [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md), [`traceability.md`](../traceability.md) |

## Database and state

| Question | Primary sources |
|---|---|
| Exact fresh-install schema | [`database/`](../../database/) numbered SQL files |
| Table and privilege design | [`database.md`](../architecture/database.md) |
| Catalog invariants | [`catalog_assertions.sql`](../../tests/database/catalog_assertions.sql) |
| Transaction and trigger behavior | [`behavior_assertions.sql`](../../tests/database/behavior_assertions.sql) |
| Release/database conformance | [`release_conformance_assertions.sql`](../../tests/database/release_conformance_assertions.sql) |
| Production persistence | [`postgres.py`](../../mcp_server/src/gds_etl_workbench/infrastructure/postgres.py) |
| Repository boundary | [`ports.py`](../../mcp_server/src/gds_etl_workbench/application/ports.py) |

## App Service

| Question | Primary sources |
|---|---|
| Composition and lifecycle | [`runtime.py`](../../mcp_server/src/gds_etl_workbench/runtime.py), [`app.py`](../../mcp_server/app.py) |
| App dependency closure | [`pyproject.toml`](../../mcp_server/pyproject.toml), [`uv.lock`](../../mcp_server/uv.lock), [`requirements.txt`](../../mcp_server/requirements.txt) |
| Runtime settings and promotion | [`configuration.py`](../../mcp_server/src/gds_etl_workbench/configuration.py), [`promotion.py`](../../mcp_server/src/gds_etl_workbench/promotion.py) |
| Human/workload identity | [`identity.py`](../../mcp_server/src/gds_etl_workbench/adapters/auth/identity.py), [`middleware.py`](../../mcp_server/src/gds_etl_workbench/adapters/auth/middleware.py) |
| Tenant, Model, role, and grant authorization | [`access.py`](../../mcp_server/src/gds_etl_workbench/access.py), [`authorization.py`](../../mcp_server/src/gds_etl_workbench/domain/authorization.py) |
| MCP protocol, projection, and resources | [`server.py`](../../mcp_server/src/gds_etl_workbench/adapters/mcp/server.py), [`tool_bindings.py`](../../mcp_server/src/gds_etl_workbench/adapters/mcp/tool_bindings.py) |
| Workflow Control routes | [`routes.py`](../../mcp_server/src/gds_etl_workbench/adapters/workflow_control/routes.py) |
| Public errors and telemetry | [`errors.py`](../../mcp_server/src/gds_etl_workbench/domain/errors.py), [`observability.py`](../../mcp_server/src/gds_etl_workbench/observability.py) |

## Features and common application logic

| Capability | Primary sources |
|---|---|
| Catalog | [`catalog/feature.py`](../../mcp_server/src/gds_etl_workbench/catalog/feature.py) |
| Model reads, readiness, snapshots, DBML | [`model_context/feature.py`](../../mcp_server/src/gds_etl_workbench/model_context/feature.py), [`readiness.py`](../../mcp_server/src/gds_etl_workbench/application/readiness.py), [`snapshot.py`](../../mcp_server/src/gds_etl_workbench/application/snapshot.py), [`dbml.py`](../../mcp_server/src/gds_etl_workbench/application/dbml.py) |
| Change Sets and compilation | [`change_sets/feature.py`](../../mcp_server/src/gds_etl_workbench/change_sets/feature.py), [`compiler.py`](../../mcp_server/src/gds_etl_workbench/application/compiler.py) |
| Profiling run/publication | [`profiling_runs/feature.py`](../../mcp_server/src/gds_etl_workbench/profiling_runs/feature.py) |
| Workflow Grant/Run control | [`workflow_runs/feature.py`](../../mcp_server/src/gds_etl_workbench/workflow_runs/feature.py) |
| Committed Mapping reconstruction | [`mapping/feature.py`](../../mcp_server/src/gds_etl_workbench/mapping/feature.py) |
| Durable idempotency | [`idempotency.py`](../../mcp_server/src/gds_etl_workbench/application/idempotency.py) |

## Public contracts

| Question | Primary sources |
|---|---|
| Typed requests and results | [`tool_models.py`](../../mcp_server/src/gds_etl_workbench/contracts/tool_models.py) |
| Model/Section types | [`models.py`](../../mcp_server/src/gds_etl_workbench/contracts/models.py) |
| Canonical JSON | [`canonical.py`](../../mcp_server/src/gds_etl_workbench/contracts/canonical.py) |
| Tool/resource registry source | [`registry.py`](../../mcp_server/src/gds_etl_workbench/contracts/registry.py) |
| Generated registry/capabilities/deployments | [`contracts/`](../../mcp_server/src/gds_etl_workbench/contracts/) |
| Exact generated JSON Schemas | [`schemas/v1/`](../../mcp_server/src/gds_etl_workbench/contracts/schemas/v1/) |
| Design rules and limits | [`contracts.md`](../architecture/contracts.md) |

## Databricks jobs

| Question | Primary sources |
|---|---|
| Thin notebook entry points | [`jobs/notebooks/`](../../jobs/notebooks/) |
| Compiled Notebook Definitions | [`notebook_definition.py`](../../jobs/src/gds_etl_jobs/notebook_definition.py), [`notebook.py`](../../jobs/src/gds_etl_jobs/notebook.py) |
| Activation and contract loading | [`runtime/launch.py`](../../jobs/src/gds_etl_jobs/runtime/launch.py), [`adapters/workflow_mcp.py`](../../jobs/src/gds_etl_jobs/adapters/workflow_mcp.py) |
| Production managed-identity adapters | [`adapters/production.py`](../../jobs/src/gds_etl_jobs/adapters/production.py), [`adapters/settings.py`](../../jobs/src/gds_etl_jobs/adapters/settings.py) |
| Snapshot verification and projection | [`adapters/snapshot.py`](../../jobs/src/gds_etl_jobs/adapters/snapshot.py), [`adapters/projection.py`](../../jobs/src/gds_etl_jobs/adapters/projection.py) |
| Shared deadlines, coverage, Sections, and handoff | [`runtime/`](../../jobs/src/gds_etl_jobs/runtime/) |
| Agent runtime envelope | [`adapters/agents.py`](../../jobs/src/gds_etl_jobs/adapters/agents.py) |
| Workflow implementations | [`profiling/`](../../jobs/src/gds_etl_jobs/profiling/), [`analysis/`](../../jobs/src/gds_etl_jobs/analysis/), [`conceptual/`](../../jobs/src/gds_etl_jobs/conceptual/), [`logical/`](../../jobs/src/gds_etl_jobs/logical/), [`dimensional/`](../../jobs/src/gds_etl_jobs/dimensional/), [`mapping/`](../../jobs/src/gds_etl_jobs/mapping/), [`dbml/`](../../jobs/src/gds_etl_jobs/dbml/) |
| Exact third-party closure | [`pyproject.toml`](../../jobs/pyproject.toml), [`uv.lock`](../../jobs/uv.lock), [`requirements-databricks.txt`](../../jobs/requirements-databricks.txt) |

## Tests and release

| Question | Primary sources |
|---|---|
| Full test inventory | [`tests/`](../../tests/) |
| MCP protocol and actor inventory | [`test_mcp_protocol.py`](../../tests/mcp/application/test_mcp_protocol.py) |
| Change Set behavior | [`test_change_sets.py`](../../tests/mcp/application/test_change_sets.py) |
| Workflow control/grants/profiling | [`tests/mcp/`](../../tests/mcp/) |
| Workflow algorithms | [`tests/workflows/`](../../tests/workflows/) |
| Packaged end-to-end lifecycle | [`test_appservice_boot.py`](../../tests/acceptance/appservice/test_appservice_boot.py) |
| Mapping committed-state path | [`test_mapping_materialization_integration.py`](../../tests/acceptance/workflows/test_mapping_materialization_integration.py) |
| Complete local gate | [`verify_local.sh`](../../scripts/verify_local.sh) |
| Databricks and App ZIP builders | [`build_databricks_source.py`](../../scripts/build_databricks_source.py), [`build_mcp_artifact.py`](../../scripts/build_mcp_artifact.py) |
| Recovery and environment smoke | [`recovery.md`](../runbooks/recovery.md), [`t25-external-smoke.md`](../runbooks/t25-external-smoke.md) |

## Reading rule

Use prose to understand why and sequence. Use strict models and generated
schemas for wire shape, SQL for persistence shape, and rejecting tests for
edge behavior. Never infer a new public capability from an internal class or a
legacy symbol.
