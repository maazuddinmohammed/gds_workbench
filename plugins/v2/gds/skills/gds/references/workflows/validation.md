# Validation Authoring

Call this workflow Validation, never QA. Author `validation_group` and `validation_check` Model records for selected source Systems/targets. Enter only when Validation Authoring is selected or explicitly included in the journey; ordinary Mapping/Code review creates no Validation records. Show available Silver/Gold layers, Systems, and targets; ask what to cover. Both layers may be selected explicitly, with distinct identifiable groups. Resolve transformation-output versus loaded-data checks, or both.

Before authoring, present Systems/targets and a broad validation coverage plan; wait for user confirmation. Propose applicable categories:

- **Technical** — execution, columns/types, nullability, keys, uniqueness, references.
- **Reconciliation** — counts, control totals, Mapping coverage, transformation consistency.
- **Functional/business** — confirmed Assertions, domain rules, expected outcomes.

Reuse existing valid checks. Split groups by useful purpose: key uniqueness, mapping compatibility, references, or supported business features. Layer/feature/purpose belong in clear names and descriptions; use the existing Group/Check schema and System association. Do not put all technical checks in one generic group, create a group per trivial check, or multiply redundant assertions. Derive functional features from Mapping and confirmed rules without inventing thresholds.

Give representative examples, not every final query. Identify exclusions/evidence gaps. One confirmation covers the boundary; material coverage change requires confirmation again. Existing explicit acknowledgement satisfies this gate in every interaction mode.

Use applied Mapping and current relevant Code when present. Read frozen Snapshots with bounded local `select`; `read_model_section` reads live applied records, requiring revision reassessment. Generated Code/Validation are Snapshot-only. Resolve contradictory Mapping before deriving checks. Each Check stores SQL/assertion contracts, never execution results.

Interpret Object `source_objects` as input Objects/aliases and `steps` as ordered natural-language preparation, joins, predicates, filters and grain changes. Attribute transformations contain field rules. Current Code should implement successive temporary-view stages followed by the target-column SELECT. Trace stages against Mapping; repeated whole-pipeline SQL proves nothing.

Each Check tests one clear assertion using only necessary preparation stages. Do not copy the complete generation pipeline into every Check. Query A and Query B are independent SQL batches: each declares its temporary views before use. Never rely on Code Generation, another Check or Query A to prepare Query B. Check loaded data against actual target relations.

Derive expected results independently from Mapping and confirmed rules, not by copying generated SQL. Cover failed conversions, join multiplication, lost keys and precision loss when applicable. Match scope/batch/filter boundaries; specify empty-input and null behavior. Never assume empty input passes or syntax proves business correctness.

Follow the dataset schema. Except `executes_successfully`, comparisons return exactly one row/column with declared type; other cardinality is a query-contract error. For framework execution qualify persistent relations as schema.table, following `../orchestration-rules.md`; direct preflight resolves its required catalog separately. Only temporary relations declared earlier in the same batch may be unqualified.

Statically trace each check's expected value, scope and failure condition. Reject constant passing checks and unsupported assertions. Optional governed `execute_databricks_sql` preflight is external: obey saved SQL policy/current authorization and resolve specific uncertainties without unchanged repeated checks. No-result output proves neither failure nor assertion success. Apply complete Groups/Checks through a Model Change Set and stop.
