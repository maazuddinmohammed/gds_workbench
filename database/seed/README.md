# Seeds

Run only after compatible schema installation and `20_verify_install.sql` succeeds.
These are configuration/fixture seeds, not schema migrations. Never run demo/local
seeds on populated or production databases. Local cleanup is container disposal only.

| File | Purpose and order |
| --- | --- |
| `04_application_reference.sql` | Required workflow stages and backend-resolved variables; apply before prompt defaults. |
| `05_global_prompt_defaults.template.sql` | Canonical system/instruction prompts and reader selections for every agentic stage. |
| `07_global_mapping_output_templates.template.sql` | Canonical Logical/Dimensional Object/Attribute template definitions. |
| `02_human_principal_access.template.sql` | Explicit human Entra Principal/access bootstrap; starts with Viewer. |
| `01_metadata_snapshot_demo.sql` | Test-only physical metadata fixture. |
| `03_local_super_admin.template.sql` | Disposable local identity bootstrap; never production. |
| `08_local_workbench_review.sql` | Review Model fixture installed by the local runner; never run manually against a populated database. |

## Required defaults

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f database/seed/04_application_reference.sql
```

For seed 05/07, copy the template outside the repository and replace every identity
placeholder with one approved active Super Admin's Entra Tenant ID, Entra Object ID
and Principal type. The seed revalidates that identity; ordinary authentication does
not grant Super Admin. Use interactive database credential handling:

```bash
cp database/seed/05_global_prompt_defaults.template.sql /tmp/gds_global_prompt_defaults.sql
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f /tmp/gds_global_prompt_defaults.sql
```

Use the same procedure for seed 07. Keep prepared copies untracked and outside the
repository. Editing a source seed does not alter published database versions.

- Seed 04: exact replay makes no writes. Updated descriptions/examples refresh in
  place; IDs, existing order/settings and custom variables stay intact. New variables
  append. Conflicting resolver/type definitions fail explicitly.
- Seed 05: merges by stable template code through governed functions. Existing
  templates are reused; exact replay is a no-op. Changed content publishes one new
  immutable version and updates the active seed-owned default, without duplicate
  templates or active assignments. Historical versions/assignments are retained.
  Custom defaults/unrelated drafts are protected; frozen Runs keep their versions.
- Seed 07: exact replay is a no-op. Conflicting immutable template definitions fail;
  custom selections and frozen IDs/digests stay intact. Install the four active defaults
  for runs that omit a custom selection. Templates guide document fields, not business
  truth or independent execution permission.

The runtime variable/reader registry and these seeds must change together; see
[workflow maintenance](../../docs/workflows.md). Deterministic stages do not use prompts.

## Identity and local fixtures

Human bootstrap requires a reviewed active Tenant and actual Entra identity. Copy
seed 02 outside the repository; replace all placeholders before execution. Email is
administrative metadata, not login identity. The template rejects unresolved
placeholders, inactive/missing Tenants and duplicate identities.

Use `python3 web_app/local/run.py` for local review. It generates random database
credentials and identity, installs local fixture seeds and disposes its container
on exit. Seed 03 verifies the expected disposable database/identity; seed 08 checks
the generated local database convention. Do not substitute an existing database.
