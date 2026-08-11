# Operations and deployment

## Operating model

Release 1 has three independently deployed parts:

1. a PostgreSQL 16 database created from the canonical eleven SQL files;
2. one Azure Linux App Service ZIP containing the MCP modular monolith; and
3. one immutable Databricks source release containing the jobs library and
   seven separate notebooks.

Both Python runtimes use the `3.12.*` release line with exact locked production
dependencies. PostgreSQL is the pinned 16 release line.

The database is installed by a deployment identity before the application
starts. App Service startup never applies DDL. The jobs release never contains
database credentials and never imports App Service code. Deployment and cloud
mutation require separate environment authority; repository verification alone
does not grant it.

## Configuration and fail-closed startup

Configuration comes from the environment or approved secret references, never
from a checked-in `.env` file. Invalid configuration exposes process liveness
but keeps readiness and product traffic unavailable.

### App Service

`RuntimeSettings` requires:

- production mode, one PostgreSQL DSN with a host, database, and
  `sslmode=verify-full`;
- the exact workload Entra Tenant and Object IDs;
- one credential-free HTTPS MCP URL ending at `/mcp`;
- a bounded cursor-signing key and HTTPS enforcement;
- request concurrency, request timeout, draft TTL, snapshot, and cache bounds;
- schema version `1.0.0`; and
- per-instance pool settings that pass the runtime's
  `WEB_CONCURRENCY * pool_max <= budget - headroom` check.

The deployment owner must additionally size all instances so
`instance_count * WEB_CONCURRENCY * pool_max <= database_connection_budget -
connection_headroom`.
Runtime settings do not discover the App Service instance count.

The runtime login has exactly one direct database-role membership,
`gds_app_write`. It is not the migration owner, administrator, superuser, or a
member of another database group. Startup verifies that posture and closes a
new pool when it differs.

The process is read-only by default. A bare mutation flag is invalid. Mutation
registration requires the complete release-evidence binding described in
[Testing and release](11-testing-and-release.md#release-evidence-and-promotion).

Production telemetry also requires environment-owned retention, access, and
deletion policy. Payload tracing must be `false`. No production test
authenticator or test signing-key setting exists.

Intended defaults are pool min/max `1/5`, pool timeout `10` seconds,
`WEB_CONCURRENCY=2`, connection budget/headroom `100/20`, request timeout `120`
seconds, request concurrency `64`, draft TTL `14,400` seconds, and snapshot
archive/cache `64/256` MiB. The cursor key is 32–4,096 bytes. Production
telemetry retention is explicitly supplied and bounded to 1–3,650 days. See
[current gaps](14-current-gaps.md) for a late numeric-validation defect; the
defect is not the intended policy.

### Databricks jobs

The production jobs adapter accepts only:

- the HTTPS MCP URL and its Entra `/.default` scope;
- one approved Microsoft Foundry `/openai/v1/` URL and
  `https://ai.azure.com/.default` scope;
- an optional managed-identity client ID;
- bounded request timeout and token-refresh margin; and
- for DBML only, one `/Volumes/<catalog>/<schema>/<volume>` root.

Bearer tokens and client secrets are intentionally absent. Managed identity
obtains tokens lazily. Normal workflow behavior belongs to the checked-in,
compiled Notebook Definition, not mutable environment variables. Each task
receives only `WorkflowRunID` and `WorkflowGrantID` widgets.

Jobs request timeout defaults to 60 seconds and is bounded to 1–300. Token
refresh margin defaults to 300 seconds and is bounded to 30–900.

The exact environment-key owners are:

- App runtime: `GDS_ENVIRONMENT`, `GDS_DATABASE_DSN`,
  `GDS_DATABASE_POOL_MIN`, `GDS_DATABASE_POOL_MAX`,
  `GDS_DATABASE_POOL_TIMEOUT_SECONDS`, `GDS_DATABASE_CONNECTION_BUDGET`,
  `GDS_DATABASE_CONNECTION_HEADROOM`, `WEB_CONCURRENCY`,
  `GDS_WORKLOAD_ENTRA_TENANT_ID`, `GDS_WORKLOAD_ENTRA_OBJECT_ID`,
  `GDS_MCP_PUBLIC_URL`, `GDS_CURSOR_SIGNING_KEY`, `GDS_REQUIRE_HTTPS`,
  `GDS_REQUEST_TIMEOUT_SECONDS`, `GDS_REQUEST_CONCURRENCY_LIMIT`,
  `GDS_DRAFT_TTL_SECONDS`, `GDS_SNAPSHOT_MAX_BYTES`,
  `GDS_SNAPSHOT_CACHE_BYTES`, `GDS_SCHEMA_VERSION`, and platform-owned `PORT`;
- App telemetry: `GDS_TELEMETRY_RETENTION_DAYS`,
  `GDS_TELEMETRY_ACCESS_OWNER`, `GDS_TELEMETRY_DELETION_OWNER`, and
  `GDS_TELEMETRY_TRACE_PAYLOADS`;
- jobs transport: `GDS_JOBS_MCP_URL`, `GDS_JOBS_MCP_SCOPE`,
  `GDS_JOBS_OPENAI_BASE_URL`, `GDS_JOBS_OPENAI_SCOPE`, optional
  `GDS_JOBS_MANAGED_IDENTITY_CLIENT_ID`,
  `GDS_JOBS_REQUEST_TIMEOUT_SECONDS`,
  `GDS_JOBS_TOKEN_REFRESH_MARGIN_SECONDS`, and optional
  `GDS_JOBS_DBML_OUTPUT_ROOT`; and
- jobs telemetry: the same four policy suffixes under the
  `GDS_JOBS_TELEMETRY_*` prefix.

`startup.sh` requires `PORT`, `WEB_CONCURRENCY`, and
`GDS_REQUEST_TIMEOUT_SECONDS` to be positive integers. This startup boundary is
stricter than the Python settings parser, which represents the request timeout
as a number of seconds.

## Integration boundaries

| Integration | Product use | Boundary |
|---|---|---|
| Easy Auth v2 | Authenticate human and workload HTTP requests | App code parses bounded normalized claims; it does not validate token signatures itself |
| PostgreSQL | Authoritative Models, drafts, runs, grants, receipts, idempotency, and audit | Only App Service connects; jobs have no driver or credentials |
| Databricks | Run one of seven predefined notebooks | Launch is an operator/platform action; the workload activates through MCP |
| Spark and catalog | Read approved Bronze/Silver physical data for deterministic workflow work | Raw rows do not cross MCP and generated Mapping code is not executed |
| Microsoft Foundry | Agent-backed Analysis, Conceptual, Logical, Dimensional, and Mapping phases | Managed identity, one approved endpoint, typed output, shared budgets, no provider tracing |
| Unity Catalog Volume | Publish verified DBML files | DBML only; writes stay beneath one configured root and use safe relative paths |
| Telemetry service | Collect typed JSON diagnostics and metrics | It is diagnostic only; PostgreSQL audit remains authoritative |

Physical Silver/Gold registration, generated-code execution, platform identity
changes, and cloud deployment are not App Service or notebook responsibilities.

## Deployment artifacts

### Database

`database/01_*.sql` through `database/13_*.sql` are one fresh-install schema, not
an in-place migration chain. Apply them once, in order, in one transaction with
the migration identity. There is no destructive downgrade or populated-
database cleanup helper.

### App Service ZIP

The selected ZIP root contains only:

- `app.py`;
- `startup.sh`;
- `requirements.txt`;
- `BUILD_MANIFEST.json`; and
- the installed `gds_etl_workbench` package and approved assets.

It excludes tests, notebooks, jobs source, SQL, secrets, caches, symlinks,
reference material, and nested archives. `startup.sh` starts Gunicorn with
Uvicorn workers. Every packaged file is bound by the build manifest and release
evidence.

The deployment path reopens the selected ZIP without following symlinks, then
hashes and uploads from that same open file descriptor. It rejects any digest
change between selection and upload. This prevents an artifact swap after
verification.

### Databricks source release

The jobs artifact publishes the allowlisted `gds_etl_jobs` source beneath the
immutable release folder, currently
`/Workspace/GDS_ETL/releases/2026.08.06.2/library`, plus seven notebooks. There
is no first-party wheel. Third-party dependencies come from the complete
hash-bound `requirements-databricks.txt` closure exported from `jobs/uv.lock`.

The deployment identity may create a release; the workload may only read it.
A published release is never changed in place. The checked-in Workflow
Deployment registry binds each job key to its workflow, source release,
Notebook Definition version, and delegated MCP operations.

## Process lifecycle and health

Startup validates settings, telemetry policy, mutation proof, and all seven
Workflow Deployment definitions before composing features. It then opens one
bounded PostgreSQL pool, verifies runtime posture, starts an immediate expiry
pass, and repeats draft/grant expiry every 30 seconds. Shutdown drains bounded
work, cancels the expiry task, closes the pool, and flushes telemetry.

- `GET /health/live` checks only that the process can respond.
- `GET /health/ready` checks bounded database access, exact role posture,
  schema `1.0.0`, and a safe pool-saturation ratio.
- Excess protected-request concurrency fails quickly with `429`.
- Requests beyond the configured deadline fail with `504` if response headers
  have not started. If a streaming MCP response has started, the server ends
  the stream and cannot replace it with a new `504` envelope.

Do not route traffic until readiness is `200`. After deployment, verify human
and configured-workload MCP inventories, actor-projected contract resources,
hidden-name behavior, snapshot contents, and DBML archive integrity.

## Observability and audit

PostgreSQL transactional records are the source of truth. Logs, metrics, and
alerts help diagnosis but never prove that a mutation committed.

Diagnostics use fixed typed JSON fields. Human work uses its validated request
correlation ID. A workflow uses `workflow:<workflow-run-uuid>` across
activation, MCP, jobs, audit, retries, and completion. Hidden MCP calls are
recorded only as the generic unregistered operation.

The code-owned metrics are:

- request latency, readiness failures, and database pool saturation;
- workflow latency, retries, repair rounds, model calls, model tokens, and
  materialization failures; and
- typed errors, conflicts, validation findings, draft expiry, grant expiry,
  and idempotent replay.

Diagnostics never contain prompts, physical values, generated documents,
credentials, secret names or references, connection strings, tokens, complete
MCP bodies, raw model output, or exception text. Environment owners define and
evidence retention, access review, deletion, alert destinations, thresholds,
and escalation.

## Recovery rules

| Condition | Safe recovery |
|---|---|
| Lost mutation or no-op response | Retry the exact actor-bound idempotency key and request content; trust the durable receipt |
| Stale or expired draft | Read current state and build a new Change Set; never force a revision or extend expiry |
| Revoked or expired Workflow Grant | Stop the workload and obtain fresh human authorization |
| Post-commit Mapping materialization failure | Retry generation from the immutable receipt and committed state; never apply again |
| Snapshot or DBML cache loss | Request the same revision and rebuild from PostgreSQL; verify the content-addressed manifest |
| Pool exhaustion | Preserve liveness, return bounded backpressure, reduce load or workers, and restore valid pool arithmetic |
| Database recovery | Restore into a separate database, validate schema, privileges, and audit continuity, then change configuration through review |

Normal recovery is a forward fix. Rollback is allowed only by pairing a prior
content-addressed release with a separate database created from that release's
exact schema and evidence. Never route an older binary to an incompatible
database or run destructive downgrade SQL.

Authoritative sources:
[`configuration.py`](../../mcp_server/src/gds_etl_workbench/configuration.py),
[`runtime.py`](../../mcp_server/src/gds_etl_workbench/runtime.py),
[`jobs adapters/settings.py`](../../jobs/src/gds_etl_jobs/adapters/settings.py),
[`App Service runbook`](../runbooks/app-service.md),
[`Databricks runbook`](../runbooks/databricks.md),
[`observability policy`](../operations/observability.md), and
[`recovery runbook`](../runbooks/recovery.md).
