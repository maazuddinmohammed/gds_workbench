# PostgreSQL 16 fresh-install runbook

Use these instructions only for a new, empty database. The numbered files are
fresh-install DDL, not migrations for a populated database.

The Azure PostgreSQL server administrator must run the installation. The MCP
runtime login must never own schema objects or run these files.

## 1. Connect securely

Use PostgreSQL 16 `psql` and TLS hostname verification:

```bash
psql "host=<server>.postgres.database.azure.com port=5432 dbname=<database> user=<server-admin> sslmode=verify-full"
```

Enter the administrator password only at the prompt. Do not put it in a shell
command, SQL file, repository file, or chat message.

## 2. Run the read-only preflight

From the repository root:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/deployment/00_preflight.sql
```

Stop if the preflight fails. In particular, do not run fresh-install DDL over a
database where any release schema already exists.

## 3. Install the canonical schema

Run each file exactly once, in numeric order. `--single-transaction` makes each
individual file atomic and `ON_ERROR_STOP` prevents execution after an error.

```bash
for file in database/{01_reference,02_core,03_security,04_model,05_workflow_analysis,06_workflow_conceptual,07_workflow_logical,08_workflow_dimensional,09_workflow_mapping,10_mcp,11_runtime_integrity}.sql
do
  psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
    --single-transaction -f "$file" || exit 1
done
```

If a file fails, preserve the error and stop. Do not drop, truncate, reset, or
rerun earlier files.

## 4. Verify the installed schema and group roles

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/deployment/12_verify_install.sql
```

The last row must report `schema_version = 1.0.0` and
`verification_status = passed`.

## 5. Create the runtime login

This psql-only script creates `gds_mcp_runtime`, grants exactly one direct group
membership (`gds_app_write`), grants database connection, and prompts for the
password without storing it in a file:

```bash
psql "<admin-dsn-without-password>" -X \
  -f database/deployment/13_create_runtime_login.psql
```

Then verify it:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/deployment/14_verify_runtime_login.sql
```

The runtime DSN used by App Service must include `user=gds_mcp_runtime` and
`sslmode=verify-full`. Store that complete DSN in Key Vault; do not commit it.

## 6. Seed only when appropriate

See `database/seed/README.md`. Demo seeds are for a new test database only.
Never run demo seed data against a populated or production database.
