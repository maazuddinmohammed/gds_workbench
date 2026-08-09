# Release 1 common contract registry

The common v1 registry is the compatibility interface shared by the MCP App
Service, developer clients, and source-loaded Databricks jobs. It is
transport-neutral: Pydantic models and generated JSON Schemas do not import MCP,
HTTP, PostgreSQL, Spark, Databricks, or provider SDKs.

## Runtime and dependency baseline

- Python is exactly the 3.12 release line.
- PostgreSQL tests use `postgres:16.13-bookworm` at the multi-platform index
  digest `sha256:472efd9a66f2b2f1a5aeb18b28de74332e6ef88c2b93a1a5d812fb6db67a5f60`.
- The MCP SDK is the stable `2.0.0` line. Pydantic, Psycopg/pool, Uvicorn, and
  Gunicorn are direct exact pins; all transitive versions and source hashes are
  frozen in `mcp_server/uv.lock`.
- Test and quality dependencies are exact pins. Tests do not load `.env`, and
  database tests reject DSN/PG/App-Service connection environment variables
  before starting their own disposable container.

The test fixture randomizes its database, role, password, and run marker,
verifies loopback/container/database/user/PostgreSQL-major ownership before
DDL, and exposes connections only through its opaque capability. Applying the
thirteen numbered SQL files is one fail-fast transaction and may happen once per
fixture. Stopping the container is the only cleanup operation.

## Canonical JSON v1

`canonical_json_bytes` is the single digest serialization implementation.

- Input is a Pydantic model or JSON-compatible value.
- Model defaults and explicit nulls are included; omission is therefore a model
  validation decision, not a serializer heuristic.
- Strings and object keys are normalized to Unicode NFC and encoded as UTF-8.
- Object keys are lexicographically sorted; array order is preserved unless a
  specific contract validator has already normalized a set-like collection.
- Output uses compact comma/colon separators and no insignificant whitespace.
- Aware datetimes become UTC RFC 3339 values using `Z`; naive datetimes fail.
- UUIDs become lowercase standard strings. Finite Decimals become normalized
  non-exponent strings with insignificant trailing zeroes removed.
- Binary values, sets, cycles, non-string object keys, floats, NaN, Infinity,
  and duplicate NFC-normalized keys fail closed.

`canonical_sha256` returns lowercase SHA-256 over those bytes. Server-generated
activity and `latest-validation.json` mirrors are separate contracts and never
enter a candidate payload or digest.

## Strict common models

All external models are immutable and use `extra="forbid"`. They freeze:

- lifecycle `active|needs_review|inactive|deprecated`;
- owning-Tenant roles `developer|architect|admin`;
- workflows `profiling|analysis|conceptual|logical|dimensional|mapping|dbml`;
- workflow operations `build|extend` and artifact operations
  `create|update|lifecycle`;
- coverage `full|selected` and all six section names;
- typed existing/local references, issues, stable errors, pagination,
  idempotency, activity events, apply receipts, and snapshot manifests;
- six required whole-replacement section documents in canonical order.

`SectionOperation.document` is the sole deliberate common-schema extension
point. It is a bounded JSON object because T02 precedes the six layer schema
tasks. A section adapter must validate that object against the corresponding
versioned layer model before application code can accept it. Unknown fields are
forbidden everywhere else.

Create and update operations may carry a lifecycle atomically with their
complete document. Omission defaults a create to `active` and preserves an
update's current lifecycle; a lifecycle-only operation still targets one
existing ID and carries no document. Conceptual Object/Relationship operations
may additionally carry the bounded transient DD-054 fields `creation_basis`,
`source_object_ids`, `physical_support_object_ids`, and `evidence_refs_used`.
The contextual compiler verifies every declared source and physical-support
Object against both the frozen authoritative catalog and the exact Model Scope.
A verified-Evidence basis must resolve to an active record under an active
document, be marked verified, and be applicable to Conceptual modeling. The
compiler also checks future parent/support lifecycle, then strips all four
transient fields before effective-state comparison and persistence. They never
become Evidence foreign keys.

## Frozen MCP inventory

Every definition has one exact audience selected from the server-derived
`ActorKind`; an MCP client cannot declare or override it. The complete registry
contains 22 tools in three disjoint partitions:

Human-only (5, all read-only):

1. `list_tenants`
2. `list_objects`
3. `get_objects`
4. `list_models`
5. `get_modeling_evidence`

Shared (9):

1. `get_model` (read-only)
2. `check_model_readiness` (read-only)
3. `get_model_snapshot` (read-only)
4. `get_model_dbml` (read-only)
5. `get_model_change_set` (read-only)
6. `create_model_change_set`
7. `put_model_change_set_section`
8. `validate_model_change_set`
9. `apply_model_change_set`

Workload-only (8):

1. `get_mapping_materialization` (read-only)
2. `get_profiling_run` (read-only)
3. `get_workflow_run_contract` (read-only)
4. `complete_workflow_no_op`
5. `complete_dbml_export`
6. `activate_workflow_run`
7. `create_profiling_run`
8. `complete_profiling_run`

A human therefore has 14 available tools and the exact configured workload has
17. Verified mutation promotion registers all tools in the current actor's
inventory. Without it, registration is read-only: ten tools for a human and
eight for the workload.

Validation tools are not annotated read-only: although they never change
effective Model/Profile rows or `model_revision`, they persist outcomes/events
and refresh activity. `put_model_change_set_section` and apply carry a
destructive hint because they replace staged content or can transition effective
lifecycle. Annotations never grant access or select an audience.

`complete_workflow_no_op` is the only server-owned zero-operation terminal
path for modeling workflows. It requires the exact active grant, frozen request,
selection, workload, human/context identities, and an empty candidate; it
atomically completes the grant and run summary without creating a draft or
advancing the Model revision. Exact retries replay the durable receipt.

`get_model_dbml` is a read of applied Model state. Its strict request selects
`conceptual`, `logical`, or `both`, selects Logical `complete` or `bundle`
output, and enables or disables colors. A bundle contains complete and
per-Submodel views plus an optional default view for Entities with no Submodel.
It accepts no output path. Its result
identifies an immutable, Model-revision-bound ZIP resource and a typed manifest
whose sorted file inventory, per-file digests, total size, render options, and
export digest bind the output. An MCP client owns writing those returned bytes
to its current or selected directory; the App Service cannot write into a
remote client's filesystem.

The `dbml` Workflow Run freezes the same render options plus a bounded relative
output directory. `complete_dbml_export` is workload-only and records the
verified export and safe relative published directory only after the
deterministic Databricks workflow has published it under its configured Unity
Catalog Volume root. It does not change effective Model state or advance the
Model revision, and exact completion retries replay the durable receipt.

Resources expose capabilities, the registry, allowlisted schemas/examples,
revision-bound snapshot manifests/archives, and revision-bound DBML
manifests/archives. Release 1 exposes no MCP prompts.
The served capability and registry documents are projected to the current
principal. A tool-schema resource is served only when its tool belongs to that
principal's enabled MCP inventory. A hidden tool or schema fails with the same
generic response as an unknown name, before request-schema validation. This
projection is recomputed per request so cached human and workload sessions
cannot contaminate each other.

The generated capability asset records the complete audience classification.
The served capability resource adds the exact actor-projected registration:
`available_read_only_tools`, `available_mutating_tools`,
`mutation_registration_enabled`, `enabled_tools`, `read_only_tools`, and
`mutating_tools`. With the default read-only posture, the served
`mutating_tools` list is empty and `enabled_tools` is byte-for-byte derived from
the same names returned by MCP tool discovery.

The process composition root cannot pass a boolean into MCP registration.
`GDS_MUTATION_ENABLED=true` is only a request to validate a promotion; it does
not itself enable anything. Registration requires a `VerifiedMutationPromotion`
created from a bounded, read-only T24 evidence file, its independently pinned
digest, the selector-recorded App Service ZIP digest, and the extracted ZIP's
canonical `BUILD_MANIFEST.json`. The validator requires the exact complete
`local` or protected `ci` gate order (including both OSV audits), zero adverse
test outcomes, a clean recorded source revision, and matching source, contract,
lock, staged-content, and per-file identities. Any missing or mismatched input
makes runtime configuration unready and registers no tools.

There is no foundational mutation, Scope mutation, lock toggle, Tenant Lease,
generic database/Spark SQL, Connection value/secret retrieval, delete/cleanup,
arbitrary filesystem output, code execution, upload, or general REST surface.
The only non-MCP product routes beyond health are the three fixed workflow
control operations below. Modeling Evidence is authored only through the
Evidence section of a Model Change Set; Mapping has no independent apply tool.

## Human workflow-control contract

`authorize_workflow_run` and `revoke_workflow_run` are not MCP tools, MCP schema
resources, aliases, or prompts. Human control is limited to three strict
JSON-only routes:

- `POST /workflow-control/v1/authorize`
- `POST /workflow-control/v1/revoke`
- `POST /workflow-control/v1/status`

Authorize and revoke reuse their strict v1 request/result models and require a
process-start `VerifiedMutationPromotion`; when it is absent they return the
safe not-found envelope before parsing a body. Status is registered in read-only
posture. It requires the exact Workflow Run and Workflow Grant UUID pair and is
available only to the initiating human with current workflow authorization or
an owning-Tenant Tenant Admin/super admin. Missing, mismatched, and private identifiers
normalize to not-found.

The status result contains only `workflow_run_id`, `workflow_grant_id`,
`model_id`, `workflow`, `grant_status`, `run_status`,
`expected_item_count`, `completed_item_count`, `failed_item_count`,
`warning_count`, `started_time`, `completed_time`, `has_change_set`,
`has_profiling_run`, and `diagnostic_count`. It never returns the workload run
contract, prompts, source rows, Profile rows, raw diagnostics, secrets, or
arbitrary nested content. All three routes use the common safe error envelope,
request/result bounds, Easy Auth identity, and `Cache-Control: no-store`.

Active state is part of authorization. An inactive Tenant contributes no
membership or role to a resolved human principal and cannot authorize a read or
mutation; mutation resolution also fences the active Tenant row for the whole
transaction. An inactive Model remains safely readable to its owning Tenant,
but change-set authoring/validation/apply, workflow activation, and profiling
mutations reject it. Apply takes the authoritative Model-row lock first and
rechecks active state, authorization, revision, and context before committing.

The shared MCP `check_model_readiness` tool and non-MCP workflow authorize
operation call the same internal checker. It projects the bounded transitive
physical catalog, verifies exact Object/Attribute and ingestion endpoints,
Bronze Scope and request selection, context digests, and lock identities, then
applies workflow-specific batch, policy, Logical-to-Silver, registered-target,
Mapping-header, and business source-System lineage checks. The checker performs
reads only; it does not call an agent, Spark, or the filesystem.

`get_workflow_run_contract` is workload-only and lifecycle-aware. Normal reads
require the exact active, unexpired grant and every read re-resolves the
initiating human's current owning-Tenant workflow-authorize capability. A
completed grant is readable only for a Mapping materialization resume whose
allowed operations, selection digest, applied change set, receipt
candidate/revision, current Model revision, and one-way grant binding all agree.
Revoked, expired, non-Mapping, or incompletely bound completed grants fail
closed. Humans use the bounded workflow-control status operation instead; it
never exposes the immutable workload contract.

## Notebook Definition audit values

The Notebook Definition is notebook-owned configuration. It is not part of the
common generated registry. At startup, the jobs source strictly compiles the
definition. Its safe run identity contains the workflow, source release, and
Notebook Definition version. It never contains raw or rendered prompts, prompt
parameters, source values, provider output, secrets, secret references, or
bearer tokens.

The fixed Databricks workspace and job configuration, immutable source-release
folder, and safe run identity replace wheel, package-inventory, entry-point,
profile-registry, workflow-configuration-registry, and phase-registry identity.
The MCP run contract binds the expected source release and Notebook Definition
version. The jobs source compares them before Spark or a model call. Widgets
cannot supply or override them.

Model and reasoning settings, system and instruction prompt templates, prompt
parameters, requested tools, and workflow settings remain visible in each of
the five agent-backed modeling notebooks. Profiling and DBML are deterministic,
zero-agent Notebook Definitions. Code-owned hard limits, tool allowlists, typed agent outputs,
redaction, authorization, and database rules are not notebook-editable.

## Generated assets and compatibility

Run the generator only from the source tree:

```bash
uv run --project mcp_server python -m gds_etl_workbench.contracts.generate_assets
```

It writes deterministic JSON Schemas, accepted/rejected examples, capability
and registry resources, and a schema catalog containing each file hash plus the
canonical whole-bundle digest. Contract tests regenerate into a temporary
directory and require byte identity. Any intentional public change requires a
new versioned decision, updated models/registry/examples/documentation, and an
explicit golden diff; silent reinterpretation of v1 is forbidden.

The public generated bundle and a human-readable Model Snapshot have different
purposes. Snapshot construction copies an explicit transport-neutral allowlist:
the common section/reference/issue/receipt/manifest schemas, generic examples,
and the Mapping-standard and source-catalog contract documents. It does not
copy `capabilities-v1.json`, `registry-v1.json`, the schema catalog, or any MCP
tool request/result DTO schema. Snapshot membership is not derived by walking
the generated asset directory.

Each MCP `allowed_operations` array is sorted, unique, and validated with the
dedicated lowercase colon-segment operation-code grammar when the server creates
the Workflow Grant and when the jobs source parses the run contract. Generic
safe identifiers are not widened to accommodate delegated operation codes.

The jobs source does not generate phase prompts, profile selections, workflow
configuration, or a package manifest. Each notebook contains that developer
guidance. Root contract tests compile all seven Notebook Definitions with strict
missing-parameter handling and verify the code-owned tool and resource limits.
