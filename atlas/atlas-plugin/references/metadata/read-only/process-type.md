# Process type — `reference.process_type`

Operator-registered type of the file containing Process logic. The confirmed framework uses SQL and Python.

**Datasets:** `process_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `process_type_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `process_type_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Process Type. |
| `process_type_description` | string; required; null allowed | Plain-language description of the Process Type. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [process](../tables/process.md).

## How authoring uses these values

Process.process_type_name references process_type.process_type_name. The confirmed meanings are:

| Logic type | Executable | Location |
|---|---|---|
| SQL | Actual filename including .sql, for example build_customer.sql. | Path to the logic file in the framework's expected form. |
| Python | Actual filename including .python, for example build_customer.python. | Path to the logic file in the framework's expected form. |

- Read-only reference context for Metadata Change Sets; use an existing active registered name.
- Use the registered name corresponding to SQL or Python. The current schema remains a registered-name string/FK; this decision does not add a database enum or alter registrations.
- Notebook in legacy test seeds does not establish support in the user's SQL/Python framework. Preserve unrelated registrations; do not invent a reference value or infer support from its presence alone.
- Preserve the stated .python extension; do not silently substitute .py, strip the extension or rename an existing executable.
- Resolve how the framework consumes location and filename from working metadata or the relevant code when needed; do not assume a universal path-joining rule.
- Registering a Process does not deploy, schedule, or execute its artifact.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:139,343`.
- `database/01_reference.sql:212`.
- `database/seed/01_metadata_snapshot_demo.sql:59`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:362,557`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:244`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:34`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
