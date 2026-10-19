# Lane — `core.lane`

Registered organizational grouping to which Tenants belong.

**Datasets:** `lane`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `lane_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset lane` for every field: it states each one's type, limits, required and null rules, description and population guidance.

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [tenant](tenant.md).

## How authoring uses these values

Resolve tenant.lane_code to understand the selected Tenant's lane. Editable operational metadata does not directly reference lane_code.

- Foundational, operator-managed context; not editable through Metadata Change Sets.
- Use an existing lane_code; codes are registered values, not a closed enum.
- DEMO_LANE is a test-only seed example, not an available production option.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

[All metadata tables](../index.md) · [Common validation](../validation.md)
