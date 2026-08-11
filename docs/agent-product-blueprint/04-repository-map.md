# Repository map

## Top-level ownership

```text
database/             canonical fresh PostgreSQL schema
mcp_server/           App Service project and locked dependencies
jobs/                 Databricks source project and seven notebooks
tests/                all test code and test-only adapters
scripts/              guarded verification and artifact builders
docs/                 decisions, architecture, security, operations, and guides
reference_snapshot/   immutable planning evidence; never a runtime dependency
artifacts/            generated local evidence; not source authority
```

## Production entry points

| Entry | Trigger | Next owner |
|---|---|---|
| `mcp_server/startup.sh` | App Service process start | Gunicorn/Uvicorn `app:app` |
| `mcp_server/app.py` | Python application import | `create_application()` |
| `mcp_server/src/gds_etl_workbench/runtime.py` | Composition | Repository, features, routes, middleware |
| `jobs/notebooks/<workflow>.py` | Databricks task | Compiled Notebook Definition and shared runner |
| `jobs/src/gds_etl_jobs/notebook.py` | Notebook execution | Workflow launch and selected workflow |
| `database/01_*.sql` through `13_*.sql` | Fresh database install | Five PostgreSQL schemas |

## App Service modules

| Area | Main modules | Responsibility |
|---|---|---|
| Composition | `runtime.py`, `configuration.py` | Validate settings and build one application graph |
| Transport | `adapters/auth`, `adapters/http`, `adapters/mcp`, `adapters/workflow_control`, `adapters/health` | Bound requests, derive identity, filter and dispatch interfaces |
| Access | `access.py`, `domain/authorization.py` | Human capabilities, ownership, workload shape, grant binding |
| Catalog | `catalog/feature.py` | Human open-catalog reads |
| Model context | `model_context/`, `application/snapshot.py`, `application/dbml.py` | Model reads, Assertions, readiness, snapshots, DBML |
| Change control | `change_sets/feature.py`, `application/compiler.py` | Draft lifecycle and complete future-graph validation |
| Run state | `workflow_runs/`, `profiling_runs/`, `mapping/` | Grants, summaries, Profiling Runs/receipts, committed Mapping reads |
| Contracts | `contracts/` | Pydantic models, registry, canonical JSON, schemas, examples |
| Persistence | `infrastructure/postgres.py` | One production repository, pool, transactions, locks, SQL |
| Resource cache | `infrastructure/snapshots.py` | Bounded reconstructible bytes |
| Operations | `observability.py`, `promotion.py`, `release_integrity.py` | Safe telemetry and release-bound mutation registration |

Each MCP tool binds directly to one feature. There is no generic service
facade.

## Databricks modules

| Area | Main modules | Responsibility |
|---|---|---|
| Notebook seam | `notebook_definition.py`, `notebook.py` | Compile config once, load grant, enforce deadline, return safe JSON |
| Production wiring | `adapters/production.py`, `adapters/settings.py`, `adapters/identity.py` | Strict environment, managed identity, workflow construction |
| MCP | `adapters/mcp.py`, `adapters/workflow_mcp.py` | Bounded structured calls and resource downloads |
| Snapshot | `adapters/snapshot.py`, `adapters/projection.py` | Verify archive and project workflow-specific context |
| Agent execution | `adapters/agents.py` | One selected runtime under shared budgets and safety rules |
| Spark | `adapters/spark.py`, `profiling/spark.py`, `analysis/spark.py` | Fixed physical reads and metrics |
| Shared runtime | `runtime/` | Requests, context, coverage, graph, policy, execution, handoff |
| Workflows | `profiling/`, `analysis/`, `conceptual/`, `logical/`, `dimensional/`, `mapping/`, `dbml/` | Workflow-specific orchestration and deterministic rules |

## Test ownership

- `tests/mcp/`: App Service behavior, identity, configuration, and repository.
- `tests/workflows/`: Databricks runtime and all seven workflows.
- `tests/contracts/`: wire compatibility and architecture boundaries.
- `tests/database/`: static SQL plus fixture-owned PostgreSQL behavior.
- `tests/acceptance/`: artifact, boot, and cross-boundary workflows.
- `tests/support/`: test-only fakes and disposable fixtures.

No test code is copied into either deployment.

## Generated and immutable material

- Generated schemas and registry assets under `mcp_server/.../contracts/` are
  checked-in compatibility artifacts. Regenerate them through their owner;
  never hand-edit semantic content.
- `reference_snapshot/` is immutable planning evidence. Production code must
  not import it or add it to `PYTHONPATH`.
- The live sibling reference workspace is read-only and is never a build,
  test, formatting, or output target.

Primary source: [`docs/code-guide/01-repository-map.md`](../code-guide/01-repository-map.md).
