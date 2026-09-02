# Platform lifecycle

Tenant intake establishes Tenant, Systems, Connections, and Source discovery through a Metadata Change Set. Source-to-Bronze ingestion uses registered Objects/Attributes, ingestion Mapping, Copy Group, and Copy. Bronze may be skipped when a Source is available through a foreign catalog.

```text
Tenant Intake and Source/Bronze Metadata
→ Model Input Scope (Model Apply and fresh Model Snapshot)
→ Profiling, Assertions, Analysis, optional Conceptual
→ Logical
→ Silver Target Registration (Metadata Apply)
→ Logical Model Binding (Model Apply)
→ Logical Mapping → Code and/or Validation

Logical Mapping
→ optional Dimensional
→ Gold Target Registration (Metadata Apply)
→ Dimensional Model Binding (Model Apply)
→ Dimensional Mapping → Code and/or Validation
```

Model Input Scope must be applied before Profiling or model development. Metadata registration must succeed before Model Binding. Binding must succeed before Mapping or Code. Process metadata comes later when the user supplies real artifact paths and orchestration details.

Generated SQL is handed to the user. It may be preflighted with governed Databricks SQL, but the plugin never deploys or runs the orchestration pipeline. Runtime triggers, scheduling, and loading remain orchestration ownership.
