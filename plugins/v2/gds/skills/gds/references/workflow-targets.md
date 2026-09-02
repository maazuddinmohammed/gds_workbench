# Workflow targets

Choose one target and Full/Selected scope per task:

1. **Metadata Authoring** — Source, Bronze, ingestion, and Copy metadata.
2. **Model Input Scope Authoring** — select active Source and/or Bronze inputs for one Model.
3. **Logical Build** — Profiling, relationship Analysis, Conceptual, and Logical work.
4. **Silver Target Registration** — applied Logical to DDL and Silver Metadata.
5. **Logical Model Binding** — bind Logical records to registered Silver metadata.
6. **Logical Mapping** — bound Silver targets by source System.
7. **Logical Code Generation** — SQL or requested artifact from applied Mapping.
8. **Dimensional Build** — optional model from applied Logical Mapping.
9. **Gold Target Registration** — Dimensional to DDL and Gold Metadata.
10. **Dimensional Model Binding** — bind Dimensional records to registered Gold metadata.
11. **Dimensional Mapping** — bound Gold targets by source System.
12. **Dimensional Code Generation** — artifact from applied Mapping.
13. **Validation Authoring** — Logical or Dimensional Validation Groups and Checks from Mapping and optional Code.
14. **Process Registration** — later Metadata from user-supplied artifact paths.

Profiling, relationship Analysis, and Conceptual are required phases inside Logical Build, not separate targets. Assertions are supporting records authored only from user-confirmed business evidence. Grill With Docs is an interaction mode, never a target.

Load only the active guide:

- Metadata: `workflows/metadata-authoring.md`
- Model Input Scope: `workflows/model-input-scope.md`
- Profiling/Assertions/Analysis/Conceptual: their named guide
- Logical/Dimensional: `workflows/logical-build.md`, `workflows/dimensional-build.md`
- Registration/Binding: `workflows/target-registration.md`, `workflows/model-binding.md`
- Mapping/Code/Validation/Process: their named guide
