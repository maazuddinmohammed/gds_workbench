# GDS overview

GDS ETL Workbench lets developers inspect governed metadata, prepare complete
metadata or Model changes, validate them, and apply them through controlled
workflows.

## Governance

- A Tenant owns metadata, Models, and authorization scope.
- A Principal is the authenticated human or workload identity.
- Tenant Visibility controls reading. Tenant Role controls capabilities.
- A Tenant Lock is a time-bound lease owned by one exact Principal. Ordinary
  metadata and Model writes require the appropriate role and an owned lock.
- The server derives identity, Tenant access, role, and authorization policy.

## Metadata

Metadata describes Projects, Tenants, Systems, Connections, physical Objects
and Attributes, ingestion mappings, Copy configuration, and Process
configuration across Source, Bronze, Silver, and Gold Zones.

A Metadata Snapshot is an immutable, ID-free Tenant metadata archive for
selective local inspection. A Metadata Change Set contains complete pending
operational dataset records. Validation checks the proposed future metadata;
Apply resolves natural keys and commits the valid change atomically.

Use `manage-gds-metadata` for metadata discovery, snapshots, Tenant Locks, or
Metadata Change Sets.

## Models

A Model is a governed aggregate containing scope, policy, effective Sections,
and one current revision. Model Scope identifies the physical Objects and
Attributes the Model may use. Modeling Assertions persist structured support
derived from documents, messages, meetings, or direct input.

A Model Change Set replaces complete Sections such as Scope, Profiling,
Assertion, Analysis, Conceptual, Logical, Dimensional, or Mapping. It is not a
Metadata Change Set. Model changes validate one future graph and apply
atomically.

Use `manage-gds-model` for generic Model reads, Scope/evidence, and Model Change
Set lifecycle work. Use a layer builder only when designing that layer.

## Workflow boundary

Reads need Tenant visibility but no Tenant Lock. Ordinary writes require the
correct Tenant Role and the current Principal's active Tenant Lock. Snapshot
archives provide bounded context; Change Sets provide revision-fenced drafts;
Apply is the governed mutation boundary.
