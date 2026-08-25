# GDS Agent Plugin

The GDS plugin connects an agent to the governed GDS Workbench MCP server and teaches
it how to inspect physical Metadata, collect modeling evidence, design data models, and
move complete Change Sets through review and validation.

It does not give the agent credentials or direct database access. The server derives
the authenticated Principal, Tenant authorization, source Connection ownership, and
Global Data Store route.

## Start with the stopping point

Every workflow has a boundary. State it in the request when it matters:

| Boundary | Result | What does not happen |
|---|---|---|
| Read | Current governed facts or an explanation | No draft or lock. |
| Proposal | Checked records/design in the conversation | No file or server write. |
| Local draft | Saved files under `GDS/change-set` or `GDS/model-change-set` | No lock or MCP mutation. |
| Validated server draft | Staged Change Set passes server validation | Nothing is Applied. |
| Applied change | Exact validated revision is Applied and verified | Apply still requires fresh explicit approval. |

If no boundary is stated, authoring skills stop at a proposal. Reading a dependency
does not make it part of the change.

## Choose the skill

| Skill | Use it when | Default result |
|---|---|---|
| `$understand-gds` | You need a GDS concept explained or do not know which workflow fits. | Explanation and route. |
| `$manage-gds-metadata` | You need physical Tenant/Object/Attribute, Copy/Process, Snapshot, Lock, or Metadata Change Set work. | Focused read or requested Metadata boundary. |
| `$author-model-metadata` | You need the exact JSON shape or a synthetic example for physical Metadata. The name is legacy; it does not author Model records. | Schema-checked example. |
| `$run-gds-databricks-sql` | You need general governed Databricks read SQL or temporary views/tables. | Reviewed SQL or bounded final result. |
| `$profile-gds-data` | You need fixed table/column Profile metrics and `profiling_profile` records. | Aggregate evidence proposal. |
| `$analyze-gds-relationships` | You need directed key coverage/uniqueness evidence and an `analysis_result`. | Aggregate relationship-evidence proposal. |
| `$capture-modeling-assertions` | Requirements, policies, glossaries, spreadsheets, notes, or supplied text should become sourced modeling facts. | Located Assertion proposal. |
| `$manage-gds-model` | You need existing Model/Scope/evidence/layer reads, Snapshot/DBML, or Model Change Set lifecycle/handoff. | Focused read or requested Model boundary. |
| `$build-conceptual-model` | You need business concepts, vocabulary, grain, and high-level relationships. | Conceptual proposal. |
| `$build-logical-model` | You need normalized Entities, Attributes, identifiers, optionality, and relationships. | Logical proposal. |
| `$build-dimensional-model` | You need a star schema, Fact grain, Dimensions, measures, additivity, or history choices. | Dimensional proposal. |
| `$build-data-mapping` | You need physical-to-Logical/Dimensional Object and Attribute mappings. | Mapping proposal. |
| `$open-gds-metadata-workbench` | You want to inspect a downloaded Snapshot or edit a local Change Set in the browser. | Local files only. |
| `$grill-data-model` | You explicitly want a bounded, one-question-at-a-time modeling interview. | Decisions, gaps, and readiness summary. |
| `$run-data-modeling-goal` | You want a durable multi-checkpoint modeling objective or a paste-ready goal prompt. | Prepared or explicitly started goal. |

The shared [workflow map](references/workflow-map.md) resolves overlapping words such
as Analysis, Profiling, Mapping, Snapshot, SQL, and Change Set.

## How to ask each skill

### Orientation and governance

- **Understand GDS:** give the term or outcome you are unsure about. Ask:
  `Use $understand-gds to explain Model Scope versus Metadata Discovery Scope and tell
  me which workflow I need. Do not make changes.`
- **Manage Metadata:** give the Tenant, physical area, operation, and boundary. Ask:
  `Use $manage-gds-metadata to inspect active Silver Objects for Tenant 5. Read only.`
- **Manage Model:** give the existing Model, requested evidence/layer, and boundary.
  Ask: `Use $manage-gds-model to inspect current Analysis and Assertions for Model 41.
  Do not create a Change Set.`
- **Author physical Metadata JSON:** name one physical dataset and whether you want an
  explanation or synthetic example. Ask: `Use $author-model-metadata to explain the
  source_object canonical key and show one synthetic schema-valid record.`
- **Open the Data Workbench:** have an extracted `GDS/metadata-snapshot` or
  `GDS/model-snapshot` available. Ask: `Use $open-gds-metadata-workbench to open my GDS
  workspace. Local files only.`

### Databricks and evidence

- **General SQL:** provide or identify the registered source Connection, Environment,
  and question. Ask: `Use $run-gds-databricks-sql with source connection 41 in TEST to
  review this query, then run it. Every physical table is catalog.schema.table.`
- **Profiling:** provide the existing Model/Object, exact Databricks relation,
  Environment, and—only when configured—batch mode/IDs. Ask: `Use $profile-gds-data to
  profile Model 41's gds_test.sales.orders table in TEST. Use its configured batch
  Attribute; ask me for missing batch IDs. Stop at a proposal.`
- **Relationship Analysis:** identify the directed source and target Attributes,
  FQNs, Environment, intended relationship kind, and any batch scope. Ask:
  `Use $analyze-gds-relationships to test
  gds_test.sales.orders.customer_id → gds_test.crm.customers.customer_id in TEST and
  prepare an analysis_result. Stop at a proposal.`
- **Assertions:** attach or identify accessible source material, the existing Model,
  extraction scope, and boundary. Ask: `Use $capture-modeling-assertions to extract
  grain, identifier, cardinality, history, and calculation rules from sections 2–5 of
  this requirements document. Preserve page/section locations; stop at a proposal.`

### Model design

- **Conceptual:** give the business domain/outcome, vocabulary or sources, evidence,
  owner, and boundary. Ask: `Use $build-conceptual-model for order fulfillment. Define
  concepts, instance grain, relationships, and support; stop at a proposal.`
- **Logical:** give approved vocabulary, expected normalization, identifiers,
  optionality/history decisions, sources, and boundary. Ask: `Use $build-logical-model
  to design the normalized Order domain for Model 41 from current Scope and Assertions.
  Preserve naming templates; create a local draft.`
- **Dimensional:** give one measurable process, intended Fact grain, consumers,
  measures, history/conformance decisions, evidence, and boundary. Ask:
  `Use $build-dimensional-model for order-line sales at one row per fulfilled line.
  Challenge grain and additivity; stop at a proposal.`
- **Mapping:** give physical source keys, modeled targets, transformation decisions,
  dependency order, and boundary. Ask: `Use $build-data-mapping to map the ERP order
  Objects to the existing Logical Order entities. Report unmapped fields; proposal only.`

### Planning and interviewing

- **Grill:** supply the current brief/documents and target layer. Ask:
  `Use $grill-data-model to stress-test this dimensional brief. Ask one question at a
  time, maximum seven, and finish with decisions, owners, and readiness.`
- **Goal:** use this only for genuinely multi-checkpoint work. Name one existing Model,
  bounded domain/process, ordered evidence/layer sequence, exclusions, owner,
  acceptance checks, and stopping boundary. Ask: `Use $run-data-modeling-goal to
  prepare—but not start—a goal for profiling, Assertions, and a validated Logical
  draft for Model 41. Nothing may be Applied.`

## Databricks SQL workflow

`execute_databricks_sql` expects three user-facing values:

1. `connection_id`: the active tenant-owned source Connection, not the Global Data
   Store Connection;
2. `environment_code`: the configured environment such as `TEST`; matching is
   case-insensitive, but preserving configured spelling is clearer; and
3. `sql`: 1–100,000 characters, at most 25 governed statements.

The server then validates SQL, derives the Principal, loads the source Connection,
derives its Tenant, authorizes Tenant Read, follows that Tenant to its configured
Global Data Store Connection, resolves the requested Environment's server-held
hostname/path/token, opens one Databricks SQL session, executes in order, and returns
at most 50 rows from the final statement. Credentials never return to the agent.

Persistent physical relations must be fully qualified as `catalog.schema.table`.
Identifier case should be preserved. SQL may read and may create unqualified temporary
views/tables in the same session. DML, persistent DDL, secret functions, and direct
PostgreSQL SQL are rejected. Submitted SQL is retained in the governed audit, so never
put credentials or sensitive literals in it.

`rows_truncated=true` means the answer is incomplete. `cells_truncated=true` means at
least one value is lossy. Aggregate or narrow the query instead of presenting either
as complete.

## Profiling workflow

1. Resolve one active registered Object, its physical Attributes, actual source
   Connection ID, and `batch_attribute_name`.
2. Confirm exact `catalog.schema.table` and Environment.
3. If a batch Attribute exists, choose `initial` with exactly one ID or `incremental`
   with the complete ID list. The batch Attribute itself is not profiled. Without a
   configured batch Attribute, use an unfiltered aggregate query.
4. Generate fixed aggregate SQL in chunks of at most 50 Attributes.
5. Execute each chunk through the governed tool and reject any truncation or invariant
   mismatch.
6. Produce complete ID-free `profiling_profile` records and stop at the requested
   boundary.

An empty incremental batch is an intentional no-op: no SQL and no zero-valued Profile
records. Profiling never returns sample values, top values, patterns, or raw rows.

## Relationship Analysis workflow

1. Resolve two different active scoped physical Attributes and their exact source and
   target relations.
2. Confirm direction, relationship kind, Environment, and independent batch scopes.
3. Compare declared types directly. A cross-type comparison requires an explicit
   accepted cast; values are never silently trimmed or case-folded.
4. Execute one aggregate statement that returns non-null/distinct counts, missing
   source keys, unused target keys, duplicate target rows, and a supported,
   inconclusive, or unsupported result.
5. Create one complete ID-free `analysis_result` with honest confidence and a basis
   describing population limits.

This proves selected-population value coverage and target uniqueness for one Attribute
pair. It does not prove business meaning, composite-key validity, temporal validity,
minimum participation, or a declared constraint.

## Documents to Modeling Assertions

Modeling Assertions are durable, source-located facts. They make document evidence
reusable by later modeling work without storing the entire source in the Model.

1. Identify a stable source title/version, type, safe location scheme, Tenant/System
   scope, and extraction coverage.
2. Read existing Assertion Documents/Records for the same source to preserve keys and
   avoid duplicates.
3. Extract atomic facts that affect definition, grain, identity, cardinality,
   optionality, history, calculations, mappings, ownership, quality, or scope.
4. Preserve conditions, exceptions, effective dates, and page/section/sheet/range
   locations. Paraphrase; quote only when exact wording controls meaning.
5. Create one `modeling_assertion_document` per stable source version and one
   `modeling_assertion_record` per fact. Keep conflicts as separate `needs_review`
   records.
6. Later, retrieve Documents first, then their Records; filter by layer, status,
   semantic subject, and source location. Cite assertion keys in model support.

This is RAG-like governed retrieval, not vector search. It is strongest when sources
have stable locations and assertions are atomic. It does not guarantee full-text or
semantic recall, so report extraction coverage and skipped sections.

Never store full documents, temporary URLs, sensitive local paths, credentials, raw
prompts, or raw physical rows in Assertion records.

## Model-building workflow

Conceptual, Logical, Dimensional, and Mapping skills share one authoring contract:

1. infer the requested read/proposal/local/server/Apply boundary;
2. resolve the existing Model and read only affected records/direct dependencies;
3. preserve current naming templates by default;
4. use physical Scope, Profiles, Analysis, Assertions, and accepted decisions as
   evidence without fabricating missing observations;
5. request the live schema only for datasets being authored;
6. create complete ID-free records and review canonical-key/reference effects; and
7. stop at the selected boundary.

Conceptual work defines business concepts and relationships. Logical work defines
normalized structure and identifiers. Dimensional work starts with one business
process and exact Fact grain before Dimensions/measures. Mapping connects physical
Objects/Attributes to existing Logical or Dimensional targets; it is different from
Source-to-Bronze/Silver/Gold ingestion metadata.

## Grill workflow

Use Grill only when an interview is wanted. It asks exactly one material question per
turn, defaults to seven questions, and stops early when the brief is ready. Give it
current documents or capture Assertions first so it does not ask what the sources
already answer. The result separates accepted decisions, source evidence,
recommendations, assumptions, unresolved owners, and the next skill/boundary.

The interview may update an authorized local decision log. It does not automatically
create governed Assertions, acquire a lock, run SQL, Stage, Validate, or Apply.

## Goal workflow

Use a goal when the work needs multiple evidence/design/validation checkpoints and a
durable stopping condition. Do not use it for a quick read, one SQL call, or a single
small proposal. A good goal specifies:

- one existing Tenant/Model and bounded domain/process;
- ordered evidence and model layers;
- source Objects/FQNs, Environments/batches, or documents;
- owner, exclusions, assumptions, and acceptance checks;
- proposal, local draft, validated draft, or applied model as the end state; and
- pause rules for decisions, access, another lock owner, external actions, and Apply.

“Prepare a goal” returns a paste-ready prompt and does not start it. “Start/run the
goal” may invoke the host goal mechanism. Apply remains a separate fresh approval even
inside an active goal.

## Local draft to server handoff

The Data Workbench reads immutable `GDS/metadata-snapshot` or `GDS/model-snapshot` and
writes only the matching local Change Set. Local checks are not server validation.

For Metadata, use `$manage-gds-metadata` and its platform helpers. For Model drafts,
use `$manage-gds-model` and `scripts/model-change-set.js` to validate the local draft,
bind it to the exact created/resumed server draft, reconcile every nonempty resumed
dataset, prepare a redacted Stage review, and record only confirmed Stage/Validate
revisions. This cross-platform helper requires Node.js; PowerShell users should run its
commands on one line or use PowerShell backticks for continuation. Then:

1. recheck the Model revision and Tenant Lock;
2. show the exact Stage review and obtain approval;
3. Stage complete affected dataset replacements;
4. Validate the future graph and repair one failed phase at a time;
5. show the authoritative server `action_review`; and
6. Apply only after fresh approval, then verify and release the lock.

Never replay an ambiguous non-idempotent result or overwrite unseen resumed work.

## Install in VS Code

Node.js is required for the packaged Profile/Relationship generators and Model handoff
helper. The browser Workbench itself does not require Node.js.

1. Extract the intended environment-specific ZIP.
2. Open VS Code Settings (JSON) and register the extracted `gds` directory:

   ```json
   {
     "chat.plugins.enabled": true,
     "chat.pluginLocations": {
       "/absolute/path/to/gds": true
     }
   }
   ```

3. Run `Developer: Reload Window`.
4. Run `Chat: Open Customizations` and confirm the GDS skills appear.
5. Run `MCP: List Servers`, start `gds-workbench`, and complete Entra browser sign-in
   if requested.
6. Invoke a skill naturally or with `/gds:<skill-name>`.

If the workspace also registers the same server in `.vscode/mcp.json`, disable that
entry while using the plugin. Duplicate registrations expose duplicate tool names.

## Package for the correct MCP environment

The endpoint in `mcp.json` is baked into each ZIP. It selects the GDS MCP deployment.
This is separate from the per-query Databricks `environment_code`.

The repository default targets TEST. To build a different package without modifying
source `mcp.json`:

```sh
python3 plugins/build_gds_plugin_zip.py \
  --output plugins/v1/dist/gds-agent-plugin-company.zip \
  --mcp-url https://company-host.example/mcp
```

The override requires HTTPS, an exact `/mcp` path, no credentials/query/fragment, and
an explicit new output path. The build is deterministic and changes only the archived
`gds/mcp.json`.

Before governed writes, open `https://company-host.example/health/ready`. Require HTTP
200, `status="ready"`, and a `tool_contract_sha256` equal to the value in packaged
`tool-contract.json`. A matching endpoint alone does not prove tool-schema parity.

## Packaged content

The plugin contains `plugin.json`, `mcp.json`, the 57-tool contract fingerprint, this
README, shared workflow/model references, all skill instructions/UI metadata,
deterministic Profile/Analysis SQL generators, Metadata/Model local-handoff helpers,
and the browser Data Workbench. It contains no token, client secret, password, or
authorization header.

## Safety and best practices

- Name the Tenant/Model, exact target, evidence, and stopping boundary.
- Prefer natural keys and exact registered physical identities over approximate names.
- Preserve configured identifier case, naming templates, and Environment spelling.
- Start with focused reads; use Snapshots only for genuinely broad context.
- Treat Profiles as observations, Analysis as tested relationship evidence,
  Assertions as sourced statements, and decisions/assumptions as separate things.
- Never infer credentials, connection values, database IDs, or unsupported record
  fields.
- Keep local draft, Stage approval, server validation, and Apply approval distinct.
- Never expose temporary URLs, raw prompts, raw physical rows, SQL containing secrets,
  or unredacted tool output.

## Smoke tests

Read-only connection test:

```text
Use $manage-gds-metadata to list the GDS Tenants I can access. Do not make changes.
```

Goal preparation test:

```text
Use $run-data-modeling-goal to prepare a goal for a validated Logical draft. Do not
start it and do not Apply anything.
```

Local utility test:

```text
Use $open-gds-metadata-workbench to open the GDS Data Workbench. Local files only.
```
