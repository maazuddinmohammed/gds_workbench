# Physical review and result detail UI plan

Read-only production audit, 2026-09-05. This document is the only change in this
slice. Findings below come from current source/contracts; the existing result
screens have not received a new browser audit during this pass. New enrichment
surface remains frozen after its separate 216-test/types/build/browser checkpoint.

## 1. Physical Object/Attribute review: complete discovery before controls

Use the existing Tenant Metadata catalog, not the natural-key workbook editor or
active Model Scope API. Add one leaf screen under Metadata:
`/tenants/$tenantId/metadata/objects`, with an optional typed `objectId` search
parameter for its inspector. Link it from the Metadata screen (“Objects and
Attributes”) and the Model Input Scope inspector (“Review physical metadata”).
Keep the existing workbook/dataset editor unchanged. No new main sidebar entry.
The new screen is Tenant-owned, not Model-owned; describe shared effects once.

Why this placement:

- `features/model_input_scope/ModelInputScopeScreen.tsx` calls
  `readModelInputScopeObject`, not the Metadata catalog. Its list and Attribute
  queries exclude inactive rows. Object deactivation can make that entry
  disappear, so controls there alone would strand reactivation.
- The current Scope screen also ignores `next_cursor` and has no Refresh command.
  Do not reuse its one-page list for authoritative physical selections.
- `features/metadata/MetadataScreen.tsx` and `MetadataRowSurface.tsx` display
  canonical workbook rows, whose identities are natural keys. They contain no
  guaranteed physical IDs or opaque review revisions. Never add IDs to canonical
  workbook rows, derive them from names, or hash displayed/truncated values.
- Existing backend `/metadata/objects` and `/metadata/objects/{object_id}` already
  provide physical IDs, Source Tenant ownership and inactive discovery. Their
  frontend transport is absent from `features/metadata/api.ts` and `src/api.ts`.

### Current read contract and necessary additions

| Existing read | Current data | Gap before lifecycle UI |
| --- | --- | --- |
| GET `/api/v1/tenants/{tenant}/metadata/objects` | `ObjectCatalogPage`: schema_version, tenant_id, items, next_cursor. Summary has object_id, schema/name, object/zone type, connection ID/code, system ID/code/name, Source Tenant ID/code/name, attribute_count, batch_attribute_name, is_active. | Add summary `is_locked` and authoritative `review_revision`; frontend DTO/transport. |
| GET `/api/v1/tenants/{tenant}/metadata/objects/{object}` | Summary + description, connection/type names, is_locked, all Attributes. | Object review_revision; Attribute review_revision. |
| Attribute in that detail | attribute_id, name/ordinal, description, storage/inferred types, nullable, surrogate/natural/meta/masking/mapped/purge flags, is_locked, is_active. | Parent Object gives context; use its real ID and lock state. Parent-sensitive token must come from backend. |
| POST `/api/v1/tenants/{tenant}/metadata/review` | Not implemented in audited source. | Fixed record_type/action, records[{record_id, expected_review_revision}], mandatory Idempotency-Key, safe result/errors. Root owns backend. |

Catalog list filters already supported: `zone` source/bronze/silver/gold;
`system_code`; `source_tenant_code`; `active_state` active/inactive/all;
page_size 1..200 (default50); opaque cursor <=2048 characters. No Object-name
filter exists on this catalog route. Do not pretend local filtering searches the
whole catalog; initially use existing filters and a clearly labeled Object-ID
lookup. A server Object-name filter is an optional later usability improvement.

Catalog cursor is bound to Tenant, page size and filter digest. It is offset-based,
not a snapshot/Model revision: do not promise stable whole-catalog snapshots.
Revision fencing for review must use each backend row token, not the cursor or
current Model revision. Detail caps at 2,000 Attributes and currently fails if the
Object has more; UI must show the safe error, never claim a partial view is complete.
If wide Objects >2,000 are required, add a separately paginated catalog Attribute
read before claiming complete lifecycle support at that size.

### Minimal screen and inspector

1. Header: “Objects and Attributes”; Tenant Lock and role reason; explicit Refresh.
   Copy: these controls change shared physical records, not Model Scope membership.
2. Object table: selection, schema/name, Zone, System, Source Tenant, Active/Inactive,
   Locked/Open, Attribute count, Inspect. Default active; visible Active/Inactive/All
   selector. No descriptions or 64-character revision digests in the main ledger.
3. Selected-Object bar: Lock, Unlock, Make inactive, Make active. Exact displayed
   selection count; no silent skipping of locked/ineligible selected rows.
4. Inspector: Object name, status and lock; description; Object action controls;
   Attribute table with its own Active/Inactive/All filter (default All, so inactive
   Attributes remain obvious). Columns: selection, Attribute name, storage type,
   inferred type, status, lock. Expand one row for description/key/masking flags.
5. Attribute action bar acts only on selected Attribute IDs from this Object.
   Locked parent disables all Attribute actions with “Unlock the Object first”.
   Parent inactive and child active are independent states; say so when relevant.
   Do not suggest reactivating a child makes an inactive parent workflow-eligible.
6. Native table/checkbox/buttons, explicit labels, keyboard-accessible scroll area,
   Escape/close focus restoration for inspector. No modal confirmation for these
   reversible, explicitly chosen actions; no raw digest or event payload display.

### Selection, concurrency and retry behavior

- Limit selected records to 200; keep Object and Attribute selections separate.
  Simplest initial paging: 50 Objects per server page, 50 Attributes per local page
  of the bounded Object detail. “Select page”, not “Select all matching”. Selection
  clears on Tenant/filter/page/Object changes and Refresh. No cross-page bulk state.
- Capture immutable `{record_id, expected_review_revision}` pairs at click time.
  Disable changes to that selection/action while mutation is unresolved. Reuse the
  same key and exact command after an ambiguous network/5xx failure; changing action
  or selected revisions starts a new request only after the previous outcome is
  resolved. Use established Analysis review retry behavior as reference.
- Backend remains authoritative: human identity, Developer+ Metadata Write, owned
  Tenant Lock, Source ownership, no running Tenant Workflow, exact row/parent
  revisions, parent locks. Browser can mirror known role/lock constraints only.
  Current Metadata route already computes Developer+ as effective_role != viewer.
  Do not authorize using placement Connection Tenant or cached UI roles.
- Lock/unlock may be audited no-ops when already satisfied; status changes on locked
  records reject. Mixed conflicting selections are an atomic denial, not a subset
  success. Show reviewed/changed counts from server, including “0 changed”.
- On success, clear selection, refetch catalog/detail and Tenant home once. Invalidate
  affected active Model Scope and workflow scope caches by existing prefixes; do
  not fabricate a Model revision bump. Inactive-filter deactivation may remove a
  row from the current page; reset to first page rather than using shifted offsets.
- On stale revision, retain no executable stale selection: show Refresh required.
  On ownership loss/403/404, hide stale detail and disable actions. On parent lock,
  show explicit parent-unlock requirement. On running workflow, use the existing
  Tenant workflow conflict message. Never surface raw database exception/records.

Backend signature/locking/audit details are in the latest correction section of
`.scratch/metadata-governance-inventory.md`; earlier Metadata Change Set enrichment
proposal in that document is superseded. Physical review is not a Model Change Set
and must not acquire any Model Apply path.

### First complete UI gate once backend is ready

Exact read URLs/filters/cursors; inactive Object discovery; inactive Attribute
selection; all four actions for Object and Attribute; row tokens/IDs exact; no-op
counts; parent-locked controls; viewer/wrong/expired lock; stale/foreign response
hiding; ambiguous key replay and exact payload; post-mutation paging reset;
no Model/physical-field values in command; no changes to workbook rows. Browser
at desktop/390px and keyboard, then frontend full check. Backend disposable-DB
fences are a separate prerequisite, not replaced by fake HTTP tests.

## 2. Result lifecycle gap remains broader than physical review

Confirmed current public `ReviewModelRecordsRequest.dataset` is
`Literal["analysis_result"]`, and service uses `read_analysis_review_records` /
`apply_analysis_review`. Only AnalysisResults renders Lock/Unlock/Make inactive/
Make active. Other ledgers show status/lock but expose no review actions. General
validator helpers do not mean those public lifecycle paths already work.

Later extend one modeled family at a time through governed Model review after
full-graph validation is corrected. IDs already present in detail/ledger DTOs:
Conceptual Object/Relationship IDs; Logical Entity/Attribute/Relationship/Submodel
IDs; Dimensional Entity/Attribute/Relationship IDs; Mapping Object/Attribute IDs.
Use each canonical dataset/record ID; never route them to physical Metadata review.
Code currently exposes `generated_sql_artifact_id`; first confirm its canonical
`generated_code` identity and lock/review DTO before adding controls. Do not infer
that an artifact ID is interchangeable with a Model row ID.

## 3. Result detail cleanup: concrete observations and smallest ordered slices

Common reading order: generated result/definition first, why/evidence second,
source navigation next, audit provenance on demand. Keep inactive/locked/stale
states and bounded-response warnings visible. No new generic renderer abstraction
or frontend interpretation of validation policy. Each row below is a separate
verified production slice; source paths are under `web_app/frontend/src/features/`.

| Order | Current source evidence | Smallest useful change | Check |
| --- | --- | --- | --- |
| 1 — Profiling | `profiling/ProfilingDetail.tsx:76` shows 12 Object facts, including Object/Model/Source Tenant/System/Connection IDs and duplicate counts. `:116` renders a 22-column table: identity, every count/length/percentage and five provenance fields including full source digest on every row. | Keep Object qualified name/System/last profiled + returned/total warning. Main Attribute ledger: name, profiled type, rows, null %, blank %, distinct %, duplicate %. Native per-row details hold exact counts, lengths and provenance. Explain metrics using stored values; do not invent quality thresholds or turn profiling type into inferred source type. | Known metrics remain associated with correct Attribute; exact long counts/null values; all details available; truncated warning visible; 2,000-row bounded input; keyboard/table width. |
| 2 — Code | `code_generation/GeneratedSqlDetail.tsx:153–266` places Target, Systems, Mapping supports and extensive generation provenance before Stored SQL at `:267`. Target Object and modeled layer repeat header facts. | Move Stored SQL directly after current/stale status and actions; retain literal-text rendering and .sql download. One concise target/source context; native collapsed “Mapping evidence” and “Generation details” below. Keep stale-support absence/truncation warning visible near relevant section. | Same SQL byte/text fidelity and download URL; stale vs current remains accurate; no HTML interpretation or execution; regenerate permissions unchanged. |
| 3 — Mapping | `mapping/MappingDetail.tsx:75–103` places IDs and template metadata before transformation. Attribute page adds parent mapping + five template facts first. Template code repeats again in provenance. `MappingDocumentView.tsx` recursively expands every object/array into nested definition lists and “Record n” cards. | Put target ← modeled source summary then Transformation document. Move ID/template/version/status provenance to one disclosure; avoid duplicate code facts. For recognized canonical Mapping keys, present ordered source→target Attribute/expression/dependency sections using actual stored schema. Keep a bounded native disclosure for unrecognized/free-form template fields; no data loss or made-up package/header. | Both canonical and real custom/free-form documents; null/empty/boolean/Unicode; long arrays, nesting and 390px. Confirm actual persisted mapping schemas before specializing renderer. |
| 4 — Conceptual | Definition/grain already lead (`conceptual/ConceptualDetail.tsx:85`), but every support (`:209`) expands 6–11 facts, repeats Object name from header, and shows both support_reason/detail plus full assertion text. Relationship endpoint names pass through `humanize`, changing underscores/case in real names. | Preserve definition/grain and relationship/cardinality reasoning. Compact support ledger with source, role, confidence/status and main reason; one native disclosure for detailed rationale/assertion text/IDs/time. Remove duplicate name fact; display real endpoint names verbatim; link endpoints/sources where an existing authorized route exists. | 0/1/many support records, physical/assertion branches, exact source names, inactive/lock states and all expanded evidence reachable. |
| 5 — Logical | Entity page (`logical/LogicalDetail.tsx:139`) has definition/grain, but membership expands its own facts per row (`:151`), followed by repeated source cards. Entity detail DTO contains sources/submodels, no Attributes. Attribute definition renders four separate key booleans alongside nullable/ordinal. Unlike Conceptual/Dimensional, Logical headings are not focused after navigation. | Keep Entity definition/grain/type first; compact memberships into linked rows. Compact source/evidence ledger using same presentation behavior as Conceptual without a premature generic adapter. Add “View Attributes” navigation using existing logicalEntityId filter; do not fake a nested Attribute list from source mappings. Group meaningful Attribute key roles; preserve nullable and explicit absence. Fix heading focus in this slice. | Parent→Attribute filters and return path, membership/source identity, key flags, no source/target confusion, keyboard focus; unchanged authorized read contracts. |
| 6 — Dimensional | `dimensional/DimensionalDetail.tsx:128` shows Fact type “Not applicable” for dimension rows. Membership/source records repeat Logical card pattern. Attribute grid (`:247`) shows 12 parallel facts, mixing key role, measure aggregation and SCD behavior with “Not applicable/Not specified”. | Lead with definition and grain. For facts, show fact type; for measures, show aggregation/additivity and basis; for dimensional attributes, show change behavior where populated. Keep unknowns explicit when relevant, hide genuinely inapplicable empty fields. Compact memberships/sources. Add filtered Attribute navigation through existing dimensionalEntityId API. | Fact/dimension/measure/key/audit variants; aggregation basis not lost; unknown vs not applicable distinct; status/locks; source assertion/physical variants. |
| 7 — Analysis | `analysis/AnalysisDetail.tsx` repeats endpoints in title and a full comparison, then raw validation counts and provenance. Validation support result is visible but inactive status is omitted, policy digest/version appears without explanatory outcome. No heading focus or local Refresh. | Lead with endpoint pair and actual supported/unsupported/inconclusive or not-yet-validated state; show inactive/lock status. Keep relationship basis and material validation counts, group secondary counts + policy/provenance in details. Preserve exact labels and distinguish inferred confidence from deterministic validation. Add focus/manual Refresh with existing query keys. | All three validation outcomes and no evidence; unsupported missing/duplicate counts; truncated basis warning; inactive states; literal endpoint names. |

Each detail currently relies on mount/cache reads; most have no local Refresh.
Add explicit Refresh during each relevant slice, with request pending/error state,
without interval/window-focus polling or refetching while reading every disclosure.
Do not bury failure, stale, truncation, permission or unresolved warnings inside
collapsed provenance. Native disclosure should reduce initial clutter while the
actual stored output remains fully inspectable.

## 4. Dependencies and stop conditions

- Physical UI starts only after revised read DTOs + fixed lifecycle mutation land.
- Modeled review family starts only after its backend contract/graph checks land.
- Mapping semantic presentation waits for confirmed canonical persisted document
  contracts; current arbitrary recursive renderer is not a schema definition.
- Prompt-variable redesign is a separate user-requested backend-first slice.
  Current Prompt list exposes name/type/resolver/description + bounded example;
  detail omits example entirely. No surface currently conveys useful source,
  shape, purpose and stage-specific usage. This plan adds no prompt changes.
- Reuse `shared/ui.tsx`, existing formatters, native details/tables and design tokens.
  No new framework, diagram library, universal inspector or presentation DSL.

## Modeled review implementation notes from root

After history and physical review gates, expand modeled review in verified family
slices. Reuse the existing applied Model CS audit/idempotency/revision path and
full Model Snapshot; do not run generic materializers for lifecycle-only edits
(they can replace supports and clear deterministic evidence).

A fixed backend dataset registry can supply primary key + canonical-key lookup,
status/lock column, and snapshot section/tuple field. Read selected real IDs under
Model lock, resolve canonical records from the complete snapshot by exact typed
keys, mutate only the two allowed lifecycle fields, validate the full graph, then
update those database columns with row-count fences. No user-authored content,
SQL, actor or target-table input. Explicit unlock shadows only selected records'
lock fields for validation, preserving parent/content/nested locks. Audit actual
before/after record actions against the unmodified snapshot.

Prefer actionable bounded dependency conflicts to today's generic review_conflict
message: active child/relationship needs an active endpoint; no silent cascade.
Physical identity is not a modeled dataset ID; Code artifact identity must be
confirmed from actual stored projection before enabling its review controls.

## Current-source recheck after token UI — 2026-09-05

No production edits in this recheck. Cost slice precedes implementation.

Confirmed absent: `application.review_metadata_records`, `metadata_review_event`,
`POST /metadata/review`, all physical `review_revision` fields, and frontend
Object catalog transport. Existing Model review remains Analysis-only. Neither
new enrichment completion nor working Analysis review supplies physical lifecycle
controls. Keep these three operations separate.

Corrected assumption: current SQL11 `workflow.list_tenant_visible_objects` selects
`object.source_tenant_id = requested Tenant`, including shared GDS placement.
It no longer expands visibility to foreign-owned Objects. Some catalog unit HTTP
fixtures still return Source Tenant 8 under request Tenant 7; these are synthetic
mocks, not evidence of actual SQL visibility. Test real Source ownership with
other placement Tenant allowed, foreign Source Tenant rejected. UI should still
reject stale/mismatched response IDs and ownership fields before enabling review.

The old plan's proposed `expected_review_revision`, `reviewed_count`, and
`changed_count` names are superseded by the final agreed contract at the end of
`.scratch/metadata-governance-inventory.md`:

- Request: `{record_type, action, records:[{record_id, expected_revision}]}`.
- Response: `{review_event_id, action_count, records:[{record_id,
  review_revision, is_active, is_locked}]}`.
- Selected/reviewed count is `records.length`; `action_count` is changed rows.
  A replay or already-satisfied action must not be shown as an error.

### Smallest next backend checkpoint

Implement physical lifecycle only, all four actions for both record types through
one fixed governed transaction. Add full-row opaque catalog revision tokens;
no description/type editing, Model Change Set, cascades, extra CRUD, or public MCP
surface. Verify this backend checkpoint before adding buttons.

Exact production files:

- `database/14_application_workflow_execution.sql`: append-only review event and
  fixed function; stable canonical digests needed by both read and locked recheck.
- `database/19_runtime_integrity.sql` (actual filename): web-only execute grant,
  private event data, readiness/privilege contracts.
- `database/20_verify_install.sql`: install and least-privilege assertions.
- `web_app/backend/gds_workbench_api/features/metadata/contracts.py` and
  `repository.py`: required Object/Attribute review_revision; Object summary
  is_locked; hashes before 2,000-character description display truncation.
- `features/model_input_scope/service.py`: its shared ObjectAttribute DTO now
  also needs the digest, without changing active-only workflow scope semantics.
- New `features/metadata/review.py`: cohesive strict request/result, dedicated
  service and small router is sufficient; fixed SQL boundary owns transitions.
  Alternatively follow nearby three-file feature structure if this grows; do not
  change the generic read-only catalog service to perform lifecycle mutation.
- `main.py`, `runtime.py`: explicit review service/router composition; `database.py`
  only if its readiness contract requires the new function/table there.
- `CONTEXT.md`: document physical vs Model review and parent-lock behavior.

Exact tests:

- New `tests/web_backend/test_metadata_review.py`: strict command, unknown fields,
  duplicate/bounds/digest format, required idempotency key, human-only route and
  safe error mapping; exact SQL parameters and transaction rollback behavior.
- New `tests/web_backend/test_database_metadata_review.py`: actual disposable
  `gds_web_runtime` call, eight record/action combinations, already-satisfied
  no-op, exact replay/divergent key, stale full value and parent revision, locked
  parent/status denial, Source ownership vs placement, whole-selection denial,
  unchanged non-lifecycle fields and current metadata draft, wrong/expired/revoked
  lock/role, review/start serialization and two concurrent reviews, audit rollback
  and denied raw core/audit/MCP access. No user DSN or external Databricks.
- Extend existing `test_metadata.py`, `test_metadata_repository.py`,
  `test_model_input_scope.py` for new required fields, inactive catalog discovery,
  >2,000-Attribute safe rejection, source-owned shared placement, and stable digest
  under equivalent session timezone. Run install/readiness regression tests.

### Smallest following UI checkpoint

Keep earlier dedicated `/tenants/$tenantId/metadata/objects` leaf placement.
Native Object ledger and one Attribute inspector; 50 Objects/page, bounded local
Attribute pages; one page's selection only, max200; explicit Active/Inactive/All
and Refresh. Use real IDs/revisions, parent lock explanation, four reversible
actions and immutable ambiguous-retry command. No workbook natural-key lookup.

Files: `features/metadata/api.ts` (+ catalog/review DTO/transport), `src/api.ts`,
new `features/metadata/PhysicalMetadataScreen.tsx` (+ focused test), `app.tsx`,
MetadataScreen link, ModelInputScopeScreen review link, existing metadata CSS.
Reuse current AnalysisScreen pending-command ref/error policy, not a generic
review framework. Use TenantRouteFrame; no new main navigation item.

Tests: exact filters/cursor/query/payload; active/inactive Object and Attribute
selection; all actions/no-op; ownership and parent-lock disable; expired lock,
viewer, 403/404 hiding, stale row Refresh, immutable network/5xx retry; clear
selection/reset page on successful mutation; no polling; route/link/focus.
Run frontend check and desktop/390px keyboard QA.

The >2,000 Attribute catalog bound is real (`get_object` rejects before detail).
Keep that explicit in the first UI. If support for wider Objects is required,
add paginated Attribute catalog reads as its own following backend/UI checkpoint;
never silently label the first 2,000 as complete.

## Frontend implementation handoff after cost — 2026-09-05

Production remains unchanged in this preparation. The backend is now being
implemented; the earlier statements that its route/revisions are absent are
historical. Current `features/metadata/review.py` confirms the final POST contract
above, human-only identity, mandatory UUID `Idempotency-Key`, sorted results and
exact result-ID coverage. Current `metadata/contracts.py` requires Object summary
`is_locked` and `review_revision`, and Attribute `review_revision`. Catalog read
routes and the 2,000-Attribute detail cap remain unchanged. Frontend work waits for
root's disposable-database checkpoint and explicit coordinated GO.

### Concrete component and transport changes

- Add `PhysicalMetadataScreen.tsx` under `features/metadata`. One cohesive screen
  owns catalog queries, current cursor/history, filter state, immutable review
  request and separate Object/Attribute selections. A local Object inspector may
  be a second component in that file; use native tables/details and the existing
  inspector classes, not a generic review framework.
- Register `/tenants/$tenantId/metadata/objects` in `app.tsx` using
  `TenantRouteFrame`, active navigation `metadata`, and an optional positive safe
  integer `objectId` search parameter. Key the screen by Tenant to clear local
  state on Tenant navigation. A linked Object may open directly even when inactive
  or absent from the current catalog page; fetch its real catalog detail.
- Add a supporting “Objects and Attributes” link to the existing Metadata command
  bar. Add “Review physical metadata” to the successful Model Input Scope detail,
  passing the actual `detail.object_id` and Tenant route parameter. Pass Tenant ID
  through `ScopeView`/`ScopeDetailDrawer`; leave active-only scope filtering and
  canonical workbook rows unchanged. Do not link from a stale/error fallback.
- Add catalog summary/page/detail/filter and strict review command/result DTOs to
  `features/metadata/api.ts`. Transport methods: `listMetadataObjects`,
  `readMetadataObject`, `reviewMetadataRecords`. GET uses existing query names
  `zone`, `system_code`, `source_tenant_code`, `active_state`, `page_size`, `cursor`;
  POST sends only `record_type`, `action`, and sorted real ID/revision pairs.
  `src/api.ts` already composes `createMetadataApi`; extend its type exports only
  where needed, with no separate duplicate API factory.
- The existing frontend `ObjectAttribute` lives in `model_input_scope/api.ts`.
  Move its single authoritative declaration to `metadata/api.ts`, add required
  `review_revision`, and re-export its type from the old module for compatibility.
  Both detail DTOs then use that exact shared shape; update typed fixtures only.
- Extend `metadataQueryKeys` with `objects(tenant, filters, cursor)` and
  `object(tenant, objectId)`. Reuse existing CSS before adding only screen-specific
  table widths/responsive inspector layout to `styles/metadata.css`.

### Interaction decisions

The first page contains 50 Objects with explicit Previous/Next cursor navigation,
Active/Inactive/All, Zone and existing System/Source Tenant code filters, Apply
filters, and Refresh. Use one filter form submission rather than request on every
keystroke. A page heading states that lifecycle changes affect shared physical
metadata across Models. IDs and opaque revisions stay out of the visible ledger.

The Object inspector shows qualified name, description, state, lock and its own
single-Object actions, so a deep link can unlock an Object without finding its
catalog page. The catalog selection bar separately supports page bulk actions.
Keep only one review command pending across both areas. Attribute review acts on
that inspector's real Attributes, defaults to All, and uses 50-row local pages of
the already bounded complete detail. Select-page checkboxes select only displayed
records; filter/page/inspector changes clear that area's selection. No cross-page
selection or silent skipping. All four explicit actions are available, including
audited no-op lock/unlock; state changes explain locked-row restrictions before
submission. A locked parent disables every Attribute action, including unlock.

Mirror known access constraints: effective human role above viewer, currently
owned Tenant Lock with a future expiry, valid response Tenant/Source Tenant and
Object IDs, and usable opaque revisions. Recheck lock expiry at click time;
backend remains authoritative for identity, role/lock changes and running Runs.
No timers or speculative local authorization cache are needed. A current catalog
error hides its cached rows; a detail 403/404 or mismatched identity hides cached
detail and disables its actions. Historical schema/name is never an ID lookup.

Capture exact command + UUID together. During pending or ambiguous failure,
disable new actions, selection, paging/filter changes and inspector changes;
show “Retry review” using the same command/key. An HTTP 408, network error or 5xx
may have committed. Definitive 4xx clears the command; a stale/selection conflict
also clears selected IDs and requires fresh catalog/detail before a new review.
Safe error mapping uses current codes: `metadata_revision_conflict`,
`metadata_selection_conflict`, `metadata_review_conflict`, `object_locked`,
`attribute_locked`, `tenant_workflow_conflict`, and authorization/Tenant Lock.
Show no database exception text. Success copy uses `records.length` reviewed and
`action_count` changed, including zero; do not interpret replay as failure.

Success clears selections and resets Object cursor/local Attribute page, then
invalidates catalog/detail, `metadata-rows`, `tenant-home`, `model-input-scope`,
`model-input-scope-object`, and the three `workflow-run-*-scope` Tenant prefixes
once. Mapping/Code eligible-target caches should also be marked stale by their
existing Tenant prefixes when their current read contract depends on physical
status; do not manufacture a Model revision or refetch every Model. Explicit
Refresh clears selection and refetches the active catalog/detail and Tenant home.
Focus returns to the trigger on inspector close, or the page heading after a
direct-link inspector; new detail focuses its close button. All wide ledgers use
keyboard-focusable horizontal scroll regions.

### Bounded frontend verification gate

Add `PhysicalMetadataScreen.test.tsx` with fake HTTP through the actual router/API
composition, plus focused additions to `metadata/api.test.ts`,
`MetadataScreen.test.tsx` and existing `app.test.tsx` Model Input Scope tests:

- Exact initial/manual-filter/cursor GETs; active and inactive discovery; deep-link
  inactive Object; all/inactive Attribute local paging and selection reset.
- Eight record/action cases with exact IDs, opaque revisions, sorted payload and
  UUID header; reviewed/changed no-op copy; parent-lock/locked-state behavior.
- Viewer, wrong/expired Tenant Lock, stale revision, ownership/ID mismatch, detail
  403/404 and >2,000-detail safe error; no hidden cached rows actionable.
- Ambiguous failure retries the identical command/key; selection cannot change;
  definitive stale denial requires Refresh; success returns to first page and
  invalidates affected caches once. No polling or raw token display.
- Metadata and Scope links, direct-link close, keyboard selection/details/focus,
  preserving storage versus inferred types and description text.

Run focused tests, then full frontend `npm run check`; browser inspect the actual
new screen at desktop and 390px with keyboard. Backend fixtures remain the proof
of physical lifecycle authorization, atomicity and revision fencing.

## Modeled result review: verified dependency boundary — 2026-09-05

Read-only production audit after physical catalog/review implementation. The
physical implementation supersedes older absent-route/DTO statements above.
Model review still accepts only `analysis_result`. This section is a proposal,
not a claim that the other controls exist.

### Reproduced blockers

Ran fourteen bounded pure-fixture checks against `complete_model_graph()`, its
unchanged baseline snapshot, `complete_physical_scope()`, and the real
`validate_future_graph`; printed only validity, changed counts and issue codes.
No database, raw records or production edits. Baseline passes.

| Lifecycle selection | Actual result |
| --- | --- |
| Conceptual Object alone | `active_dependency_invalid` on its active Relationship. Object plus incident Relationship passes. |
| Logical Entity alone | Active child Attributes, incident Relationships and Object Binding block it. |
| One bound Logical Attribute | `binding_coverage_missing` for modeled Attribute coverage. |
| That Attribute plus its Attribute Binding | Still `binding_coverage_missing`, now physical Attribute coverage. |
| Object Binding alone | `inactive_parent` from its Attribute Bindings. |
| Mapping Attribute alone | Active Mapping must cover every active bound Attribute for that System. |
| Mapping Object alone | Its Mapping Attributes, Code source assignment and last System Validation Group block it. |
| Code artifact alone | Its active source assignment blocks it. Artifact plus assignment passes. |
| Validation Group alone | Active Checks block it. Group plus Checks passes. |
| One Logical Attribute plus its complete Binding/downstream retirement | Eleven explicit lifecycle changes pass. Other modeled Attributes/Entity and all physical metadata remain unchanged. |

The Attribute case is decisive: adding separate dataset buttons cannot produce
a valid sequence while its physical target Attribute remains active. The current
Binding contract requires complete active coverage on both modeled and physical
sides. A Model-only decision must retire that whole Object Binding and dependent
outputs, or the user must separately change shared physical metadata. Never choose
the physical change automatically.

Verified rules are in `application/change_sets/model_validation.py`:
`_validate_bindings` (coverage, historical physical eligibility),
`_validate_active_dependencies` (active dependencies), `_validate_references`
and `_validate_modeled_layer` (historical existence). Do not add inferred cascades
through Conceptual-to-Logical lineage, supports, memberships or assertions:
current rules require their references to exist, not blanket active propagation.

### Smallest usable command boundary

Keep the existing Analysis command compatible. Extend its fixed backend dataset
allowlist and exact-ID lookup/field-only update pattern; do not expose canonical
record payloads, table names, physical mutation or a generic graph editor.

Add one read-only review preview for a selection/action/expected Model revision.
It resolves real IDs from the owned complete snapshot and proposes the complete
set of lifecycle changes needed by the existing rules. Response contains selected
versus additional rows, dataset, real record ID, bounded display name, before/after
state, lock state, a short dependency reason, per-dataset counts and an opaque
digest of the complete plan. No SQL, transformation bodies, raw evidence or
provenance need to travel in this preview. Hidden Binding and Code assignment rows
are visible here; a separate Binding-management screen is unnecessary.

Exact confirmation boundary: when additional rows are needed, show this plan in
the result screen and require an explicit “Apply these N changes” action. Sending
the original row action must not silently accept additional changes. Apply carries
the original selection/action/revision plus plan digest and mandatory idempotency
key. Backend recomputes under write fences, compares the digest, validates the
whole future graph, then atomically changes only the reviewed lifecycle columns.
One Model revision and one existing applied Model Change Set/audit receipt cover
the whole decision. Any changed plan requires a fresh preview; ambiguous retries
reuse the exact original command/key. Exact leaf actions can retain their current
single-step path because they have no additional affected records.

Use straightforward fixed family rules, then the canonical validator as the final
gate. No generic dependency language or persistent plan service is needed:

- Conceptual Object retirement includes incident active Relationships.
- Modeled Entity retirement includes active children/incident Relationships and
  its Binding. Attribute retirement includes incident Relationships; if Binding
  coverage cannot remain complete, show retirement of that complete Binding.
- Binding retirement includes Attribute Bindings, Mapping Objects/Attributes,
  Code artifacts and their assignments. Mapping Attribute retirement may require
  its whole System Mapping for coverage. Retire a Validation Group only when its
  System loses its last active Mapping; include its active Checks then.
- Code retirement includes source assignments. If other active artifacts remain,
  exact one-artifact-per-mapped-System coverage may require a broader explicitly
  reviewed retirement. Never silently reassign Systems or edit generated content.
- Reactivation evaluates prerequisites and coverage as a complete plan too.
  Preserve existing definitions and bindings; do not reactivate unrelated history
  or invent a target/transform/assignment. Ambiguous historical choices must be
  shown for explicit selection, then revalidated. Do not label an incomplete
  single-row reactivation implementation as full lifecycle support.

Locked selected or dependent records block a status plan. Preview identifies the
specific rows; explicit Unlock is a separate lifecycle decision using those exact
IDs, followed by a fresh status preview. It never implicitly unlocks a dependency.
For nested record locks, preserve the existing canonical lock semantics; shadow
only the explicitly unlocked record during validation. Full canonical documents
are retained for validation/audit, but direct UPDATE statements touch only lock,
status and audit timestamp/actor. This preserves support rows, generated content,
deterministic validation evidence, digests and original workflow provenance.

Keep the current selection bound of 200, but do not cap the dependency set at 200:
one Entity can legitimately have more children. Reuse existing Model Change Set
bounds (50,000 pending records; existing section byte limits) and provide bounded,
revision-bound pages of plan rows if needed. Existing `action_review.keys` is
truncated at 100 per dataset and uses natural keys, so it is not a complete ID
manifest. Never apply a truncated dependency subset. Existing storage-bound
failures remain explicit; do not introduce a new lower limit that strands a valid
wide-Entity transition.

### Concrete files and remaining schema/read work

- `features/model_change_sets/{contracts,router,service,repository}.py` owns the
  existing review route. `review_records` already fences Model revision, human
  authorization, idempotent replay, graph validation and field-only Analysis
  writes. Extend here in cohesive family slices. Replace generic `review_conflict`
  for dependency denials with bounded actionable plan rows/reasons.
- Public Logical/Dimensional/Mapping DTOs already expose their own real IDs and
  locks. They do not expose Object/Attribute Binding IDs. Read these server-side
  for preview and accept only exact owned IDs from the fixed review contract.
- `code_generation/read_service.py` explicitly aliases
  `generated_code.generated_code_id AS generated_sql_artifact_id`; identity is
  verified. SourceSystemReference contains System identity, not assignment ID.
  Resolve assignment IDs on the server. The current Code list is based on
  `list_code_generation_target_context`; once a Binding/Mapping is inactive its
  artifacts can disappear from target discovery. Add an owned historical artifact
  ledger/discovery path before claiming reactivation is reachable. Detail by real
  artifact ID already reads historical records, but supports only SQL artifacts.
- `validation/read_service.py` applied ledger retains inactive Groups/Checks;
  eligibility/currentness reads remain separate. Preserve this distinction.
- `domain/modeling_records.py` and `database/10_workflow_code_validation.sql` have
  **no lock fields** on Generated Code, its source assignments, Validation Groups
  or Checks. The public Code/Validation DTOs agree. All-four-action support needs
  an explicit fresh-install schema + canonical/snapshot/materializer/authoring/
  plugin parity + read-contract slice. Do not manufacture lock state in the UI or
  report those families as fully fixed with status actions alone.
- Existing review locks Model first, then `tenant_model_write` authorization
  obtains Tenant Lock SHARE (`database/03_security.sql`). The plain running-Tenant
  check can race a different Model's start, whose Tenant Lock is also SHARE.
  Before expanding this boundary, serialize the same Tenant fence exclusively,
  before write authorization (no SHARE-to-UPDATE upgrade), preserving Model-first
  ordering used by Run start. Verify concurrent different-Model start/review and
  physical-review interleavings with disposable DB fixtures.
  Root correction: the web role must not gain direct Tenant Lock UPDATE rights
  merely to obtain this fence. Reuse a governed SQL boundary or add a narrow
  protected authorization/fence function. Do not change global authorization
  SHARE semantics without auditing every caller and lock order.

First implementation gate: actual field-only multi-family lifecycle round trips,
the reproduced Attribute/Binding coverage case, locked hidden dependencies,
reactivation ambiguity, inactive discovery, exact replay/stale plan, owned IDs,
cross-Tenant denial, no-running-Run concurrency, and byte-for-byte unchanged
content/provenance/nested evidence. Add UI only after the corresponding backend
family passes; keep canonical validation unchanged.
