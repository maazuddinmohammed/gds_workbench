# Decision record

This page explains the choices that define Release 1. It is a summary, not a
replacement for the accepted ADRs or approved decision text.

## Product-level choices

| Choice | Reason | Consequence |
|---|---|---|
| PostgreSQL is authoritative | Model state, authorization, locks, receipts, and idempotency need one transactional truth | Caches and Databricks output are reconstructible; jobs never write the metadata database |
| One feature-first App Service monolith | The features share identity, authorization, transactions, and one database | No microservices, internal HTTP, command bus, or event bus |
| Whole-Section Model Change Sets | A graph must be validated as one future state, not as unrelated row edits | Eight complete typed documents compile and apply atomically |
| Tenant Metadata Change Sets | Core metadata spans Objects, Attributes, Copy, and Process configuration | Twelve typed documents validate as one Tenant-owned draft |
| Server-derived actor inventories | Client metadata and discovered tool names are not authority | Human and workload MCP discovery and dispatch use the same projection |
| Workflow Control is outside MCP | Humans authorize work but must not see workload execution tools | Exactly three narrow human JSON routes; MCP remains actor-separated |
| Workload handles are references | A leaked UUID must not grant access | Every call rechecks identity, grant, run, human authority, operation, Model, binding, and expiry |
| Notebook-owned definitions, code-owned limits | Teams need editable prompts and model settings without editable safety rules | Each notebook selects phases and one runtime; common code owns budgets, tools, retries, redaction, and persistence |
| Source-loaded Databricks release | The target deployment cannot install a first-party jobs wheel | Seven notebooks load an immutable, versioned, allowlisted source tree |
| Deterministic projection around agents | Agent output alone cannot enforce graph, policy, or coverage rules | Typed output is compiled, normalized, checked, and repaired within fixed limits |
| Idempotency is durable | Network loss must not cause duplicate mutation | The key is bound to canonical request bytes and the durable response |
| One Model revision per effective transaction | Call counts and row counts are not useful versions | No-op, draft, validation, and export do not advance revision |
| Lifecycle instead of deletion | History and relationship integrity must remain auditable | Product roles have no delete or populated-database cleanup path |
| External physical registration | Release 1 governs metadata design, not infrastructure deployment | Silver and Gold registration pauses are explicit operator gates |
| Content-addressed archives | Snapshots and visual exports must be safe to cache and replay | URI, manifest, members, and SHA-256 digests form one immutable identity |
| Local proof before mutation promotion | A bare feature flag is not release evidence | Mutating surfaces register only when T24 evidence and the exact App ZIP digest verify |

## Approved data-design decisions

### DD-108: Profiling batch selection

Each Connection stores nullable development/test initial `BIGINT` values and
incremental `BIGINT[]` values. A declared batch Attribute uses the exact field
for the requested environment and mode. Null means unconfigured and blocks;
an empty incremental array is an intentional no-op. There is no environment,
mode, or unfiltered fallback. Arrays are ordered, unique, null-free, and limited
to 1,000 values. The exact-case batch Attribute must be active and integral,
and Spark uses column/literal expressions without casting the source column.

This preserves the distinction between missing configuration and an approved
empty batch, and prevents a bad filter from silently becoming a full scan.

### DD-109: combined Mapping persistence and profile

Mapping has one Source System Dependency control table plus Object Mapping and
Attribute Mapping. Dependency rows control parallel/sequential source waves.
Mapping rows bind modeled identities to registered targets and, when authored,
contain the transformation documents. Header authorship is all-or-null.
Existing binding identities cannot be repointed.

The only Release 1 profile is `mapping.standard@1.0.0` with
`HeaderMapperOutputV1`, `AttributeMapperBatchOutputV1`, and
`GeneratorDocumentV1`. Agent stages may use stable database IDs. The generator
document is derived after commit, uses names and provenance, contains no
database IDs or secrets, and needs no metadata lookup. Target Attribute chunks
contain at most 500 items. Package, section, coverage, dependency, and document
limits are fixed by the approved contract.

This keeps identity, transformation, validation, and post-commit generation in
one atomic model while ensuring generated content is based only on committed
state.

### DD-110: Silver and Gold policy documents

A Model stores exactly five JSON policy documents: two Silver documents and
three Gold documents. The Silver pair is complete or null; the Gold triple is
complete or null. A missing group is allowed for foundational bootstrap but
blocks the dependent workflow.

Release 1 naming is PascalCase only. Collision and overlength are errors; names
are never truncated or suffixed. Policies deterministically project audit
Attributes, Dimension surrogate keys, Type 2 fields, and role-aware Fact or
Bridge foreign keys. Agents never author or rename policy-owned technical
Attributes.

This makes generated technical structure reproducible and separates business
modeling judgment from platform policy.

The exact normative shapes are in
[`RELEASE-1-DECISIONS.md`](../design/RELEASE-1-DECISIONS.md).
They are application validation contracts, not PostgreSQL template-validator
functions. PostgreSQL enforces only Silver-pair and Gold-triple completeness.

## Complete Feature 001 decision coverage

Feature 001 contains 110 decision rows. The three rows frozen as open are
approved by the plan and release decision record. The table below accounts for
every row without duplicating its normative text.

| Decisions | Theme | Blueprint owners |
|---|---|---|
| DD-001–012 | Platform boundary, snapshots, Change Sets, lifecycle, cross-Tenant Scope, bounded reads, durable drafts, and client journal | [Intent](01-product-intent.md), [architecture](03-system-architecture.md), [contracts](06-interfaces-and-contracts.md), [Change Sets](08-model-change-sets.md) |
| DD-013–028 | Roles, delegation, secrets, revisions, Profiling atomicity, Mapping ownership, business locks, Tenant Lease exclusion, and relational identity | [Data](05-data-model-and-state.md), [security](07-security-and-invariants.md), [runtime](09-workflow-control-and-runtime.md) |
| DD-029–040 | Conceptual Support, generated IDs, workflow separation and coverage, build/extend, fresh DDL, Scope removal, and visibility | [Data](05-data-model-and-state.md), [Change Sets](08-model-change-sets.md), [workflow index](workflows/README.md) |
| DD-041–048 | Modeling Evidence terminology, persistence, read boundary, Section ownership, and context-only use | [Domain](02-domain-language.md), [data](05-data-model-and-state.md), [Conceptual](workflows/conceptual.md) |
| DD-049–053 | Analysis phases, Spark classification, reconciliation, repair, freezing, and execution modes | [Analysis](workflows/analysis.md) |
| DD-054–061 | Conceptual creation basis, notebook boundary, ledgers, Evidence packages, reconciliation, validation, and final handoff | [Conceptual](workflows/conceptual.md) |
| DD-062–065 and DD-091–102 | Logical details, validators, naming/audit projection, seven-family lifecycle, downstream protection, signals, locks, keys, cardinalities, types, and uniqueness | [Logical](workflows/logical.md), [data](05-data-model-and-state.md) |
| DD-066–078 | First-class Dimensional layer, seven-family shape, combined Mapping boundary, environment-neutral identity, Fact/Bridge grain, coverage, signals, repair, and Gold projection | [Dimensional](workflows/dimensional.md), [Mapping](workflows/mapping.md) |
| DD-079–090 | Mapping formats, binding creation, build/extend, package coverage, generator, dependency graph, versioned profile, validation, System identity, waves, and final flow | [Mapping](workflows/mapping.md), [approved DD-109](#dd-109-combined-mapping-persistence-and-profile) |
| DD-103–107 | Verification/Azure gate, Python standard, task map, Release 1 boundary, and external-bootstrap readiness | [Operations](10-operations-and-deployment.md), [testing](11-testing-and-release.md), [rebuild](13-rebuild-guide.md) |
| DD-108–110 | Exact batch, Mapping, and Silver/Gold policy contracts | [Approved decisions](#approved-data-design-decisions) and the workflow pages |

The exact choice, rationale, and affected-task text remains in the immutable
[`FEATURE-001.md`](../../reference_snapshot/docs/features/FEATURE-001.md). Apply
the supersession rules below before rebuilding any historical row.

## Architecture amendments

1. [ADR-0001](../adr/0001-source-loaded-databricks-and-modular-app-service.md)
   replaced the jobs wheel, self-reported package/notebook byte identity,
   profile registry, generated workflow-configuration registry, and phase
   registry with notebook-owned definitions and a versioned source release. It
   also fixed the App Service as one modular monolith and moved every test under
   root `tests/`. It did not remove generated MCP contract registries.
2. [ADR-0002](../adr/0002-principal-separated-mcp-and-workflow-control.md)
   separated human and workload MCP inventories and moved authorize, revoke,
   and safe status into three narrow non-MCP routes.
3. [ADR-0003](../adr/0003-notebook-selected-agent-runtimes.md) allowed each
   modeling notebook to select one of three agent runtimes behind the same
   code-owned safety envelope.
4. [ADR-0004](../adr/0004-governed-dbml-export.md) added deterministic DBML
   export, reversed the earlier DBML deferral, and added a seventh notebook and
   two tools. The count changed from the initial actor-neutral 25, to ADR-0002's
   actor-separated 23, then actor-separated 25 after DBML. Removing the four
   staged Profiling operations in favor of one completion operation produces
   the current 22: 5 human-only, 9 shared, and 8 workload-only. Final promoted
   discovery is 14 human and 17 workload tools.

## Frozen Feature 001 supersession ledger

These older decisions still appear in the immutable Feature 001 history. A
rebuilder must apply the final state, not combine every historical proposal.

| Decision | Final treatment |
|---|---|
| DD-038 | Fully superseded by DD-069 and DD-079, with DD-080–090 supplying final workflow detail. Mapping uses combined rows and a post-commit generator handoff; generated-code execution is deferred beyond Release 1. |
| DD-044, DD-045 | Fully superseded by DD-048. Modeling Evidence is workflow context and its own Section, not persisted downstream support lineage. |
| DD-068 | Fully superseded by DD-069. Mapping keeps two public levels, but no separate materialization or contributor table. |
| DD-070 | Fully superseded by DD-071. Environment-specific variants are deferred; Release 1 Mapping identity is environment-neutral. |
| DD-066 | Partly retained: Dimensional remains a distinct sixth Section sourced through registered Silver Mapping. DD-069 supersedes its separate materialization-table boundary. |
| DD-082 | Partly retained and refined by DD-089: build/extend, full/selected, and one run-wide artifact type remain; source-System filters and exact target/System pairs define coverage. |
| DD-083 | Partly retained and refined by DD-088: Header then Attribute mapping, no per-Attribute agent loop, and bounded deterministic chunks remain. A work package is keyed by target Object and source System. |
| DD-084 | Partly retained and refined by DD-088: one self-contained, name-based document requires zero metadata lookup, excludes IDs and secrets, and is stale-context protected. It now covers one target/source-System package and separates original provenance from executable inputs. |

## How to change a decision

Do not silently reinterpret a frozen field, state, audience, digest, or
boundary. Add an ADR when changing architecture or trust boundaries. Add an
approved design decision when changing persistent meaning or deterministic
policy. Version public contracts when compatibility changes, regenerate all
contract assets, add a rejecting test, and update the traceability matrix.
