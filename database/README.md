# PostgreSQL 18 fresh-install order

These files are for a new, empty database. They are not migrations for a
populated database. Run them as the Azure PostgreSQL server administrator; the
MCP runtime account must never own schema objects or install DDL.

## 1. Connect securely

```bash
psql "host=<server>.postgres.database.azure.com port=5432 dbname=<database> user=<server-admin> sslmode=verify-full"
```

Enter the administrator password at the prompt. Never put it in a repository
file, shell command, or chat message.

## 2. Run the read-only preflight

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/00_preflight.sql
```

Stop if it fails. Never run fresh-install DDL over existing release schemas.

## 3. Run the ordered installation files

Run `01` through `12` exactly once and in order. Each command is atomic:

```bash
for file in database/{01_reference,02_core,03_security,04_model,05_workflow_analysis,06_workflow_conceptual,07_workflow_logical,08_workflow_dimensional,09_workflow_mapping,10_mcp,11_runtime_account,12_runtime_integrity}.sql
do
  psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
    --single-transaction -f "$file" || exit 1
done
```

If any file fails, preserve the error and stop. Do not drop, truncate, reset, or
rerun earlier files.

`11_runtime_account.sql` creates `gds_mcp_runtime` with no password, grants its
only direct membership (`gds_app_write`), and grants connection to this database.
The passwordless account cannot authenticate.

## 4. Set the runtime password securely

While connected as the administrator in interactive `psql`, run:

```text
\password gds_mcp_runtime
```

The prompt asks twice without storing the password in a SQL file or shell
history.

## 5. Verify everything

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/13_verify_install.sql
```

The last row must show `schema_version = 1.0.0` and
`verification_status = passed`.

The App Service DSN must use `user=gds_mcp_runtime` and
`sslmode=verify-full`. Store the complete DSN in Key Vault; never commit it.

## 6. Optional test seed

See `database/seed/README.md`. Demo seed data is only for a new test database.
