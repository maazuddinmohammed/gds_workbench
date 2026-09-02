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
The cleanup reference at the top of `00_preflight.sql` is intentionally
commented and is not part of preflight execution. Do not uncomment it to bypass
a failed installation; it is reserved for the whole-server retirement process
in section 7.

## 3. Run the ordered installation files

Run every file below in the fixture's lexical order. Each command is atomic:

```bash
for file in database/{01_reference,02_core,03_security,04_model,05_workflow_analysis,06_workflow_conceptual,07_workflow_logical,08_workflow_dimensional,09_workflow_mapping,10_workflow_code_validation,11_workflow_eligibility,12_application_configuration,13_application_workflow_runs,14_application_workflow_execution,15_mcp_change_sets,16_mcp_metadata_apply,17_mcp_tool_call_log,18_runtime_account,19_runtime_integrity}.sql
do
  psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
    --single-transaction -f "$file" || exit 1
done
```

If any file fails, preserve the error and stop. Do not drop, truncate, reset, or
rerun fresh-install files.

`18_runtime_account.sql` creates three separate passwordless logins. MCP uses
`gds_mcp_runtime`, whose only direct membership is `gds_app_write`. The web app
uses `gds_web_runtime`, whose only direct membership is `gds_web_write`.
Databricks notebooks use `gds_notebook_runtime`, whose only direct membership
is also `gds_web_write`. All memberships disable inheritance and administration
and allow explicit transaction-scoped role activation. The notebook base login
therefore retains only its governed wrapper surface until shared workflow code
issues `SET LOCAL ROLE gds_web_write`. All three receive database connection
access, but none can authenticate until its own password is set.

`application.create_workflow_run` accepts the exact selected Object IDs plus
bounded workflow-specific inputs. Mapping selected coverage accepts one target
Object/source System pair and `build|extend`. The caller does
not choose its modeled layer or route. PostgreSQL resolves those from the
active Model Object Binding and target Zone, then freezes the pair and route.
Code Generation
is target-first: selected coverage supplies exact target Object IDs, while
all-eligible coverage supplies an empty selection and lets PostgreSQL derive all
eligible targets. Each Run freezes its modeled layer, Model revision, canonical
selection, and active published explicit-or-default SQL Generation Guide
version and digest. PostgreSQL also resolves the actor and derives every
canonical selection digest/count. A Profiling or Analysis batch ID is accepted
only when the selected eligible Objects belong to one System; no-batch
multi-System runs remain valid. Callers never supply a digest or count.

Workflow execution is claimed only through
`application.claim_next_workflow_run`. It uses PostgreSQL time and
`FOR UPDATE SKIP LOCKED` to give one worker the oldest eligible running Run.
Leases are 1 through 300 seconds. The raw UUID claim token is internal worker
state: never serialize it to a browser response, log it, or persist it. The Run
stores only its SHA-256 digest. `renew_workflow_run_claim` heartbeats an exact
live token, `release_workflow_run_claim` clears an exact live token, and an
expired lease may be reclaimed at most five times. Each reclaim rotates the
token and increments the recovery count. A sixth expired lease is atomically
failed with the bounded `workflow_run_recovery_exhausted` reason and one safe
failed Run event. A running Run whose Model, actor, or exact unambiguous actor
identity is no longer active is similarly failed once with the bounded
`workflow_run_context_unavailable` reason. Each claim call processes at most
100 rows in each housekeeping class. Repeated claim calls drain any backlog;
neither case can leave the Tenant-wide running guard wedged. Final business
writes must call
`assert_workflow_run_claim` inside the same database transaction before writing;
the assertion locks the Run row and rejects stale, expired, terminal, or wrong
tokens. Only `gds_web_write` may execute these four internal functions. It has
no direct Run DML, and MCP has no Application schema or claim-function access.
The internal claim result also returns the active owning Tenant, execution
mode, and exact active Entra Principal identity needed to reconstruct the
server-derived worker Principal. Those identity fields are internal too and
must never enter browser responses, logs, or events. A Run with an inactive or
missing Model, actor, or identity is never returned as a claim; bounded claim
housekeeping terminalizes it safely. Nullable legacy identity provenance is
claimable only when the Principal has exactly one active Entra identity.

`workflow.list_code_generation_target_context` returns one canonical row per
bound target Object. It aggregates every active, complete Mapping and its
ordered source Systems, returns the modeled entity name, and derives one
`code_input_digest` over Mapping plus source context. Current Code Generation
writes `workflow.generated_code` only through validated Model Change Set Apply.
Generated SQL is never executed by this database path.

Large Code stays one `generated_code` record. The normal Model Stage Batch may
switch from complete-record chunks to ordered JSON byte fragments for that
dataset only. `mcp.model_stage_payload_chunk` stores the transport fragments;
Commit verifies and concatenates them, parses one canonical record array, and
stages the reconstructed record atomically. Code content has no separate
domain-size limit, and fragment bodies never enter MCP audit metadata.

Every Object stores its required source Tenant directly in
`core.object.source_tenant_id`. Source Objects use their source Tenant's
non-GDS Connection. Bronze, Silver, and Gold Objects use that source Tenant's
configured GDS Connection even though the Connection is registered under the
GDS placement Tenant.

`application.get_profiling_execution_context` returns the complete selected
Source/Bronze Object and Attribute plan for one authorized running Profiling
Run. Source rows require and return foreign catalog/schema/Object/Attribute
coordinates. Bronze rows return native GDS coordinates. The separate
`application.get_profiling_connection_values` returns one complete credential
tuple per selected Connection for one active Environment, or one fixed safe
failure with no partial values. Only `gds_web_write` may execute either function.

Analysis validation uses the same governed split through
`application.get_analysis_validation_execution_context` and
`application.get_analysis_validation_connection_values`. It returns only
active relationships whose two input endpoint Objects were
explicitly selected, includes locked rows for validation-only refreshes, and
never exposes partial connection values.
`application.persist_analysis_validation_results` then atomically updates only
the complete validation payload and validation Run provenance, preserving all
inference, status, and lock fields. It rechecks and stores a database-computed
source-context digest so physical metadata cannot silently change between query
execution and persistence. The digest also binds the selected Environment and
non-secret row-version witnesses for the host, HTTP path, and token settings;
raw connection values never enter provenance. Manual and MCP-authored evidence
may leave that web Run provenance nullable.

`application.persist_profiling_results` atomically replaces the complete active
Attribute Profile set for a running Profiling Run's selected Objects. It derives
Tenant and Model ownership from the Run, rechecks actor, Tenant Lock, revision,
and exact Bronze Attribute coverage, preserves Profiles outside the selection,
and returns the current revision for `complete_workflow_run`.

`application.complete_authoring_workflow_run_no_op` atomically records an exact
unchanged-Candidate receipt for Analysis, Conceptual, Logical, Dimensional, or
Mapping. It rechecks the actor, Run identity, mode, correlation, base revision,
and Candidate digest; rejects any Run-bound Model Change Set; appends the exact
workflow-specific backend-validation event and completes the Run without
advancing the Model revision. Only an exact request can replay the stored
receipt.

Web Model authoring uses only `application.create_model`, `update_model`, and
`archive_model`. These fixed-search-path functions
derive authorization from the active identity and the Model's owning Tenant,
require the caller to own the current Tenant Lock, fence updates with
`model_revision`, and record one revision transaction per actual change. Model
archive also rejects while any Workflow Run is running for the owning Tenant.
Model Input Scope is applied through the governed Model Change Set boundary and
contains only Source/Bronze inputs. Silver/Gold targets are registered first by
Metadata Change Set, then tied to modeled entities through Model Object and
Attribute Bindings. The web role has no direct Application-table DML.

## 4. Set the runtime passwords securely

While connected as the administrator in interactive `psql`, set a different
password for each login:

```text
\password gds_mcp_runtime
\password gds_web_runtime
```

Each command prompts twice without storing its password in a SQL file or shell
history.

## 5. Verify everything

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/20_verify_install.sql
```

The last row must show `schema_version = 1.0.0` and
`verification_status = passed`.

The MCP App Service DSN must use `user=gds_mcp_runtime`; the Databricks web App
DSN must use `user=gds_web_runtime`. Both require `sslmode=verify-full`. Store
each complete DSN in its approved secret resource; never commit it.

This repository provides no executable migration, backfill, reset, or repair
helper for populated databases. The numbered SQL is only for a new, empty
database. Test databases are cleaned up only by disposing their containers.

## 6. Install required web application reference data

After `20_verify_install.sql` passes, install the canonical application
reference seed:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f database/seed/04_application_reference.sql
```

This seed is required for the Databricks web App deployment. Web readiness
requires exactly 49 active workflow stages and 80 active backend-resolved
variables. The seed contains no prompt bodies, credentials, connection values,
or business data and is safe to replay unchanged.

## 7. Install global default Prompts

After an active Super Admin Principal and Entra identity exist, install
`database/seed/05_global_prompt_defaults.template.sql` as documented in
`database/seed/README.md`. It supplies all 36 agentic stage defaults required
when a Workflow Run has no run or Model override. Profiling and the other
deterministic stages do not use Prompts.

## 8. Clean redeployment

Provisioning a new server remains the preferred clean-redeployment path. If an
authorized DBA must retire and reuse the entire GDS server environment, the top
of `00_preflight.sql` contains an exhaustive but disabled cleanup reference for
the seven release schemas and five release roles. Use it only after stopping
clients, completing backup and retention checks, and confirming that no other
database or application uses those cluster-wide roles.

`DROP OWNED` is database-scoped, so its five statements must be considered in
every database containing a role dependency before the roles are dropped.
Schema `CASCADE` can remove cross-schema dependents; selective schema redeploy
is therefore not supported. After full cleanup, run the unchanged read-only
preflight, complete installation, required reference seed, and verification,
then switch the approved application DSNs and validate both applications.

## 9. Optional demo and identity seeds

See `database/seed/README.md`. `04_application_reference.sql` is required
application reference data. The global Prompt seed is installed after its
explicit Super Admin identity exists. Demo metadata is optional and only for a
new test database; identity templates are environment-specific operator inputs.
