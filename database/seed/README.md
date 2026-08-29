# Seed data

Seed files are separate from canonical DDL. Run them only after
`database/13_verify_install.sql` passes.

## Application reference metadata

`04_application_reference.sql` installs 47 stable workflow stages and 78 allowed
backend-resolved prompt variables. It includes deterministic stages, but gives
variables only to agentic stages. It contains no prompt or SQL-generation-guide
bodies, credentials, connection values, or business data.

Run it in a fresh application database after install verification. Replaying
the exact file is safe and does not update existing rows:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f database/seed/04_application_reference.sql
```

## Global default Prompts

`05_global_prompt_defaults.template.sql` creates the governed global default
for all 35 agentic Workflow Stages. The 12 deterministic stages, including
Profiling, do not accept Prompts.

Run `04_application_reference.sql` first. Then find one active Super Admin
identity:

```sql
SELECT principal.principal_display_name,
       principal.principal_type,
       identity.entra_tenant_id,
       identity.entra_object_id
  FROM security.principal AS principal
  JOIN security.entra_principal_identity AS identity
    ON identity.principal_id = principal.principal_id
   AND identity.principal_type = principal.principal_type
 WHERE principal.is_super_admin
   AND principal.is_active
   AND identity.is_active;
```

Copy the template outside the repository and replace the Entra Tenant ID,
Entra Object ID, and Principal type placeholders with one row from that query:

```bash
cp database/seed/05_global_prompt_defaults.template.sql \
  /tmp/gds_global_prompt_defaults.sql
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f /tmp/gds_global_prompt_defaults.sql
```

The seed refuses a missing or non-Super-Admin identity. Exact replay is a
no-op. Changed seed content publishes a new immutable version and moves the
seed-owned global assignment without duplicating the template or overwriting
history. It refuses to replace an active global default owned by another
template.

The agent runtime already supplies bounded context, naming rules, Mapping
output templates, SQL guides, and the required output schema separately. The
defaults therefore do not duplicate those potentially large values. Only the
outer reconciliation stages interpolate their allowlisted
`validation_failures` value.

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

## Local Super Admin

`03_local_super_admin.template.sql` creates the single database identity used
when `GDS_ENVIRONMENT=local`. It is manual, local-development data; never run it
in production.

Copy it outside the repository, then replace:

- `__REPLACE_WITH_EXPECTED_DATABASE_NAME__` with the exact target database;
- `__REPLACE_WITH_ENTRA_TENANT_ID__` with `GDS_ENTRA_TENANT_ID`; and
- `__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__` with a generated UUID that also
  becomes `GDS_LOCAL_PRINCIPAL_OBJECT_ID`.

Run the edited copy as the database administrator with
`psql -X -v ON_ERROR_STOP=1 --single-transaction -f <edited-copy>`. The script
refuses unchanged placeholders, a database-name mismatch, zero UUIDs, and
duplicate local identities. Super Admin grants authorization, but it does not
bypass Tenant Locks, revisions, validation, or audit.
