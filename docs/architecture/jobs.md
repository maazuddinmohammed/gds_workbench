# Historical Databricks jobs architecture

> This records the superseded Workflow Grant and source-loaded `jobs/` design.
> It does not describe the current independent source-imported notebooks. See
> [`databricks_notebooks/README.md`](../../databricks_notebooks/README.md) for the
> eight current workflow entry points, prerequisite notebooks, and shared-code
> boundary.

## Boundary and authority

The jobs source computes Candidates and deterministic convenience exports. It
is not an authority for metadata. A job reads and changes metadata only through
authenticated, typed MCP calls. It
imports no PostgreSQL client, receives no database credentials, and cannot
deploy physical Silver or Gold objects. The MCP App Service remains responsible
for Tenant authorization, locks, compare-and-swap revisions, future-graph
validation, ordered persistence, audit, and transactions.

A predefined Databricks task receives only two non-secret UUID handles:
`WorkflowRunID` and `WorkflowGrantID`. The workflow calls these MCP tools first,
in this order:

1. `activate_workflow_run`, with the fixed Databricks workspace and job identity,
   the source-release version, the Notebook Definition audit values, and safe
   workspace/job/run evidence;
2. `get_workflow_run_contract`, with the same handles.

The workflow validates the returned `workflow_request` once. It verifies the
handles, workflow, active and unexpired state, configured workspace/job identity,
allowed operations, source release, and Notebook Definition audit values. It
then keeps the typed value through the workflow. A widget cannot replace the
operation, coverage, selection, lifecycle, Model, workspace, job, or release.

The workload's server-derived `ActorKind` exposes the nine shared MCP tools
(`get_model`, `check_model_readiness`, `get_model_snapshot`,
`get_model_dbml`, `get_model_change_set`, `create_model_change_set`,
`put_model_change_set_section`, `validate_model_change_set`, and
`apply_model_change_set`) and the eight workload-only tools
(`get_mapping_materialization`, `get_profiling_run`,
`get_workflow_run_contract`, `complete_workflow_no_op`,
`complete_dbml_export`, `activate_workflow_run`, `create_profiling_run`,
and `complete_profiling_run`). It cannot discover or
invoke the five human-only catalog/navigation tools. Without verified mutation
promotion, only the workload's eight read-only tools are registered. With
promotion, workload discovery contains exactly 17 tools; promoted human
discovery contains 14.

Humans authorize or revoke outside MCP through the fixed workflow-control
routes. Authorization returns safe run/grant handles, but it does not launch a
job. An operator manually starts the predefined task with those two handles;
the workload then activates and obtains its immutable contract through MCP.

## Source loading

There is no first-party jobs wheel. Deployment copies only the allowlisted jobs
source into a fixed, versioned, read-only workspace folder. Each notebook adds
that folder's parent to `sys.path` before its first jobs import:

```python
import sys

GDS_JOBS_PARENT_PATH = "/Workspace/GDS_ETL/releases/2026.08.06.2/library"
if GDS_JOBS_PARENT_PATH not in sys.path:
    sys.path.insert(0, GDS_JOBS_PARENT_PATH)

import gds_etl_jobs as gds

definition = gds.compile_notebook_definition(
    workflow="analysis",
    agent_runtime=AGENT_RUNTIME,
    source_release="2026.08.06.2",
    notebook_definition_version="analysis-2",
    agents=AGENT_CONFIG,
    workflow_settings=WORKFLOW_CONFIG,
    prompt_parameters=PROMPT_PARAMETERS,
)

gds.run_databricks_notebook(definition, dbutils=dbutils, spark=spark)
```

The deployment identity alone can create the versioned folder. The job identity
can only read it. A release never changes in place. Rollback selects an older
approved versioned folder and updates the predefined task. Third-party packages
come from the approved cluster environment. They do not change how first-party
source is loaded.

The seven notebooks remain separate:

- Profiling
- Analysis
- Conceptual
- Logical
- Dimensional
- Mapping
- DBML

Each of the five agent-backed modeling notebooks owns one allowlisted runtime choice, its Foundry
deployment, optional reasoning effort and verbosity, bounded outer retries,
parameterized system and instruction prompts, requested tools, model limits,
and workflow settings. This configuration is called the **Notebook
Definition**. The runtime choice is exactly `openai_agents_sdk`,
`langchain_create_agent`, or `langchain_deep_agent` and applies to all phases
in that workflow. The notebook compiles the definition once at startup. It
does not load a generated profile, workflow-configuration, phase registry, or
arbitrary runtime module. Profiling and DBML have no runtime or agent
configuration. Both are deterministic and make no model call; DBML also makes
no Spark call.

The shared adapter uses Microsoft Foundry's credential-free OpenAI-compatible
v1 endpoint and treats each phase's `model` as the Foundry deployment name.
Managed identity supplies bearer tokens. Framework-native retries are disabled;
the existing bounded outer loop owns retries, while one aggregate provider-call
and generated-token budget covers every model node and reserves at least one
call and one request-token share for each remaining outer attempt. MCP
event-stream reconnects are also zeroed.
LangChain uses an explicit tool-based structured-output strategy. Deep Agents
has ephemeral state only, with built-in filesystem/execute calls denied and its
default subagent, persistence, memory, skills, tracing, and ambient profile
plugins unavailable. A final prompt boundary removes Deep's injected
filesystem instructions; its notebook-selected 64 KiB aggregate context cap
keeps the pinned middleware's message-eviction paths unreachable.
The Databricks requirements artifact is the complete frozen, SHA-256-bound
production dependency closure, rather than direct pins that a cluster could
resolve to a different transitive graph or substituted same-version artifacts.

## Dependency direction

```text
seven source-loaded notebooks
    -> compile Notebook Definition once
        -> one workflow entry interface
            -> typed workflow core
                -> typed MCP / Spark / agent interfaces
                    -> Databricks implementations
```

Core modules import no Databricks globals. PySpark stays in portable helpers and
the Databricks implementation. Provider SDKs and cloud transports stay in the
Databricks implementation. No jobs module imports MCP App Service internals.

## Notebook Definition

The notebook supplies plain Python data. The jobs source converts it into one
immutable typed definition at startup. Both prompt templates use Jinja with
`StrictUndefined`. A missing parameter, unknown field, invalid tool request, or
limit outside a code-owned hard maximum stops before activation, Spark, or a
model call.

Model names, reasoning settings, prompt text, prompt parameters, and normal
workflow limits are developer guidance. The notebook can change them in a new
source release. The jobs source still owns the tool allowlist, hard resource
limits, typed output schemas, redaction, and safe logging. MCP and PostgreSQL
still own authorization and data-integrity rules.

Prompt compilation and definition validation happen once. Prompt rendering
happens for each call with the already compiled template and typed parameters.
Raw prompts, rendered prompts, provider output, and source rows are never sent
to MCP or telemetry.

## Validation seams

Raw data becomes a trusted typed value once at each seam:

1. Compile the Notebook Definition at notebook startup.
2. Parse the MCP run contract after the authenticated response.
3. For modeling workflows, parse each Model Snapshot into one indexed
   `VerifiedModelGraph`; DBML instead verifies the immutable DBML manifest and
   every ZIP member before publication.
4. Validate each new provider output against its phase output type.
5. Validate each complete Candidate before handoff.

A repair attempt creates new output, so it is validated again. Code does not
convert a trusted model to a dictionary only to repeat the same shape checks.
Apply still rechecks changing authorization, grant, expiry, lock, Model
revision, Candidate digest, graph, compare-and-swap, and idempotency facts in
the server transaction.

## Shared execution invariants

- Pydantic contracts are frozen and reject unknown fields.
- `coverage=full` forbids a selection field, including an explicit empty list;
  `coverage=selected` requires a nonempty, unique, positive selection.
- Canonical JSON sorts keys, forbids floats and non-string keys, and supplies
  stable SHA-256 digests and section-local refs.
- Coverage ledgers require one explicit terminal disposition for every owned
  slot. Pending and fatal slots block release; only a workflow-defined
  nonfatal disposition may proceed.
- Every configured phase has one deterministic `<workflow>.<phase>` identity.
  Its notebook entry binds model guidance, compiled prompts, requested tools,
  turns, retries, concurrency, context size, and repair rounds. The jobs source
  rejects unknown tools, output-schema drift, or limits above its hard maxima
  before contacting the provider.
- Agent work is typed, read-only, concurrency-bounded, timeout-bounded, and
  cancellation-aware. Analysis, Conceptual, Logical, and Dimensional each share
  one workflow-owned semaphore across their bounded parallel phases, so their
  sequential phase fan-outs cannot each establish an independent concurrency
  budget. Only classified provider failures retry.
- Repair regenerates a complete candidate from frozen inputs. It retains the
  best diagnostics and stops on acceptance, limit, or repeated digest.
- Recursive diagnostic redaction removes sensitive keys, secret-shaped values,
  and oversized strings before safe rendering.
- Accepted modeling workflows create at most one whole replacement section.
  `WorkflowLaunch` owns the one grant activation; `FinalHandoff` then owns
  create, put with CAS, validate, and atomic apply. A valid zero-operation
  result calls the server-owned `complete_workflow_no_op`, creates no draft,
  and refetches committed Mapping materialization when required.
- The exact reconciler intents
  `create|update|unchanged|reactivate|needs_review|inactivate|deprecate`
  compile to at most one canonical operation per governed artifact. Content and
  lifecycle changes travel atomically; reactivation and `needs_review` carry an
  update document, while inactivation/deprecation are existing-ID lifecycle
  operations. Locked artifacts and incomplete dependent retirement closure
  block the whole candidate.
- `FinalHandoff` validates the authoritative change-set ID, draft revision,
  validation seal, candidate digest, and apply/no-op receipt at every boundary.
  A mismatched response fails closed instead of allowing the client to infer a
  commit or continue with a different server object.
- Deployment uses a source allowlist. It rejects tests, generated bytecode,
  symlinks, non-regular files, and files outside the jobs source and seven
  notebooks. Safe release evidence records the source revision, source release,
  and copied allowlist. Runtime trust comes from the fixed versioned folder,
  deployment permissions, configured workspace/job identity, and Notebook Definition
  audit values. A job never trusts a release identity supplied by a widget.

## Workflow contracts

| Workflow | Frozen input and coverage | Deterministic boundary | Persistence result |
|---|---|---|---|
| Profiling | Exact full/selected Objects and per-Connection DD-108 environment/mode batch policy | Column/literal batch filters and one aggregation per Attribute; technical, audit, and batch Attributes excluded | One bounded idempotent success/failure result is published atomically; all-failed records a retained failed attempt without advancing the Model revision |
| Analysis | Selected Bronze Objects, stable endpoints, existing outgoing relationships, and exact mode/target | Finder/Resolver coverage, one Reconciler/Reviewer loop, then at most one versioned Spark CASE pass over the frozen candidate | Pending staged Analysis or one final Analysis replacement/apply according to the exact mode branch |
| Conceptual | Selected Bronze Objects, baseline, Object Ledger, relationship evidence packages, Assertions, and Relationship Ledger | Sole whole-Model Reconciler, deterministic checks, unified Validator, repeated-digest repair | One `conceptual.json`; Support persists exactly one governed Object or same-Model Assertion Record basis |
| Logical | Selected Bronze Objects, topology/detail coverage, seven-family baseline, signal ledger, locks, and downstream dependency paths | Sole Reconciler, naming/audit projection, dependency waves, packaged Validators plus one Lead | One `logical.json`; policy audit Attributes are Boolean-marked and unsourced |
| Dimensional | Only active registered Logical-to-Silver Mapping sources, exact source contributions, seven families, and signals | First local policy projection, packaged semantic validation, second role-aware Gold FK/name/order projection | One `dimensional.json`; no Mapping write or Gold deployment |
| Mapping | Exact eligible `(target Object, source System)` pairs with pre-registered headers and DD-109 profile | Header Mapper, chunked Attribute Mapper, target Validator/repair, normalized packages, target/System DAGs and safe waves | One `mapping.json`, one atomic apply, then retryable name-only generator materialization |
| DBML | Applied Model revision; `conceptual`, `logical`, or `both`; Logical `complete` or `bundle`; color choice; and a safe relative output directory | Read and verify the immutable MCP ZIP, then publish regular manifest-listed files through a sibling pending directory and one atomic rename beneath the configured Unity Catalog Volume root | A safe relative publication receipt; byte-identical replay is idempotent, different existing bytes, traversal, and symbolic links fail closed; no Model revision change |

## DBML publication boundary

The DBML job receives no absolute output path. The server-frozen request carries
only a normalized relative directory plus the render choices. Deployment owns
the absolute `GDS_JOBS_DBML_OUTPUT_ROOT`, which must identify the approved Unity
Catalog Volume root; widgets cannot override or discover it. The workflow calls
`get_model_dbml`, reads the returned immutable ZIP resource, verifies the
archive digest, typed manifest, exact member names, sizes, and per-file digests,
and only then publishes.

The final directory is derived from that relative directory plus the Model ID,
Model revision, and export-digest prefix. Publication refuses traversal,
symbolic links, non-regular files, and a pre-existing directory whose bytes are
different. It writes a uniquely owned sibling pending directory, synchronizes
the files, and renames once. If the exact final bytes already exist, the result
is an idempotent replay. Only after publication succeeds does
`complete_dbml_export` record bounded digest, file-count, byte-count, and safe
relative-location metadata. The completion never exposes the configured root,
changes effective Model state, or advances the Model revision.

## Profiling and Analysis Spark boundary

Profiling's DD-108 policy distinguishes `NULL` from an explicit empty
incremental array. It resolves the exact case-sensitive active batch Attribute,
checks every signed BIGINT value against byte/short/integer/long or
`DECIMAL(p,0)`, and never casts the data column or interpolates SQL. An explicit
empty array is a deterministic no-op, never a full scan.

Analysis removes arbitrary Bronze query tools. Its Spark helper exposes one
static, versioned CASE expression. Spark failures propagate and block; normal
unsupported or rejected relationship classifications are successful diagnostic
outcomes. A discovery-only put durably leaves the run `awaiting_validation`.
When validation-only work is retried after a terminal apply, the adapter derives
`completed` versus `no_op`, applied revision, candidate digest, and replay state
from the persisted terminal change-set receipt; it never reconstructs success
from the retry request.

## DD-110 policy projection

Logical and Dimensional workflows consume code-owned naming, audit, surrogate,
Type 2, and foreign-key templates. Naming is deterministic PascalCase with an
explicit acronym set. Collisions and maximum-length failures block rather than
truncate or suffix. Dimensional FK projection copies the target Dimension
surrogate key type and nullability, includes role names when configured, and
orders dependencies only after relationship endpoints are complete.

## DD-109 Mapping safety

The persisted `mapping.standard@1.0.0` Pydantic/generator document profile
covers `HeaderMapperOutputV1`, `AttributeMapperBatchOutputV1`, and
`GeneratorDocumentV1`. Agent execution independently binds
`mapping.header_mapper`, `mapping.attribute_mapper`, and
`mapping.target_validator`, each with its own immutable limits and tool set.
Agent-stage documents may carry stable IDs; the final generator document
contains only names and complete embedded provenance. A recursive safety check
rejects database-ID field names, secret fields, secret-shaped values, documents
over 4 MiB, and incomplete target-column coverage. Mapping section payloads are
bounded at 16 MiB.

Existing Object/Entity and Attribute/Attribute binding identities are never
repointed. Package profile/artifact/instruction fields must normalize to the
same digest. Missing prerequisites, complete cycle paths, mixed Systems, and
unsafe shared-target parallel writes block before handoff. A generator failure
after a committed apply returns `materialization_pending`; retrying
materialization reads the receipt-bound committed Model snapshot and must not
reapply the candidate. A Mapping no-op has no change-set binding and
materializes the current committed Mapping state under its durable no-op
receipt.
