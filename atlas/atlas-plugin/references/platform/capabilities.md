# Capability boundaries

This is a source contract guide, not proof of what a particular deployment exposes. Inspect available tool schemas and local command contracts; unavailable capabilities remain explicit prerequisites. Never replace a missing governed operation with direct SQL, a human-only HTTP endpoint, or an invented tool.

| Work | Supported route / boundary |
|---|---|
| Tenant, Model and scope discovery | Authorized listings and `get_model_input_scope`. No foundational CRUD or Model Input Scope mutation through plugin authoring. |
| Physical Metadata | Snapshot/read capabilities plus governed Metadata Change Sets for supported datasets. Physical description correction changes Metadata, not Model-owned enrichment. |
| Model evidence and design | Snapshots, supported `read_model_section` datasets, and governed Model Change Sets. Profiling is backend-run; do not stage Profile records. |
| Model-owned enrichment | The web workflow stores Model-specific descriptions/types/key/nullability/PII findings. Current plugin Model snapshot/read/Change Set contracts do not expose this workflow. Report the gap; do not substitute physical Metadata changes or invent enrichment fields. User-supplied findings can inform reasoning with their provenance; they are not proof of saved enrichment. |
| Mapping consumer context | `read_mapping_context`; obtain all five components under one revision/context binding and follow required pages. |
| Code and Validation definitions | Read relevant Model Snapshot datasets; `read_model_section` does not currently serve these datasets. |
| New transformation language | SQL generation is supported; preserve existing Python records. New Python generation needs an established consumer contract. |
| Data execution | Backend profiling tools or the governed `execute_databricks_sql` route under user authorization and SQL policy. Its SQL restrictions do not themselves enforce Model Input Scope or metadata masking. Use [query-scope checks](../query-scope.md); unresolved scope/protection blocks the affected query. |
| Submission | Host Stage Runner/connector, server validation and separately approved Apply. Unknown Stage outcomes require read-only reconciliation before another write. |
| Operational handoff | Target/Process registration and local creation DDL. No upload, persistent DDL execution, deployment or pipeline execution is implied. |

Authoritative Model-owned enrichment access and stronger server-enforced analysis scope/masking require backend work; instruction changes cannot supply them. Local dependency review is advisory and may be incomplete. No automated helper proves business meaning or recovers undocumented decisions.

See [release scope](../release-scope.md) for host packaging and supported execution surfaces; [tool selection](../tools/reads.md) for focused retrieval.
