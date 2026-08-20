# Databricks SQL execution contract

## Inputs

`execute_databricks_sql` accepts exactly:

- `connection_id`: positive ID of an active, tenant-owned, non-global source
  Connection;
- `environment_code`: 1–100 characters, matched case-insensitively to one configured
  Environment; and
- `sql`: 1–100,000 characters and at most 25 statements;
- `schema_version`: `1.0`.

SQL may read or create unqualified temporary views/tables. It cannot run DML,
persistent DDL, secret functions, or code. Every persistent relation must use
`catalog.schema.table`; only temporary relations created earlier in the same batch may
be unqualified. The final statement supplies the returned rows.

## Server workflow

1. Parse and reject disallowed SQL before opening Databricks.
2. Derive the authenticated Principal from the request.
3. Load the selected source Connection. It must be active and non-global.
4. Derive that Connection's Tenant and authorize the Principal for Tenant Read.
5. Resolve server-held connection values using the source Connection, the Tenant's
   configured Global Data Store Connection, and the requested Environment.
6. Validate the resolved hostname, SQL Warehouse HTTP path, and token without exposing
   them.
7. Open one Databricks SQL session and execute statements in order. Temporary objects
   exist only in this session.
8. Return columns and at most 50 rows from the final statement. Cells and the complete
   result are bounded; truncation is explicit.
9. Append bounded tool metadata to the audit. The complete submitted SQL is retained;
   credentials and sensitive literals must never be included.

The caller never chooses a Tenant or Global Data Store Connection directly. Changing
`connection_id` changes the source Connection and derived Tenant. Changing
`environment_code` selects that Environment's stored parameters for the derived route.

## Error interpretation

- `connection_not_found`: source ID is inactive, global, missing, or not visible.
- `databricks_connection_configuration_*`: the selected route lacks valid server-held
  values; an administrator must repair configuration.
- `databricks_connection_failed`: Databricks could not be reached or authenticated.
- `databricks_statement_failed`: correct the reported statement; do not retry the
  entire batch blindly when temporary state or external effects are ambiguous.
- `databricks_result_too_large`: aggregate, narrow columns, or split analysis. Do not
  bypass bounds or sample raw rows.
