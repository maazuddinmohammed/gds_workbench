# ADR 004: Code Generation and Validation as Model Sections

- Status: accepted
- Date: 2026-09-01

## Context

Generated Code and Validation definitions must participate in the same
Snapshot, review, Model Change Set, revision, and audit boundary as the rest of
the Model. Runtime orchestration remains a manual handoff: the agent authors and
preflights SQL, then the user places it in the required path and runs the
orchestration layer.

## Decision

Code Generation and Validation are first-class Model sections.

- A Code Artifact belongs to one Model Object Binding and stores an artifact
  name, type, complete content, status, and server-derived integrity context.
- Code-to-source-System associations are separate records. This supports one
  file per System or one combined file for several Systems without encoding
  file layout in Mapping.
- Active transformation artifacts cover every active target Mapping source
  System exactly once. Support files may have no source-System association.
- Mapping documents remain flexible JSON. Output Templates guide their shape
  but are not a database-enforced schema.
- Validation contains Validation Groups and Validation Checks. A Group belongs
  to one Model, Tenant, and System. A Check belongs to its Group.
- Validation authoring uses applied Mapping and current generated Code when
  present. The server derives and stores internal currentness digests; public
  records do not carry author-authored technical digests.
- Validation stores definitions only. It never stores execution results.
- Code and Validation use the normal Model Change Set lifecycle. Apply stores
  Model state and advances the Model revision; it does not execute, deploy, or
  schedule an artifact.
- Mapping may be followed by Code and Validation in later Change Sets. A
  dependent step never proceeds without the required applied Binding and
  Mapping context.
- Unrelated Model changes do not automatically invalidate retained Code or
  Validation. Currentness is derived from their exact relevant inputs.

Generated SQL may be preflighted with the existing governed
`execute_databricks_sql` tool. It can prove syntax and bounded query behavior,
but missing upstream loaded data is not itself a generation failure.

## Consequences

Model Snapshots and Model Change Sets share `generated_code`,
`generated_code_source_system`, `validation_group`, and
`validation_check` datasets. Web, notebooks, MCP, and the Agent Plugin use
the same records and Apply boundary.

Process registration and orchestration triggers are later, separate workflow
concerns. Generated file placement and production execution remain explicit
user handoffs.
