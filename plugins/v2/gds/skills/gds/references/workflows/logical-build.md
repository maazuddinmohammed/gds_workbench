# Logical Build

Require fresh Metadata and Model Snapshots and an applied Model Input Scope. Read `model-input-scope.md`, `profiling.md`, `analysis.md`, and `conceptual.md`. Read `assertions.md` when Assertions exist or the user supplies business rules. Use bounded `read_model_section` and `inspect_metadata` calls for focused context.

Logical Build is one target. Run these phases in order without separate user review between them:

1. **Profile** every scoped Source/Bronze Object and Attribute. Use existing Profile evidence first. Under the SQL policy, collect missing bounded evidence about counts, nulls, distinctness, value patterns, grain, and candidate keys.
2. **Analyze relationships**. Enumerate plausible relationships within the complete scope, including cross-System candidates. Support, reject, or retain each candidate as an explicit inference using metadata, Profiles, Assertions, and permitted key/cardinality/orphan checks.
3. **Build Conceptual**. Consider each input Object, identify the business concept or concepts it represents, and then consolidate matching concepts across Objects and Systems. Define the important business relationships. Conceptual is required before Logical.
4. **Build Logical**. Produce a normalized operational model from the combined evidence. Split mixed grains and repeating groups; consolidate only proven same-grain structures. Normalize when it improves operational integrity, not merely to create more Entities.

Apply the session SQL policy throughout:

- `never`: execute no SQL. Work from Metadata, Snapshots, existing Profiles/Analysis/Assertions, and user evidence. Keep unmeasured conclusions identifiable as inference.
- `essential`: query only when a specific unresolved evidence gap would otherwise block a responsible Logical result.
- `as_needed`: run bounded queries whenever they materially improve Profiling, relationship confidence, grain, or normalization decisions.

Prefer aggregates and deterministic key/relationship checks. Read a small representative sample only when values or record shape materially clarify the model; never persist raw query output. Use governed `execute_databricks_sql` with default environment `dev`. Source and Bronze coordinates must follow `profiling.md`.

Default Entity and Attribute names use PascalCase. Identifier Attributes end in `ID` with both letters capitalized, such as `CustomerID`. User instructions or Model naming policy override the default. Keep every intended physical, audit, technical, and constant-valued target Attribute. Preserve source support and rationale; never fabricate keys, lineage, types, or measured evidence.

Across every phase, mark each scoped input represented, context-only, excluded with reason, or blocked. Supported records are `active`; unresolved structural facts block Apply rather than persisting `needs_review`.
