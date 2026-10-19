# Object type — `reference.object_type`

Operator-registered classification of the kind of physical Object.

**Datasets:** `object_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `object_type_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset object_type` for every field: it states each one's type, limits, required and null rules, description and population guidance.

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [object](../tables/object.md).

## How authoring uses these values

Each Source/Bronze/Silver/Gold Object supplies object_type_code referencing this table. Use its description when interpreting the Object.

- Read-only reference context for Metadata Change Sets; use an existing active registered code.
- The Object contract requires a code reference, not an Object Type name or database ID.
- TABLE is seeded as a test example meaning a relational table; it is not the complete allowed type list.
- Additional types and their runtime implications must be resolved from actual registered descriptions and consumer requirements.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

[All metadata tables](../index.md) · [Common validation](../validation.md)
