# Interfaces and contracts

The public contract version is `1.0`, the installed database schema version is
`1.0.0`, and the current actor-aware registry version is `1.2.0`. These versions
have different owners and must not be treated as interchangeable.

## HTTP surface

| Path | Methods | Actor | Purpose |
|---|---|---|---|
| `/health/live` | `GET` | Anonymous | Process liveness only |
| `/health/ready` | `GET` | Anonymous | Database, schema, role, and pool readiness |
| `/mcp` | MCP Streamable HTTP methods | Human or configured workload | Actor-filtered tools and resources |
| `/workflow-control/v1/authorize` | `POST` JSON | Human | Create a pending Workflow Grant |
| `/workflow-control/v1/revoke` | `POST` JSON | Human | Revoke pending or active work |
| `/workflow-control/v1/status` | `POST` JSON | Human | Read bounded safe status |

Authorize and revoke require verified mutation promotion. Status and safe reads
remain available in read-only posture.

The three Workflow Control routes accept JSON only, use the standard request
and result bounds, require Easy Auth, return the common safe error envelope,
and set `Cache-Control: no-store`. They are not an expandable REST API.

## MCP tool inventory

The registry has exactly 22 tools.

### Human-only reads

1. `list_tenants`
2. `list_objects`
3. `get_objects`
4. `list_models`
5. `get_modeling_evidence`

### Shared tools

Read-only:

1. `get_model`
2. `check_model_readiness`
3. `get_model_snapshot`
4. `get_model_dbml`
5. `get_model_change_set`

Mutating:

6. `create_model_change_set`
7. `put_model_change_set_section`
8. `validate_model_change_set`
9. `apply_model_change_set`

### Workload-only tools

Read-only:

1. `get_mapping_materialization`
2. `get_profiling_run`
3. `get_workflow_run_contract`

Mutating:

4. `complete_workflow_no_op`
5. `complete_dbml_export`
6. `activate_workflow_run`
7. `create_profiling_run`
8. `complete_profiling_run`

A promoted human sees 14 tools. The exact configured workload sees 17. In
read-only posture these become 10 human and 8 workload reads. Discovery and
direct dispatch require both actor authorization and promotion registration.
Capabilities distinguish actor-available tools from currently enabled tools.
The registry lists the actor's complete inventory, including unpromoted
mutations, while schema resources expose only currently enabled tools. Hidden
and unknown names fail alike.

## MCP resources

| Resource | Identity |
|---|---|
| Server capabilities | `gds://contracts/v1/capabilities` |
| Contract registry | `gds://contracts/v1/registry` |
| Contract schema | Allowlisted schema name |
| Accepted/rejected example | Allowlisted classification and example name |
| Model Snapshot manifest and ZIP | Model ID, revision, archive SHA-256 |
| DBML manifest and ZIP | Model ID, revision, layer, mode, color mode, archive SHA-256 |

Snapshot and DBML bytes live in a bounded process-local cache. A missing entry
is rebuilt from PostgreSQL and accepted only when the complete content-addressed
URI remains identical. Every read reauthorizes the current principal, Model,
exact revision, and Workflow Grant when applicable. It also verifies the
archive digest and every digest in the embedded manifest. Possession of a URI
or cache entry does not grant access.

### Model Snapshot workspace layout

A Model Snapshot ZIP is both immutable workflow input and a transport-neutral
human authoring workspace. It contains:

- `input/manifest.json`, `input/model.json`, `input/source-catalog.json`, and
  `input/modeling-evidence.json`;
- `output/change-set.json` and one output file for each of the eight documents;
- `output/_workbench/activity.jsonl` and `latest-validation.json`; and
- an allowlisted `contract/` directory with common schemas, examples, the
  source-catalog schema, and the Mapping profile schema.

The manifest binds every listed member, Model revision, source-context digest,
Evidence digest, and total size. ZIP entries are deterministically ordered with
fixed metadata. The activity and validation mirrors never enter a Candidate
digest.

The current public `get_model_snapshot` request selects only Model and optional
expected revision, so its output workspace starts empty. A human reads an
existing draft through `get_model_change_set`. The feature's unused internal
draft-overlay argument is not a public contract and must not be exposed without
an explicit compatibility decision.

## Contract rules

- External Pydantic models are immutable and forbid unknown fields.
- Schema version is `1.0` unless a more specific version is named.
- Nullable fields are explicit; omission does not invent a meaning.
- `SectionOperation.document` is the one bounded generic extension point. The
  section adapter must validate it against its exact artifact model.
- Results are validated again before leaving the App Service or notebook.
- Errors use one bounded envelope with a stable public code, correlation ID,
  retryability, issues, and optional retry delay. Raw exception details are not
  returned.

The frozen public error codes are `invalid_request`,
`unsupported_schema_version`, `authentication_required`,
`authorization_denied`, `not_found`, `conflict`, `stale_model_revision`,
`stale_draft_revision`, `candidate_not_sealed`,
`candidate_digest_mismatch`, `draft_expired`, `idempotency_key_reused`,
`payload_too_large`, `rate_limited`, `dependency_unavailable`, and
`internal_error`. More specific internal causes map into this non-disclosing
vocabulary.

Canonical JSON v1 includes defaults and nulls, normalizes strings and keys to
Unicode NFC, sorts object keys, preserves meaningful array order, writes compact
UTF-8, normalizes supported timestamps/UUIDs/Decimals, and rejects floats,
non-finite values, cycles, binary data, non-string keys, and duplicate
NFC-normalized keys. SHA-256 over these bytes binds candidates, selections,
packages, requests, resources, and receipts.

The App Service implementation is authoritative for this serializer. See the
jobs-side parity gap in [current gaps](14-current-gaps.md).

## Size and count limits

Important registry limits are:

| Limit | Value |
|---|---:|
| Standard request/result | 1 MiB / 2 MiB |
| Whole-Section transport request | 17 MiB |
| Evidence Section | 4 MiB |
| Analysis or Conceptual Section | 8 MiB |
| Logical or Dimensional Section | 12 MiB |
| Mapping Section | 16 MiB |
| Change Set result | 64 MiB |
| Page size | default 50, maximum 200 |
| Multi-ID selection | 100 |
| Issues | 1,000 |
| Correlation or idempotency key | 128 characters |
| Snapshot or DBML manifest | 2 MiB |
| Snapshot archive / verified expanded content | 64 MiB / 256 MiB |
| DBML file count / one file | 1,002 / 12 MiB |
| DBML total files / ZIP archive | 16 MiB / 20 MiB |

Mapping adds stricter nested limits: 1,000 packages per run, 500 target
Attributes per deterministic agent chunk, 5,000 target Attributes per package,
and bounded JSON/text sizes defined by DD-109.

Paged reads use stable ordering and an opaque URL-safe cursor containing
version, collection, offset, and canonical filter digest. HMAC-SHA-256 binds
those bytes to the server cursor key. A changed filter, collection, signature,
or invalid offset rejects the cursor; it never carries authorization.

There are no MCP prompt definitions. Notebook prompts are deployment source,
not a discoverable server prompt surface.

## Workflow Deployment registry

All seven deployments use source release `2026.08.06.2`.

| Workflow | Job key | Definition | Delegated operation groups |
|---|---|---|---|
| Profiling | `gds-profiling` | `profiling-2` | readiness, Model/snapshot reads, Profiling create/read/complete, contract read |
| Analysis | `gds-analysis` | `analysis-2` | readiness, Model/snapshot reads, Analysis Change Set create/read/put/validate/apply, contract read |
| Conceptual | `gds-conceptual` | `conceptual-2` | readiness, Model/snapshot reads, Conceptual Change Set create/put/validate/apply, contract read |
| Logical | `gds-logical` | `logical-2` | readiness, Model/snapshot reads, Logical Change Set create/put/validate/apply, contract read |
| Dimensional | `gds-dimensional` | `dimensional-2` | readiness, Model/snapshot reads, Dimensional Change Set create/put/validate/apply, contract read |
| Mapping | `gds-mapping` | `mapping-2` | readiness, Model/snapshot reads, Mapping Change Set lifecycle, committed materialization read, contract read |
| DBML | `gds-dbml` | `dbml-1` | DBML read/complete and contract read |

The checked-in deployment registry, not the notebook or caller, selects the
allowed operations and expected release identity.

Exact sources:
[`registry-v1.json`](../../mcp_server/src/gds_etl_workbench/contracts/registry-v1.json),
[`workflow-deployments-v1.json`](../../mcp_server/src/gds_etl_workbench/contracts/workflow-deployments-v1.json),
and [`schemas/v1/`](../../mcp_server/src/gds_etl_workbench/contracts/schemas/v1/).
