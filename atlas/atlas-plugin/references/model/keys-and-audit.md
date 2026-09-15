# Keys and audit columns

Confirmed shared defaults for Logical and Dimensional builds. Explicit user choices or an approved Model policy can override them. Reuse approved choices during incremental work; apply [record protection](../record-state.md), and do not rename existing records to impose a new convention. See [naming](naming.md) and [Model Change Set authoring](change-sets.md).

## Keys

| Field | Default |
|---|---|
| Logical own surrogate | First Attribute, `<Entity>ID`, BIGINT, database-generated, non-null. |
| Dimensional own surrogate | First Attribute, `<Entity>Key`, BIGINT, database-generated, non-null; applies to every newly created modeled table, including facts and bridges. |
| Foreign key | References the appropriate generated key with a compatible type. Its value comes from the required lookup/mapping; it is not another generated identity. Nullability follows the relationship. |
| Natural/business identity | Separate from the surrogate; preserve the complete evidenced identifier or composite tuple. Qualify by System or other context when values are unique only within that context. |

For a Logical own surrogate, use the [Logical Attribute contract](logical.md):

```text
logical_attribute_is_primary_key = true
logical_attribute_is_surrogate_key = true
logical_attribute_is_natural_key = false
logical_attribute_is_nullable = false
logical_attribute_is_audit_column = false
logical_attribute_ordinal_position = 1
```

A Dimensional own surrogate uses `dimensional_attribute_key_role="surrogate"`, a permitted key/technical role, non-nullability and ordinal 1. Use its published dataset schema for the remaining fields; Logical boolean key flags are not Dimensional fields.

- A surrogate does not prove uniqueness of the business grain, deduplicate repeated loads or reconcile customers across Systems. Retain the complete business-key definition and supporting evidence.
- Mark each component of an evidenced Logical natural-key tuple as natural; the tuple is the identifier, not necessarily each component alone. Do not mark the generated surrogate as natural. Logical primary/natural/surrogate flags require non-nullability under the current schema.
- Do not relabel a source business identifier as the target's generated key. Preserve actual physical source names and keys in lineage. If a source identifier collides with the generated name, choose a meaningful distinct modeled name under the naming guide; never silently merge the two meanings.

## Audit policy

After business Attributes and any selected Source audit fields, use this shared block in order. The configured Model template supplies exact types and nullability; do not infer them from names. `SourceSystemID` retains the confirmed BIGINT default unless explicitly overridden.

| Order | Column | Population |
|---:|---|---|
| 1 | `SourceSystemID` | Registered originating System provenance, typically Bronze `source_system_id`; SQL supplies the mapped value. |
| 2 | `IsDataValid` | Framework. |
| 3 | `HashKey` | Framework. |
| 4 | `IsActive` | Framework. |
| 5 | `GDSBatchID` | Framework. |
| 6 | `PipelineRunID` | Framework. |
| 7 | `CreatedDate` | Framework. |
| 8 | `UpdatedDate` | Framework. |
| 9 | `CreatedBy` | Framework. |
| 10 | `UpdatedBy` | Framework. |

The other nine types and all missing nullability settings require the approved template or a user decision before affected definitions are finalized. Do not invent hash semantics, flag values, timestamps or identities. Multiple contributing Systems need a confirmed provenance rule; never choose one arbitrarily.

Mark the approved audit fields as audit columns using the layer's schema; being in the audit block does not make a field a surrogate or primary key. Preserve any evidenced source-namespace component of business identity. If its key/nullability requirements conflict with the configured audit projection, resolve that conflict rather than silently dropping part of the natural-key tuple.

Optional Source audit fields precede that block, only where meaningful source values exist:

- `SourceCreatedDate`, `SourceUpdatedDate`: TIMESTAMP.
- `SourceCreatedBy`, `SourceUpdatedBy`: STRING.

Specify actual source expressions and any confirmed missing-value behavior per System. These describe source events, not framework-generated target events.

## Population boundary and implementation alignment

Keep every intended column in the Model, target DDL and Binding. Load SQL projects business fields, selected Source audit fields and `SourceSystemID` last; omit the target's own generated surrogate, the nine framework-populated audit fields and applicable framework-populated Type 2 history fields. Mapping accounts for their population without fabricated source expressions.

Additional history columns are governed by [Dimension history](../dimensional-build/history.md). The framework populates them using natural keys; retain their definitions and mark them omitted from transformation SQL. Keep them distinct from the audit block. This confirmed rule does not make every technical column framework-generated.

Implemented backend projection:

- New active Logical entities receive an own first BIGINT surrogate; new dimensions, facts and bridges receive their configured own first surrogate. Existing approved table identities are preserved. Multiple own surrogates, source-derived generated identities and business-name collisions are rejected rather than silently relabeled.
- Business Attributes retain relative order after the own surrogate; configured audit fields follow. Dimensional foreign-key projection does not displace the own surrogate.
- SourceSystemID may retain physical lineage. Other configured framework audit fields remain source-less. Logical projection preserves existing provenance primary/natural-key flags rather than deleting a component of business identity.
- Reapplying the same approved candidate yields no redundant attribute edits. These projection rules do not prove business grain or normalization quality; run the shared technical and modeling review.
- The nine framework populations and Type 2 history fields remain the external orchestration consumer contract. Inspect that consumer when its configured behavior is unclear; the local build does not deploy it.

Source: existing GDS `references/model-conventions.md` and `references/orchestration-rules.md`; backend `features/logical/policy.py` and `features/dimensional/policy.py`; shared `domain/modeling_records.py`. Backend policy/executor and disposable integration tests cover this alignment.
