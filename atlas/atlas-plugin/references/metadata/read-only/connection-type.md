# Connection type — `reference.connection_type`

Operator-registered classification of a Connection's technology or connection mechanism.

**Datasets:** `connection_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `connection_type_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset connection_type` for every field: it states each one's type, limits, required and null rules, description and population guidance.

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [connection](connection.md).

## How authoring uses these values

Connection.connection_type_code selects the type. Workflows resolve its description through the Connection associated with the selected Object or source context.

- Read-only reference context for Metadata Change Sets; use an existing active registered code.
- Allowed codes come from current reference records, not a fixed enum.
- DEMO_POSTGRESQL is a test-only seed example.
- A type label alone does not establish foreign-catalog availability, credentials, or supported execution behavior.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

[All metadata tables](../index.md) · [Common validation](../validation.md)
