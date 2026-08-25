# Release 1 invariant traceability

> Historical release-planning evidence. Entries referring to Workflow Grants,
> Tenant Lease exclusion, the former 22-tool registry, or missing test paths do
> not describe the current scaffold. Current authorization evidence is
> `tests/mcp/test_database_authorization.py`; see
> [ADR 001](adr/001-direct-principal-authorization-and-tenant-locks.md).

This is the canonical Release 1 traceability map required by Section 16.1 of
`IMPLEMENTATION_PLAN.md`. `PASS` records focused local evidence for the cited
invariant; it does not claim that the aggregate clean-checkout T24 gate has
passed. Environment evidence remains `EXTERNAL (T25)` until the separately
authorized Azure/App Service/Databricks smoke is actually run.

Each row names a positive path and a distinct negative path. SQL references are
the exact labels passed to the fixture's fail-closed `expect_error` helper.

Disposable-database regression evidence on 2026-08-24 is 280 passing MCP
database tests and 36 passing web-backend database tests, each against only the
fixture-created random PostgreSQL container. Ruff format/check passes for the
five corrected fixture files. Strict Pyright is not recorded as passing: the
current aggregate command reports 555 errors outside the corrected SQL fixture
rows, so this evidence does not claim the aggregate T24 gate is complete.

| ID | Invariant | Source | Accepting test | Rejecting test | Owner | Local | Environment |
|---|---|---|---|---|---|---|---|
| INV-01 | PostgreSQL is authoritative for applied state, drafts, grants, staging, receipts, and events. | IMPLEMENTATION_PLAN.md §6, invariant 1 | `tests/mcp/infrastructure/test_postgres_repository.py::test_application_change_set_apply_and_replay_are_atomic` | `tests/mcp/infrastructure/test_postgres_repository.py::test_rollback_removes_artifact_receipt_and_revision` | T03–T07, T10, T13–T14 | PASS | EXTERNAL (T25) |
| INV-02 | Every Model-owned row has `model_id`. | IMPLEMENTATION_PLAN.md §6, invariant 2 | `tests/database/behavior_assertions.sql::behavior assertions passed` | `tests/database/behavior_assertions.sql::cross-Model Conceptual endpoint` | T03–T07 | PASS | EXTERNAL (T25) |
| INV-03 | Every Model-owned parent/child foreign key includes `model_id`. | IMPLEMENTATION_PLAN.md §6, invariant 3 | `tests/database/test_schema_static.py::test_model_owned_integrity_revision_and_locks_have_database_guards` | `tests/database/behavior_assertions.sql::cross-Model Conceptual endpoint` | T03–T07 | PASS | EXTERNAL (T25) |
| INV-04 | Object/Attribute pairs are enforced relationally. | IMPLEMENTATION_PLAN.md §6, invariant 4 | `tests/mcp/application/test_service_readiness_and_lifecycle.py::test_mapping_readiness_requires_header_target_and_source_system_lineage` | `tests/mcp/application/test_service_readiness_and_lifecycle.py::test_readiness_and_authorization_share_exact_physical_validation` | T03, T05, T07, T09, T11, T15 | PASS | EXTERNAL (T25) |
| INV-05 | Stable server-generated IDs are persisted; names are never relational mutation identity. | IMPLEMENTATION_PLAN.md §6, invariant 5 | `tests/mcp/application/test_compiler_contracts.py::test_typed_local_references_resolve_before_persistence` | `tests/workflows/test_mapping_generator_safety.py::test_generator_safety_rejects_database_ids_and_secret_shaped_values` | T02, T11–T15, T17–T23 | PASS | EXTERNAL (T25) |
| INV-06 | Applied lifecycle uses exactly active, needs_review, inactive, and deprecated. | IMPLEMENTATION_PLAN.md §6, invariant 6 | `tests/contracts/mcp/test_models.py::test_lifecycle_vocabulary_is_exact` | `tests/mcp/application/test_compiler_contracts.py::test_evidence_document_rejects_unsupported_lifecycle_during_validation` | T02–T07, T11 | PASS | EXTERNAL (T25) |
| INV-07 | Candidate state exists only in unapplied in-memory/change-set content. | IMPLEMENTATION_PLAN.md §6, invariant 7 | `tests/mcp/application/test_change_sets.py::test_change_set_cas_validate_apply_and_replay` | `tests/database/behavior_assertions.sql::idempotency outcome append-only` | T06, T10–T13 | PASS | EXTERNAL (T25) |
| INV-08 | Omission means unchanged; no workflow infers retirement from omission. | IMPLEMENTATION_PLAN.md §6, invariant 8 | `tests/mcp/application/test_change_sets.py::test_empty_candidate_is_noop_and_omission_preserves_applied_state` | `tests/workflows/test_analysis_modes.py::test_selected_extend_cannot_omit_existing_outgoing_relationship` | T11–T13, T18–T23 | PASS | EXTERNAL (T25) |
| INV-09 | Physical deletion is outside automated workflows. | IMPLEMENTATION_PLAN.md §6, invariant 9 | `tests/contracts/mcp/test_registry.py::test_forbidden_public_surface_is_absent` | `tests/database/test_schema_static.py::test_foreign_keys_are_non_cascading_and_fresh_only` | T07, T13, T18–T23 | PASS | EXTERNAL (T25) |
| INV-10 | Locked curated rows and protected descendants are immutable through every write path. | IMPLEMENTATION_PLAN.md §6, invariant 10 | `tests/mcp/application/test_locked_immutability_acceptance.py::test_omitting_a_locked_artifact_preserves_it_byte_for_byte` | `tests/mcp/application/test_change_sets.py::test_locked_artifact_reports_validation_issue`<br>`tests/workflows/test_logical_workflow.py::test_locked_aggregate_and_dependency_cycle_block_compilation` | T04–T07, T12–T13, T21 | PASS | EXTERNAL (T25) |
| INV-11 | Validation reports every safely discoverable issue and performs no effective Model write. | IMPLEMENTATION_PLAN.md §6, invariant 11 | `tests/mcp/application/test_change_sets.py::test_change_set_cas_validate_apply_and_replay` | `tests/mcp/application/test_compiler_contracts.py::test_compiler_rejects_incomplete_documents_and_wrong_section_families` | T11–T12 | PASS | EXTERNAL (T25) |
| INV-12 | Apply revalidates the exact candidate and commits all sections or none. | IMPLEMENTATION_PLAN.md §6, invariant 12 | `tests/mcp/infrastructure/test_postgres_repository.py::test_application_change_set_apply_and_replay_are_atomic` | `tests/mcp/infrastructure/test_postgres_repository.py::test_rollback_removes_artifact_receipt_and_revision` | T07, T12–T13 | PASS | EXTERNAL (T25) |
| INV-13 | One effective transaction increments `model_revision` once; no-op, draft, read, put, and validation operations do not. | IMPLEMENTATION_PLAN.md §6, invariant 13 | `tests/mcp/application/test_workflow_grants_profiling.py::test_profiling_partial_failure_preserves_prior_profile_and_increments_once` | `tests/mcp/application/test_workflow_grants_profiling.py::test_all_failed_profiling_commits_failed_receipt_and_replays_without_revision` | T03, T07, T10, T13–T14 | PASS | EXTERNAL (T25) |
| INV-14 | Same-Model commits serialize on the Model row; different Models may commit concurrently. | IMPLEMENTATION_PLAN.md §6, invariant 14 | `tests/mcp/infrastructure/test_postgres_repository.py::test_apply_holds_model_row_fence_against_concurrent_deactivation` | `tests/mcp/infrastructure/test_postgres_repository.py::test_model_lock_fences_direct_dml_and_narrow_lock_commands` | T07, T13 | PASS | EXTERNAL (T25) |
| INV-15 | Routine modeling never uses the long-lived Tenant Lease. | IMPLEMENTATION_PLAN.md §6, invariant 15 | `tests/contracts/mcp/test_registry.py::test_public_tool_inventory_is_exact_and_disjoint` | `tests/contracts/mcp/test_registry.py::test_forbidden_public_surface_is_absent` | T07, T15, T17 | PASS | EXTERNAL (T25) |
| INV-16 | Source-context changes are detected by deterministic digest rather than stale snapshots. | IMPLEMENTATION_PLAN.md §6, invariant 16 | `tests/workflows/adapters/test_snapshot_projection.py::test_verified_snapshot_projects_profiles_and_full_evidence_records` | `tests/workflows/adapters/test_snapshot_projection.py::test_snapshot_rejects_outer_and_inner_digest_tampering`<br>`tests/mcp/application/test_change_sets.py::test_context_drift_invalidates_sealed_candidate` | T02, T09, T12–T13, T17 | PASS | EXTERNAL (T25) |
| INV-17 | Tenant/Model ownership and actor identity are derived server-side. | IMPLEMENTATION_PLAN.md §6, invariant 17 | `tests/mcp/application/test_change_sets.py::test_apply_receipt_persists_the_actual_human_applier` | `tests/mcp/application/test_change_sets.py::test_same_mutation_content_and_key_cannot_replay_across_human_actors` | T08–T15 | PASS | EXTERNAL (T25) |
| INV-18 | Source catalog discovery is open to active authenticated users; private Model/draft access is not. | IMPLEMENTATION_PLAN.md §6, invariant 18 | `tests/workflows/unit/test_source_catalog.py::test_source_catalog_accepts_a_sorted_transitive_lineage_closure` | `tests/mcp/application/test_catalog_snapshot.py::test_catalog_is_open_but_model_is_owning_tenant_private` | T08–T09, T15 | PASS | EXTERNAL (T25) |
| INV-19 | Only effective architects, Tenant Admins, or super admins can validate, apply, or lock Model changes. | IMPLEMENTATION_PLAN.md §6, invariant 19 | `tests/mcp/application/test_change_sets.py::test_change_set_cas_validate_apply_and_replay` | `tests/mcp/infrastructure/test_postgres_repository.py::test_inactive_tenant_removes_membership_and_denies_mutation_and_lock_commands` | T08, T10–T15 | PASS | EXTERNAL (T25) |
| INV-20 | Workflow grants bind the human, Model, run, selection, operations, workload identity, and expiry. | IMPLEMENTATION_PLAN.md §6, invariant 20 | `tests/mcp/application/test_service_readiness_and_lifecycle.py::test_completed_mapping_contract_requires_exact_applied_materialization_binding` | `tests/mcp/application/test_service_readiness_and_lifecycle.py::test_completed_non_mapping_contract_is_not_readable` | T06, T08, T15, T17 | PASS | EXTERNAL (T25) |
| INV-21 | Databricks never connects directly to metadata PostgreSQL. | IMPLEMENTATION_PLAN.md §6, invariant 21 | `tests/workflows/adapters/test_production_adapter.py::test_databricks_notebooks_import_source_without_a_wheel_or_entry_point` | `tests/workflows/adapters/test_production_adapter.py::test_production_adapter_has_no_database_or_server_core_imports` | T17–T24 | PASS | EXTERNAL (T25) |
| INV-22 | Raw physical datasets do not traverse MCP. | IMPLEMENTATION_PLAN.md §6, invariant 22 | `tests/workflows/adapters/test_snapshot_projection.py::test_verified_snapshot_projects_profiles_and_full_evidence_records` | `tests/workflows/adapters/test_mcp_gateway.py::test_gateway_never_falls_back_to_unstructured_tool_content` | T14, T17–T24 | PASS | EXTERNAL (T25) |
| INV-23 | Secrets, tokens, raw prompts/tool output/run dumps, and secret references never appear in ordinary results or logs. | IMPLEMENTATION_PLAN.md §6, invariant 23 | `tests/workflows/unit/test_redaction.py::test_redaction_is_recursive_and_removes_secret_shaped_values` | `tests/workflows/test_mapping_generator_safety.py::test_generator_safety_rejects_database_ids_and_secret_shaped_values` | T02, T08, T16–T24 | PASS | EXTERNAL (T25) |
| INV-24 | Mutating tools remain disabled or unregistered until the complete local gate passes. | IMPLEMENTATION_PLAN.md §6, invariant 24 | `tests/mcp/configuration/test_runtime_settings.py::test_mutation_registration_requires_complete_evidence_bound_to_running_release` | `tests/mcp/configuration/test_runtime_app.py::test_bare_runtime_mutation_flag_exposes_no_mcp_registration` | T15, T24 | PASS | EXTERNAL (T25) |
| INV-25 | MCP tool and contract-resource exposure is derived from server-owned actor kind; humans cannot discover or invoke workload workflow/profiling surfaces through MCP. | IMPLEMENTATION_PLAN.md §6, invariant 25 | `tests/mcp/application/test_mcp_protocol.py::test_read_only_registration_has_exact_actor_inventory`<br>`tests/mcp/application/test_workflow_control.py::test_human_can_authorize_read_safe_status_and_revoke` | `tests/mcp/application/test_mcp_protocol.py::test_contract_schema_resources_are_actor_filtered_and_fail_closed` | T02, T08–T09, T15, T17, T24 | PASS | EXTERNAL (T25) |
| INV-26 | DBML export is deterministic, revision-bound, content-addressed, and reconstructible: MCP accepts no filesystem path, while Databricks publishes only beneath its configured root with exact archive/receipt validation and byte-identical replay. | IMPLEMENTATION_PLAN.md §0.3 governed DBML export amendment | `tests/mcp/application/test_dbml_export_workflow.py::test_human_dbml_export_is_revisioned_content_addressed_and_downloadable`<br>`tests/workflows/unit/test_dbml_workflow.py::test_dbml_workflow_verifies_publishes_then_completes_and_replays` | `tests/workflows/unit/test_dbml_workflow.py::test_dbml_archive_and_publisher_reject_tampering_and_links`<br>`tests/mcp/application/test_dbml_rendering.py::test_dbml_export_excludes_inactive_rows_and_fails_closed_on_live_orphans` | S17, T02, T06, T08–T09, T15, T17, T24 | PASS | EXTERNAL (T25) |

### Audited architecture-maintenance checkpoints

These checks deepen existing modules and remove false seams while preserving
explicit package interfaces for export control. They do not add, remove, or
renumber any of the 26 canonical Release 1 invariants above.

- Web Profiling publication is one bounded, revision-fenced PostgreSQL
  operation. It derives Tenant, Model, and actor from a running Profiling
  Workflow Run; requires the caller-owned Tenant Lock; requires exact eligible
  Attribute coverage for the immutable selected Objects; replaces only those
  Objects' Profiles; and leaves direct web table DML denied. Accepting and
  fail-closed anchors are
  `tests/mcp/test_database_profiling_persistence.py::test_running_profiling_results_replace_selected_profiles_and_complete`,
  `tests/mcp/test_database_profiling_persistence.py::test_one_invalid_profile_rolls_back_every_profile_and_revision`,
  `tests/mcp/test_database_profiling_persistence.py::test_profiling_payload_requires_exact_selected_attribute_coverage`,
  `tests/mcp/test_database_profiling_persistence.py::test_profiling_persistence_denies_cross_tenant_actor`,
  `tests/mcp/test_database_profiling_persistence.py::test_profiling_persistence_requires_owned_lock_and_current_revision`,
  and
  `tests/mcp/test_database_profiling_persistence.py::test_web_role_has_function_only_profiling_write_surface`.
  MCP Profile upserts explicitly clear prior web-run provenance through
  `tests/mcp/test_model_materializer.py::test_profile_materializer_clears_prior_workflow_provenance`.
- Profiling planning and GDS credential reads are web-only governed database
  boundaries. They require one bound running Profiling Run, current revision,
  owned Tenant Lock, exact immutable selection, active eligible Attributes, and
  the unique active Discovery Scope assignment. Batch requests require one
  selected System, while no-batch multi-System runs remain valid. Anchors are
  `tests/mcp/test_database_profiling_execution_context.py`,
  `tests/mcp/test_database_workflow_run_lifecycle.py::test_create_workflow_run_rejects_only_batch_across_multiple_systems`,
  `tests/mcp/test_database_metadata_discovery_scope.py::test_active_discovery_scope_assigns_each_gds_schema_to_one_tenant`,
  and
  `tests/mcp/test_database_application_governance.py::test_verify_install_requires_unique_active_discovery_assignment`.
- Deterministic Analysis validation is a separate web-only Run path. It binds
  the exact actor, Tenant, Model, revision, selected endpoints, Environment,
  and non-secret connection-value row versions; executes fixed aggregate-only
  Databricks SQL with bounded concurrency; and atomically persists the complete
  validation set plus Run completion. Empty eligible sets skip credentials and
  Databricks. Failures persist only safe Run state and never partial evidence.
  MCP/manual Analysis writes remain valid with nullable web provenance. Anchors
  are `tests/mcp/test_database_analysis_validation.py`,
  `tests/web_backend/test_analysis_validation_execution.py`, and
  `tests/web_backend/test_analysis_validation_workflow.py`.
- GDS Object source-Tenant attribution is consistent across workflow
  eligibility, MCP/web visibility, Metadata Snapshot projection, and governed
  change-set resolution. Unassigned GDS Objects cannot seed or extend recursive
  visibility. Focused anchors are
  `tests/mcp/test_database_model_eligibility.py::test_unassigned_gds_object_is_not_workflow_eligible`,
  `tests/mcp/test_read_catalog_tools.py::test_get_objects_returns_batched_objects_and_attributes`,
  `tests/web_backend/test_metadata_repository.py::test_gds_object_tenant_comes_only_from_active_discovery_scope`,
  `tests/web_backend/test_profiling_analysis.py::test_database_review_labels_gds_objects_from_discovery_scope`,
  `tests/mcp/test_modeling_source_tenant_sql.py`,
  `tests/web_backend/test_review_source_tenant_sql.py`,
  `tests/mcp/test_database_metadata_snapshot_selection.py::test_selection_uses_all_approved_seeds_and_active_mapping_closure`,
  `tests/mcp/test_database_application_model_mutations.py::test_scope_replacement_rejects_active_object_outside_visible_closure`,
  and
  `tests/mcp/test_database_metadata_change_set.py::test_apply_allows_global_object_inside_tenant_discovery_scope`.
- Package initializers are explicit module interfaces: each MCP and jobs package
  declares a literal, duplicate-free `__all__` that exactly controls its public
  re-exports, all declared jobs exports resolve, and the jobs root preserves the
  shared notebook API's six established symbols. The rejecting anchors are
  `tests/contracts/workflows/test_architecture_simplification.py::test_job_package_exports_are_explicit_and_complete`,
  `tests/contracts/workflows/test_architecture_simplification.py::test_job_package_exports_resolve`,
  `tests/contracts/workflows/test_architecture_simplification.py::test_job_root_preserves_the_shared_notebook_api_exports`,
  and
  `tests/mcp/foundation/test_import_boundaries.py::test_package_reexports_are_controlled_by_explicit_all`.
- Dead and own-test-only abstractions stay absent through
  `tests/contracts/workflows/test_architecture_simplification.py::test_dead_job_abstractions_are_removed`
  and
  `tests/mcp/foundation/test_import_boundaries.py::test_dead_mcp_abstractions_are_removed`.
  Fixed feature construction remains behind the narrower interface asserted by
  `tests/mcp/foundation/test_import_boundaries.py::test_zero_variation_construction_seams_are_removed`.
- Exact one-use forwarding interfaces stay local to their primary operations
  through
  `tests/mcp/foundation/test_import_boundaries.py::test_one_use_forwarding_seams_are_removed`
  and
  `tests/contracts/workflows/test_traceability_locality.py::test_one_use_job_seams_stay_with_their_primary_operations`.
  These guards are scoped to the former module/class locations; they preserve
  the exported `McpApplication` interface and do not forbid a meaningful future
  module merely because it uses the same private name. Catalog detail response,
  ordering, defaults, missing-ID behavior, and recursive redaction are pinned by
  `tests/mcp/application/test_feature_modules.py::test_catalog_object_detail_is_ordered_redacted_and_preserves_missing_ids`;
  Workflow contract drift, including `job_key`, remains fail-closed through
  `tests/workflows/unit/test_launch_and_notebook.py::test_notebook_rejects_server_contract_definition_or_tool_drift`.
- The complete S16 inventory covers all 158 files under `mcp_server/src`, all
  64 under `jobs/src`, and all 16 under `scripts`. Its exact-location
  architecture anchors are
  `tests/mcp/foundation/test_import_boundaries.py::test_one_use_forwarding_seams_are_removed`,
  `tests/contracts/workflows/test_traceability_locality.py::test_one_use_job_seams_stay_with_their_primary_operations`,
  and
  `tests/mcp/foundation/test_release_integrity.py::test_release_integrity_has_one_low_level_owner`.
  They remove false forwarding/type-lie/duplicate-integrity seams without
  forbidding domain, authorization, persistence, provider, transport, or
  independently testable validation boundaries.
- DD-109 Mapping bounds and cross-runtime contract parity are pinned by
  `tests/contracts/mcp/test_assets.py::test_operation_and_snapshot_schema_runtime_parity_matrices`,
  both Mapping-profile
  `test_mapping_profile_schema_has_no_unbounded_string_leaf` checks, both
  `test_generator_safety_honors_exact_dd109_text_limits` checks, and
  `tests/contracts/workflows/test_section_compatibility.py::test_mapping_profile_asset_copies_are_byte_identical`.
  The greenfield web contract replaces the orphaned internal fingerprint with
  the code-generated `mapping.standard@1.0.0` digest
  `b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa`.
  The backend recomputes it from the three validation-mode Pydantic schemas and
  rejects configuration drift; it does not trust the JSON registry value.
  Current anchors are `tests/web_backend/test_mapping_contracts.py` and
  `tests/mcp/test_database_mapping_workflow_run.py::` followed by
  `test_mapping_run_freezes_one_inferred_logical_to_silver_pair`.
- Mapping dependency ordering now has one shared planner and exact caller-level
  failure translation. The accepting and rejecting anchors are
  `tests/workflows/test_mapping_workflow.py::test_mapping_dependency_planner_preserves_all_failure_translations`
  and
  `tests/workflows/adapters/test_snapshot_projection.py::test_committed_mapping_dependency_failures_preserve_projection_messages`.
  The narrow projection input and absence of the former local fake projection
  are also asserted by
  `tests/contracts/workflows/test_traceability_locality.py::test_one_use_job_seams_stay_with_their_primary_operations`.
- Behavior-sensitive MCP inlining preserves authorization/privacy ordering,
  malformed-row filtering, user resolution, no-op missing-Model handling, and
  PostgreSQL result translation through
  `tests/mcp/application/test_feature_modules.py::test_modeling_evidence_preserves_actor_and_private_identifier_ordering`,
  `tests/mcp/application/test_workflow_grants_profiling.py::test_profiling_context_ignores_non_mapping_attribute_rows`,
  `tests/mcp/application/test_change_sets.py::test_change_set_mutations_require_a_resolved_principal`,
  `tests/mcp/application/test_mapping_materialization.py::test_completed_mapping_no_op_materializes_current_committed_state_without_draft`,
  and the three local repository anchors
  `test_outcome_status_matches_the_response_code_contract`,
  `test_profiling_selection_and_correlation_are_persisted_locally`, and
  `test_invalid_profiling_selection_is_rejected_before_opening_a_connection`
  in `tests/mcp/infrastructure/test_postgres_repository_local.py`.
- Release-file and Git integrity now have one stdlib-only owner. Direct tests
  cover no-follow descriptor walking, nonblocking FIFO rejection, exact bounded
  reads, named replacement, restored-mtime mutation, descriptor-close faults,
  minimal credential-free Git execution, and dirty checkout states in
  `tests/mcp/foundation/test_release_integrity.py`. Caller-level bounded hashing
  and error translation remain pinned by
  `tests/mcp/foundation/test_verify_entrypoint_hardening.py::test_promoted_appservice_files_translate_disappearance_after_resolution`,
  `tests/mcp/foundation/test_verify_entrypoint_hardening.py::test_promoted_appservice_zip_rejects_same_bytes_replacement_during_hash`,
  `tests/mcp/foundation/test_verify_entrypoint_hardening.py::test_promoted_appservice_zip_rejects_append_during_bounded_hash`,
  and
  `tests/mcp/configuration/test_release_artifact_selection.py::test_git_spawn_errors_keep_checkout_and_source_context`.
- The one promotion-owned complete T24 evidence rule, used by runtime promotion,
  artifact selection, and the separately guarded T25 path, is asserted by
  `tests/mcp/foundation/test_release_gate_contract.py::test_complete_release_evidence_validation_has_one_owner`.
  This ownership check does not constitute a completed T24 aggregate or any T25
  authorization.
- The prior append-only trigger design is preserved in the disabled behavior
  archive. Its former static ownership anchor is
  `tests/database/test_schema_static.py::test_change_state_is_bounded_append_only_and_secret_free`;
  `tests/mcp/infrastructure/test_postgres_repository.py::test_catalog_identity_health_and_schema_are_normalized`
  also passes against the disposable PostgreSQL fixture. It is not a current
  numbered-DDL guarantee.

Audited service checkpoints:

- T09/T15 readiness parity is covered by
  `test_readiness_and_authorization_share_exact_physical_validation`,
  `test_dimensional_readiness_requires_effective_logical_to_silver_mapping`,
  and `test_mapping_readiness_requires_header_target_and_source_system_lineage`.
- T10 draft repository-time expiry is covered in memory by
  `test_expiry_worker_uses_repository_time_and_persists_one_terminal_event` and
  in PostgreSQL by
  `test_database_time_expiry_worker_persists_terminal_status_and_event`.
- T15 workflow-grant expiry is covered in memory by
  `test_grant_expiry_uses_repository_time_and_updates_run_summary`, in
  PostgreSQL by
  `test_database_time_grant_expiry_is_durable_with_terminal_summary`, and at the
  apply race boundary by
  `test_grant_expiry_between_validation_and_apply_is_terminal_and_atomic`.
- T15 completed-contract confinement and current-human reauthorization are
  covered by `test_completed_non_mapping_contract_is_not_readable`,
  `test_contract_read_rechecks_current_initiating_human_capability`, and
  `test_completed_mapping_contract_requires_exact_applied_materialization_binding`.
- T08/T13 active-state fencing is covered by
  `test_inactive_tenant_removes_membership_and_denies_mutation_and_lock_commands`,
  `test_inactive_model_remains_readable_but_rejects_every_model_mutation`, and
  `test_apply_holds_model_row_fence_against_concurrent_deactivation`.
- The disposable PostgreSQL harness proves the positive different-Model
  concurrency path at the exact emitted anchor
  `run_postgres_catalog.sh::database_concurrency_assertion=different_models_commit_independently`.

Audited workflow completion and integrity checkpoints:

- Server-owned zero-operation completion, including no draft, no revision
  advance, terminal grant/summary state, durable exact replay, and rejection of
  a nonempty or no-longer-authorized request, is covered by
  `tests/mcp/application/test_workflow_no_op_completion.py::test_no_op_completion_is_terminal_unbound_revision_stable_and_replay_safe`,
  `tests/mcp/application/test_workflow_no_op_completion.py::test_no_op_completion_reauthorizes_human_and_rejects_nonempty_section`, and
  `tests/mcp/infrastructure/test_postgres_repository.py::test_workflow_no_op_completion_is_atomic_durable_and_replay_safe`.
- DD-054 creation/reactivation accepts only a fresh physical or verified
  Evidence basis, verifies exact Model Scope and Evidence applicability, and
  strips all transient basis fields before effective persistence. The accepting
  and rejecting anchors are
  `tests/mcp/application/test_compiler_contracts.py::test_dd054_accepts_verified_evidence_for_new_and_reactivated_artifacts`,
  `tests/mcp/application/test_compiler_contracts.py::test_dd054_rejects_unresolved_source_or_inapplicable_evidence`, and
  `tests/mcp/application/test_compiler_contracts.py::test_dd054_rejects_physical_support_outside_exact_model_scope`.
- The exact seven lifecycle intents are
  `create|update|unchanged|reactivate|needs_review|inactivate|deprecate`.
  Atomic compilation and retirement/lock rejection are covered by
  `tests/workflows/test_conceptual_workflow.py::test_conceptual_object_and_relationship_intents_compile_atomically`,
  `tests/workflows/test_logical_workflow.py::test_logical_compiler_maps_all_seven_intents_for_all_seven_families`,
  `tests/workflows/test_logical_workflow.py::test_locked_logical_entity_rejects_every_transition`,
  `tests/workflows/test_dimensional_workflow.py::test_dimensional_compiler_maps_all_seven_intents_atomically`, and
  `tests/workflows/test_dimensional_workflow.py::test_dimensional_deprecated_parent_requires_dependent_lifecycle_closure`.
- Analysis discovery-only state and terminal replay truth are read from durable
  server state rather than inferred by the job. The exact anchors are
  `tests/mcp/application/test_workflow_no_op_completion.py::test_discovery_only_put_durably_awaits_validation`,
  `tests/workflows/adapters/test_workflow_mcp.py::test_completed_analysis_outcome_uses_persisted_terminal_receipt`, and
  `tests/workflows/adapters/test_workflow_mcp.py::test_completed_analysis_outcome_rejects_unbound_terminal_summary`.
- Mapping materialization is derived from the receipt-bound committed Model
  snapshot after apply, or from current committed state after an unbound no-op;
  a post-commit generator retry never reapplies. This is covered by
  `tests/mcp/application/test_mapping_materialization.py::test_completed_mapping_read_is_exact_filtered_and_rechecks_human`,
  `tests/mcp/application/test_mapping_materialization.py::test_completed_mapping_no_op_materializes_current_committed_state_without_draft`, and
  `tests/acceptance/workflows/test_mapping_materialization_integration.py::test_post_apply_materialization_retry_uses_committed_state_once`.
- Final handoff accepts only authoritative create/put/validate/apply or no-op
  receipts whose IDs, revisions, and digests match the request chain. Positive
  and fail-closed anchors are
  `tests/workflows/unit/test_handoff.py::test_final_handoff_uses_one_complete_section_and_one_atomic_apply`,
  `tests/workflows/unit/test_handoff.py::test_no_op_handoff_uses_only_terminal_completion_without_a_draft`, and
  `tests/workflows/unit/test_handoff.py::test_final_handoff_rejects_mismatched_authoritative_receipts`.

The actor-separated registry, workflow-control contracts, and regenerated
contract assets change the App Service artifact and contract digests. Any T24
evidence created before this change is invalid for promotion. The aggregate T24
release gate remains fail-closed until a new final clean-checkout run, including
consent-authorized OSV audits, completes and writes both release evidence
formats. No row above is environment-release evidence.

Exact deterministic T24 scale anchors:

- 101-Object Analysis Finder/Resolver coverage with independently observed
  concurrency saturation and exact call counts:
  `tests/workflows/test_analysis_scale.py::test_101_object_analysis_scale_is_exact_and_concurrency_bounded`.
- 101-Object aggregate, bounded work, and bounded concurrency:
  `tests/workflows/test_conceptual_workflow.py::test_101_object_scale_gate_bounds_agent_calls_and_concurrency`.
- 101-Object Logical topology/detail/validation coverage, exact call/package
  counts, and one shared concurrency ceiling of eight across all three phases:
  `tests/workflows/test_logical_workflow.py::test_logical_101_object_scale_has_exact_calls_packages_and_concurrency`.
- 101-Object Dimensional topology/detail/validation coverage, exact call/package
  counts, and one shared concurrency ceiling of eight across all three phases:
  `tests/workflows/test_dimensional_scale.py::test_dimensional_101_object_scale_holds_all_parallel_phases_at_eight`.
- 501-column wide target packaging and bounded work:
  `tests/workflows/test_mapping_workflow.py::test_wide_mapping_chunks_501_columns_with_bounded_agent_calls`.

Additional T17/T24 source-release evidence:

- Each modeling Notebook Definition selects exactly one allowlisted runtime
  (`openai_agents_sdk`, `langchain_create_agent`, or
  `langchain_deep_agent`); missing/unknown values and any Profiling runtime
  fail before provider work. Optional reasoning and verbosity remain omitted
  when unset. The rejecting anchors are
  `tests/workflows/unit/test_notebook_definition.py::test_modeling_notebook_selects_one_allowlisted_runtime_with_optional_tuning`,
  `tests/workflows/unit/test_notebook_definition.py::test_notebook_definition_rejects_missing_unknown_or_profiling_runtime`,
  and
  `tests/workflows/adapters/test_production_adapter.py::test_modeling_notebooks_expose_runtime_and_optional_model_tuning`.
- All three runtime choices retain one code-owned deadline, retry, concurrency,
  model-call/token-budget, typed-output, MCP allowlist, redaction, and telemetry
  envelope. LangChain reuses one non-redirecting Foundry v1 client, disables
  native retries/tracing, and requires structured MCP content. Deep Agents uses
  ephemeral state and denies filesystem, execute, persistence, memory, skills,
  and default subagents. The accepting/rejecting anchors are
  `tests/workflows/adapters/test_agents.py::test_notebook_runtime_dispatches_only_to_the_selected_executor`,
  `tests/workflows/adapters/test_agents.py::test_runtime_model_settings_are_forwarded_only_when_configured`,
  `tests/workflows/adapters/test_agents.py::test_langchain_create_agent_uses_one_foundry_client_and_shared_budget`,
  `tests/workflows/adapters/test_agents.py::test_langchain_mcp_adapter_requires_and_canonicalizes_structured_content`,
  `tests/workflows/adapters/test_agents.py::test_openai_sdk_serializes_and_byte_bounds_valid_mcp_results`,
  `tests/workflows/adapters/test_agents.py::test_openai_agents_sensitive_debug_flags_are_code_owned`,
  `tests/workflows/adapters/test_agents.py::test_multi_turn_failure_preserves_call_and_token_capacity_for_retry`,
  `tests/workflows/adapters/test_agents.py::test_attempt_budget_exhaustion_advances_without_spending_reserved_call`,
  `tests/workflows/unit/test_notebook_definition.py::test_notebook_definition_rejects_retries_without_one_call_per_attempt`,
  `tests/workflows/unit/test_notebook_definition.py::test_deep_agent_rejects_context_that_can_trigger_filesystem_eviction`,
  `tests/workflows/adapters/test_agents.py::test_langchain_runtimes_build_real_graphs_without_provider_io`,
  and
  `tests/workflows/adapters/test_agents.py::test_deep_agent_is_ephemeral_and_has_no_builtin_or_subagent_surface`.
- The added runtime packages are exact in the jobs project, Databricks
  requirements, and lockfile through
  `tests/acceptance/release/test_databricks_source_release.py::test_repository_agent_runtime_dependencies_are_exact_and_locked`,
  `tests/acceptance/release/test_databricks_source_release.py::test_databricks_requirements_are_the_exact_frozen_production_closure`,
  and
  `tests/acceptance/release/test_databricks_source_release.py::test_build_rejects_pins_without_sha256_hashes`.
  Live Foundry deployment capability is still T25 `EXTERNAL`; these local
  checks do not claim it.
- All seven separate notebooks use the fixed versioned workspace parent and
  compile their complete Notebook Definition once. The release builder also
  rejects a missing guarded path insertion, alias/definition rebinding, an
  incomplete run call, and incomplete deployment rows:
  `tests/workflows/adapters/test_production_adapter.py::test_databricks_notebooks_import_source_without_a_wheel_or_entry_point` and
  `tests/workflows/adapters/test_production_adapter.py::test_shipped_notebooks_compile_complete_startup_definitions`,
  `tests/workflows/unit/test_notebook_definition.py::test_notebook_definition_compiles_and_renders_one_strict_context`,
  `tests/acceptance/release/test_databricks_source_release.py::test_build_rejects_incomplete_notebook_source_load_contract`,
  `tests/acceptance/release/test_databricks_source_release.py::test_build_rejects_notebook_gds_alias_reassignment`,
  `tests/acceptance/release/test_databricks_source_release.py::test_build_rejects_incomplete_notebook_run_call`,
  and
  `tests/acceptance/release/test_databricks_source_release.py::test_build_rejects_incomplete_deployment_contract_row`.
- Parameterized system and instruction prompts render with strict missing-value
  handling, and prompt content is absent from diagnostics:
  `tests/workflows/unit/test_notebook_definition.py::test_notebook_definition_rejects_missing_prompt_parameter_at_startup` and
  `tests/workflows/unit/test_notebook_definition.py::test_strict_prompt_rendering_rejects_a_missing_nested_value`.
- Unknown tools, wrong output types, and resource limits above code-owned hard
  maxima fail before a provider call:
  `tests/workflows/unit/test_notebook_definition.py::test_notebook_definition_rejects_unsupported_tools_and_limit_overrides` and
  `tests/workflows/unit/test_notebook_definition.py::test_notebook_definition_requires_the_exact_workflow_phase_set`.
- The jobs publication allowlist accepts only source and the seven notebooks and
  rejects tests, test support, generated bytecode, symlinks, and other files:
  `tests/acceptance/release/test_databricks_source_release.py::test_build_creates_the_exact_no_wheel_source_tree` and
  `tests/acceptance/release/test_databricks_source_release.py::test_build_rejects_tests_inside_the_product_package`.
- Colon-delimited delegated operation codes are canonical at the server loader
  and jobs run-contract seam:
  `tests/mcp/configuration/test_runtime_app.py::test_workflow_deployment_document_rejects_noncanonical_values` and
  `tests/contracts/workflows/test_typed_workflow_boundaries.py::test_workflow_ports_use_exact_request_and_result_types`.
