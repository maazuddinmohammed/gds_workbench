# Product intent and scope

## Mission

GDS ETL Workbench helps developers and architects turn governed source
metadata into an applied data Model. It combines deterministic validation,
bounded AI-assisted modeling, Spark-based physical checks, and one controlled
metadata write path.

The product is a modeling control plane. It does not deploy or execute the data
pipelines that its Mapping output describes.

## Problem being solved

Data modeling crosses several layers: physical source metadata, evidence,
analysis, conceptual design, logical Silver design, dimensional Gold design,
and source-to-target Mapping. If each layer is edited independently, references
can drift, partial changes can become visible, and automated work can exceed
the authority granted by a human.

Release 1 solves this by:

- keeping applied state in PostgreSQL;
- preparing changes as whole-Section Model Change Sets;
- validating the complete future graph before any effective write;
- applying one sealed candidate atomically;
- binding automated work to a short-lived Workflow Grant; and
- separating physical reads, AI reasoning, metadata writes, and file export.

## People and systems

| Actor | Purpose | Allowed entry point |
|---|---|---|
| Developer | Inspect open source metadata and owned applied Models | Human MCP surface |
| Architect | Developer access plus profiling, Model mutation, and workflow authorization | Human MCP and Workflow Control |
| Tenant admin | All Tenant capabilities, including security administration | Human MCP and Workflow Control |
| Databricks workload | Execute one exact human-authorized workflow | Workload MCP surface |
| External metadata owner | Bootstrap foundational metadata, Model Scope, targets, identities, and Mapping headers | Outside Release 1 public APIs |
| Platform operator | Install PostgreSQL, publish artifacts, configure identity, and run guarded release gates | Deployment runbooks |

## Main product journey

1. An active human inspects Tenants, Bronze Objects, Attributes, ingestion
   lineage, owned Models, and Modeling Evidence.
2. The human checks readiness for the intended workflow.
3. An authorized Architect/Tenant Admin either edits through the shared Model Change Set tools or
   authorizes one Databricks Workflow Run through Workflow Control.
4. A predefined Databricks task receives only the Workflow Run and Workflow
   Grant identifiers.
5. The workload activates the grant, loads the server-frozen request, and
   obtains a verified Model Snapshot or DBML archive.
6. The workflow performs bounded Spark work, bounded agent work, or a
   deterministic export.
7. A modeling result becomes one complete Candidate Section. The App Service
   validates and applies it, or records an exact no-op. Profiling and DBML use
   their own finalization paths.
8. PostgreSQL stores the authoritative receipt and terminal run state. A human
   reads only the bounded safe status.

The intended cross-layer sequence is:

1. Profiling
2. Analysis
3. Conceptual
4. Logical
5. External Silver Object, Attribute, and Mapping-header registration
6. Logical-to-Silver Mapping
7. Dimensional
8. External Gold Object, Attribute, and Mapping-header registration
9. Dimensional-to-Gold Mapping
10. Optional Conceptual or Logical DBML export

The two registration pauses are deliberate. The workbench never invents or
deploys physical Silver or Gold tables.

## Included in Release 1

- A fresh-install PostgreSQL schema with relational integrity, audit state,
  locks, revision control, roles, and grants.
- Human catalog and Model reads through MCP.
- Actor-separated MCP discovery and dispatch.
- Model readiness, immutable Model Snapshots, and governed DBML resources.
- Eight-document Model Change Sets: Model Scope, Profiling, Evidence, Analysis,
  Conceptual, Logical, Dimensional, and Mapping.
- Tenant Metadata Change Sets for physical Objects/Attributes and Copy/Process
  configuration.
- Short-lived Workflow Grants and safe Workflow Run status.
- Profiling, Analysis, Conceptual, Logical, Dimensional, Mapping, and DBML
  Databricks workflows.
- Deterministic local verification and immutable App Service and Databricks
  release artifacts.

## Explicit non-goals

- A React or general management UI.
- General REST management or foundational CRUD.
- Public Model Scope or business-lock mutation.
- Public Tenant Lease operations.
- Arbitrary SQL, file upload, code execution, or delete tools.
- Physical Silver or Gold DDL creation, deployment, registration, scheduling,
  or execution.
- Hard deletes, destructive cleanup, in-place schema migrations, or backfills.
- Passing raw physical rows, secrets, prompts, or raw provider/agent tool output
  through MCP or ordinary telemetry.

## Product success

Release 1 succeeds when an authorized actor can produce a complete,
traceable, replay-safe Model result without exposing secrets, bypassing locks,
writing a partial graph, or confusing local verification with a real cloud
release.

Primary sources: [`README.md`](../../README.md),
[`IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md), and
[`docs/architecture/overview.md`](../architecture/overview.md).
