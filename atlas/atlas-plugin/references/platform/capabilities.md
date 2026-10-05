# Capability boundaries

This is a source contract guide, not proof of what a particular deployment exposes. Inspect available tool schemas and local command contracts; unavailable capabilities remain explicit prerequisites. Never replace a missing governed operation with direct SQL, a human-only HTTP endpoint, or an invented tool.

| Work | Supported route / boundary |
|---|---|
| Tenant, Model and scope discovery | Authorized listings and `get_model_input_scope`. No foundational CRUD or Model Input Scope mutation through plugin authoring. |
| Physical Metadata | Snapshot/read capabilities plus governed Metadata Change Sets for supported datasets. Physical description correction changes Metadata, not Model-owned enrichment. |
| Model evidence and design | Snapshots, supported `read_model_section` datasets, and governed Model Change Sets. Profiling is backend-run; do not stage Profile records. |
| Model-owned enrichment | Model Snapshots, `read_model_section` and local `object_enrichment` / `attribute_enrichment` proposals use governed Model Change Sets. See [enrichment](../model/enrichment.md). Preserve Model ownership and locks; do not substitute physical Metadata changes. |
| Mapping consumer context | `read_mapping_context`; obtain all five components under one revision/context binding and follow required pages. |
| Code and Validation definitions | Read relevant Model Snapshot datasets; `read_model_section` does not currently serve these datasets. |
| New transformation language | SQL generation is supported; preserve existing Python records. New Python generation needs an established consumer contract. |
| Data execution | Backend profiling tools or the governed `execute_databricks_sql` route under user authorization and SQL policy. Its SQL restrictions do not themselves enforce Model Input Scope or metadata masking. Use [query-scope checks](../query-scope.md); unresolved scope/protection blocks the affected query. |
| Submission | Host Stage Runner/connector, server validation and separately approved Apply. Unknown Stage outcomes require read-only reconciliation before another write. |
| Operational handoff | Target/Process registration and local creation DDL. No upload, persistent DDL execution, deployment or pipeline execution is implied. |

Use compatible deployed backend contracts for Model-owned enrichment. Stronger server-enforced analysis scope/masking remains separate backend work; instruction changes cannot supply it. Local dependency review is advisory and may be incomplete. No automated helper proves business meaning or recovers undocumented decisions.

See [release scope](../release-scope.md) for host packaging and supported execution surfaces; [tool selection](../tools/reads.md) for focused retrieval.
