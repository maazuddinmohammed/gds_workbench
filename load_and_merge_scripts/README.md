# Excel loader

This replaces the Databricks sample with a normal Python script. It reads the
current workbook templates, stages selected rows in session-temporary PostgreSQL
tables, then runs current-DDL `MERGE` statements in dependency order.

## Setup

```bash
cd load_and_merge_scripts
uv sync
cp .env.example .env
```

Set these only in `.env` or the shell:

```text
GDS_LOADER_DSN=<dedicated loader DSN with sslmode=verify-full>
GDS_LOADER_WRITE_ACK=I_UNDERSTAND_THIS_WRITES_DATA
```

Use a dedicated non-owner, non-superuser login with only the target DML,
sequence, temporary-table, lookup, and governed-function permissions it needs.
The loader verifies this. Do not use a database owner, bootstrap admin,
`gds_app_write`, or `gds_mcp_runtime`. Role/grant creation stays with the DBA;
this script never changes roles. Never commit `.env` or populated workbooks.

Data workbooks are bootstrap/provisioning only. The loader refuses them after
any Tenant Lock, workflow, revision, change-set, or MCP audit activity exists.
Stop the application and workers for the entire bootstrap load; the loader
serializes other loader runs and locks its target tables, but it cannot pause
external runtimes. Normal runtime data changes use governed change-set
operations.

`locks.xlsx` is separate. Its authenticated PostgreSQL `session_user` must equal
the active Principal's email (user) or application UUID (service principal).
The database resolves that login to one active Entra identity, then requires
the correct Tenant role and an active Tenant Lock owned by the same Principal.
No caller-supplied actor UUID is accepted. Model rows must include the current
`expected_model_revision`; changes compare, advance, and audit that revision.

## Run

List sheets:

```bash
uv run python loader.py --list
```

Validate one sheet without connecting:

```bash
uv run python loader.py --workbook foundational.xlsx --sheet Environment
```

Execute after the dry run passes:

```bash
uv run python loader.py --workbook foundational.xlsx --sheet Environment --execute
```

To use the sample's uncomment-and-run style, uncomment entries in
`MANUAL_LOAD_SELECTIONS`, then run `uv run python loader.py` (dry run) or add
`--execute`.

Omitting `--sheet` loads one whole workbook atomically. Any failure rolls back
every selected sheet. Missing sheets, wrong headers, blank required values, and
duplicate source keys fail instead of being skipped.

Whole-workbook order is `foundational.xlsx`, `tenant_modeling.xlsx`, then
`users_security.xlsx`. Run `locks.xlsx` separately. Manual selections spanning
data files are sorted automatically; one `--workbook` run cannot load
prerequisites from a different file.

All four workbooks must remain under `load_and_merge_scripts/data/`. CLI options
use workbook filenames, not paths.

## Staging

PostgreSQL cannot put a true temporary table in a named schema. The loader uses
session tables named `pg_temp.staging_<schema>_<table>`. They disappear when the
connection closes, so no `DROP`, `TRUNCATE`, or cleanup helper is needed.

## Included data

- `foundational.xlsx`: Reference data, Project, System, notebook paths.
- `users_security.xlsx`: Principal, Entra identity, Tenant access.
- `tenant_modeling.xlsx`: Tenant/Core configuration, Model, Model Scope.
- `locks.xlsx`: allowlisted lock columns only.

Workflow/MCP tables, workflow Mapping, Tenant Lock leases/events, Model event
logs, Modeling Assertion load sheets, and revision transactions are intentionally
omitted. Core ingestion mappings remain because Copy configuration depends on
them. `LockControl` can still change the lock flag on an existing Modeling
Assertion Record.

`LockControl` supports:

- `core.object.object_id` -> `is_locked`
- `model.model_scope.model_scope_id` -> `model_scope_is_locked`
- `model.modeling_assertion_record.modeling_assertion_record_id` ->
  `modeling_assertion_record_is_locked`

`security.tenant_lock` is not a Boolean lock and cannot be changed here.
Leave `expected_model_revision` blank for `core.object`; supply it for both
`model.*` targets. A stale value rolls back the whole workbook.

## Legacy samples

`load_script.txt` and `merge_script.txt` are preserved reference samples. They
are outdated Databricks code and must not be run. `loader.py` and
`load_config.yaml` are authoritative.
