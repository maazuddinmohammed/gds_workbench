# Existing work and change impact


Before Dimensional Build, Target Registration, Mapping, Code Generation, Validation authoring or Process metadata, always inspect existing outputs and resolve what to create, reuse or update. Each workflow follows this shared rule; it does not assume entry means rebuild everything.

1. Read current Snapshot records, pending changes and relevant local files. Use task decisions, known Change Set results, retained input versions and authoritative freshness information where available. Establish what changed by identity/content and actual dependencies; conversation/history helps locate changes but does not replace current state. A Model revision change or file timestamp alone does not prove every output changed.
2. Identify **new/missing**, **changed/affected**, **unchanged reusable**, and **unresolved/protected** items. Show a compact list of names and reasons, scoped to the current workflow/Model/layer. Trace relevant bindings, source references, target columns, Mapping branches, lookup dependencies and file/System assignments. Distinguish definite effects from possible effects needing review; missing history is unknown, not proof that everything is unchanged.
3. Resolve the selection before authoring. Follow an explicit instruction such as "regenerate Customer and Order" or "update only what changed"; state the resolved items and reuse that answer. Otherwise ask the appropriate question below. Ask once for the related batch, not for each column or file. If a new dependency changes the agreed scope, show it and resolve that addition before changing it.
4. Update only the selected items and necessary agreed dependencies. Reuse valid unchanged work, preserve manual edits and locks, and retain unselected/blocked work explicitly. A selected target may require complete per-System Mapping coverage or rewriting a whole shared Code artifact while preserving its unaffected branches. Explain that consequence; never silently widen to unrelated targets.
5. Save the selection, evidence/basis and affected artifact paths in the existing task's inputs/progress/evidence. No separate handoff ledger or full snapshot-history archive is required. Run the workflow's checks against the complete effective graph; a narrow edit scope does not permit broken references or incomplete target coverage. Selecting work does not approve Stage/Apply or execute SQL.

| Context | Exact question / behavior |
|---|---|
| Known model/data-contract changes or newly added items | "New or affected: [names and short reasons]. Update these items, or select a subset from this list?" Offer **Update affected** and **Choose affected items**. Do not offer a blanket rebuild of unchanged work here. Follow a broader explicit user request if supplied. |
| Existing work, no specific change-driven request | "Existing [workflow outputs] are available. Reuse them, update selected items, or rebuild all in this [Model/layer] scope?" Options: **Reuse existing**, **Selected items**, **All in scope**. Show missing items separately. |
| No applicable outputs yet | "Create [workflow outputs] for all [named requested targets], or selected targets?" Options: **All listed targets**, **Selected targets**. Reuse an already explicit selection. |
| Scope already clear from the conversation | State "I'll update [resolved list] and preserve [unaffected work]." Do not ask the same selection again. |
| Impact cannot be established reliably | Show the known changes and uncertain dependencies; ask the user to identify targets or broaden the review. Do not claim the affected list is exhaustive or regenerate everything automatically. |

"All" means the named workflow/Model/layer scope, never all Tenants or unrelated work. Rebuild means review/regenerate permitted local content; it never means dropping/recreating database tables, deleting history or unlocking records.

| Workflow | Impact to resolve |
|---|---|
| Dimensional Build | Selected analytical processes and affected facts, dimensions, bridges, Attributes/relationships. Trace effects of shared dimensions across processes; preserve unrelated designs and agreed grain/history decisions. |
| Target Registration | New/changed target definitions and their Object/Attribute records. DDL remains optional with its own selected table scope; regenerate only requested complete table definitions. |
| Mapping | Affected target/System branches, Attribute rules, grain/key/lookup effects and dependencies. Inspect complete target coverage while preserving unchanged rules. |
| Code Generation | Artifacts that implement affected Mapping or target contracts, plus source-System assignments. A combined file can be affected by one branch; unrelated files remain reusable. |
| Validation authoring | Checks/groups whose tested fields, Mapping behavior, output contract or code changed, plus missing required coverage. Regenerating definitions is separate from executing checks. |
| Process metadata | Missing/affected artifact-to-Process assignments, runtime locations, Group/Copy Group links and invocation dependencies. Code text changes alone do not require new registration; existing natural-key changes remain manual database work. |

Example: adding Customer.Email can affect Customer registration, relevant Mapping branches, Customer code and checks for that field. It does not automatically require regenerating unrelated Order transformations. A changed Customer key or lookup contract may affect Order too; follow actual dependencies rather than names alone. Do not run later workflows automatically merely because their outputs may be affected.
