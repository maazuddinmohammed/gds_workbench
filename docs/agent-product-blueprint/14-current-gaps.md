# Current gaps and external boundaries

This page records observations from the working tree on 2026-08-07. These are
not intended product behavior. Reverify each item before acting because the
implementation may change.

## Confirmed implementation gaps

### Activation audit fields are not persisted

The `activate_workflow_run` binding creates audit keys `workspace_id`, `job_id`,
and `run_id`. The PostgreSQL repository reads `databricks_workspace_id`,
`databricks_job_id`, and `databricks_run_id`. Activation still binds the digest,
but the three database audit columns receive null.

Intended correction: use one typed audit model or identical field names at the
binding and repository seams, and add a real PostgreSQL assertion that all
three activation values persist and become write-once.

Sources:
[`tool_bindings.py`](../../mcp_server/src/gds_etl_workbench/adapters/mcp/tool_bindings.py)
and [`postgres.py`](../../mcp_server/src/gds_etl_workbench/infrastructure/postgres.py).

### Jobs canonical JSON is not Unicode-equivalent to the server

The server canonical serializer normalizes strings and object keys to Unicode
NFC and rejects keys that collide after normalization. The jobs serializer
sorts keys but does neither. A non-NFC value can therefore produce different
bytes and digests on the two sides.

Intended correction: share golden vectors without creating a production import
between packages, implement NFC value/key normalization and collision
rejection in jobs, and test byte parity for decomposed Unicode.

Sources: [`contracts/canonical.py`](../../mcp_server/src/gds_etl_workbench/contracts/canonical.py),
[`runtime/canonical.py`](../../jobs/src/gds_etl_jobs/runtime/canonical.py), and
[`contracts.md`](../architecture/contracts.md).

### Four numeric settings miss the fail-closed validation point

`RuntimeSettings.from_environment` checks its accumulated invalid-key set, then
parses pool timeout, request timeout, request concurrency, and draft TTL while
constructing the result. Those parsers can add invalid keys after the only
check. Bad values may enter settings or raise outside the intended
`ConfigurationError` path instead of producing the safe live-but-unready app.

Intended correction: parse every setting before the final invalid-key check,
then add startup tests for malformed and out-of-range values for all four keys.

Source: [`configuration.py`](../../mcp_server/src/gds_etl_workbench/configuration.py).

### Build mode is not enforced by four modeling runners

Accepted intent says Build must reject an existing effective layer, while
Extend starts from that layer. Current Analysis, Conceptual, Logical, and
Dimensional runners/readiness do not use `request.operation`, so Build can
proceed when its layer already exists. Mapping implements its specialized mode
behavior.

Intended correction: enforce the empty-layer Build precondition in readiness
and preserve each workflow's selected/full Extend semantics with rejecting
tests.

Sources: the four workflow modules under
[`jobs/src/gds_etl_jobs/`](../../jobs/src/gds_etl_jobs/) and DD-035/DD-051 in
[`FEATURE-001.md`](../../reference_snapshot/docs/features/FEATURE-001.md).

### Mapping incorrectly accepts a caller-selected route

Accepted DD-082 requires no caller-supplied route. Logical-to-Silver or
Dimensional-to-Gold must be inferred from immutable preregistered Mapping
headers with target-zone agreement. The current `MappingRequest` exposes a
`route` field and the workflow uses it.

Intended correction: remove the route through an explicit versioned contract
change, infer it from the frozen headers, and add mixed-route and wrong-zone
rejection tests.

Sources: [`mapping/contracts.py`](../../jobs/src/gds_etl_jobs/mapping/contracts.py)
and [`FEATURE-001.md`](../../reference_snapshot/docs/features/FEATURE-001.md).

### Combined Analysis retries can repeat Spark validation

Accepted DD-053 requires validation-only and combined retries to return the
completed frozen-Candidate outcome without rerunning Spark. The current replay
lookup is used only by validation-only.

Intended correction: perform the same completed-outcome lookup before the
combined path reaches Spark, and test that a lost final response does not cause
a second physical-data scan.

Source: [`analysis/workflow.py`](../../jobs/src/gds_etl_jobs/analysis/workflow.py).

## Documentation and generated-asset drift

- `.env.example` gives an `api://.../.default` Foundry scope, while executable
  jobs validation requires exactly `https://ai.azure.com/.default`.
- `.env.example` does not show `GDS_JOBS_DBML_OUTPUT_ROOT`; a DBML production
  run needs one exact `/Volumes/<catalog>/<schema>/<volume>` root.
- `jobs/runtime/handoff.py` still declares an unused `SCOPE` enum value. Jobs
  author Analysis, Conceptual, Logical, Dimensional, and Mapping; Model Scope
  is server-owned and must not be implemented from this legacy symbol.
- `IMPLEMENTATION_STATUS.md` records Git base `32dcffb...`; the inspected HEAD
  is `4449586...`. Treat the status file as dated evidence, not current Git
  identity.
- The three currently modified generated JSON assets are semantically equal to
  their committed versions but byte-reformatted: capabilities, Mapping schema,
  and registry. Generated parity and a clean-checkout T24 run require exact
  bytes. These pre-existing working-tree changes were not altered by this
  documentation work.

## Release evidence still missing

### T24 local release gate

The dated ledger reports 695 MCP tests, 527 Jobs tests including three Spark
tests, 25 PostgreSQL assertion groups, 26 traced invariants, and reproducible
source and App ZIP artifacts. Those results are useful evidence, but T24 is
still `BLOCKED_OSV_CONSENT`. The exact clean-checkout aggregate and two
explicitly consent-gated OSV audits have not completed. No valid final
promotion evidence exists, so verified mutation registration must remain off.

### T25 environment release gate

T25 is entirely `EXTERNAL`. There is no approved evidence here for Azure
PostgreSQL, App Service/Easy Auth, Key Vault or managed identity, Databricks,
Foundry model compatibility, Unity Catalog Volume publication, physical target
registration, or Mapping generator-document materialization. T25 requires
explicit user approval and the sentinel-guarded test environment. Local passing
tests must not be reported as environment release. Generated-code execution is
deferred beyond Release 1 and is not something T25 proves.

The promotion evidence format is operator-controlled and not provider-signed.
The present trust root is an operator who controls the selected App ZIP,
read-only evidence mount, and settings. Stronger signed provenance is future
work.

## Intentional Release 1 boundaries

The following are not defects:

- no UI, generic REST management API, generic dispatcher, or MCP prompts;
- no foundational CRUD, Model Scope mutation, lock toggles, Tenant Lease,
  individual graph mutation, arbitrary SQL, delete, or populated-DB cleanup;
- no startup migration, upgrade chain, down migration, or database downgrade;
- no server-side client path, file upload, arbitrary path write, or code
  execution;
- no direct Databricks access to metadata PostgreSQL or server internals;
- no workbench-owned Silver/Gold creation or execution/deployment of Mapping
  generator output; and
- no production claim for a live agent runtime until T25 proves its configured
  Foundry deployment.

The live sibling reference workspace has drifted independently. Only the
checked-in immutable `reference_snapshot/` and its verified manifest may be
used as historical evidence.
