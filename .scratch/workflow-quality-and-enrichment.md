# Workflow quality and Metadata enrichment

User request: repair all authoring modes and review actions; simplify result
screens; add Model-scoped Metadata enrichment across web, notebooks, and plugin.
Implement and verify one cohesive change at a time. Preserve pre-existing dirty
worktree. No deployments, external writes, Databricks runs, migrations, or pushes.

## Verified so far

- Shared repair feedback limit incorrectly aborted large invalid candidates
  before configured retries. Fixed and focused regression checks passed.
- Analysis selected-result review buttons were deliberately disabled. Backend
  review endpoint implemented and verified (45 targeted tests including actual
  disposable PostgreSQL); frontend wiring DONE (12 focused tests, typecheck).
- Generic authoring validators reject unlocking locked records. Keep those
  protections; review operation must accept only explicit server-built status
  changes, preserving content and provenance.
- Provider JSON parsing rejected malformed output before candidate repair.
  FIXED: non-JSON text remains ephemeral and is repaired through schema feedback;
  40 targeted adapter/repair tests + Ruff/Pyright pass, both SDKs covered.
- Final authoritative validation lies outside repair; invalid draft rolls back.
- Assertion-layer validator-only reproduction is NOT a confirmed production
  cause: the real context loader already filters applicable Assertions.
- Production-reachable full-graph mismatch: retire bound Logical Entity, local
  candidate passes, authoritative validation rejects active_dependency_invalid.
  Need full applied snapshot + physical catalog precheck after materialization,
  policy projection and final detailed assembly; expose dependencies in context.
- Physical Attribute schema foundation DONE: required nullable
  attribute_inferred_data_type + required is_locked, database/snapshots/catalog/
  web metadata/selected authoring context SELECTs, Python/JS/PowerShell locks,
  SQL Apply lock barrier, readiness/install guards, updated synthetic fixtures.
  126 metadata/schema/Apply tests + 46 existing web/catalog DB tests pass.
  39 JS + 80 plugin Python tests pass; PS runtime missing (11 skips).
  Required fields intentionally reject old incomplete snapshots, avoiding silent
  erasure/unlocking. Physical data type stays unchanged.

## Remaining sequence

1. Wire Analysis review UI to completed backend endpoint.
2. Shared malformed-output repair; final authoritative repair and retained,
   inspectable schema-valid drafts on exhaustion; actionable bounded feedback.
3. Extend explicit review controls to supported result families and physical
   Attributes. Respect parent locks, Tenant Lock, authorization, revision,
   idempotency, audit, dependencies, and provenance.
4. Metadata schema foundation done; still propagate inferred type into Mapping,
   Code and Validation source contexts/digests and frontend detail type labels.
5. Metadata enrichment runtime: selected Model inputs, actual Metadata Change
   Set, durable run, source/bronze schema inspection, bounded sample inference,
   missing description authoring, safe fallback, review/apply.
6. Enrichment web launch/results, notebook, plugin Workflow Target and packaging.
7. Result screens: generated content first, compact profile comparisons, full
   details available, secondary provenance, useful error/empty states.
8. Full local regression/lint/types/build and artifact probes. Report live
   verification limits accurately; no claim that mocked agents prove quality.

## Enrichment decisions

- Metadata owns physical descriptions and inferred type; Model scope selects
  eligible inputs. Never put physical changes in a Model Change Set.
- Fill missing descriptions only; preserve locked Objects/Attributes and
  existing descriptions. Keep physical attribute_data_type unchanged.
- Prefer trustworthy actual source schema, use registered source metadata and
  Bronze schema as evidence, inspect a bounded sample when types are string or
  unreliable. Keep raw values ephemeral and out of logs/persisted evidence.
- Conservative inference: preserve leading-zero strings and mixed values;
  avoid unsupported certainty for empty/all-null samples or inaccessible data.
- Use existing runtime, connectors, Metadata Change Set service, and controls.
  Display inferred type separately so downstream authoring can reason about
  casts without confusing inferred semantics with physical storage.

## Assigned agents

- workflow_diagnosis: repair/prompt/context/authoritative validation diagnosis.
- lock_diagnosis: Analysis review backend and plugin physical locks completed;
  idle, needs followup_task. Broader review still pending. Found active graph
  parent/endpoint deactivation gaps (conceptual/logical) in general validator.
- results_ui_review: UI audit + schema fixture updates complete; idle, needs
  followup_task. UI detail changes not started.

## Implementation notes / next coordination

- Run only ONE cohesive production slice at a time. Agents can parallelize
  bounded parts of that SAME slice (e.g. root schema, agent fixtures, agent JS
  lock parity), while others do read-only research.
- Analysis review route: POST /api/v1/tenants/{tenant_id}/models/{model_id}/change-sets/review;
  Idempotency-Key; {dataset:'analysis_result',record_ids:[...max200],
  action:'lock'|'unlock'|'deactivate'|'reactivate',expected_model_revision}.
  Returns model_id,model_change_set_id,model_revision,action_count.
  Service builds exact rows, adjusts selected unlock bits in validation snapshot,
  normal validate_future_graph, accurate action summary vs ORIGINAL snapshot,
  direct lifecycle-only UPDATE preserving evidence/provenance, audited applied
  Model Change Set. Generic agent lock acceptance unchanged. Existing draft kept.
- Shared model.py now exposes load_model_physical_scope alias; use for fullgraph
  prechecks. model_validation.py exports build_model_action_review.
- Metadata Change Set web service ALREADY EXISTS at
  features/metadata_change_sets/service.py; reuse canonical fixed SQL + validators.
- Enrichment needs durable run integration, new Workflow enum/stage seed, actual
  Metadata Change Set link. Monitor currently hardcodes Model draft ids/status;
  expose real draft kind/id and run-scoped review/apply dispatcher or equivalent.
- Enrichment can use per-object / <=25 attribute batches with agent output only
  short descriptions + server-owned references. Backend carries forward full
  metadata rows and derives types via read-only source schema/bounded samples;
  no LLM authoring of physical key/lock/status fields.
- New AttributeRecord fields are REQUIRED. Fixture helpers now updated.
  Mapping DTOs/read contexts, Code/Validation SQL digest context still need edits.
- Runtime guards previously required absence of core.attribute.is_locked; both
  database/19_runtime_integrity.sql and 20_verify_install.sql now require it.
- Fresh-install SQL only. No populated-DB migration helper; no external changes.
- Docker socket needs exec_command require_escalated for fixture tests. Allowed
  scoped fixture commands have succeeded; use --tb=no --show-capture=no.
- Packaging ZIP rebuild deferred until source stable. Current pre-existing plugin
  version0.5.0 artifact, stage-runner0.1.0 VSIX. Do not lose pre-existing changes.
- Baselines: notebook132, Workbench44, frontend8 result suites51 passed before edits.

No real-data failure detail was available beyond "backend validation failed".
User confirmed every mode produces poor candidates. Use synthetic end-to-end
reproductions and distinguish verified bugs from hypotheses.

## Current checkpoint / next implementation

- Logical full-graph repair DONE: 83 focused tests,3 notebook checks, real
  disposable DB context→execute→validated draft→Apply with provenance pass;
  Ruff/Pyright clean. Root added6private-context regression cases;22context
  tests pass. Full original snapshot/catalog private; bounded dependencies.
- Active production slice: results_ui_review implementing restored Detailed
  Mapping stages/partitions/byte budgets/fake adapter dispatch and tests. Root
  updating prompt seed/shared output guidance and seed→runtime contract test.
- Next Mapping fix should RESTORE existing detailed stage identities, not simply
  rename fresh seeds: existing deployed/frozen plans contain header_mapper,
  attribute_mapper, target_validator. Runtime currently accepts only
  mapping_authoring. Use current simple transformation models for header,
  bounded attribute authoring/review, backend complete-candidate reconciliation.
  Avoid full-draft echo to review large outputs.
- All Mapping default prompts use obsolete package/header/batch/coverage fields.
  Actual current complete output: schema_version, object_mapping,
  attribute_mappings. Conceptual tool-assisted also incorrectly asks for
  excluded/blocked dispositions. Shared wording must explain backend-owned lock
  preservation, and regenerate when previous_candidate_omitted is true.
- Both adapters ALREADY append authoritative JSON-schema guidance. Strengthen
  once to resolve outdated format instructions/context echo; never rewrite
  frozen/custom prompt versions or digests.
- Remaining stage prompt audit (36 stages) found no other concrete shape mismatch.
- Mapping prompts/shared instruction fixes DONE. Updated5Mapping defaults,
  Conceptual tool dispositions, backend-owned locks, omitted-candidate regeneration.
  Keep defaultprompt length bounds. Existing global seed DB test passes. New
  tests/web_backend/test_database_mapping_stage_contract.py installs actualstage
  registry+defaults in disposableDB, readsFrozenStages+variables, executes all3
  modes through real Mapping executor+LocalFakeAgentAdapter;3tests pass, single
  complete2dataset handoff. Mockedhandoff here; real Logical DB Apply testedabove.
  Bothadapter+repair33tests pass; tinyrepair-summary budget now derives overhead
  plus450bytes, stillforces omission and checks exactsentbudget. No runtimebound
  increased. Ruff/Pyright rootchangesclean.
- Mapping readonly descriptions/definitions have2k DTO caps despite sourceTEXT
  allowingmore. Agent will removearbitraryreadonlycaps, keepoverallbytebounds;
  test3kmetadata case. Newgeneratedtransformationdocs reject{}; storedpreserved
  documentsremainunchanged.
- Remaining Logicaledgecase: auditpolicy addingattrs to ALREADY boundentity can
  fail bindingcoverage; agentcannoteditbindings. Correctlyblocked afterretries.
  Need retainedcandidate/actionablediagnostics, neverfalseNoOp/success.
- workflow_diagnosis nowread-only preparingfailed-draftrecoveryimplementation.
- Enrichment and physical review SQL inventory:
  .scratch/metadata-governance-inventory.md. Metadata drafts need physical
  baseline fencing because Model revision doesn't cover shared physical edits.
- Source inspection can reuse bounded ConnectorDatabricksSqlExecutor. Existing
  SQLGlot rejects DESCRIBE QUERY and DESCRIBE TABLE column syntax; ordinary
  information_schema.columns reads work and return full_data_type/comment.
  DESCRIBE TABLE fallback is bounded 50 rows; avoid assuming all columns fit.
  typeof(column) SELECT is parseable but empty-table result needs fallback.
  No live Databricks calls made.
- Enrichment correction: updateonlyselected physicalSource/BronzeObjects/Attrs.
  When a selectedBronzeAttribute maps to Source, readthatSourceas evidence;
  do not automaticallyenrich an unselectedSourceObject. Resolve through actual
  ingestionObject/Attribute mappings, not guessed samenames.

## Recovery checkpoint in progress

- Mapping restoration frozen: 23 candidate/executor tests, 17 notebook workflow
  tests on Python 3.12, Ruff/Pyright clean. Root seeded-runtime tests: 3 modes.
- Root failed-draft UI complete: failed active draft summary, bounded error
  groups/examples, explicit dataset read, one canonical generated record at a
  time; stale Model/draft revision/expiry guards. Apply remains unavailable.
- Web Model Change Set Get now uses existing bounded_validation_outcome, matching
  MCP behavior. No raw provider output retained or displayed.
- UI verified with actual local Vite/CUA at desktop and 390px, plus keyboard
  navigation. Fixed global table minimum width and improved readable text.
  Temporary preview files, server, and browser tab removed.
- Full frontend check passes: 195 tests, typecheck, production build. Existing
  large bundle warning remains. 9 Model Change Set API tests pass.
- workflow_diagnosis owns backend retained draft integration: shared handoff
  staging, active digest NULL, fresh real validation, atomic governed run failure;
  all seven canonical executor paths and Logical callback exhaustion.
- lock_diagnosis owns new disposable DB recovery regression suite (9 cases).
- Next checkpoint must finish these before starting another production slice.

## Next confirmed Mapping source defects

Read-only discovery while recovery tests finish:
- CONTEXT.md:197–221: Dimensional Model/Mapping uses eligible Silver with
  active Logical binding and applied Logical Mapping. `_MAPPING_SOURCE_CONTEXT_SQL`
  instead inner-joins Model Input Scope and filters only Source/Bronze for BOTH
  modeled types. Silver cannot be Model Input Scope; real Dimensional Mapping
  has no source records. Existing database preparation test only EXPLAINs queries.
- Mapping physical DTO `tenant_id` is connection placement Tenant; loader rejects
  sources/targets unless this equals owning Tenant. Shared GDS placement can be
  another Tenant. Add explicit Source Tenant identity and check it for ownership;
  keep placement/catalog values for physical qualification. Eligibility function
  already enforces Source Tenant ownership.
- Next slice after recovery gate: repair this source/ownership path, with actual
  disposable DB dimensional preparation and cross-Tenant placement regressions.
  Root owns Mapping production, lock_diagnosis owns tests after recoverytests.
  Do NOT propagate defective query into Code context.
- Then physical inferred-type propagation: root Mapping DTO/query/partition,
  lock agent Code/Validation context+digest, frontend agent scope/catalog labels.
  Frontend plan: ObjectAttribute required inferred nullable +lock; Storage type,
  Inferred type, Lock in drawer; metadata generic sheets already receive columns,
  change shared metadataFieldLabel only. Preserve full row flags in editor tests.

## Active source-path slice

- Recovery FROZEN/GREEN: 147 executor/shared repair/handoff/lifecycle tests,
  14 all-family retention success/failure tests, 9 actual DB retention tests,
  full frontend195/typecheck/build, Model API9, notebook17. Ruff/Pyright clean.
- Root now edits preparation_repository.py only: source_reference carries Model
  and modeled type; source query separates Logical Source/Bronze in Input Scope
  from Dimensional eligible Silver via active Logical binding and applied upstream
  Mapping/dependency for the selected source System. Fourth parameter remains
  Model ID (now canonical eligibility); seventh new parameter repeats source
  System. Tuple: (model,target,type,model,system,system,system).
- Target/source JSON includes source_tenant_id; target SQL checks actual owner,
  source SQL joins owning Model; loader checks source_tenant_id against requested
  Tenant instead of connection placement tenant_id. Placement IDs/catalog remain.
- workflow_diagnosis owns required source_tenant_id DTO, fixture updates and
  readiness source-zone guard (Logical Source/Bronze, Dimensional Silver).
- lock_diagnosis owns actual DB source/placement/ownership/ineligible regressions
  plus existing EXPLAIN test parameter update. Root SQL awaiting verification.
- Inferred-type propagation intentionally NOT included yet; it follows this gate.

## Downstream physical metadata propagation checkpoint

- Source-path slice complete: nine real DB cases plus prior-query reproduction.
- Root Mapping type propagation: required nullable attribute_inferred_data_type
  in physical DTO, target/source SQL and detailed source evidence; all three
  modes preserve storage type, inferred type and description. 52 focused tests,
  Ruff and explicit-interpreter Pyright pass.
- Frontend Object details show Storage type / Inferred type / Lock; shared
  catalog labels align. 40 focused tests and TypeScript pass; frozen.
- Shared SQL selector workflow.list_mapping_source_objects(model,target,type,system)
  now supplies Mapping and Code, retaining the fixed source/owner eligibility.
  Initial ten real DB/EXPLAIN checks pass; full Code metadata digest gate running.
- Next enrichment design simplified to direct atomic missing-only completion,
  as user requested physical fills and did not request another draft/Apply.
  Exact run owner/claim/revision/scope/baseline and Tenant Lock remain mandatory.
  Record safe counts/type-evidence methods and inspect actual enriched metadata;
  never persist sample rows. Metadata Change Set linkage is no longer planned
  unless a concrete existing contract requires it.

## Enrichment integration checkpoint (2026-09-05)

- Backend direct completion implemented and verified: fixed Source/Bronze scope,
  original-source linkage/schema evidence, conservative bounded sample inference,
  missing-only physical descriptions/types, parent/field locks, complete coverage,
  physical baseline drift, Source Tenant authorization, owned Tenant Lock, exact
  claim/revision, idempotent completion; no Model revision or raw sample retention.
- Read API returns paginated field outcomes plus whole-run status and three-field
  applied counts. Current labels are ownership-filtered; historical values stable.
- Integration found/fixed missing web start route and seeded resolver mismatch.
  Start now uses same governed lifecycle and fixed one_shot; seed-installed public
  create→service.start→claim→execute tests pass all four provider/lock scenarios.
- Notebook metadata_enrichment entry point uses shared runtime; fixed mode, 1–200
  Objects, no Batch, safe count output and direct physical update explanation.
  Notebook141 tests, Python3.12 Ruff/Pyright, three extracted artifact probes pass.
- Root web start/read/assembly19 tests, backend Ruff/full Pyright pass.
- Frontend and plugin final gates in progress. Do not confuse fake-provider or
  disposable database coverage with a live Databricks/customer-data run.
- NEW user scope: meaningful normalized prompt variables, explicit purpose/schema/
  source/usage, thoughtful default stage/loop prompts, actual rendered-prompt tests.
  Audit assigned; no broad prompt production changes made yet.
- Lifecycle audit reproduced inactive Conceptual Object with active Relationship,
  inactive Logical/Dimensional Entity with active Attributes/Relationships accepted
  by canonical validator. Binding checks alone do not protect these parent edges.
  Fix this before expanding Model review controls.

## Active model-layer dependency checkpoint

- FROZEN/GREEN: canonical65 tests, Logical27 tests, root broader154 tests plus
  22 actual DB Apply round trips and1 Analysis review round trip. New errors are
  delivered inside Logical repair; exact feedback expectation updated to include
  both active Attribute-parent and Binding dependency failures.
- Plugin parity:176 Python,45 Node,12 packaging;30 PowerShell runtime skips.
  ZIP0.5.0 rebuilt. Model-only historical existence fixed in PS declared refs;
  inactive historical child/parent records remain allowed.
- Enrichment SQL helper probe moved out of Windows plugin suite to backend
  test_plugin_metadata_enrichment_sql.py;44 fixture DB tests pass there.

## Active physical-history validation slice

- Pre-control audit found physical deactivation makes ALL retained Scope/Profile/
  Analysis/support/Binding history fail wholegraph validation (including inactive
  outputs). Profiling has no inactive flag, so output deactivation cannot repair it.
- Root changes model.py physical Scope loader: retain all owned Object/Attribute
  keys regardless their active flags. Connection/System/Tenant authorization and
  active flags remain unchanged; governed current eligibility sets remain active.
- review_and_prompt_audit owns canonical classification/validation: exact baseline
  or only lock/unlock/deactivation (including typed nested records) is history.
  No new inactive, reactivation, content or reference edit gets history privileges.
  Retained references still require actual ownership/existence, not just snapshot
  presence. Historical bound active Attribute targets preserve Binding coverage;
  future Dimensional augmentation cannot promote inactive Silver to new eligibility.
- enrichment_finish owns JS/PS parity and ZIP. Root new actual DB test in
  test_database_model_history_scope.py covers inactive Object vs Attribute,
  unchanged durable Profile, unrelated Model description/lifecycle edit, rejection
  of new metrics, and SourceTenant ownership transfer. Gate in progress.
- Physical web review API/controls NOT implemented yet. Agreed contract appended
  to .scratch/metadata-governance-inventory.md; UI plan exists in
  .scratch/results-and-review-ui-plan.md. Prompt overhaul remains required after
  its detailed read-only audit; do not lose latest user scope.

## NEW AI runtime and consumption steering (user confirmed)

- Only OpenAI Agents SDK and Microsoft Foundry for AI execution. Remove LangChain
  harness/dependencies and Databricks AI Model Serving integration/choices. Preserve
  Databricks SQL connector, source/schema/sample inspection, profiling and notebooks.
- Workflow UI/Notebook AI choices become model and reasoning effort; SDK/provider
  fixed internally. Existing execution-mode selection remains a workflow choice.
- Capture token consumption and Foundry model cost across ALL workflow runs, web
  app and notebooks (explicit user answer). Include all stages/turns/repair attempts.
  No Tenant aggregate request. No implementation made yet; sequence after current
  history gate, before normalized prompt rewrite so new prompts target one harness.
- Current adapter uses OpenAIChatCompletionsModel with Runner.run, tracing disabled.
  AgentExecutionResult currently only candidate/turn_count/tool_call_count, no usage.
  Must inspect installed SDK usage fields and official docs when implementing;
  cost must distinguish estimated/unpriced from actual billed totals, never guess.
- Registry currently contains foundry-primary (gpt-5.6-sol), foundry-gpt-5.6-luna,
  two Databricks models, bothSDK profiles. Avoid mutating existing published/frozen
  prompts or populated DB defaults; new-run fallback must handle deprecated stored
  SDK/provider/model defaults explicitly. Historical runs remain readable, with
  usage unavailable where never recorded; do not fabricate retroactive consumption.

## Snapshot history correction during root DB gate

- First actualDBtests exposed Snapshot data loss BEFORE validator: shared current
  PROFILING_SQL and ANALYSIS_SQL silently omit physical-inactive evidence. Root
  changed profiling_analysis.py into shared SELECT projections + current eligibility
  and ownership-only historical prefixes; public/current queries stayunchanged;
  model_snapshot uses HISTORICAL_* constants. RootDB2 tests now rerunning.
- review_and_prompt_audit owns same correction for Conceptual nested supports and
  Logical/Dimensional nested sources, which also silently filtered inactive physical
  evidence. Keep public current readqueries filtered; snapshots retain ownedhistory.
- Canonical historicalvalidator88 tests green; rootfull gate awaits snapshotfixes.
- workflow_diagnosis purecandidateechoaudit32 tests: exact unchanged applied evidence
  outside current selectedsubset is rejected by all4 Analysis/Conceptual/Logical/
  Dimensional candidatevalidators; in-scope echo normalizes to no changes. Omitting
  appliedrecords preserves them. Genuine newoutsideevidence/copyundernewowner rejects.
  Need narrow preservation fix or clearloopcontract follow-up; no productionyet.

## Physical history gate complete; Foundry-only cleanup active

- Canonical history/snapshot100tests+4ownedphysical Source/Silver DB cases green;
  rootProfile/Analysis/historyApplyresolver+MCProundtrip15DB green. Applyresolvers
  require ownedexistingphysicalkeys, leaving currenteligibility to fullvalidation.
- Additional all-at-once materialization gap discovered: firstDimensionalphysical
  sources precede LogicalBindings in ModelMaterializer.apply. Track for reliability.
- Backend SDKconfiguration/adapters57focused tests green; LangChain and Databricks
  Model Serving auth removed. OpenAI-only capabilityregistry and shareddefault
  resolver installed. ImplicitnewRun selection forwarded explicitly fromvalidated
  availablemodels; retireddefaults fallback onlyfornewruns; historicalDTOs unchanged.
- Rootcapability/commands/runtime/Mapping87tests+backendPyrightgreen. Root/backend
  uvlocks regenerated offline, removing24unusedtransitivepackages. DatabricksSDK
  retained for web identity and notebookSQL preflight.
- Notebook157tests+3extractedPython3.12probesgreen; model+effortonlywidgets,
  explicitredactedFoundry configoptionalfordeterministiccommands/replay.
- Frontend232tests/types/buildgreen;browsergatepending. Deploymentagent finishing
  canonicalFoundryapp.yaml,removeDatabricksartifactvariant and duplicateexample.
- Broadbackendrun1130pass/16fail/9errors; all31failingfiles passed in isolation.
  Fullsuiteorder reproduction running with sanitizedfilename/typeplugin;don't
  declarefullgateuntilresolved.
- Costresearch: https://learn.microsoft.com/en-us/azure/foundry/concepts/manage-costs
  says meters/deployment/contract vary; HTTP statusdoesn'testablishbillability.
  https://azure.microsoft.com/en-us/blog/gpt-5-6-now-available-in-microsoft-foundry/
  hasStandardGlobalshortcontext rates andSolpromoSep1-Nov30(2026). Deployment
  pricingbasisunknown; asyncquestionpending StandardGlobal/DataZone/provisioned.
  Do notguessregionalrates/longcontext/cachedwrite costs orcallestimates invoices.

## Durable usage checkpoint (continuing entire task)

- Foundry-only full backend gate resolved: module-isolated fixture containers
  prevent global worker queues stealing pending Runs from another test module.
  1155 backend tests passed; notebook157, frontend232, packaging25 and four
  Python3.12 extracted artifact probes passed before usage changes.
- Actual HTTP request receipts now survive tool calls, repair attempts, SDK HTTP
  retries, malformed candidates, and terminal failures. Persist before sending;
  capture numeric usage only. Missing data stays unknown. Persistence failure
  after a paid response blocks further calls without retrying that paid response.
- Root70 SDK/repair/dispatcher/assembly tests pass; frontend244 +types/build and
  desktop/narrow/keyboard checks pass. Read11 disposable DB tests pass; writer
  final DB and notebook157 gates being finished. Full Pyright initially found two
  test typing issues; root parameter naming corrected, writer correcting kwargs.
- User does not know pricing basis. Default cost must be unpriced, with optional
  administrator-configured rates and immutable per-request pricing snapshots.
  Next cohesive slice detailed in .scratch/foundry-cost-contract.md.
- Still required: physical review backend/UI; broader result review controls;
  unchanged outside-subset candidate history; full-graph repair for other
  families; materialization ordering; normalized prompt catalog/defaults/UI;
  remaining result design changes; comprehensive final checks/artifact rebuilds.
- Never treat mocked provider success as a live Foundry/customer data run. No
  external execution, deployment, push, or populated database changes performed.

## Cost checkpoint complete; physical review backend active

- Cost uses optional configured USD rates, immutable per-request schedule,
  actual request-time applicability and exact NUMERIC totals. No guessed price
  defaults; missing configuration/breakdowns/categories/window applicability
  remains unpriced. Web shared Run monitor/Profiling drawer and notebook
  completion/replay show identical durable estimates.
- Gates: 27 writer/governance DB, 28 read/API DB, root actual SDK→DB→failed Run
  cost/replay1, config74, frontend253/types/build/desktop/narrow/keyboard,
  notebook160/types, backend full sweep1250 plus one updated architecture
  contract pass (adapters may import only execution and numeric usage ports).
  Full backend Pyright0. Artifact rebuild remains final-source work.
- Physical review backend active: writer SQL14 helpers/audit/governed command,
  SQL19/20/readiness; reader catalog/Scope revision fields/queries/tests; root
  new metadata/review.py command/service/router and main/runtime wiring.
  Root32 API/service tests+types green. HTTP real DB2 gate initially blocked by
  in-progress install verification, safe P0001 only; rerun after writer says ready.
- New reliable reproduction of all-at-once materialization order is retained:
  .scratch/model-materializer-order-findings.md and reproduction2DBtests.
  Canonical-valid12dataset graph fails fk_dimensional_entity_source_binding;
  ordered Logical→Logicalbindings→Dimensional→Dimensionalbindings→Mapping works.
  Production fix belongs to next reliability slice; no weakening validation.

## Physical review complete; Apply ordering correction active

- Physical Object/Attribute lifecycle API, governed SQL, revision-bearing reads,
  and catalog UI complete. All four actions preserve content, parent locks,
  Source Tenant ownership, Tenant Lock, atomicity and idempotent retries.
- Full backend1311 and notebook160 passed; frontend287/types/build plus real
  desktop/390px/keyboard checks passed. No live external systems used.
- Materializer now applies each layer's bindings after its entities and before
  downstream consumers. Existing materializer7 tests, Ruff and MCP Pyright pass;
  permanent public MCP/web disposable database regression gate in progress.
- SDK37-stage audit confirmed unconstrained plain-text output and intentional
  flexible Mapping JSON. Next small transport fix uses JSON mode everywhere,
  retaining the backend schema/repair flow and accounting for format overhead.
  Avoid strict SDK prevalidation which would bypass current repair diagnostics.
- The actual web full-graph test found missing Input Scope and Binding draft
  columns in stage_documents. Both now persist with the canonical document set.
  Scope mutations belong to the separately governed Scope command (web has no
  direct Scope write privileges), so web Change Sets reject them at every stage
  and pending Validate/Apply boundary. Binding drafts remain supported. No new
  table write permission was granted. Public web binding Apply gate continues
  with existing Scope, while MCP also exercises its existing full graph path.

## Apply and JSON transport gates closed; exact history echo active

- Apply gate: new MCP3, web binding1, Analysis review1 disposable DB tests pass;
  existing full-model roundtrip and actual Logical/Dimensional Workflow Apply3
  pass. Web Input Scope rejects early through all staging/pending boundaries;
  accepted Binding documents survive Get/Validate/Apply. Root unit17 and types
  clean; no direct Scope privileges added.
- JSON mode complete:12 real SDK MockTransport cases,42 adapter/usage,57 shared
  repair/assembly,65 Python3.12 SDK/notebook cases,78 root byte-budget/native
  executor cases. Output schema remains in prompt and authoritative backend;
  fixed response_format overhead included in envelope budget. Ruff/types clean.
- Exact canonical echo fix landed in Analysis/Conceptual/Logical/Dimensional
  candidate modules. Root63 tests green: unchanged/locked/omitted history,
  mixed new selected output, edited/copied/nested/status evidence, duplicates,
  and forbidden agent locks. Broader candidate/executor gate in progress.
- Full graph repair audit distinguishes actionable generated failures from
  stale/unauthorized/preexisting graph problems. Conceptual active relationships
  referencing an authored inactive Object are a confirmed remaining case.
  Analysis has no equivalent agent-caused gap proven yet; do not add retries
  merely to mask stale state. Dimensional receipt-only reconciliation cannot
  repair Entity/Attribute definitions without native authoring rerun.

## History and Conceptual graph repair complete; review fence active

- Exact history echo gate closed:167 candidate/executor tests,94 Python3.12,
  root63 focused tests; Ruff/format/Pyright clean.
- Conceptual one-shot/tool-assisted validates the complete frozen graph inside
  repair. Detailed reruns native reconciliation pages with preserved prior
  stage evidence and exact coverage.14 new regressions include exhaustion,
  later malformed output and custom prompts omitting feedback placeholders.
  Last complete rejected changes survive for inspection; never applied invalid.
- Conceptual backend130,Python3.12/notebook53,root privatecontext22 all pass.
  Root real database5 includes two new context→repair→draft→Apply/retained-failure
  paths and existing Conceptual Apply/context checks. Repaired run is explicitly
  completed_with_repair, revision advances only at Apply. Full backend Pyright0.
- No baseline issue subtraction: candidate merges can change issue indices,
  so subtracting superficially matching errors could hide new failures.
- Existing Analysis review/start race reproduced both orders across two Models
  in one Tenant, plus direct Tenant Lock UPDATE denial. New narrow governed
  authorize_model_record_review function locks Model→Tenant exclusively before
  write authorization; root repository/service use it and reauthorize just
  before writes. Authorized replay remains before stale/running checks.
  SQL14/19/20/readiness and promoted concurrent DB gates in progress; no direct
  table privilege expansion or new result-family controls in this slice.
- Prompt census:37 stages,873 actual context renders against fresh installed
  defaults,111 tests pass. No missing variables today; the remaining task is
  meaningful typed inputs/help and thought-through prose, not placeholder repair.
  First Metadata catalog/projection tests prepared, no prompt production yet.

## Metadata named prompt inputs and shared reference UI complete — 2026-09-05

- Fixed typed catalog and registered-only projection now expose exact assigned
  description refs and discriminated Object/Attribute metadata requests. Strict
  bounds, nullable evidence, no samples/private snapshot, duplicate refs rejected;
  legacy values/templates preserve original identities and rendering.
- Both Prompt read paths expose schema, source, availability, delivery and context
  path. SQL04 registers two optional inputs (84 total), SQL05 default uses compact
  refs and reads structured evidence once; readiness and seed expectations updated.
- Both Prompt screens share a readable variable table with full synthetic examples,
  schemas and source/path help. Legacy help stays honest. Original-case placeholders
  preserved after browser review caught inherited header capitalization.
- Gates: backend input/Prompt/read/render44; installed seed→frozen plan→real
  enrichment runner→physical completion5; seed replay/default/readiness7;
  frontend289 tests/39 files, types/build. Browser desktop and390px horizontal
  table access plus native Enter/Space disclosure verified. Preview closed.
- Existing Analysis review Tenant fence final gate85 passed, including both
  workflow/review orders, cross-Model and physical review serialization, PostgreSQL
  Lock waits, expiry, replay and least-privilege/readiness checks.
- Next: family-specific Analysis/Conceptual prompt contracts, followed by remaining
  families. Dimensional repair and results screen plans remain pending.

## Analysis one-shot/tool prompt inputs complete — 2026-09-05

- Seven optional inputs separate Model identity/description, selected metadata,
  profiles, applied relationships, Assertions and tool dataset counts. Canonical
  wire schemas/examples, strict count consistency, private-state exclusion and
  legacy value identity retained. Catalog inventory now91; metadata slice intact.
- Defaults now explain the actual evidence paths, inferred versus storage types,
  evidence strength/uncertainty and fragment retrieval semantics without copying
  large evidence collections into prompt text. Existing1900-character instruction
  bound retained after tightening two instructions.
- Actual SQL-installed frozen stages now replace test prompts inside real
  Analysis/Conceptual executors: all13 stage identities across11 scenarios,
  including fragmented context, repair and Conceptual relationship refinement.
  Provider-boundary fingerprints prove the installed renders execute.
- Gates: new inputs + existing metadata/Analysis52; Python3.12 inputs/notebook
  execution59; installed executor scenarios11; full backend Pyright0. Seed
  replay/readiness inventory checked; final prompt-only seed gate1 passed.
- Next: detailed Analysis exact left/right assignment, then remaining stage inputs.

## Detailed Analysis finder assignment complete — 2026-09-05

- Exact validator left/right groups now included before evidence page sizing.
  Normalized sides contain one Object identity and their exact Attribute names;
  same-Object cross-chunk membership is explicit, including empty sides.
- Two optional named inputs expose slice_assignment and evidence_delivery with
  strict schemas, useful examples and complete-record versus fragment guidance.
  Default uses exact assignments and explains one-based fragment limitations.
  SQL/readiness inventory93. Existing legacy values keep their resolver meanings.
- Tests:34 focused Analysis inputs/assignment/executor;18 disposable seed,
  readiness and actual installed Analysis/Conceptual executor cases; full backend
  Pyright0 and owned Ruff clean. Both full and fragmented assignments are tested
  against the validator groups and8192-byte bound.

## Analysis remaining detailed prompt assignments complete — 2026-09-05

- Resolver now exposes assigned_candidate_refs and canonical endpoint_candidates;
  reconciliation/review each expose exact current-page proposed/applied references.
  They are fragment review refs, not global counts or original IDs. Six optional
  registrations added; reference/readiness inventory99. Defaults reference large
  evidence once through its actual structured path and explain decisions vs audit.
- Input projection rejects duplicate refs, wrong types/kinds, missing evidence and
  conflicting pre-resolved values. All6 documented examples validate. Canonical
  endpoint schema is loaded lazily because Analysis package initialization imports
  StageRunner; no copied candidate schema or relaxed validation was introduced.
- Gates:64 focused Analysis/Metadata/executor tests;18 disposable seed/readiness/
  true installed Analysis+Conceptual executor scenarios; Python3.12 inputs and
  notebook execution71; backend Ruff/Pyright clean. Metadata and all6 Analysis
  agent stage registrations now have useful named inputs.
- Added missing Validation option in the Prompt workflow filter (bounded UI fix).

## Conceptual one-shot/tool named inputs complete — 2026-09-05

- Eight optional inputs reuse canonical Model/metadata/profile/Assertion contracts,
  with explicit applied Analysis evidence and nullable applied Conceptual history.
  Tool manifests include Conceptual datasets; Model identity is checked against
  its actual workflow and documented with that workflow's exact schema constant.
  Common pure projection is shared with Analysis; old variables remain unchanged.
- Effective naming_instructions is now actually interpolated by both Conceptual
  defaults. Evidence paths stay structured, active retained endpoints are explicit,
  and unvalidated physical hypotheses cannot establish business cardinality.
- Gates:48 input regressions;18 disposable seed/readiness/installed executor
  scenarios; full backend Ruff/Pyright clean; Python3.12 input/notebook71.
  Reference/readiness variable inventory107. Prompt UI filter tests7 passed.
- Next: detailed Conceptual contribution and coverage inputs. Dimensional native
  full-graph repair, broader result lifecycle and result UI plans still pending.

## Conceptual contribution inputs complete — 2026-09-05

- Exact contribution/Object/global-evidence assignment and explicit complete versus
  fragmented delivery. Named inputs have strict schemas, source and availability.
  Default consumes effective naming policy and explains first-Object global evidence.
- Real complete/fragment constructors preserve context and byte limits; absent
  global fragments are not treated as evidence of absence.
- Gates:49 input tests;40 disposable database/installed-prompt/readiness checks;
  Ruff clean. Inventory109. Final broad gates still pending.

## Conceptual consolidation/detail assignments complete — 2026-09-05

- Three optional inputs expose exact proposal partitions and canonical entity refs.
  Full detail uses entity.contribution_refs, never every proposal inside shared
  contributions. Compact pages use only their scoped proposal refs.
- Canonical contribution property reused; real full/compact constructor checks
  include an unassigned sibling proposal. Defaults consume naming instructions,
  explain truncated summaries and distinguish business concepts from columns.
- Gates:4 focused Conceptual tests;40 disposable database/installed prompt checks;
  Ruff clean. Inventory112.

## Conceptual relationship/reconciliation inputs complete — 2026-09-05

- Six optional inputs: exact package/endpoints, native typed relationship signals,
  and four distinct required-coverage lists. Full/compact branches preserve their
  actual identities, including Unicode, spaces and applied fragment punctuation.
- Defaults consume naming policy, explain unvalidated signals and compact evidence,
  and distinguish outer reconciliation findings from inner stage repair feedback.
- Gates:51 input regressions;40 disposable database/installed workflow checks;
  Python3.12 input/notebook74; backend Pyright and Ruff clean. Inventory118.
- All seven Conceptual agent stage identities now have documented named inputs.
  Next: proven Dimensional projection/full-graph repair, then remaining prompt
  families and results/lifecycle UI. Broad final checks/artifacts still pending.

## Dimensional one-shot/tool whole-graph repair complete — 2026-09-05

- Gold projection now runs inside the shared bounded repair callback, followed by
  canonical complete-future-graph validation. Candidate-specific projection
  conflicts are typed separately from configuration/auth/finalization failures.
- Private physical catalog loaded for Dimensional. Existing Logical dependency
  projection shared as modeled_layer_dependencies; Dimensional receives its own
  read-only Binding/Mapping/Code identities without SQL/Mapping document bodies.
- Last projected rejected draft survives later malformed responses. A first
  unprojectable candidate can be retained as a rejected raw draft, never applied.
- 18 executor regressions cover both modes and inactive parents, retained Binding
  coverage after Type2 projection, long generated policy names, repair/exhaustion/
  later malformed output. Four prior native-schema witnesses now permanent.
- Gates:103 focused checks (one new scope-loader test then corrected and all22
  context tests passed);4 disposable shared context/handoff DB checks; Python3.12
  Dimensional/notebook63; full backend Pyright clean; Ruff clean.
- Detailed Dimensional still needs native topology/detail restart after fullgraph
  failure and fresh downstream receipts. No detailed-production retry change yet.

## Detailed Dimensional native repair complete — 2026-09-05

- One bounded outer counter now restarts topology reconciliation and Entity detail,
  rebuilding relationship ledgers, manifests, receipts and worker/lead packages.
  Physical contributions stay frozen; receipts never validate changed manifests.
- Complete projected future-graph validation runs before worker review. Typed
  Gold projection conflicts enter the same native retry. First-pass and retry
  contexts include actual frozen Gold policy; scoped read-only Binding records
  explain constraints. Feedback is capped at8192 bytes with count/digest/omission
  flags and is present during batch fitting, not added after byte checks.
- Per-run rejected-candidate state retains projected graph failures or worker
  blockers across malformed later stages. Exhaustion never applies the draft.
- Nine native graph regressions cover status, bound Type2 growth and long names
  with repair/exhaustion/malformed output; two additional worker-retention tests
  and a multibyte feedback-bound check. Corrected candidate changes its manifest.
- Gates:115 backend focused tests; Python3.12 Dimensional/notebook75; global seed1;
  actual SQL-installed defaults19 cases across21 Analysis/Conceptual/Dimensional
  stage identities (including native graph repair); full backend Pyright clean.
- Remaining: Logical/Dimensional/Mapping/Code/Validation named inputs/defaults,
  modeled result lifecycle + broad result UI cleanup, remaining family audits,
  final broad testing and rebuilt artifacts. No live Foundry/Databricks execution.

## Profiling results review complete — 2026-09-05

Nine-column comparison and one selected Attribute inspector preserve all recorded metrics/provenance. IDs disclosed after evidence. Full frontend check: 289 tests, types and build passed. Browser desktop and 390px: literal long names, internal table scroll (1029px), document width 390px, Enter/Space selection, Escape and focus restoration verified. No polling.

## Stored SQL results review complete — 2026-09-05

Stored SQL follows compact target/currentness, preceding support/provenance. Literal text and download preserved, Mapping support links added, currentness distinguished from execution. Twelve focused tests + types pass; desktop/390px browser hierarchy and internal scrolling verified.

## Analysis results review complete — 2026-09-05

Inference and recorded validation evidence separated, exact Connections displayed, state/lock preserved, counts compared without deriving result, policy digest disclosed. Four result variants + existing governance flows: 14 tests pass, types pass. Native browser Enter opens digest, 390px remains internally scrollable without outer overflow.

## Conceptual results review complete — 2026-09-05

Exact relationship endpoint names preserved. Support rationale, Assertion text, state/lock and source identity precede disclosed numeric IDs/workflow/timestamps; duplicate source names removed. Eight tests + types pass. Desktop/390px browser review and Space disclosure verified.

## Logical results review complete — 2026-09-05

Shared existing header now focuses all record types; type/nullability and keys grouped, source evidence precedes compact linked Submodel membership ledger. Repeated identities removed; source order and provenance preserved/disclosed. Four full journey tests + types pass. Desktop/390px Attribute review and native Enter source disclosure pass.

## Dimensional results review complete — 2026-09-05

Type/role, keys/grain and recorded aggregation/change behavior grouped; null fields honest, no not-applicable wall. Source evidence before compact Submodel ledger, exact identity once, native source provenance disclosure. Six journey tests and types pass; desktop/390px and Enter disclosure verified.

## Mapping results review complete — 2026-09-05

Source/target and template context consolidated, transformation first, parent Mapping linked, IDs/digest disclosed. Open JSON retains exact keys/type/array order/null/empty/absent distinctions and literal strings. Thirteen tests + types pass. Native Enter record details and desktop/390px nested document review pass.

## Results screens verification complete — 2026-09-05

All seven detail families reviewed and improved. Validation definitions/currentness separated from execution; assertion before SQL, Enter/Space/Escape/close restore focus, literal operands preserved, collapsing group clears selection. Browser caught and fixed grid min-width overflow (390px workspace/361px group, table scroll only; 1280px desktop no overflow). Full frontend: 302 tests /40 files, types and production build pass. Synthetic previews closed and Vite stopped. Modeled lifecycle controls and remaining prompt families are still pending.

## Logical one-shot/tool named inputs complete — 2026-09-05

Nine named inputs added (127 registry variables at checkpoint), reusing canonical source/Assertion/Analysis/Conceptual/Logical schemas. Tool manifests include actual Logical and read-only dependency datasets; source records vs retrieval fragments remain distinct. Defaults now consume naming, identity and dataset inputs, explain inferred types/audit policy and bound dependencies. 61 focused tests and 29 DB/readiness/actual-installed executor checks pass; Ruff and full backend Pyright clean. Actual installed execution now covers 22 synthetic executor scenarios across four families (29 registered stage identities loaded). No live Foundry or external execution.

## Logical topology-builder named inputs complete — 2026-09-05

Four inputs now describe the exact contribution, lossless source metadata, batch and bounded supporting evidence. Shared projection also runs inside the actual request-size probe. Corrected synthetic test construction and native reference example. Six dedicated tests pass (including wide custom-prompt partitioning); prior broad focused run 63 passed with only that test-fixture failure. Thirty SQL/default/executor checks and full backend Pyright pass. Registry now 131 variables. No live provider execution.

Logical topology reconciliation: lossless typed contributions, exact proposal refs, batch and applied-evidence delivery added. 35 focused Logical tests and 30 disposable SQL/installed-default tests pass; 135 registered variables.

Logical entity-detail inputs: canonical Entity assignment/topology, lossless source metadata/proposals and batch documented and projected. Registry 140. Installed executor gate now validates every named input/example against its schema and includes maximal Logical supporting evidence:31 tests pass. Two test-only JSON Schema type-stub warnings corrected with the existing typed-test boundary pattern; final type rerun pending.

Logical whole-model reconciliation: typed review assignment, canonical topology/details/signals, batch and applied-evidence delivery. 146 variables.31 installed/default/SQL tests plus two new real wide-model/partition-repair tests pass; full backend Pyright clean. Exact reference coverage survives merged-graph repair; no live provider.

Logical validation-worker inputs: lossless typed package, package identity and exact review refs. Default distinguishes omitted cross-package/policy evidence from demonstrated violations; whole-graph validation stays authoritative.149 variables.33 installed/SQL/executor tests and full backend types pass.

## All Logical named-input stages complete — 2026-09-05

Eight Logical stage identities now have typed inputs, examples, source/delivery/availability and exact assignment contracts. Lead receives lossless reviews and backend-derived package/finding/error assignments; its default matches the actual reference-list/repair-brief output schema (no nonexistent handoff field). New mixed warning/error tests preserve exact refs; all manifest/conflict denials remain safe.151 registry variables.37 focused Logical tests,34 installed SQL/default/executor tests (including wide models, graph partition repair and worker-error repair), Ruff and full backend Pyright pass. All previous frontend302 tests/types/build remain the last UI gate; no new UI changes in this slice. Remaining:15 named stage identities (Dimensional8,Mapping5,Code1,Validation1), modeled lifecycle controls, final broad gates and artifacts. No live provider/Databricks or external writes.

## Dimensional one-shot/tool inputs complete — 2026-09-05

Twelve typed inputs: eligible Silver metadata, current Model/manifest, profiles/Assertions/Analysis, applied Logical/Dimensional/Mapping history and complete Gold technical/audit policy. No Bronze-source alias. Dataset manifest now recognizes actual Dimensional and Mapping collections; backend still owns eligibility.163 registered variables.34 installed/SQL/executor checks pass.53 focused tests passed plus one fixture-only expected-dataset failure corrected (fixture has no Dimensional downstream Binding/Code); dedicated two tests now pass. Test-only JSON narrowing fixed; full type rerun running. No new direct byte-fit changes yet (only common stages registered). Read-only follow-up found detailed Dimensional intentionally drops Object/Attribute descriptions; next cohesive fix will retain bounded semantic descriptions with explicit truncation before documenting native-stage inputs.

## Dimensional descriptions now reach detailed authoring — 2026-09-05

Reproduced actual topology request losing Object/Attribute descriptions. Compact source evidence now retains the first512 characters plus explicit per-field truncation booleans; source keys/types/flags and full original record digests remain unchanged, transformation/custom-code bodies remain omitted. This restores enriched semantics with bounded size.55 focused Dimensional tests pass, including20,000-Attribute exact partitioning and untouched original evidence.27 actual installed executor cases pass. Initial default-template guard found1903 vs1900 characters; shortened repeated policy prose, then global seed guard passes. Final full type/artifact verification still pending. Native Dimensional input contracts must describe this compact source shape, not SelectedObjectContext losslessness.

## Dimensional topology inputs complete — 2026-09-05

Six native inputs expose exact contribution/batch, honestly typed compact Silver metadata, bounded support delivery and complete Gold technical/audit policy. Source schema reuses canonical field definitions while excluding omitted code bodies, constraining descriptions and documenting truncation; original canonical schemas remain unchanged. Registered projection also runs in native request-size probes.169 variables.56 focused tests and34 installed SQL/default/executor checks pass. Two typing issues corrected (test private-access marker and nullable dynamic annotation); dedicated three input tests pass, full backend Pyright clean. Remaining native Dimensional5 plus Mapping5/Code1/Validation1, modeled lifecycle, final broad checks/artifacts.

Dimensional topology reconciliation inputs complete: lossless proposal schema/exact refs, honest count/digest-only history summary, canonical typed read-only Object/Attribute Bindings, complete Gold policies.175 variables. Four dedicated input checks and34 installed/SQL/executor checks pass; full backend Pyright clean. Next concrete quality gap: native entity-detail context contains proposal source keys but no source type/description records; add scoped compact source metadata before documenting that stage.

## Dimensional entity detail now receives source evidence — 2026-09-05

Reproduced missing selected_objects/type/description evidence in native detail context. Backend now resolves only proposal-assigned physical keys against frozen selection, supplies compact metadata with recorded inferred types/descriptions, and fails safely if authoritative source records are missing. No out-of-partition Attribute leakage.58 focused checks +28 installed/default executor checks pass; additional legal wide Unicode topology-to-detail test passes without algorithm changes. Existing byte budgets accommodate this case; no speculative new splitter added. Four remaining Dimensional native stage catalogs still pending.

Dimensional entity-detail catalog complete: seven typed inputs for exact Entity/topology/proposals, scoped compact source metadata, Binding constraints and Gold policy. Source metadata now legitimately available and documented as a list, not a fabricated full context alias.182 registry variables.34 installed SQL/default/executor checks pass; full backend types clean. Static synthetic hash formatting corrected for Ruff. Remaining Dimensional3 native stages, Mapping5/Code1/Validation1, modeled lifecycle, broad gates/artifacts.

Dimensional reconciliation catalog complete: partition ref, whole-draft manifest, current ordered signal refs/records, typed bounded repair summary and Gold policy.189 variables. Caught and corrected wrong example field (AgentValidationIssue uses path) and duplicate prompt prose over1900 characters. Seven dedicated input/scope tests and34 installed SQL/default/executor tests pass; Ruff clean. Receipt test distinguishes global count from current partition and validates partial40-finding feedback without claiming success. Two Dimensional review catalogs remain.

## All Dimensional named inputs complete — 2026-09-05

Worker/lead expose lossless packages/reviews, exact backend-derived refs and complete Gold policy. Native package digests verified; long Dimensional refs preserved; cross-package omissions remain unknown. Lead output now matches actual reference lists and nullable repair_brief.198 registry variables.20 dedicated Logical/Dimensional input tests,34 installed SQL/default/executor checks and full backend Pyright pass; Ruff clean. Remaining Mapping5/Code1/Validation1 catalogs, modeled lifecycle and final broad gates/artifacts.

## Mapping named inputs complete — 2026-09-05

All five stages now expose typed pair/route/operation, actual target/source metadata, existing transformations, policy, readiness, template/dependency guidance; tool mode has its own real dataset schema and fragment semantics. Detailed inputs retain all source columns but mark target/transform partition scope; target review receives only its candidate. Native request-byte probes use the shared projection.252 registry variables.18 focused executor/common-input tests passed; three new fixture-only source-count assumptions corrected, all7 input tests now pass.36 installed SQL/executor tests passed with only lean-prompt bound failure corrected; separate final seed gate passes. Full backend Pyright clean. Remaining Code/Validation common catalogs, modeled lifecycle and broad final gates/artifacts.

## Code prompt contract correction — 2026-09-05

Six normalized Code inputs use the actual SQL source-context projection, shared for upcoming Validation schemas. Tested on disposable Logical/Dimensional SQL projections. Registered common/NULL mode remains distinct from internal detailed execution.258 variables. Installed executor with real repository-built SQL evidence exposed a concrete default mismatch: artifacts require artifact_name, artifact_role and source_system_codes as well as target_ref/generated_sql, and multiple target/support files are supported. Earlier one-file assumption was wrong; its context edit was reverted. Updated default/variable/output-schema description to exact source-System coverage across artifacts, preserving multi-artifact behavior. Installed test provider now returns explicit fields without the old test helper filling them. Both direct and malformed-ref repair cases pass. Code seed length1954 corrected by removing duplicate System-coverage prose; final seed rerun pending. Ruff clean; full type run in progress. Remaining Validation catalog, modeled lifecycle, final broad gates/artifacts.

## All workflow stage input catalogs complete — 2026-09-05

264 registered variables. Validation has exact System scope/ref, typed shared SQL Mapping evidence, optional current Code, applied groups and checks; full-ledger replacement is explicit. Common registration works with internal detailed execution.40 installed registry/executor/readiness checks pass (34 executor cases across36 registered stages) and full backend types clean. Final lean-prompt gate now passes after removing duplicate Validation prose; SQL scalar cardinality/operator/qualification rules preserved. Code seed test now requires artifact_name/role/System codes too. Remaining: modeled lifecycle controls, concrete aggregate/full-graph audits, final broad verification and artifact rebuilds. No live Foundry/customer-data/Databricks runs.

## Shared lifecycle identity read groundwork — 2026-09-05

Added read_model_review_snapshot returning the unchanged canonical snapshot plus a private records_by_id index for20 lifecycle datasets; build_model_snapshot remains the compatible wrapper. Reuses existing owned/history-preserving SQL rather than duplicating20 identity queries. Analysis query lacked its own result ID; added it (already stripped from canonical/MCP output by existing internal-field logic).44 disposable snapshot/history/review/governance tests pass; MCP Pyright clean. All other result lifecycle work still pending; no new endpoint/UI enabled yet. Next cohesive slice should extend Analysis review to Conceptual with explicit dependency preview/digest, preserving field-only writes and existing Model-then-Tenant exclusive fence. Reuse index for later Logical/Dimensional/Binding/Mapping/Code/Validation. Code/Validation still need real lock fields before enabling lock actions.

## Conceptual lifecycle complete — 2026-09-05

Backend now previews/applies exact Object/Relationship lifecycle changes using shared owned numeric identity reads, existing Model/Tenant write fences, canonical full-graph validation, opaque plan digests and idempotent field-only writes. Object retirement includes active incident Relationships; Relationship reactivation includes only inactive endpoints. Additional changes require explicit plan confirmation; locked dependencies block status changes, never implicit unlock. Paged 205-Relationship round trip, all four actions, content/provenance preservation, replay and cross-Model denial pass.43 focused/governance DB and pure tests plus backend types pass.

Web Conceptual ledgers now select exact IDs and share a review dialog with complete selected/dependency counts, paged rows, blocked reasons, explicit Apply and exact uncertain-request retry. Selection clears on view/filter changes.312 frontend tests/types/build pass. Browser desktop1280x900 and390x844 checks passed after overriding a shared table width rule; focus wrap/Escape/restore verified. Synthetic preview only; local Vite stopped/browser tab closed. New shared frontend `features/model_record_review/` is ready for subsequent result families; no other lifecycle families enabled yet.

## Scope change: remove detailed coverage entirely — 2026-09-05

User explicitly removed detailed coverage from every layer: backend runtime/native planners/workers, stage registry/defaults/variables, database constraints, web, notebook, plugin/artifacts/tests/docs. Only one_shot and tool_assisted remain. Preserve and improve their normalized inputs and shared repair. Also provide discoverable configurable tool-assisted tool catalog/settings under backend validation; never let prompt text enable arbitrary tools. This supersedes prior detailed-mode development and tests; remove those implementations instead of maintaining compatibility execution. Existing assigned/frozen historical data must not be destructively migrated. This cleanup now follows current lock-schema slice before further modeled lifecycle work.

## Code/Validation lock schema foundation — 2026-09-05

Fresh SQL10 adds generated_code_is_locked, generated_code_source_system_is_locked and Validation Group/Check is_locked (all non-null defaultfalse). Required canonical bool fields, complete snapshots, materializer insert/update values, authoring construction/defaultfalse, applied context SQL/parsing, read DTOs/API fields, runtime/install checks and static examples updated. ValidationGeneratedCodeArtifact inherits GeneratedCodeRecord, so its SQL evidence and examples also require the lock flag. Physical Code/Validation currentness digests intentionally ignore these review flags.

163 focused Python tests pass;16 snapshot/schema tests pass.43 disposable SQL/snapshot/installed-executor tests passed plus one synthetic Validation Code fixture missingnewflag; corrected, both installedValidationcases now pass. New actual SQL test verifies all4 trueflags survive materialization/snapshot and canonical validators reject statuschanges/unlock from ordinary authoring.31 Workbench JS tests pass including4 real-lock checks. Backend types passed before latestnewtest; frontend type correction carries flag through detail-to-target projection. Final broaderchecks/artifacts pending. No Code/Validation lockUI enabled yet; workflow reconciliation still needs preserve/repair againstlockedappliedrecords before claiming fullquality.

Formatting note: a too-broad Ruff format invocation reformatted92 backend/test files and51 MCP/test files already in this large dirtytree. No semantic changes intended by those format passes; do not reset/overwrite pre-existing work. Use explicit touched-file lists going forward.

## Detailed coverage removal and Prompt tools complete — 2026-09-05 continuation

All detailed-mode source modules, native runtime paths/fake providers, stage definitions,
mode unions, SQL constraints, default prompts/variables, web/notebook choices, docs and
tests removed. No remaining native mode/stage names in production source. Stage inventory
is now25 (13agentic), variable inventory106. Code/Validation fixed internal profile uses
one_shot. Retained one-shot default request ceiling512KiB permits the legal256KiB SQL
guide plus Mapping evidence; request size remains bounded. Full Python regression after
cleanup/tool foundation:2553passed,44skipped,2stale expectedcounts/bounds; both corrected
and272focused/packaging tests pass. Frontend312tests/types/build, notebooks159 on3.12,
Workbench51 and extension70 tests passed. MCP/backend/notebook Ruff/Pyright were clean
before latest Mapping graph work (verifyagain). Three extracted notebook probes pass.
No live external runs/deployment or Windows PowerShell execution.

Prompt versions now have nullable agent_tool_names TEXT[]; NULL means registered defaults,
explicit selection must include family dataset tool and can omit manifest. SQL guard
rejects duplicates/unknown/cross-family/one-shot settings, includes policy in contentdigest
and immutable published comparisons; governed save_draft gets optional10thTEXT[] argument.
Fresh install/grants/readiness/verification/function inventories updated. Plan freezes names,
shared StageRunner filters actual catalog discovery and invocation before rendering/repair.
Backend registered_tool_definitions is reused by both catalogs and Prompt detail API.
New available_tools variable resolves exact filtered names/descriptions/input schemas and
runtime page bounds; no prompt text can grant tools. SQL04/05register5variables/defaults.
Editor checkboxes save/copy tool permissions with version; backend tool inventory displayed.
Synthetic browser verified save, keyboard Space, narrow390x844 no horizontal overflow.
Vite81158 stopped; browser3 closed. 55installed/foundation tests initially1staletestfixture;
fullsuite confirmsfixed. Tests added for SQLdigest/replay/immutability/stagerestriction,
StageRunnerdisabledinvocation, precisevariables, frozenplanconsistency, editorpersistence.
Temporaryscripts /tmp/gds_*tool*.py alreadyapplied; DONOTRERUN.

Code/Validation reconciliation now never overwrites/reactivates/retires locked applied
records. Four reproduced failures fixed;27focused candidate/executor tests pass. Lock
fields were previously false on regenerated candidates and caused final validation failures.
This does not yet add lifecycle controls for those families.

Artifacts rebuilt once: plugin0.5.0ZIP, stage-runner0.1.0VSIX/bundle, MCP0.2.0ZIP,
artifacts/databricks-ui app/notebook ZIPs. LATEST Mapping/JS/domain edits after rebuild
mean MCP/plugin/notebook/app archives need one final rebuild. Builders refuse existing
archives: build --output into TemporaryDirectory then Path.replace(target) (local artifacts).
Deployment builder --replace permitted only for its marked directory.

## Mapping whole-model repair and stale Code blocker — latest active checkpoint

MappingPreparation now holds private excluded/reprFalse optional snapshot/physical_scope.
Production MappingReadinessService loads both inside its existing authorized repeatable
transaction using ModelReadContext from exact frozenplan+context. Mapping executor refuses
missing graph before provider, calls full validate_future_graph inside StageRunner repair,
keeps last complete rejectedchanges/issues even if latercandidate malformed, and uses
existing governed rejected-draft retention afterexhaustion. Unit fixtures now build real
canonical graphs/bindings/physicalcatalog through mapping_validation_preparation helper.
27Mapping tests +44installed/default/DB/notebookworkflow tests pass; latest addeddataset-only
Mapping test running/justcompleted session72756; logs types /tmp/gds_mapping_graph_types.txt.
Earlier2Pyright fixtureannotations fixed(source_attribute dict and typedattributes list).

Found actual upstream blocker: adding newMappingSystem failedbecauseoldCode lackedassignment.
Python model_validation._validate_active_dependencies now gets code_authoring_entities from
stagedCode/assignmentrecords. Missingcoverage acceptedforunchangedCode (currentnessdigest
marksstale); newlystagedCode/assignmentsmustcovereverymappedSystem. Duplicateassignments
anddanglingreferencesalwaysinvalid. JSworkbench equivalentderivesauthoringentities from
pendingrecords. Pythonregressionfirstfailedatthisexactdependency;now116domain/Mappingtests
pass. JSnewteststale/newCode/duplicatespasses(32Workbenchtests). CONTEXT.mdexplainsrule.
Needcheckfurtherimplication: futureCode lifecyclelock-onlyreviewshouldnotunintentionally
requirefullSystemcoverageofstaleCode; explicitreviewvalidationmayneedhandlelock-onlychanges
whenextendingCodeUI. Do NOT relax generic Code authoring coverage. No newSQLmigration.

REMAINING EARLIERUSERWORK: Logical/Dimensional/Submodel/Attribute/Relationship/Binding/
Mapping/Code/Validation governed lifecyclebackend+UI (onlyPhysical,Analysis,Conceptualdone).
Code/Validation full-modelcallbackbeforefinalization stillpending; Mappingnowdone.
Finalbroadsuite/types/lint/format/bundles/probesafterallsourcechanges. Costsunknownpricing
remainunpricedhonestly. Do notclaimentireworkcomplete orlivecustomer/Foundrysuccess.


## Completed implementation and final local verification — 2026-09-05

This completion checkpoint supersedes the pending items in earlier checkpoints.

Completed the full requested scope:
- Removed Detailed Coverage from production frontend, backend, workflow stages,
  prompts, variable registrations, SQL install contracts, notebooks, plugin,
  extension, documentation, and rebuilt artifacts. Only One-shot and Tool-assisted
  remain. Historical scratch notes are not shipped.
- Prompt versions now configure the registered tools permitted for Tool-assisted
  execution. Typed variable documentation and the available_tools variable expose
  exact names, descriptions, schemas, and limits. The backend freezes and enforces
  the tool selection; prompt text cannot grant additional permissions.
- Added Model-scoped enrichment of shared physical Object/Attribute descriptions
  and inferred source types. Existing descriptions and locked records remain
  protected. Source/registered/Bronze/sample evidence drives conservative type
  inference; downstream modeling and generation receive the inferred types.
- Retained only OpenAI Agents SDK and Microsoft Foundry for model execution.
  Recorded token usage for all workflow runs, including retries, tool rounds,
  repairs, failed attempts, and notebook runs. Costs use configured deployment
  rates; unknown pricing remains explicitly unpriced.
- Completed bounded candidate repair and full-Model graph validation inside
  Logical, Dimensional, Conceptual, Mapping, Code, and Validation authoring.
  Code and Validation retain the last complete canonical rejected draft after
  repair exhaustion, including when a later response is malformed. Final apply
  remains governed and validated; invalid output is never silently accepted.
- Completed lock/unlock/deactivate/reactivate for all 19 modeled review datasets,
  in addition to existing Physical and Analysis controls. Dependency closure,
  locked-row protection, tenant ownership, revision fencing, exact retries,
  idempotency, audit, and original content preservation are enforced server-side.
  Historical inactive Code and Dimensional Submodels are reachable through the
  owned-history endpoint and UI. Hidden locked dependencies offer an explicit
  separate unlock review, never an implicit unlock.
- Improved result details and lifecycle selection across the web app. Corrected
  medium-width toolbar overlap, oversized checkbox columns, and filter overflow.
  Shared command bars wrap; filters respond to the space left by navigation rails.

Final verification:
- MCP/backend/disposable PostgreSQL/packaging/plugin Python: 2,607 passed,
  44 PowerShell-only cases skipped on macOS (190 seconds).
- Notebook suite on Python 3.12: 159 passed.
- Frontend: 326 passed in 41 files; TypeScript and production build passed again
  after the final visual fixes.
- Plugin Workbench JavaScript: 52 passed.
- VS Code extension: 70 passed; compile and VSIX build passed.
- MCP/backend/notebook Ruff and Pyright: clean; source formatting clean.
- Rebuilt final app/notebook artifacts, then packaging tests: 61 passed;
  all three extracted notebook Python 3.12 probes passed.
- git diff --check clean. Production scans found no retired coverage modes or
  retired agent-provider implementation references. Rejection tests intentionally
  still name retired SDK/provider values to verify they cannot execute.
- Synthetic browser inspection at 1440x900, 1000x850, and 390x844: readable
  desktop/medium/mobile layouts; no narrow-page overflow; explicit dependent
  Binding unlock applied; Model revision refreshed; selection cleared; blocked
  deactivation became reviewable; keyboard focus trap, Escape, and focus return
  verified. Table contents remain horizontally scrollable without losing values.
  Browser viewport restored, temporary tab closed, preview server stopped.

Rebuilt local deliverables:
- plugins/v2/dist/gds-agent-plugin-0.5.0.zip
- plugins/v2/dist/gds-stage-runner-0.1.0.vsix and generated extension bundle
- mcp_server/dist/gds-mcp-appservice-0.2.0.zip
- artifacts/databricks-ui/gds-workbench-app-source.zip
- artifacts/databricks-ui/gds-workbench-notebooks.zip

Verification limits: no live customer-data, Foundry, or Databricks execution;
no deployment, external writes, populated-database migration, push, or PR.
Windows PowerShell 5.1 execution remains a Windows CI check. Provider outages and
unrecoverable model responses can still fail a run; local checks do not establish
an unconditional output-quality guarantee. Known safe rejected candidates are
retained for inspection rather than bypassing validation. Accurate monetary
estimates require deployment-specific rates, which the user does not yet know.


## Additional plugin and extension quality review — 2026-09-05

Reviewed Metadata/Enrichment, Profiling/Analysis, Conceptual, Logical, Dimensional,
Mapping, Code, Validation, and the deterministic Stage Runner independently.
The plugin owns authoring; the extension preserves and transports accepted
records. Neither path can establish real-data model quality from mock output.

Changes:
- Added shared evidence/type guidance: consume inferred source types while
  preserving storage types, identifiers, precision, and date/time semantics.
- Mapping now requires conversion/null/default/invalid-value decisions and
  explicit handling of joins and deduplication. Code implements those decisions,
  projects explicit bound columns, aligns System branch types, and covers each
  active Mapping System with one artifact assignment. Updated the SQL example
  to remove SELECT * from its final multi-System projection.
- Validation expected results must come independently from Mapping and confirmed
  rules. Guidance addresses failed conversions, join multiplication, scope
  alignment, lost keys, precision, empty input, and nulls.
- Fixed a reproduced Stage Runner failure: a rejected connection-close Promise
  in finally could override an already produced Stage receipt or readiness
  result. Cleanup now preserves that result; three regression tests failed
  before the fix and passed afterward. Cleanup exception details stay private.
- Added a complete nonempty Model integration test using server-exported Metadata
  and Model Snapshots. It authors all 25 Model datasets locally, compares graph
  validity with the Python backend, rejects a broken Binding/Mapping dependency,
  repairs it, accepts the exact digest, and verifies every Stage payload/hash
  without losing nested content, SQL, or optional fields.

Verification: plugin Python 192 passed / 44 Windows PowerShell skips; Workbench
JavaScript 52 passed; extension 73 passed; extension TypeScript and VSIX build
passed; new Python test Ruff/format and git diff --check clean. Rebuilt the
plugin ZIP and VSIX. Verified the final unpacked VSIX in installed VS Code
1.136.1 using a fresh isolated profile: activation, command/tool registration,
and JSON receipt API passed. No sign-in, deployed-server Stage, live model
calls, Databricks execution, or customer data were used. PowerShell 5.1 remains
covered by the existing Windows CI job. Live generation quality remains an
explicit verification limit, not an unconditional success claim.

## Shared Silver/Gold registration and Binding (2026-09-06)

- Added a shared Targets screen and entry links from Logical and Dimensional.
  Logical exports Silver Objects/Attributes; Dimensional exports Gold. Both use
  the existing Metadata XLSX manifest, importer, validation, and Apply.
- Export derives placement from the owning Tenant's active GDS Connection.
  Preserves descriptions, declared storage types, nullable/key/audit flags,
  masking, and unique ordinals. Duplicate modeled positions receive stable
  sequential target positions without changing the applied model.
- Registered target discovery is limited to the selected zone, owning Tenant,
  and its GDS Connection. Binding previews resolve exact-name suggestions and
  accept explicit numeric Attribute assignments, then validate completeness,
  types, keys, nullability, audit flags, masking, and the complete graph.
- Apply creates an isolated Model Change Set transaction, preserves locks and
  existing active Bindings, fences Model revision and metadata preview digest,
  excludes running Tenant workflows, audits the action, and replays uncertain
  submissions with the same idempotency key. Existing human lifecycle review is
  available for Object and Attribute Bindings across both layers.
- Attribute review is paginated; only the focused Attribute selector renders
  all target options. Export dialogs preserve keyboard focus and trap Tab.
- Rebuilt app/notebook source ZIPs. Kept web export/router modules out of the
  notebook artifact while retaining Binding contracts/preparation used by the
  shared Model Change Set service. No database schema changes or deployments.
- Usage guide: docs/model-target-registration.md.

Verification: full MCP/backend/packaging/plugin Python suite 2,627 passed,
44 existing Windows PowerShell skips. Final target-focused tests 19 passed,
including two additional locked-Binding preservation cases. Database integration
exercises both XLSX exports through real Metadata import/validation/Apply and
both Binding transactions with revision checks and idempotent replay. Frontend
333 tests, types and production build passed; notebooks 159; three extracted
Python 3.12 artifact probes; Workbench JavaScript 52; extension 73, types and
bundle. Ruff, backend Pyright, formatting and diff whitespace checks passed.
Desktop and narrow screenshots inspected with synthetic data. Browser automation
later timed out; full interactive browser acceptance was not completed. No live
Foundry requests, Databricks execution, customer data, or deployed app validation.
