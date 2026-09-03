# Logical Build

Require fresh Metadata and Model Snapshots and an applied Model Input Scope. Read `model-input-scope.md`, `profiling.md`, `analysis.md`, and `conceptual.md`. Read `assertions.md` when Assertions exist or the user supplies business rules. Use bounded `read_model_section` and `inspect_metadata` calls for focused context.

Logical Build is one target. Run these phases in order without separate user review:

1. **Profile** every scoped Source/Bronze Object and Attribute. Use existing Profile evidence first. Under the SQL policy, collect missing bounded evidence about counts, nulls, distinctness, value patterns, grain, and candidate keys.
2. **Analyze relationships**. For every Object, examine business process, row grain, identifiers, functional dependencies, repeating groups, header/detail structure, history, and signaled within- or cross-System relationships. Support, reject, or retain findings explicitly.
3. **Build Conceptual**. Identify processes and reusable business concepts across all inputs. Consolidate matching meaning across Systems. Conceptual is required and must remain distinct from Logical.
4. **Build Logical**. Produce a normalized operational model from business meaning and source reality. Use Kimball's process, grain, event, measurement, and descriptive-context questions for discovery; do not turn this layer into a star schema.

For each candidate Logical Entity, state its business grain, candidate key, lifecycle, source support, and the determinant for every Attribute. Then make these decisions:

- Combine sources only when they represent the same business concept at the same grain. Similar names or columns are insufficient; cross-System identity needs evidence or a confirmed rule.
- Split different grains, header/detail records, repeating or multi-valued groups, independently changing reference data, history, snapshots, events, and many-to-many associations when their semantics require it.
- Apply 1NF by removing repeating groups; 2NF by moving Attributes dependent on only part of a composite key; and 3NF by moving non-key Attributes that depend on another non-key determinant.
- Keep an Attribute with its Entity when it depends on that Entity's whole key and has no independent identity or lifecycle. Do not create small reference Entities merely because values repeat.
- Place transactions, events, associations, history, and current master state in separate Entities when their grains differ. Never mix facts from different grains in one Entity.
- Choose natural keys only when uniqueness, stability, and business meaning are supported. Add a surrogate identifier only when the target contract needs one; never fabricate key semantics.
- Derive relationship direction, cardinality, and optionality from evidence. If a structural uncertainty changes the model, query it, ask the user, or block it rather than copying the source shape.

Before authoring, run a source-projection challenge. If each source Object still maps to one similarly shaped Entity, recheck mixed grains, functional dependencies, repeating groups, code/description domains, header/detail patterns, history, and cross-System consolidation. A one-to-one result is acceptable only when this examination supports it; record that basis.

Apply the session SQL policy throughout:

- `never`: execute no SQL. Use Metadata, Profiles, Analysis, Assertions, constraints, descriptions, and user evidence. Treat unsupported conclusions as inference; ask or block material ambiguity instead of defaulting to one-to-one.
- `essential`: query only a specific evidence gap blocking a responsible structural decision.
- `as_needed`: run bounded queries for each material, testable grain, identity, dependency, relationship, or normalization hypothesis. Do not finalize a metadata-only result when a query can resolve it.

Prefer deterministic key, functional-dependency, cardinality, orphan, and overlap checks. Read a small sample only when values or record shape clarify semantics; never persist raw query output. Use governed `execute_databricks_sql` with default environment `dev`. Source and Bronze coordinates follow `profiling.md`.

Default Entity and Attribute names use PascalCase. Identifier Attributes end in `ID` with both letters capitalized, such as `CustomerID`. User instructions or Model naming policy override the default. Keep every intended physical, audit, technical, and constant-valued target Attribute. Preserve source support and rationale; never fabricate keys, lineage, types, or measured evidence.

Across every phase, mark each input represented, context-only, excluded with reason, or blocked. Supported records are `active`; unresolved structural facts block Apply rather than persisting `needs_review`.
