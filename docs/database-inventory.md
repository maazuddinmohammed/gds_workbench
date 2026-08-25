# Database inventory

## Scope and reading order

This inventories the current repository-defined PostgreSQL 18 database: the
objects installed by `database/01_reference.sql` through
`database/12_runtime_integrity.sql`. It excludes seed data, preflight and
verification queries, and disabled SQL under
`database/archived_functions_triggers/`.

Inventory totals: **93 tables, 71 functions, and 16 installed triggers**.

Read the schemas in dependency order:

`reference` → `core` → `security` → `model` → `workflow` → `application` / `mcp`

General rules: every table has a primary key; generated numeric IDs are
database-owned; foreign keys use `ON DELETE NO ACTION`; lifecycle changes are
retained rather than cascade-deleted.

## 1. Tables

### `reference` — shared lookup vocabulary (18)

- `reference.environment` — Deployment/runtime environments used when resolving environment-specific connection configuration.
- `reference.system_type` — Allowed classifications for Systems.
- `reference.zone` — Physical data zones, chiefly Source, Bronze, Silver, and Gold.
- `reference.connection_type` — Allowed connection technology/type classifications.
- `reference.object_type` — Allowed physical Object kinds, such as table or view.
- `reference.connection_parameter` — Allowed connection-setting names and whether each is Key Vault-backed.
- `reference.purge_policy` — Shared purge-policy vocabulary.
- `reference.system_notebook` — Shared notebook-definition/type vocabulary.
- `reference.location_type` — Shared storage-location role/type vocabulary.
- `reference.file_type` — Shared source-file format vocabulary.
- `reference.domain` — Shared business-domain vocabulary.
- `reference.data_operation` — Shared source/target operation vocabulary used by Copy configuration.
- `reference.chunk_type` — Shared Copy chunking-strategy vocabulary.
- `reference.pipeline` — Named pipelines and their optional parent-pipeline hierarchy.
- `reference.process_type` — Shared Process executable/type vocabulary.
- `reference.currency` — Currency codes and names.
- `reference.job_type` — Shared job/workload type vocabulary.
- `reference.lane` — Shared lane/routing vocabulary.

### `core` — ownership, physical metadata, ingestion, and processing (18)

- `core.project` — Administrative parent grouping for Tenants; it is not a governed Model.
- `core.tenant` — Primary ownership and authorization scope, including catalogs, visibility, and its GDS Connection.
- `core.system` — Registered source or target System, classified by System Type.
- `core.system_notebook_path` — One configured notebook path per System and notebook definition.
- `core.connection` — Tenant/System connection metadata, connection type, GDS flag, foreign catalog, and optional test batch settings.
- `core.tenant_metadata_discovery_scope` — Active assignment of one GDS Connection/Zone/schema tuple to one source Tenant.
- `core.connection_location` — Environment-specific storage account, secret reference, container, and path for a Connection.
- `core.connection_value` — Environment-specific raw connection parameter values; direct runtime reads are restricted.
- `core.object` — Registered physical relation, its Connection, schema/name, Zone, type, batch field, lock, and lifecycle.
- `core.attribute` — Registered physical column/field, type, ordinal, nullability, key/masking/purge flags, and lifecycle.
- `core.ingestion_object_mapping` — Active or retained source-Object to target-Object ingestion lineage.
- `core.ingestion_attribute_mapping` — Source-Attribute to target-Attribute lineage under an Object ingestion mapping.
- `core.copy_group` — Tenant/System grouping of ordered Copy definitions.
- `core.member_group` — Optional Tenant/System member partition with an initial-load date.
- `core.copy_group_control` — Run-control state joining a Copy Group to an optional same-scope Member Group.
- `core.copy` — Ordered Copy configuration: ingestion mapping, scripts/files, chunking, limits, and source/target operations.
- `core.process_group` — Tenant/System/Zone processing group tied to a Copy Group.
- `core.process` — Ordered executable/location that processes one registered Object within a Process Group.

### `security` — identity, access, and Tenant Locks (5)

- `security.principal` — Internal user or service Principal, active state, Entra application shape, and explicit Super Admin flag.
- `security.entra_principal_identity` — Unique Entra tenant/object identity mapped to one typed Principal.
- `security.tenant_principal_access` — Tenant role grant (`viewer`, `developer`, `architect`, or `tenant_admin`) with optional expiry.
- `security.tenant_lock` — Current database-time write lease for a Tenant; at most one active row per Tenant.
- `security.tenant_lock_event` — Append-style audit history for acquired, renewed, released, overridden, and expired locks.

### `model` — governed Model aggregate and audit (6)

- `model.model` — Tenant-owned Model, current revision, naming/audit policies, default agent settings, and active state.
- `model.model_scope` — Retained membership between a Model and allowed physical Objects, including business lock and lifecycle.
- `model.model_event_log` — Append-only safe workflow progress, warning, blocked, completion, and failure events.
- `model.modeling_assertion_document` — Metadata for an Assertion source document; original bytes are not stored.
- `model.modeling_assertion_record` — Structured factual Assertion records, applicable layers, confidence, lifecycle, and lock.
- `model.model_revision_transaction` — One transaction witness for each actual Model revision advance.

### `workflow` — applied modeling graph (22)

- `workflow.attribute_profile` — Current per-Model/per-Attribute profiling metrics and source-context provenance.
- `workflow.analysis_result` — Inferred physical relationship plus validation policy, evidence counts, result, provenance, lifecycle, and lock.
- `workflow.conceptual_object` — Conceptual business object, type, grain, aliases, confidence, lifecycle, and lock.
- `workflow.conceptual_relationship` — Typed/cardinal conceptual relationship between two Conceptual Objects.
- `workflow.conceptual_support` — Typed physical Object or Assertion support for one Conceptual Object or Relationship.
- `workflow.logical_submodel` — Named logical grouping within a Model.
- `workflow.logical_entity` — Logical entity, type, grain, dependency order, confidence, lifecycle, and lock.
- `workflow.logical_entity_submodel` — Retained membership between a Logical Entity and Logical Submodel.
- `workflow.logical_attribute` — Logical field with data type, ordinal, nullability, key roles, audit role, lifecycle, and lock.
- `workflow.logical_entity_source_mapping` — Ordered physical Bronze Object or Assertion support for a Logical Entity.
- `workflow.logical_attribute_source_mapping` — Ordered physical Bronze Attribute path or Assertion support for a Logical Attribute.
- `workflow.logical_relationship` — Attribute-level relationship between two same-Model Logical Entities.
- `workflow.dimensional_submodel` — Named dimensional grouping within a Model.
- `workflow.dimensional_entity` — Fact, Dimension, or Bridge with grain, dependency order, confidence, lifecycle, and lock.
- `workflow.dimensional_entity_submodel` — Retained membership between a Dimensional Entity and Dimensional Submodel.
- `workflow.dimensional_attribute` — Dimensional field with key/measure roles, grain/additivity/change behavior, lifecycle, and lock.
- `workflow.dimensional_entity_source_mapping` — Ordered eligible Silver Object or Assertion support for a Dimensional Entity.
- `workflow.dimensional_attribute_source_mapping` — Ordered eligible Silver Attribute path or Assertion support for a Dimensional Attribute.
- `workflow.dimensional_relationship` — Typed, cardinal, optional Attribute-level relationship between Dimensional Entities.
- `workflow.mapping_source_system_dependency` — Per-Model/layer ordering and lifecycle of source Systems used by Mapping.
- `workflow.mapping_object` — Logical-to-Silver or Dimensional-to-Gold Object mapping header, package/profile, transformation, output template, lifecycle, and lock.
- `workflow.mapping_attribute` — Modeled Attribute to physical target Attribute mapping and transformation under a Mapping Object.

### `application` — web preferences, authoring configuration, and run orchestration (15)

- `application.principal_preference` — One Principal’s last authorized Tenant selection.
- `application.workflow_stage` — Ordered stage definition for a workflow/execution-mode pair, including whether it is agentic.
- `application.workflow_stage_variable` — Ordered typed variable contract for one Workflow Stage.
- `application.prompt_template` — Global or Tenant-owned prompt identity for one agentic Workflow Stage.
- `application.prompt_template_version` — Draft/published/retired prompt content version with a content digest.
- `application.prompt_assignment` — Active or retained global/model default assignment of a published prompt version to a stage.
- `application.output_template` — Immutable-schema, Super-Admin-defined transformation output contract for Mapping Object or Attribute output.
- `application.output_template_field` — Ordered typed fields that make up an Output Template schema.
- `application.sql_generation_guide` — Named global SQL generation guidance identity; one active guide may be default.
- `application.sql_generation_guide_version` — Draft/published/retired guide content and digest.
- `application.workflow_run` — Durable immutable run request plus state, actor, frozen Model revision, selection digest, agent/mapping/guide inputs, claim lease, and outcome.
- `application.workflow_run_object_selection` — Immutable ordered Object selection frozen for one Workflow Run.
- `application.workflow_run_mapping_target_selection` — Immutable ordered target Object/source System pair frozen for a Mapping Run.
- `application.workflow_run_prompt_snapshot` — Immutable resolved prompt version/digest per agentic stage for one Run.
- `application.generated_sql_artifact` — One current generated SQL artifact per Model/layer/target, bound to Model, Mapping, source, guide, generator, and optional Run provenance.

### `mcp` — governed draft transport and audit (9)

- `mcp.model_change_set` — Model-owned eight-section draft, revision/digest seal, validation, expiry, workflow binding, and terminal state.
- `mcp.model_stage_batch` — Manifest and lifecycle for a chunked Model Change Set dataset upload.
- `mcp.model_stage_chunk` — Ordered, hashed JSON record chunk for a Model Stage Batch.
- `mcp.model_change_set_event` — Ordered retained lifecycle/validation/apply event for a Model Change Set.
- `mcp.metadata_change_set` — Tenant-owned sixteen-dataset physical metadata draft, revision/digest seal, validation, expiry, and terminal state.
- `mcp.metadata_stage_batch` — Manifest and lifecycle for a chunked Metadata Change Set dataset.
- `mcp.metadata_stage_chunk` — Ordered, hashed JSON record chunk for a Metadata Stage Batch.
- `mcp.metadata_change_set_event` — Ordered retained lifecycle/stage/validation/apply/archive event for a Metadata Change Set.
- `mcp.tool_call_log` — Append-only safe audit metadata for completed MCP tool calls; it stores no raw prompt, output, or physical rows.

## 2. Functions

Each entry gives purpose, then execution order.

### `reference` (1)

- `reference.is_nonblank` — Shared immutable text validator. Steps: (1) reject `NULL`; (2) trim surrounding whitespace; (3) return whether any character remains.

### `security` (7)

- `security.authorize_tenant_operation` — Central authorization decision for a server-selected policy. Steps: (1) validate Principal type and policy; (2) resolve one active Entra identity and Principal; (3) resolve the active Tenant and effective role, including global read visibility and Super Admin; (4) compare role rank with policy; (5) for metadata/model writes, require the caller-owned unexpired Tenant Lock; (6) return an authorization decision and bounded denial/lock metadata.
- `security.check_tenant_lock` — Read the active lock visible to an authorized lock manager. Steps: (1) authorize `tenant_lock_manage`; (2) find an unexpired Tenant Lock; (3) return unlocked state or owner, purpose, times, and whether the caller owns it.
- `security.acquire_tenant_lock` — Acquire a bounded Tenant write lease. Steps: (1) validate 1–240 minute duration and optional purpose; (2) lock the Tenant and authorize; (3) audit and remove a stale existing lock; (4) reject a live lock; (5) insert the new lock; (6) append an `acquired` event and return it.
- `security.override_tenant_lock` — Force-release another Principal’s lock without acquiring a replacement. Steps: (1) require a reason and authorize lock management; (2) lock/read the current row; (3) audit/remove it as expired when stale; (4) reject no lock or the caller’s own live lock; (5) append `force_unlocked`; (6) remove the lock and return prior state.
- `security.renew_tenant_lock` — Renew only the caller-owned live lock. Steps: (1) validate duration and authorize; (2) lock/read current state; (3) audit/remove stale state; (4) reject missing or other-owned lock; (5) reset acquired/expiry times; (6) append `renewed` and return the lease.
- `security.release_tenant_lock` — Release only the caller-owned live lock. Steps: (1) authorize; (2) lock/read current state; (3) audit/remove stale state; (4) reject missing or other-owned lock; (5) append `released`; (6) remove and return prior lease times.
- `security.expire_tenant_locks` — Bounded concurrency-safe expiry worker. Steps: (1) validate batch limit 1–1000; (2) select expired locks in expiry order with `FOR UPDATE SKIP LOCKED`; (3) append one `expired` event per lock; (4) remove each lock; (5) return the count.

### `model` (1)

- `model.reject_model_event_log_mutation` — Trigger function enforcing append-only Model events. Steps: (1) receive an UPDATE, DELETE, or TRUNCATE attempt; (2) raise an exception; (3) allow no mutation.

### `workflow` (4)

- `workflow.list_tenant_visible_objects` — Canonical Tenant-visible Object closure. Steps: (1) resolve each Object’s owning Tenant, using active discovery assignment for GDS Objects; (2) seed owned, discovered, Copy-referenced, Process-referenced, and current Model Scope Objects; (3) recursively traverse active ingestion mappings; (4) return each reachable Object with reason flags.
- `workflow.list_model_object_eligibility` — Canonical Object-level workflow eligibility for one active Model. Steps: (1) read active Model Scope and physical metadata; (2) resolve Object Tenant safely; (3) classify Zone; (4) mark Bronze source eligibility; (5) mark Silver dimensional-source eligibility only when effective Logical Mapping exists; (6) mark Silver/Gold Mapping target eligibility and return ordered rows.
- `workflow.list_code_generation_target_context` — Canonical complete SQL Mapping context per target. Steps: (1) start from eligible Silver/Gold targets for the requested modeled layer; (2) retain active, complete SQL Mapping headers, dependencies, entities, and child mappings; (3) reject targets having incomplete active mappings; (4) aggregate ordered source Systems, Object mappings, Attribute mappings, entity support, target metadata, and transformations; (5) hash Mapping-only and full source contexts; (6) return one row per target.
- `workflow.list_model_attribute_eligibility` — Attribute-level extension of Object eligibility. Steps: (1) call Object eligibility; (2) join active Attributes; (3) inherit Bronze and target flags; (4) mark Silver dimensional-source eligibility only when an effective Logical Attribute Mapping exists; (5) return deterministically ordered rows.

### `application` — preference and Model authoring (5)

- `application.set_principal_last_tenant` — Save the caller’s last authorized Tenant. Steps: (1) authorize Tenant read; (2) insert or update the Principal preference; (3) refresh access/audit time; (4) return the row.
- `application.create_model` — Governed web Model creation. Steps: (1) authorize `tenant_model_write`, including owned lock; (2) insert the Model and policies/default agent settings; (3) record `web_model_create` revision transaction; (4) return the Model.
- `application.update_model` — Revision-fenced Model update. Steps: (1) lock active Model; (2) authorize against its Tenant; (3) verify expected revision; (4) return unchanged row for an exact no-op; (5) update fields and increment revision; (6) record `web_model_update` and return.
- `application.archive_model` — Revision-fenced soft archive. Steps: (1) lock active Model; (2) authorize and verify revision; (3) set inactive and increment revision; (4) record `web_model_archive`; (5) return archived Model.
- `application.replace_model_scope` — Replace the complete active Model Scope. Steps: (1) validate a unique bounded Object ID set; (2) lock Model, authorize, and verify revision; (3) verify every Object is active in the canonical Tenant-visible closure; (4) return no-op if identical; (5) deactivate absent rows and insert/reactivate selected rows; (6) increment Model revision, record the revision transaction, and return counts.

### `application` — prompts (7)

- `application.guard_prompt_template` — Protect Prompt Template identity. Steps: (1) reject DELETE; (2) compare identity/creator fields on UPDATE; (3) reject identity changes; (4) allow mutable descriptive/lifecycle fields.
- `application.guard_prompt_template_version` — Protect prompt content versions and digest. Steps: (1) reject DELETE; (2) recompute digest from the three prompt texts; (3) validate it on INSERT/UPDATE; (4) freeze version identity; (5) allow only draft edits or draft→published→retired; (6) keep published content and retired rows immutable.
- `application.validate_prompt_assignment` — Validate direct assignment writes. Steps: (1) allow a shape-preserving active→inactive transition; (2) require a published version on an active agentic stage; (3) resolve active assignment actor; (4) require Super Admin/global Prompt for global default; (5) for Model default, verify Model/Tenant compatibility, Architect-or-higher authority, and caller-owned lock.
- `application.save_prompt_template` — Idempotent create/update boundary for Prompt identities. Steps: (1) resolve immutable scope/stage for updates; (2) authorize global ownership as Super Admin or Tenant ownership as model write; (3) require active agentic stage; (4) serialize same-code creates and replay exact duplicates; (5) on update enforce immutable identity, optimistic timestamp, and no active assignments before deactivation; (6) save and return.
- `application.save_prompt_template_draft` — Create or edit the single draft version. Steps: (1) validate bounded prompt text; (2) lock active template/stage and authorize by ownership; (3) compute content digest; (4) replay identical draft; (5) timestamp/ID-fence and update an existing draft, or allocate the next version and insert; (6) return the draft.
- `application.transition_prompt_template_version` — Publish or retire a prompt version. Steps: (1) lock active template and version; (2) authorize by global/Tenant ownership; (3) allow only draft→published or published→retired and replay exact target state; (4) block retirement while actively assigned; (5) write actor/time lifecycle fields and return.
- `application.set_prompt_assignment` — Replace or clear one global/model default. Steps: (1) require active agentic stage; (2) authorize global scope as Super Admin or Model scope as model write; (3) serialize the assignment key; (4) validate the target published Prompt and Tenant compatibility; (5) enforce optimistic current-assignment ID; (6) deactivate prior assignment; (7) optionally insert replacement and return.

### `application` — Mapping Output Templates (5)

- `application.guard_output_template_schema` — Freeze Output Template schema identity. Steps: (1) reject DELETE; (2) reject changes to ID, code, target type, digest, or creator identity; (3) allow only descriptive/active-state updates.
- `application.guard_output_template_field` — Make fields atomic and immutable. Steps: (1) on INSERT require the parent Template to have been created in the same transaction; (2) allow that insert; (3) reject all field UPDATE and DELETE operations.
- `application.validate_mapping_output_template` — Validate Mapping transformation JSON against its selected Template. Steps: (1) skip rows without a Template; (2) infer Object/Attribute target type; (3) require active matching Template with fields; (4) validate base schema version and transformation kind; (5) validate every required field, scalar/array type, and array item; (6) reject undeclared fields.
- `application.create_output_template` — Atomic Super-Admin Template creation. Steps: (1) authenticate active Super Admin and serialize code; (2) validate bounded nonempty field array, allowed keys/types, reserved names, examples, and unique names/orders; (3) normalize fields and compute schema digest; (4) replay an exact existing code or reject conflict; (5) insert parent and all fields in one transaction; (6) return parent.
- `application.update_output_template` — Update only descriptive/active Template state. Steps: (1) authenticate Super Admin; (2) lock Template; (3) return exact no-op; (4) enforce optimistic timestamp; (5) update name, description, actor, and active flag; (6) return.

### `application` — SQL Generation Guides (5)

- `application.guard_sql_generation_guide` — Protect Guide identity. Steps: (1) reject DELETE; (2) reject ID, code, creator, or creation-time changes; (3) allow mutable name, description, default, and active state.
- `application.guard_sql_generation_guide_version` — Protect Guide content versions. Steps: (1) reject DELETE; (2) recompute SHA-256 from content and verify digest; (3) freeze version identity; (4) allow draft edits; (5) allow only draft→published→retired; (6) keep published content and retired versions immutable.
- `application.save_sql_generation_guide` — Idempotent Super-Admin Guide create/update. Steps: (1) authenticate Super Admin and validate default must be active; (2) serialize the singleton default; (3) replay exact same-code create or reject conflict; (4) clear any prior active default when needed; (5) timestamp-fence updates and preserve code identity; (6) save and return.
- `application.save_sql_generation_guide_draft` — Create or edit the single Guide draft. Steps: (1) validate bounded nonblank content; (2) authenticate Super Admin and lock active Guide; (3) compute digest; (4) replay identical draft; (5) fence and edit existing draft, or assign next version and insert; (6) return.
- `application.transition_sql_generation_guide_version` — Publish or retire a Guide version. Steps: (1) authenticate Super Admin; (2) lock active Guide and version; (3) allow only draft→published or published→retired, with target-state replay; (4) enforce expected current status; (5) set lifecycle actor/time fields and return.

### `application` — Workflow Run control (16)

- `application.guard_workflow_run_mapping_target_selection` — Mapping-selection immutability trigger function. Steps: (1) receive UPDATE/DELETE; (2) raise; (3) preserve the frozen pair.
- `application.guard_workflow_run_object_selection` — Object-selection immutability trigger function. Steps: (1) receive UPDATE/DELETE; (2) raise; (3) preserve frozen selection.
- `application.guard_workflow_run` — Enforce Run immutability and state machine. Steps: (1) reject DELETE; (2) reject changes to frozen identity/request fields; (3) reject changes to terminal Runs; (4) while running, allow only valid lease heartbeat/recovery changes and monotonic recovery count; (5) otherwise allow only queued→running or running→terminal.
- `application.guard_workflow_run_prompt_snapshot` — Prompt-snapshot immutability trigger function. Steps: (1) receive UPDATE/DELETE; (2) raise; (3) preserve frozen resolution.
- `application.snapshot_workflow_run_prompts` — Resolve every agentic stage’s prompt once. Steps: (1) validate bounded override object and lock queued Run; (2) reject existing snapshots; (3) iterate active agentic stages in order; (4) resolve override, then Model default, then global default; (5) require published active Tenant-compatible Prompt and insert digest snapshot; (6) reject unknown overrides or no stages and return count.
- `application.create_workflow_run` — Governed, idempotent Run creation and input freeze. Steps: (1) validate workflow-specific selection, Mapping, batch, guide, prompt, and agent inputs; (2) canonicalize caller selection and compute request digest; (3) lock Model, authorize actor/identity, and replay exact correlation IDs; (4) verify revision, workflow eligibility, Mapping route/header/profile/output templates, batch System rule, and Code Generation context/guide; (5) resolve complete agent configuration; (6) insert queued Run and immutable selection rows; (7) snapshot agentic prompts; (8) return frozen run metadata.
- `application.lock_authoring_workflow_run` — Internal row-lock helper for agentic authoring. Steps: (1) match Run and Model; (2) require an authoring workflow with non-null execution mode; (3) lock the Run `FOR UPDATE`; (4) return its core identity/state.
- `application.start_workflow_run` — Start a caller-owned queued Run. Steps: (1) lock Run and active Model; (2) authorize and verify actor ownership; (3) replay non-queued state without mutation; (4) verify Model revision; (5) move to `running`; (6) append sequence-1 `started` event and return.
- `application.claim_next_workflow_run` — Worker lease allocator. Steps: (1) validate 1–300 second lease; (2) atomically fail expired claims already recovered five times and append safe failure events; (3) choose oldest eligible running Run with active unambiguous actor identity using `SKIP LOCKED`; (4) generate raw UUID token but store only SHA-256 digest; (5) set claim/expiry times and increment recovery count when reclaiming; (6) return Run, actor identity, raw token, and lease.
- `application.renew_workflow_run_claim` — Heartbeat an exact live worker lease. Steps: (1) validate Run/token/duration; (2) hash token; (3) update only matching running unexpired claim; (4) extend heartbeat/expiry; (5) raise if unavailable and return times otherwise.
- `application.release_workflow_run_claim` — Release an exact running claim. Steps: (1) validate Run/token; (2) hash and match stored digest; (3) clear all claim fields; (4) raise if unavailable; (5) return success.
- `application.assert_workflow_run_claim` — Fence final worker writes. Steps: (1) validate Run/token; (2) hash token; (3) lock the exact running, unexpired matching Run row; (4) raise on stale, wrong, expired, or terminal claim; (5) return no data.
- `application.append_workflow_run_event` — Append idempotent safe progress events. Steps: (1) validate sequence, attempt, stage, status, safe message, progress, and findings; (2) lock Run/Model, authorize, and verify owner; (3) replay an identical existing sequence or reject conflict; (4) require running/current revision and allowed attempt; (5) enforce contiguous sequence; (6) calculate percentage, insert, and return event.
- `application.complete_workflow_run` — Complete a running Run. Steps: (1) validate findings; (2) lock/authorize Run and owner; (3) reject no-op receipt conflict; (4) replay an exact prior completion; (5) verify running state and revision; (6) derive repaired/non-repaired terminal state from attempts; (7) clear claim, append final completed event, and return.
- `application.complete_authoring_workflow_run_no_op` — Atomically record an unchanged authoring Candidate. Steps: (1) validate exact Run/workflow/mode/correlation/revision/digest/final-event inputs; (2) lock/authorize Run and require no Run-bound Model Change Set; (3) replay only an exact stored receipt/event; (4) require running state, current revision, contiguous event, allowed attempt, and workflow-specific backend-validation event; (5) insert final 100% event; (6) store immutable no-op receipt, clear claim, complete Run, and return.
- `application.fail_workflow_run` — Fail a running Run safely. Steps: (1) validate bounded code/message; (2) lock/authorize Run and owner; (3) reject Runs with durable no-op or validated/applied authoring outcome; (4) replay only an exact previous failure; (5) verify running state and revision; (6) set failed state, clear claim, append failure event, and return.

### `application` — execution context and governed result storage (7)

- `application.get_profiling_execution_context` — Complete physical plan for one running Profiling Run. Steps: (1) validate Run/revision, authorize owner, and require running Profiling; (2) verify immutable selection row count; (3) require every selected Object to remain active GDS Bronze with an active discovery assignment; (4) recheck Object/Attribute eligibility and 50,000-Attribute bound; (5) return ordered catalog/schema/Object/System/batch/Attribute rows using assigned source Tenant catalogs.
- `application.get_profiling_connection_values` — All-or-nothing credentials for Profiling. Steps: (1) derive exact GDS Connections by calling the validated execution context; (2) validate and resolve active Environment; (3) snapshot host, HTTP path, and token once per Connection; (4) return one fixed safe error with no secrets if any tuple is incomplete; (5) otherwise return complete ordered tuples.
- `application.get_analysis_validation_execution_context` — Complete physical plan for deterministic Analysis validation. Steps: (1) validate/lock identity context, authorize exact owner identity, and require running deterministic Analysis/current revision/environment; (2) verify frozen selection count; (3) select active/needs-review relationships and require both endpoints selected; (4) resolve active Bronze endpoint Attributes, discovery-assigned catalogs, batch fields, and connection-value row-version witnesses; (5) compute per-relationship source-context digest; (6) reject partial endpoints, cross-Connection pairs, incomplete metadata, over 50,000 rows, or over 32 MiB; (7) return immutable ordered snapshot.
- `application.get_analysis_validation_connection_values` — All-or-nothing Analysis validation credentials. Steps: (1) derive exact Connections through the validated Analysis context; (2) validate/resolve Environment; (3) snapshot required credentials once; (4) return one fixed safe failure with no partial secrets when incomplete; (5) otherwise return complete ordered tuples.
- `application.persist_analysis_validation_results` — Atomic validation-only Analysis update. Steps: (1) validate bounded exact JSON shape, unique IDs, and internally consistent evidence counts/result; (2) lock/authorize exact running deterministic Analysis Run and current revision; (3) lock Model Analysis rows; (4) recompute expected eligible result IDs/context digests and require exact payload match; (5) update only validation provenance/policy/evidence columns, preserving inference, status, and locks; (6) advance Model revision once and record transaction only when rows changed; (7) return counts/revision.
- `application.persist_profiling_results` — Atomic replacement of selected Attribute Profiles. Steps: (1) validate bounded exact JSON shape and unique Attribute IDs; (2) lock/authorize running Profiling Run and current revision; (3) freeze selected Object/Attribute membership and recheck Bronze eligibility; (4) require payload to exactly cover eligible Attributes; (5) delete obsolete Profiles only within selected Objects and upsert submitted metrics; (6) advance Model revision once and record transaction only when changed; (7) return counts/revision.
- `application.store_generated_sql_artifact` — Only governed generated-SQL write boundary. Steps: (1) require active Model at expected revision and authorize caller-owned lock; (2) resolve exact active actor identity; (3) recompute target Mapping/source contexts and compare both digests; (4) for a Run-bound write, require matching running Code Generation Run/selection/frozen Guide; otherwise require current active published Guide; (5) recompute SQL digest; (6) insert or replace the one current Model/layer/target artifact and return it.

### `mcp` (13)

- `mcp.guard_model_change_set_workflow_binding` — Freeze a Model Change Set’s optional Workflow Run binding. Steps: (1) compare old/new `workflow_run_id`; (2) raise if changed; (3) allow other updates.
- `mcp.create_metadata_change_set` — Create one ongoing Tenant draft per Principal. Steps: (1) lock active Tenant and authorize metadata write/owned lock; (2) find any creator-owned active/validated draft; (3) return it with `metadata_change_set_exists` if present; (4) insert a new empty sixteen-dataset draft; (5) append sequence-1 `created` event; (6) return state and expiry.
- `mcp.stage_metadata_change_set` — Replace one or more complete Metadata datasets. Steps: (1) validate bounded object containing only the 16 allowed array datasets; (2) authorize metadata write and lock creator-owned draft; (3) require active/validated state and expected draft revision; (4) replace only supplied arrays; (5) reset validation, increment draft revision once, and refresh four-hour expiry; (6) append dataset-count event and return.
- `mcp.begin_metadata_stage_batch` — Start/replay a chunk manifest for one dataset. Steps: (1) validate dataset, counts, digest, and revision; (2) authorize and lock creator-owned active draft; (3) expire stale active batches for the same dataset; (4) replay identical active manifest or return conflict; (5) insert new batch bounded by draft expiry; (6) return manifest/progress.
- `mcp.put_metadata_stage_chunk` — Add one immutable chunk. Steps: (1) validate index, digest, nonempty bounded JSON array; (2) authorize and lock draft/batch; (3) require active unexpired matching state, revision, dataset, and index; (4) replay exact existing chunk or reject conflict; (5) prevent cumulative record overflow; (6) insert chunk, refresh batch activity, and return progress.
- `mcp.commit_metadata_stage_batch` — Assemble and commit a complete batch. Steps: (1) authorize and lock creator-owned draft/batch; (2) replay already committed batch; (3) require active unexpired states and exact revision; (4) verify chunk count, record count, and hash of ordered chunk digests; (5) concatenate records in chunk/index order and enforce size; (6) call `stage_metadata_change_set` once; (7) mark batch committed with resulting revision/expiry and return.
- `mcp.get_metadata_change_set` — Creator-scoped draft read. Steps: (1) authorize Tenant lock-management capability without requiring lock ownership; (2) return the exact creator/Tenant draft with all 16 documents and lifecycle fields; (3) otherwise return a bounded denial/not-found row.
- `mcp.record_metadata_change_set_validation` — Seal or unseal validation result. Steps: (1) validate revision, outcome object, and success/digest shape; (2) authorize metadata write and lock creator-owned draft; (3) require active/validated state and expected revision; (4) set `validated` plus candidate digest on success, or return to `active` on failure; (5) store outcome, refresh expiry, and append validation event; (6) return seal state.
- `mcp.archive_metadata_change_set` — Retained terminal archive. Steps: (1) authorize lock-management capability and lock creator-owned draft; (2) require active/validated state and expected revision; (3) set `archived`, terminal/activity times, and expiry; (4) append `archived` event; (5) return terminal state.
- `mcp.get_databricks_sql_connection_values` — Exact secret-bearing lookup for governed Databricks SQL. Steps: (1) validate source Connection and Environment input; (2) require active non-GDS source Connection and active Tenant; (3) follow Tenant’s configured active GDS Connection; (4) resolve active Environment; (5) read host/path/token; (6) return one safe failure with no partial values or the complete tuple.
- `mcp.reject_tool_call_log_mutation` — Trigger function enforcing append-only MCP audit. Steps: (1) receive UPDATE, DELETE, or TRUNCATE; (2) raise; (3) allow no mutation.
- `mcp.apply_metadata_change_set` — Atomic natural-key application of a validated Metadata draft. Steps: (1) authorize metadata write and lock creator-owned draft; (2) require `validated` state plus exact revision/candidate digest; (3) lock all existing touched Objects and fail on business locks; (4) defer ordinal constraints; (5) resolve natural keys and upsert all 16 datasets in dependency order: Objects, Attributes, both ingestion mappings, Copy Group, Member Group, Copy Group Control, Copy, Process Group, Process; (6) verify each affected count so changed dependencies abort transaction; (7) mark draft `applied`, append event, and return total actions.
- `mcp.runtime_readiness` — Read-only MCP runtime posture contract. Steps: (1) report schema version and PostgreSQL major; (2) verify required schemas, relations, columns, constraints, and indexes; (3) verify runtime login attributes and sole `gds_app_write` membership; (4) verify exact required and forbidden table/function/column privileges; (5) smoke-test governed query contracts with impossible IDs; (6) return booleans only.

## 3. Installed triggers

All are `BEFORE` triggers. “Row” means once per affected row; “statement” means once for the whole statement.

- `reject_model_event_log_mutation` on `model.model_event_log` — UPDATE/DELETE/TRUNCATE, statement. Steps: (1) intercept mutation; (2) call `model.reject_model_event_log_mutation`; (3) raise, keeping the log append-only.
- `guard_prompt_template` on `application.prompt_template` — UPDATE/DELETE, row. Steps: (1) intercept; (2) call `application.guard_prompt_template`; (3) reject DELETE or identity changes; (4) permit allowed descriptive/lifecycle update.
- `guard_prompt_template_version` on `application.prompt_template_version` — INSERT/UPDATE/DELETE, row. Steps: (1) recompute/verify digest; (2) reject DELETE/identity changes; (3) enforce draft→published→retired; (4) freeze published content and retired rows.
- `validate_prompt_assignment` on `application.prompt_assignment` — INSERT/UPDATE, row. Steps: (1) resolve version/template/stage; (2) require published active agentic Prompt; (3) enforce global Super Admin or Model Tenant authority/lock; (4) allow valid row.
- `guard_output_template_schema` on `application.output_template` — UPDATE/DELETE, row. Steps: (1) reject DELETE; (2) compare immutable schema identity/digest; (3) reject schema mutation; (4) allow descriptive/active update.
- `guard_output_template_field` on `application.output_template_field` — INSERT/UPDATE/DELETE, row. Steps: (1) allow INSERT only in parent’s creation transaction; (2) reject later INSERT; (3) reject every UPDATE/DELETE.
- `validate_mapping_object_output_template` on `workflow.mapping_object` — INSERT or relevant-column UPDATE, row. Steps: (1) call shared Mapping Template validator; (2) require Object target type and valid transformation document; (3) validate declared field shape/types; (4) accept or abort.
- `validate_mapping_attribute_output_template` on `workflow.mapping_attribute` — INSERT or relevant-column UPDATE, row. Steps: (1) call shared validator; (2) require Attribute target type and valid transformation document; (3) validate declared field shape/types; (4) accept or abort.
- `guard_sql_generation_guide` on `application.sql_generation_guide` — UPDATE/DELETE, row. Steps: (1) reject DELETE; (2) reject Guide identity changes; (3) allow mutable descriptive/default/active update.
- `guard_sql_generation_guide_version` on `application.sql_generation_guide_version` — INSERT/UPDATE/DELETE, row. Steps: (1) verify content digest; (2) reject DELETE/identity change; (3) enforce draft→published→retired; (4) freeze published content and retired rows.
- `guard_workflow_run_mapping_target_selection` on `application.workflow_run_mapping_target_selection` — UPDATE/DELETE, row. Steps: (1) intercept; (2) raise unconditionally; (3) keep target/System pair immutable.
- `guard_workflow_run_object_selection` on `application.workflow_run_object_selection` — UPDATE/DELETE, row. Steps: (1) intercept; (2) raise unconditionally; (3) keep selected Objects immutable.
- `guard_workflow_run` on `application.workflow_run` — UPDATE/DELETE, row. Steps: (1) reject DELETE and frozen-request mutation; (2) reject terminal mutation; (3) validate claim recovery/rotation while running; (4) enforce queued→running→terminal state flow.
- `guard_workflow_run_prompt_snapshot` on `application.workflow_run_prompt_snapshot` — UPDATE/DELETE, row. Steps: (1) intercept; (2) raise unconditionally; (3) preserve the exact prompt version/digest used by the Run.
- `guard_model_change_set_workflow_binding` on `mcp.model_change_set` — UPDATE, row. Steps: (1) compare Workflow Run binding; (2) reject any change; (3) allow unrelated Model Change Set updates.
- `reject_tool_call_log_mutation` on `mcp.tool_call_log` — UPDATE/DELETE/TRUNCATE, statement. Steps: (1) intercept mutation; (2) call `mcp.reject_tool_call_log_mutation`; (3) raise, keeping audit rows append-only.

## 4. Explicit exclusions

- `database/archived_functions_triggers/*.sql.disabled` contains draft behavior and is not installed.
- `database/seed/` changes data only; it defines no current schema inventory.
- `database/00_preflight.sql` and `database/13_verify_install.sql` inspect installation safety/posture; they do not add persistent tables, functions, or triggers.
- Views, indexes, sequences, constraints, roles, and grants are outside this requested inventory.
