# Zone — `reference.zone`

Registered physical data classification. Current Object datasets separate source, raw Bronze, conformed Silver, and presentation Gold metadata.

**Datasets:** `zone`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `zone_code`.
- Also unique: `zone_name`.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `zone_code` | string; minLength=1; maxLength=30; pattern=\S; required | Stable code identifying the Zone. |
| `zone_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Zone. |
| `zone_description` | string; required; null allowed | Plain-language description of the Zone. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [object](../tables/object.md), [process group](../tables/process-group.md).

## How authoring uses these values

Object.zone_code selects its physical dataset; Process Group references zone_code, and Process uses it as part of its Process Group key.

- Read-only reference context for Metadata Change Sets; resolve an existing active Zone.
- Object.zone_code is a fixed enum: source, bronze, silver, gold. Each zone-specific Object dataset also fixes its exact zone value.
- ZoneRecord itself accepts a registered nonblank code; do not confuse the lookup table with Object's closed enum.
- Process Group and Process zone_code fields are registered-reference strings, not the Object contract's four-value literal enum.
- Process has no independent stored Zone; its ID-free zone_code identifies the Process Group. Selected Silver groups finish successfully before Gold starts; dependency and Process orders apply within each phase.
- A Process target Object normally shares its group's Zone, but equality is intentionally unenforced. Do not add a mismatch warning, error or automatic correction.
- Use zone_code for references; zone_name is a display name. Both are unique under the published normalized-key rules.
- Do not infer an Object's zone from its Connection Type.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:111,158,333`.
- `database/01_reference.sql:40,267`.
- `database/seed/01_metadata_snapshot_demo.sql:28`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:374,531`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
