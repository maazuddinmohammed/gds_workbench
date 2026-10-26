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
| Analyze scoped sources and build a logical model; SQL Never | Reuse available metadata/evidence; mark profiles unmeasured; analyze then model only as needed. No profiling/SQL execution or fabricated counts. Runs `validate` and `coverage`; logical checks remain explicit. Adds the Project framework audit columns through the policy, states grain from saved evidence, and never renames existing names without asking. |
| Group the Input Scope into Subject Areas only | Areas named by business capability with complete Object memberships; an Object may sit in several areas. Every Bronze Object is in an active area or reported unassigned. No Logical or downstream work. |
| Build one Subject Area's Logical model | Works one area at a time: reads the area's Objects, the Entities already built from them and their neighbours; reuses those Entities, writes only changes and retires instead of deleting. Relationships point child -> parent. Runs `coverage --subject-area`. The area only chooses Objects and is never evidence; no Subject Area, Dimensional or Mapping changes. |
| Build Logical or Dimensional while Subject Areas exist | Subject Areas only choose Objects; never read them as evidence. Logical uses physical/source evidence and business Context; Dimensional retains applied Logical prerequisites. Optimizing an existing model needs no area. |
| Grill Me about Order grain; current logical draft | Same logical skill/task, focused consequential question, preserved draft. Resolve full identity before dependent keys; no duplicated phase chain. |
| Build one dimension from applied Logical inputs | Dimensional workflow; no invented fact, new profiling dataset, mandatory target registration or logical rebuild. When the Project leaves history unset, asking Type 1 or Type 2 before drafting is also acceptable. |
| Map selected Objects to an existing applied project | Mapping uses current configured template and complete target/System coverage. No Subject Area regrouping, automatic rebuild or target registration requirement. |
| Generate SQL from nonempty partial applied Mapping | Incomplete Code with explicit issues and justified typed placeholders/zero-row projection; no invented joins or claim of executable business correctness. |
| Author SQL Validation with incomplete Mapping | Block the affected definition authoring on completeness; ordinary structural/project quality verification can still proceed. |
| Validate a logical model; no Mapping | Verify structural and semantic project checks; do not require Mapping or create SQL definitions. Distinguish server-only/unrun checks. |
| Explain why an Entity exists, then update it; no rationale; locked Entity | Explain observed structure and unknown historical intent. Report modification blocked by protection; no replacement identity or fabricated rationale. |
| Update a Customer key with dependent Order lookup and unrelated Product | Inspect real dependencies; scope Customer/Order effects; preserve Product and manual edits. Do not call impact exhaustive if runtime references are missing. |
| Physical description correction selected through cross-owner Project scope | Metadata records under actual owners, exact scope/Zone, preserved nonempty values unless replacement requested; not Project-owned enrichment. |
| Request Project-owned enrichment | Author `object_enrichment`/`attribute_enrichment` proposals in the Project Change Set from scoped profiles and evidence; preserve locks and `expected_revision`. No physical Metadata substitution, invented fields or human-HTTP bypass. |
| Register targets and generated files | Separate target/Process prerequisites and owner boundaries. Creation DDL is optional; registration does not execute/upload/deploy. |
| Change request that needs data no source has (customer country) | Trace the impact across metadata, models, Mapping, Code and Validation; ask where the data comes from before changing anything; recommend the smallest path (country on Dim Customer, Fact Order unchanged). |
| User pastes a runtime error for a local SQL file that drifted from the applied code | Fix the reported table and the latent wrong column against the registered metadata and Mapping; change only that file; don't run SQL; ask the user to rerun. |
| Register a Source table from a spec with one unconfirmed column type | Draft the Object and confirmed Attributes on the stated System and Connection with actual types, keys and descriptions; ask about the unconfirmed type instead of inventing it; no Bronze, ingestion or Project records. |
| Resume with stale inputs, pending draft and unknown Stage result | Run `status` or `next`; preserve baseline/draft and reconcile actual operation state before another write. No restart, blind retry or task-note approval. |
| Inventory exceeds 200 records | Follow bound pages to completion; preserve canonical keys in projections; refetch full records before upsert. A stale cursor rejects continuation. |

Machine coverage: `test_workspace.py` exercises large selection traversal, projection,
stale draft/baseline/query rejection, compact status and paged history. The same cases
run through native PowerShell in Windows CI; a cross-runtime test exchanges cursors.
Existing lifecycle, validation, Stage, packaging and installation suites remain required.

Assess correctness and unauthorized actions first, then useful completion, coverage,
unnecessary questions and context read volume. Do not grade only the agent's success
claim or required wording. Keep real task data and raw tool traces out of this fixture suite.
