# Seed data

Seed files are separate from canonical DDL. Run them only after
`database/deployment/12_verify_install.sql` passes.

## Demo metadata

`01_metadata_snapshot_demo.sql` creates a small test-only dataset containing:

- one private Tenant and one global-data-store Tenant;
- Source, Bronze, Silver, and Gold objects and attributes;
- active ingestion mappings across all four zones;
- one copy group, member group, control row, copy, process group, and process;
- Bronze, Silver, and Gold metadata discovery scopes; and
- only the Reference values required by those rows.

Run it only in a new test database:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f database/seed/01_metadata_snapshot_demo.sql
```

Do not run this demo file against a populated or production database.

## Human Entra access

`02_human_principal_access.template.sql` contains placeholders for the actual
Entra identity. It contains no login password: App Service Easy Auth validates
the login, while PostgreSQL matches the immutable Entra Tenant ID and Object ID.
Email is display/administrative metadata only.

Copy the template outside the repository, replace every `__REPLACE_...__`
placeholder, and run that copy as the database administrator:

```bash
cp database/seed/02_human_principal_access.template.sql \
  /tmp/gds_human_principal_access.sql
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f /tmp/gds_human_principal_access.sql
```

The template grants `viewer`, which is sufficient for `list_tenants` and
`get_metadata_snapshot`. It refuses unchanged placeholders, missing/inactive
Tenants, and duplicate Principal or Entra identity records.
