# PostgreSQL fresh installation

Numbered SQL is the canonical PostgreSQL 18 schema for an empty database, not a
migration or replayable installer. Run as an authorized administrator, never a
runtime role. Existing installations need a separately reviewed release transition.
Tests/local runs may use only fixture-created disposable containers.

## Install

Connect using approved credential handling and TLS. Enter passwords interactively;
never put them in commands or tracked files. From the repository root:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 -f database/00_preflight.sql
```

Stop on failure. Install `01`–`19` once, in lexical order and one transaction per file:

```bash
for file in database/{01_reference,02_core,03_security,04_model,05_workflow_analysis,06_workflow_conceptual,07_workflow_logical,08_workflow_dimensional,09_workflow_mapping,10_workflow_code_validation,11_workflow_eligibility,12_application_configuration,13_application_workflow_runs,14_application_workflow_execution,15_mcp_change_sets,16_mcp_metadata_apply,17_mcp_tool_call_log,18_runtime_account,19_runtime_integrity}.sql
do
  psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
    --single-transaction -f "$file" || exit 1
done
```

A failed file stops installation; never drop/reset or replay earlier files to hide
failure. The disabled cleanup reference in preflight is not an installation step.

Set different runtime passwords inside interactive `psql`:

```text
\password gds_mcp_runtime
\password gds_web_runtime
```

MCP uses `gds_mcp_runtime`/`gds_app_write`; web uses
`gds_web_runtime`/`gds_web_write`. Runtime logins never own schema objects.

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 -f database/20_verify_install.sql
```

Require `verification_status = passed`. The verifier and runtime readiness checks
own the current inventory and permission requirements; do not maintain a second
manually counted schema list in docs.

## Configure application defaults

After verification, install [seed 04](seed/04_application_reference.sql), establish
the approved active Super Admin identity, then apply prepared copies of prompt
[seed 05](seed/05_global_prompt_defaults.template.sql) and Mapping-template
[seed 07](seed/07_global_mapping_output_templates.template.sql). See the
[seed instructions](seed/README.md) for placeholders, replay behavior and optional
identity/demo seeds. Seed replay does not upgrade a database schema.

Modeling and workflow semantics are in [CONTEXT](../CONTEXT.md),
[current decisions](../docs/architecture/decisions.md) and [workflow sources](../docs/workflows.md).
Exact tables/functions/constraints are in numbered SQL; meaningful installed-database
checks are under `tests/mcp/`. Runtime startup never installs or repairs schema.
