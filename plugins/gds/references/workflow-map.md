# GDS workflow map

Choose the smallest workflow that matches the user's requested stopping point. A skill
may route to another skill, but the stricter read/write and approval rules continue to
apply.

| User intent | Skill | Default stopping point |
|---|---|---|
| Explain GDS concepts or choose a workflow | `$understand-gds` | Explanation and route only. |
| Inspect or govern physical Tenant Metadata | `$manage-gds-metadata` | Requested read or explicit Metadata Change Set boundary. |
| Prepare or run general governed Databricks SQL | `$run-gds-databricks-sql` | SQL/result only; no Change Set. |
| Explain or draft synthetic physical Metadata JSON | `$author-model-metadata` | Schema-checked example only. Despite its legacy name, this skill does not author Model records. |
| Open or edit a local Snapshot/Change Set | `$open-gds-metadata-workbench` | Local saved draft only. |
| Inspect an existing Model, Profile, Analysis, Assertion, Snapshot, DBML, or Model draft | `$manage-gds-model` | Requested read or explicit Model Change Set boundary. |
| Run new physical table profiling and prepare Profile records | `$profile-gds-data` | Aggregate evidence proposal unless local/server work is explicit. |
| Test a physical Attribute relationship and prepare Analysis records | `$analyze-gds-relationships` | Aggregate evidence proposal unless local/server work is explicit. |
| Extract source-located facts from documents/text into Assertions | `$capture-modeling-assertions` | Sourced Assertion proposal unless local/server work is explicit. |
| Design Conceptual records | `$build-conceptual-model` | Proposal unless a higher boundary is explicit. |
| Design Logical records | `$build-logical-model` | Proposal unless a higher boundary is explicit. |
| Design Dimensional records | `$build-dimensional-model` | Proposal unless a higher boundary is explicit. |
| Design Model Mapping records | `$build-data-mapping` | Proposal unless a higher boundary is explicit. |
| Stress-test a modeling brief | `$grill-data-model` | Decision/readiness summary only. |
| Prepare or explicitly start a durable modeling goal | `$run-data-modeling-goal` | Prepared prompt or host-owned goal. |

## Resolve overlapping words

- **Profiling:** use `$manage-gds-model` to read existing `profiling_profile` records;
  use `$profile-gds-data` to execute new aggregate profiling or author new Profile
  records.
- **Analysis:** use `$manage-gds-model` to read existing `analysis_result` records;
  use `$analyze-gds-relationships` for the fixed relationship metrics; use
  `$run-gds-databricks-sql` for other SQL exploration.
- **Assertions:** use `$manage-gds-model` to read existing Assertions and
  `$capture-modeling-assertions` to extract or author sourced facts. Builders consume
  Assertion support but do not fabricate it.
- **SQL:** use `$profile-gds-data` and `$analyze-gds-relationships` only for their fixed
  metrics. Use `$run-gds-databricks-sql` for other governed read/temporary Databricks
  SQL. None allows DML, persistent DDL, credentials, or raw SQL against PostgreSQL.
- **Mapping:** use `$build-data-mapping` for physical-to-Logical/Dimensional Model
  Mapping. Use `$manage-gds-metadata` for Source-to-Bronze/Silver/Gold ingestion
  lineage.
- **Snapshot:** use `$manage-gds-metadata` or `$manage-gds-model` to obtain an
  authoritative server Snapshot. Use `$open-gds-metadata-workbench` only after the
  Snapshot exists locally.
- **Change Set:** identify Metadata versus Model before any write. Local draft, server
  Stage, Validate, and Apply are separate stopping points.
- **JSON:** use `$author-model-metadata` only for physical Metadata schema explanations
  and synthetic examples. Use the matching Model skill for Model records.

Never combine two write workflows into one approval. Tenant Lock acquisition, Stage,
and Apply remain separate governed decisions.
