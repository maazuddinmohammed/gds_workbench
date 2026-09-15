# System — `core.system`

Registered named system providing business and technical context; classified by a System Type.

**Datasets:** `system`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `system_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. |
| `system_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the System. |
| `system_description` | string; required; null allowed | Plain-language description of the System. |
| `system_type_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System Type. Reference: [system type](system-type.md). |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- `system_type_code` → [system type](system-type.md): `system_type_code`. Required reference.
- Referenced by: [connection](connection.md), [object](../tables/object.md), [copy group](../tables/copy-group.md), [member group](../tables/member-group.md), [process group](../tables/process-group.md).

## How authoring uses these values

Resolve system_code for Object placement and Copy/Process group ownership keys. Connections associate a System with a Tenant. Source workflows use the System's description and type as context.

- Foundational, operator-managed context; not editable through Metadata Change Sets.
- system_code is a registered global natural key; the System record itself has no tenant_code.
- system_type_code must resolve to an existing System Type.
- Use the System selected through actual Connection placement or source context; do not infer it from a name.
- Systems determine group selection. The agreed dependency order belongs to [Process Group](../tables/process-group.md#dependency-order); no System execution-order field is needed for this design.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:69`.
- `database/02_core.sql:43`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:265,393,465`.
- `docs/workflow-evidence-design.md:1816`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
