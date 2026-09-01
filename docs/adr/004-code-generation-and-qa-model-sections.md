# ADR 004: Code Generation and QA as Model Sections

- Status: accepted
- Date: 2026-08-31

## Context

Code Generation currently stores mutable SQL outside Model Change Sets, while
the local GDS plugin treats generated code as an ungoverned local artifact. QA
definitions do not yet exist. This prevents generated code and QA intent from
participating in the same review, validation, Apply, revision, Snapshot, and
large-dataset handoff used by the rest of the Model.

The operational pipeline uses Process metadata to schedule and execute code.
Those runtime rules are useful generation guidance but are not part of this
Workbench change.

## Decision

Code Generation and QA are first-class Model Sections.

- Code Generation contains one Code Artifact per Model Object.
- A Code Artifact stores its complete SQL-file, Python-file, or Python-notebook
  content and a server-verified digest. Artifact content has no separate
  domain-level size limit; transport and Change Set safety bounds remain
  independent concerns.
- QA contains Validation Groups and Validation Checks. A Group belongs to one
  Model, Tenant, and System. A Check belongs only to its Group.
- Except for `executes_successfully`, Query A and query-valued Query B each
  produce exactly one row and one column at runtime. Both cells use the Check's
  declared result type. Any other cardinality is a query-contract execution
  error, not an assertion failure. `executes_successfully` ignores Query A's
  result shape and never has Query B.
- QA authoring requires applied Mapping. It uses current relevant Code
  Artifacts when they exist; Code may be absent. Explicit user input is
  additional context.
- The Model Snapshot derives one read-only QA authoring context per eligible
  source System. It supplies the exact Mapping digest, nullable current-Code
  digest, and allowlisted current Code references. It is not Change Set data.
- Code Generation and QA Candidates use the normal Model Change Set lifecycle:
  local review, Stage, server Validate, explicit Apply, and Model revision
  advancement. An unchanged Candidate remains a no-op.
- Applied Code and QA records are included in the normal immutable Model
  Snapshot and its manifest inventory. No separate Code or QA Snapshot type is
  introduced.
- Code and QA currentness is derived from their exact stored input digests. A
  later unrelated Model revision does not by itself make them stale.
- A Validation Group's System is the pipeline/source System. Its Mapping
  context digest hashes the canonical, name-keyed list of complete active
  target Mapping-context digests that include that source System. Its optional
  Code context digest hashes the canonical list of current active Code
  Artifact digests for those targets. The Code digest is required when at least
  one current relevant artifact exists and is `NULL` otherwise.
- Code Artifact context is verified against the canonical per-target result of
  `workflow.list_code_generation_target_context`. Mapping and Code, or Code and
  QA, are applied in successive Change Sets; a dependent Candidate cannot be
  co-staged with the upstream context it claims to have read.
- Later upstream changes may leave an applied Code Artifact or Validation Group
  stale. That retained state does not block unrelated Model changes; exact
  context checks run when the dependent record is staged again.
- Apply stores Model state only. It never executes SQL or Python, deploys a
  file, changes Process scheduling, or implements pipeline orchestration.

The GDS plugin records the pipeline's same-session SQL and final-result contract
as generation guidance only. Before any plugin-originated Databricks SQL call,
the plugin records one session policy: `never`, `essential`, or `as_needed`.
It uses only the existing governed `execute_databricks_sql` tool. Declining
runtime profiling or query verification never blocks local authoring.

## Consequences

Model Snapshot and Model Change Set contracts gain Code Generation and QA
datasets. Web, notebooks, MCP, and the plugin share the same records and Apply
boundary. The terms QA and Validation Check remain distinct from authoritative
Model Change Set validation.

Code stays one logical artifact regardless of how a client transports its
content. Operational execution and persisted Profiling remain separate
workflows.
