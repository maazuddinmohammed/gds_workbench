# Workflow targets

Choose one target and Full/Selected scope per task:

1. **Tenant Intake** — Tenant, System, Connection, and required foundational Metadata.
2. **Metadata Authoring** — Source, Bronze, ingestion, and Copy metadata.
3. **Model Input Scope Authoring** — select active Source and/or Bronze inputs for one Model.
4. **Logical Build** — requested Profiling, Assertions, Analysis, optional Conceptual, and Logical work.
5. **Silver Target Registration** — applied Logical to DDL and Silver Metadata.
6. **Logical Model Binding** — bind Logical records to registered Silver metadata.
7. **Logical Mapping** — bound Silver targets by source System.
8. **Logical Code Generation** — SQL or requested artifact from applied Mapping.
9. **Dimensional Build** — optional model from applied Logical Mapping.
10. **Gold Target Registration** — Dimensional to DDL and Gold Metadata.
11. **Dimensional Model Binding** — bind Dimensional records to registered Gold metadata.
12. **Dimensional Mapping** — bound Gold targets by source System.
13. **Dimensional Code Generation** — artifact from applied Mapping.
14. **Validation Authoring** — Logical or Dimensional Validation Groups and Checks from Mapping and optional Code.
15. **Process Registration** — later Metadata from user-supplied artifact paths.

Profiling, Assertions, Analysis, and Conceptual may be bounded tasks or phases. Grill With Docs is an interaction mode, never a target.

Load only the active guide:

- Tenant Intake/Metadata: `workflows/metadata-authoring.md`
- Model Input Scope: `workflows/model-input-scope.md`
- Profiling/Assertions/Analysis/Conceptual: their named guide
- Logical/Dimensional: `workflows/logical-build.md`, `workflows/dimensional-build.md`
- Registration/Binding: `workflows/target-registration.md`, `workflows/model-binding.md`
- Mapping/Code/Validation/Process: their named guide
