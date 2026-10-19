# System type — `reference.system_type`

Operator-registered classification of a System, with a code, name, and explanatory description.

**Datasets:** `system_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `system_type_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset system_type` for every field: it states each one's type, limits, required and null rules, description and population guidance.

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [system](system.md).

## How authoring uses these values

System.system_type_code selects the type. Workflows resolve its description to understand source business and technical context; editable operational records use it indirectly through their Systems.

- Read-only reference context for Metadata Change Sets; use an existing active registered code.
- Allowed codes come from the current reference records, not a fixed enum.
- DEMO_DATABASE is a test-only seed example.
- Do not infer extraction syntax or all runtime capabilities from the type label alone.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

[All metadata tables](../index.md) · [Common validation](../validation.md)
