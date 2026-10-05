# Atlas instruction scenarios

Synthetic acceptance cases for the packaged skills. Use isolated fixture workspaces
from `snapshot_fixtures.py` and `test_workspace.py`; no live Tenant, database or SQL
execution. A manual instruction walkthrough checks routing and preserved boundaries.
An authorized independent agent evaluation should receive only the request and fixture
state, then be judged against actual artifacts and permitted tool actions. This file
is a rubric, not a record that such an evaluation passed.

| Request / fixture state | Observable acceptance |
|---|---|
| Explain how Atlas works; no workspace | Investigate/architecture answer. No Tenant questionnaire, Workbench launch, delegation setup or fabricated tool call. |
| Analyze scoped sources and build a logical model; SQL Never | Reuse available metadata/evidence; mark profiles unmeasured; analyze then model only as needed. No profiling/SQL execution or fabricated counts. Coverage and logical checks remain explicit. |
| Build a conceptual model only | Conceptual records/relationships and evidence; no compulsory logical model or Mapping. Unknown conceptual cardinality is allowed. |
| Grill Me about Order grain; current logical draft | Same logical skill/task, focused consequential question, preserved draft. Resolve full identity before dependent keys; no duplicated phase chain. |
| Build one dimension from applied Logical inputs | Dimensional workflow; no invented fact, new profiling dataset, mandatory target registration or logical rebuild. |
| Map selected Objects to an existing applied model | Mapping uses current configured template and complete target/System coverage. No automatic conceptual rebuild or target registration requirement. |
| Generate SQL from nonempty partial applied Mapping | Incomplete Code with explicit issues and justified typed placeholders/zero-row projection; no invented joins or claim of executable business correctness. |
| Author SQL Validation with incomplete Mapping | Block the affected definition authoring on completeness; ordinary structural/model quality verification can still proceed. |
| Validate a logical model; no Mapping | Verify structural and semantic model checks; do not require Mapping or create SQL definitions. Distinguish server-only/unrun checks. |
| Explain why an Entity exists, then update it; no rationale; locked Entity | Explain observed structure and unknown historical intent. Report modification blocked by protection; no replacement identity or fabricated rationale. |
| Update a Customer key with dependent Order lookup and unrelated Product | Inspect real dependencies; scope Customer/Order effects; preserve Product and manual edits. Do not call impact exhaustive if runtime references are missing. |
| Physical description correction selected through cross-owner Model scope | Metadata records under actual owners, exact scope/Zone, preserved nonempty values unless replacement requested; not Model-owned enrichment. |
| Request web-style Model-owned enrichment | Explain unavailable plugin contract; preserve work. No physical Metadata substitution, invented fields or human-HTTP bypass. |
| Register targets and generated files | Separate target/Process prerequisites and owner boundaries. Creation DDL is optional; registration does not execute/upload/deploy. |
| Resume with stale inputs, pending draft and unknown Stage result | Preserve baseline/draft and reconcile actual operation state before another write. No restart, blind retry or task-note approval. |
| Inventory exceeds 200 records | Follow bound pages to completion; preserve canonical keys in projections; refetch full records before upsert. A stale cursor rejects continuation. |

Machine coverage: `test_workspace.py` exercises large selection traversal, projection,
stale draft/baseline/query rejection, compact status and paged history. The same cases
run through native PowerShell in Windows CI; a cross-runtime test exchanges cursors.
Existing lifecycle, validation, Stage, packaging and installation suites remain required.

Assess correctness and unauthorized actions first, then useful completion, coverage,
unnecessary questions and context read volume. Do not grade only the agent's success
claim or required wording. Keep real task data and raw tool traces out of this fixture suite.
