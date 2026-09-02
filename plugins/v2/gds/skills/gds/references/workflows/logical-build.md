# Logical Build

Require fresh Metadata and Model Snapshots and an applied Model Input Scope. Read `model-input-scope.md`; use bounded `read_model_section` and `inspect_metadata` calls for focused context.

Default Entity and Attribute names use PascalCase. Identifier Attributes end in `ID` with both letters capitalized, such as `CustomerID`. User instructions or Model naming policy override the default.

For every selected Source/Bronze input:

1. Establish purpose and grain from physical/Profile/Analysis/Assertion evidence.
2. Split mixed grains and consolidate only proven same-grain structures.
3. Build normalized operational Entities, Attributes, keys, and relationships.
4. Keep every physical, audit, technical, and constant-valued target Attribute in the Logical Model. The physical model is expected to closely realize it.
5. Preserve source support and rationale. Never fabricate keys, lineage, or types.
6. Mark the input represented, context-only, excluded with reason, or blocked.

Conceptual may improve names and business boundaries but cannot determine structure. Supported records are `active`; unresolved structural facts block Apply rather than persisting `needs_review`.
