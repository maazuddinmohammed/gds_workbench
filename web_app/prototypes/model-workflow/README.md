# GDS Workbench flow prototype

Throwaway prototype for the selected layout: guided workflow navigation with compact ledgers and work surfaces.

Connected in-memory flow:

- Tenant chooser with search, last-accessed default, and explicit Workbench entry
- Tenant Home focused on governed Tenant Lock state and registered Systems
- Metadata with all 5 Foundational, 8 Reference, and 16 Operational plugin sheets; exact normalized columns; sheet-specific filters; and Tenant-Lock-gated Add/Edit/Import controls
- Models ledger and Customer 360 workflow rail
- Scope with exact normalized `model_scope` columns and Add Objects filters for source Tenant, System, Zone, and Object name
- Profiling with exact Attribute-level profile columns, explicit Databricks run configuration, run history, and on-demand event inspection
- Analysis with inference and validation on the same normalized record, row Lock/Unlock, inactive visibility, explicit run configuration, and run history
- Assertion Documents and Assertion Records
- Conceptual Objects and Relationships with dedicated full-page record review and normalized support arrays
- Logical Submodels, Entities, Attributes, and Relationships with dedicated full-page review of Submodel membership and source arrays
- Dimensional Submodels, Entities, Attributes, and Relationships with dedicated full-page review of eligible Silver inputs and source arrays
- One Mapping review workspace with Model, Entity type, and System filters; Dependencies, Object mappings, Attribute mappings, dedicated full-page document review, templates selected per run, and run history
- SQL-only Code Generation entered through a Model ledger, then driven by target Objects from applied Mapping with selected/all generation, stored SQL review, regeneration, and download

Run from this directory:

```bash
python3 -m http.server 4174
```

Open `http://localhost:4174/?screen=tenant-select`.

## Design decision

The three layout variants are closed. The prototype keeps the guided workspace structure and compact ledger. The switcher and losing variants were removed.

Large descriptive headers were removed. Compact bars keep dataset tabs, permission state, refresh, and primary actions together.

Ledger rules are consistent across Metadata, Model, and Mapping:

- no generic table search
- normalized field-specific filters
- exact ID-free business-contract columns
- Add/Edit/Lock controls enabled only while the Tenant Lock is held
- Metadata, Scope, and run-event details open on demand in closable drawers
- Conceptual, Logical, Dimensional, and Mapping details navigate to a dedicated record page and return to the exact source ledger

The three agentic authoring modes remain explicit: One-shot, Tool-assisted, and Detailed Coverage. Each authoring run exposes the registered model, reasoning effort, max turns, and validation retries. No automatic fallback or partial write is represented.

## Proposed application-only database boundary

No DDL is implemented by this prototype.

Prefer schema name `application`, not `web`: the records belong to backend application control, not frontend presentation.

First minimal table proposal: `application.principal_preference` with one row per server-derived Principal, `last_tenant_id`, `last_accessed_time`, and the repository's standard audit columns. The last accessed Tenant is the default; no separate default-setting concept is needed for Release 1.

The new workflow-stage, prompt, and allowed-variable tables may also live in `application` because they control web-application orchestration. Existing MCP, plugin, `reference`, `core`, `security`, `model`, and `workflow` behavior remains unchanged. If MCP or plugins later consume those prompts directly, reassess a shared orchestration schema then.

## API surfaces suggested by the prototype

- Authorized Tenant collection and last-Tenant preference
- Tenant summary, systems, connections, discovery scopes, and governed Tenant Lock operations
- Reference, foundational, and operational metadata collections
- Model ledger, Model Scope, and governed bulk Scope mutation
- Profiling run, run events, Object results, and Attribute results
- Analysis inference/validation runs, run events, findings, and governed bulk Lock/Unlock
- Assertion Document and Assertion Record collections
- Conceptual, Logical, and Dimensional collections plus their explicit authoring runs
- Logical and Dimensional Mapping collections, templates, runs, and governed row actions behind one combined review route
- Applied Mapping target collection for SQL generation, generation guides, stored SQL artifacts, regeneration, run events, and downloads

This remains frontend-only. Stored SQL is represented in memory only; no backend routes, database DDL, external calls, or production implementation were added.

Delete or absorb this prototype after the screen and route contracts are finalized.
