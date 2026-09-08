# Metadata workflow governance inventory

Read-only design inventory, 2026-09-05. No implementation implied.

## Enrichment Workflow Run

- Register `metadata_enrichment` in workflow checks in database/04, /12 and
  /13; start with one `one_shot` agent stage. Update Model Input eligibility in
  `application.create_workflow_run`, notebook exact claim allowlists, stage,
  variable and prompt seeds. Preserve existing Architect role, owned Tenant
  Lock, actor, Model revision, immutable selected scope and exact claim.
- Extend `mcp.metadata_change_set` with nullable immutable unique
  `workflow_run_id`, a Tenant witness FK and selected physical baseline digest.
  Derive Model and base revision from the immutable Run. Ordinary create/resume
  and `uq_metadata_change_set_ongoing_owner` must exclude workflow-linked drafts;
  otherwise a run resumes/collides with unrelated manual work.
- Existing Metadata `candidate_digest` hashes staged documents only. It does
  not detect changed physical baseline. Existing Model CS source digest is
  generated from Model/revision, also insufficient. Capture selected physical
  content through a DB-generated digest before inference and check at handoff
  and Apply. No raw physical rows or digest input in logs.
- Extend existing Metadata service with one atomic workflow handoff, reusing
  canonical `_stage_documents`, snapshot loading and `validate_metadata_documents`.
  A fixed governed SQL boundary checks identity, owned Tenant Lock, role, exact
  claim, Run owner/type/state, Model revision, scope and physical baseline.
  Accept only changed complete source/bronze Object/Attribute records; reject
  identities, status, locks, unrelated-column edits and out-of-scope rows.
- Handoff creates/validates one linked draft, records ordinary Metadata audit,
  appends bounded Run event and completes Run in one transaction. Same candidate
  replays; different candidate conflicts. Empty output can be a validated
  zero-action draft. Extend `fail_workflow_run` durable-outcome guard to Metadata.
- Generic Metadata stage/chunk mutation must reject workflow-linked drafts.
  Agent review must not acquire a generic path to bypass immutable run output.
- Reuse profiling relation/credential lookup for available evidence; load
  canonical Metadata separately. Current profiling SQL requires every selected
  source foreign-catalog/bronze relation and Attribute plus complete credentials;
  unchanged reuse would prevent metadata-only fallback.
- Register executor in execution/contracts.py, dispatcher.py, assembly.py and
  ordinary command/read contracts. Existing worker and notebook claim machinery
  remains the transport; assert claim before execution writes and finalization.
- Extend current workflow draft Apply with Metadata branch, retaining expected
  Model revision, draft revision, candidate digest and explicit review. Recheck
  completed Run owner, scope, baseline and locks, then governed Metadata Apply.
  Physical core.object/core.attribute change; no Model artifact materialization.
- `gds_web_write` has no direct SELECT/INSERT/UPDATE on Metadata Change Set tables.
  Run detail needs a bounded governed read-by-run summary function, not a new
  direct table JOIN/grant. Existing get_metadata_change_set reads owned documents.
- Notebook workflow_control.py already creates/claims durably; execution result
  and drafts.py need Metadata fields/branch. In-process transactions activate
  the same gds_web_write role; no new notebook transport or broader grants.

Verification sequence: registration/create/claim; atomic handoff/manual-draft
isolation; explicit review/Apply; notebook parity. Disposable PostgreSQL tests:
wrong actor/Tenant, missing lock, stale Model/scope/physical baseline, reclaimed
claim, locked values, generic mutation denial, matching/divergent replay,
unchanged physical fields and shared Metadata visibility across Models.

## Explicit physical lifecycle review

Read-only proposal. Existing Metadata Apply cannot unlock a locked row: both
canonical validation and SQL correctly reject it, and Apply writes complete rows.
Do not weaken either barrier or route physical rows through Model Change Sets.

- Smallest boundary: one fixed `application.review_metadata_records` SECURITY
  DEFINER function exposed only through existing web Metadata service/router.
  Inputs: authenticated identity, Tenant, `object|attribute`, unique 1..200
  selected IDs with expected opaque row revisions, fixed
  `lock|unlock|deactivate|reactivate`, idempotency UUID. No caller-authored fields,
  SQL, table names, owner or actor IDs. No MCP registration/execute grant.
- Source ownership is `object.source_tenant_id`; Attribute ownership derives
  through its Object. Never authorize from placement Connection Tenant.
  `workflow.list_tenant_visible_objects` already follows this rule and includes
  inactive rows, so reactivation remains discoverable.
- Use `tenant_metadata_write` (Developer+) and owned Tenant Lock; match current
  explicit web review's human-only restriction. Serialize the short operation
  against the Tenant Lock row before selected Object/Attribute locks, reauthorize,
  and reject any running Tenant Workflow. This prevents a start/review race
  because workflow authorization holds a SHARE lock on the same Tenant Lock.
  Verify lock ordering against other operations before implementation.
- Lock Objects in ID order, then Attributes in ID order; check complete selection,
  source ownership and revisions before any update. For Attributes lock/check
  parent Object as well. Locked parent blocks all Attribute lifecycle changes;
  explicit parent unlock comes first. Locked rows permit explicit unlock only;
  status changes reject them. Already-satisfied actions are zero-change success.
- Add server-generated full-content `review_revision` digests to catalog records,
  with parent lifecycle included for Attributes. Recompute after locking. Model
  revision and draft revision do not fence Tenant-shared physical metadata; no
  new core revision column or Model revision bump is required for this operation.
- Function updates ONLY selected is_locked/is_active plus audit timestamps/actor;
  leaves descriptions, source/inferred types, transformations, mappings and
  Model records unchanged. Physical inactive semantics already retain references
  and let eligibility filter them; no cascading children or Model Scope removal.
- Audit tradeoff: Metadata CS events require a real parent draft. Creating an
  applied synthetic CS requires full canonical documents/digests and interferes
  with manual active drafts unless carefully separated. A single append-only
  bounded physical-review event table is smaller and clearer: actor/Tenant,
  action/type, IDs and before/after lifecycle flags, request digest, counts/time,
  correlation UUID. No raw physical rows. Use unique actor+Tenant+correlation and
  stored request/result for matching retry; divergent key reuse conflicts.
- API result: reviewed/changed counts, review event ID, selected new flags and
  new row revisions. Identity is server-derived; existing function error mapping
  can expose stale/locked/missing/Tenant Workflow conflict without row contents.
- Catalog detail already includes all Attribute IDs and lock/active values;
  `ModelInputScopeScreen` reads it. Add controls there first. Generic Metadata
  sheets have natural-key records only, so their editor needs a server-resolved
  selection before invoking the same operation; never synthesize IDs client-side.

Tests: disposable PostgreSQL under actual gds_web_runtime, all four actions on
both record types, active/inactive discoverability, no-op/replay counts and one
audit, conflicting retry, mixed owned/unowned IDs atomic denial, GDS placement
versus Source ownership, stale content and parent revisions, locked parent and
locked-content denial, preserving every non-lifecycle column and existing draft,
missing/wrong/expired Tenant Lock, revoked role, concurrent workflow start/review,
MCP execute denial and no new direct core/audit mutation privilege.

## Updated implementation decision: direct missing-only completion

The earlier Metadata Change Set linkage proposal is superseded. User requested
physical fills, not a separate draft lifecycle. Use one atomic governed completion
with exact Run owner/claim, both Model/Metadata authorization, owned Tenant Lock,
Model revision, selected active Input Scope and physical baseline. Preserve all
existing content, locks, statuses and storage types. Whole-baseline drift yields
inspectable changed outcomes without stale patches; authorization/scope/claim
drift rejects atomically.

Bounds: 200 selected Objects, 5,000 selected Attributes, 10,200 field outcomes,
16 MiB metadata context, 24 MiB completion payload. Generated descriptions <=2,000
UTF-8 bytes; inferred type <=100 characters; samples <=50 values, never persisted
or passed to the description agent. Masked Attributes never issue sample queries.

Typed per-field result statuses: applied/existing/locked/inactive/changed/
unavailable/inconclusive. Evidence methods: agent_description/source_comment/
registered_type/source_schema/bronze_schema/source_sample/bronze_sample/none.
Persist applied_value only for applied outcome, no sample rows or arbitrary errors.
Summary aggregates outcomes; result API paginates immutable field records.

Context has selected objects with original connection/placement metadata and
optional physical relation {connection_id,catalog,schema,table}; relation connection
is the Databricks execution connection, not necessarily source connection. Each
Attribute has its canonical storage/inferred types, description, mask/lock/status
plus relation_column and one optional source descriptor resolved ONLY via active
ingestion Object+Attribute mappings. Multiple candidates => null source, then
Bronze evidence. Include all candidates and mappings in the baseline digest.

Inference review notes:
- Actual nonstring Source schema first. Actual STRING makes samples authoritative
  over conflicting registered numeric metadata; sampling failure never revives it.
- Unavailable Source schema may fall back to registered Source inferred/native
  nonstring type, then Bronze schema/samples. No invented generic descriptions.
- Leading zeros/mixed values stay STRING. Boolean true/false only, ISO dates and
  timestamps only. Empty/null samples alone do not justify a narrower type.
- Decimal union precision = max integer digits + max scale. Inspect Decimal tuples
  exactly; never use default28-digit arithmetic/normalization. Bound precision38
  and exponent; preserve signed64 integer limits, nonfinite values as STRING.

## Physical review implementation correction — 2026-09-05

Read-only design checkpoint; production implementation remains a later slice.

- Fixed web-only boundary: `application.review_metadata_records(UUID, UUID,
  VARCHAR principal_type, BIGINT tenant_id, VARCHAR record_type, VARCHAR action,
  JSONB records, UUID correlation_id)`. `record_type` is `object|attribute`;
  action is `lock|unlock|deactivate|reactivate`; records are exactly
  `[{record_id, expected_review_revision}]`, unique 1..200 IDs, lowercase
  64-character digests, bounded 32 KiB payload. No caller values, identity fields,
  SQL, Model ID, or Model revision. SQL requires actual human/user identity;
  HTTP service also enforces `ActorKind.HUMAN`.
- Important lock-order correction: authorize `tenant_read` first, acquire the
  exact Tenant Lock row `FOR UPDATE`, then reauthorize `tenant_metadata_write`.
  Do NOT acquire Metadata Write's Tenant Lock SHARE first and then upgrade it:
  two reviews could deadlock during that upgrade. The service must not perform
  a Metadata Write preauthorization before calling the governed function.
  Check running Tenant Workflows with plain `EXISTS`, without locking Model/Run.
  Workflow start already holds Model/Run before obtaining Tenant Lock SHARE;
  locking them after Tenant Lock would invert that order. The exclusive Tenant
  Lock serializes new review calls against starts and ordinary Metadata Apply.
- Lock owned parent Objects in ascending ID order, then selected Attributes in
  ascending ID order. Recheck exact selection, Source Tenant ownership, parent
  association, revision and lock flags after locking. Reject any incomplete,
  moved, foreign, stale or parent-locked set atomically. Locked Objects require
  their own explicit unlock before any Attribute action. Status changes on
  locked records reject; already-satisfied actions are audited no-ops and do not
  change row timestamps. Preserve independent parent/child active flags; no
  cascading child, scope, binding, mapping, description or type changes.
- One append-only `application.metadata_review_event` table can live beside the
  fixed function in SQL14: Tenant/actor/correlation, action/type, request digest,
  bounded IDs and before/after flags, returned row revisions, counts/time.
  Unique `(tenant_id, actor_principal_id, correlation_id)`. Same digest returns
  the stored response before stale-row checks; divergent replay rejects. Recheck
  authorization/owned lock for replay. No raw rows/descriptions/type values.
- Return a fixed denial code row for expected authorization/lock/stale/selection
  conflicts before writes, following existing Metadata/Tenant Lock boundaries;
  generic database exceptions otherwise become dependency failures in
  `WebPostgresDatabase`. Successful result: review event ID, reviewed/changed
  counts, selected IDs/new flags/new revisions. After writes, unexpected failure
  raises and rolls back the entire transaction. Audit records remain private.
- `review_revision` hashes the full physical row. Attribute revisions also hash
  parent Object identity/Source Tenant/lifecycle so a changed parent lock fences
  stale child actions. Hash full values before display truncation, and canonicalize
  timestamp values to UTC/epoch so tokens do not vary by database session timezone.
  No new `core` revision columns or Model revision bump.
- Exact catalog edits: `features/metadata/contracts.py` adds `review_revision` to
  Object summaries/details and `ObjectAttribute`; Object summary gains `is_locked`.
  `features/metadata/repository.py` extends `_OBJECT_LIST_SQL`, `_OBJECT_DETAIL_SQL`
  and `_OBJECT_ATTRIBUTES_SQL` with authoritative digests; Attribute query joins
  its parent. Shared `ObjectAttribute` also requires the digest in
  `features/model_input_scope/service.py::_MODEL_INPUT_SCOPE_ATTRIBUTES_SQL`.
  Existing 2,000-character display truncation must not truncate digest inputs.
- HTTP: add `POST /api/v1/tenants/{tenant_id}/metadata/review`, mandatory
  `Idempotency-Key`, strict command/result models and `review_records` on existing
  Metadata service/router. Extend its database protocol with `write_transaction`;
  call only the fixed SQL function. Reuse current runtime/router composition and
  safe Workbench errors. SQL19 grants only this function to `gds_web_write` and
  revokes the new table from its blanket application SELECT grant. SQL20 and web
  readiness must include the function/table/append-only/privilege contracts.
- UI correction: `ModelInputScopeScreen` currently calls its own active-only
  `readModelInputScopeObject`, NOT Metadata catalog detail. Both the eligibility
  join and Attribute query hide inactive rows, so adding action buttons alone
  cannot support reactivation. Metadata `/objects?active_state=all|inactive`
  and `/objects/{id}` already expose physical inactive Objects/Attributes.
  First complete UI slice must wire those catalog reads into a review surface
  and retain inactive discovery. Generic Metadata sheets use natural keys only;
  do not synthesize physical IDs/revisions or add them to canonical workbook rows.
  Preserve workflow eligibility's active-only meaning.
- Required gate: all four actions on both record types, no-op and exact/divergent
  retry, mixed-owned selection atomic denial, shared Connection placement with
  true Source ownership, stale full-row/parent revisions, parent locks, unchanged
  non-lifecycle metadata and existing draft, wrong/expired lock, revoked role,
  human restriction, actual competing start/review and concurrent reviews,
  inactive discoverability, and MCP/direct-core/audit-write denial. Only disposable
  fixture PostgreSQL; no migrations, external writes, packaging publication or
  Model Change Set materialization.

## Agreed web physical review contract for next slice

- POST `/api/v1/tenants/{tenant_id}/metadata/review`, UUID Idempotency-Key.
- Body `{record_type: "object"|"attribute", action: "lock"|"unlock"|
  "deactivate"|"reactivate", records: [{record_id, expected_revision}]}`.
  Strict object shape, 1–200 unique positive IDs, lowercase SHA256 revision.
- Success `{review_event_id, action_count, records: [{record_id,
  review_revision, is_active, is_locked}]}`; rows in ID order, counts bounded.
- Existing catalog Object summary/detail and Attribute detail add opaque
  `review_revision` string; Object summary also adds is_locked. Revision hashes
  full actual core row. Attribute revision additionally hashes parent lifecycle
  and Source Tenant ownership. UI must read actual catalog identity/revision;
  never infer ID from natural keys or use Model revision for physical writes.
- Prefer one dedicated Metadata review service/router using existing identity,
  backend transaction and fixed governed function. Generic catalog service stays
  read-only. Governed SQL returns bounded denial codes; service maps only those
  to existing safe authorization/lock/conflict errors. No raw DB error surfaced.
- Function authenticated user only; tenant_read -> TenantLock FOR UPDATE ->
  tenant_metadata_write reauthorization. Matching idempotency replay after current
  auth but before stale-row check. No Model/Run row locks after TenantLock;
  plain running-Tenant-workflow EXISTS, then owned Objects and Attributes in ID
  order. Validate entire selected set and expected revisions before mutations.
