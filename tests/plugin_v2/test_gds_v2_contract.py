from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"
MARKETPLACE = REPOSITORY_ROOT / ".github" / "plugin" / "marketplace.json"


def test_plugin_exposes_one_strict_gds_router() -> None:
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text())
    mcp_manifest = json.loads((PLUGIN_ROOT / "mcp.json").read_text())
    marketplace = json.loads(MARKETPLACE.read_text())

    assert manifest["$schema"] == (
        "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    )
    assert manifest["name"] == "gds"
    assert manifest["version"] == "0.3.3"
    assert mcp_manifest == {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {
            "gds-workbench": {
                "type": "streamable-http",
                "url": (
                    "https://gds-test-workbench-hsemb2a9cuacd0gx."
                    "canadacentral-01.azurewebsites.net/mcp"
                ),
            }
        },
    }
    assert not (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").exists()
    assert not (PLUGIN_ROOT / ".mcp.json").exists()
    assert not (PLUGIN_ROOT / "skills" / "gds" / "agents").exists()
    assert marketplace["name"] == "gds-workbench"
    assert marketplace["owner"] == {"name": "GDS Workbench"}
    assert marketplace["metadata"] == {
        "description": "GDS Workbench Agent Plugins marketplace.",
        "version": "1.0.0",
    }
    matching_entries = [
        entry for entry in marketplace["plugins"] if entry["name"] == manifest["name"]
    ]
    assert matching_entries == [
        {
            "name": manifest["name"],
            "description": manifest["description"],
            "version": manifest["version"],
            "source": "./plugins/v2/gds",
            "strict": True,
        }
    ]
    assert (REPOSITORY_ROOT / matching_entries[0]["source"]).resolve() == PLUGIN_ROOT
    assert [path.name for path in (PLUGIN_ROOT / "skills").iterdir()] == ["gds"]

    skill = (PLUGIN_ROOT / "skills" / "gds" / "SKILL.md").read_text()
    assert skill.startswith("---\nname: gds\n")
    assert "initialize GDS" in skill
    assert "Open Workbench" in skill
    assert "Do not load an entire Snapshot" in skill
    assert "Quick / Ad Hoc" in skill
    assert "Custom Build" in skill
    assert "Infer Custom + Selected for a specific bounded ask" in skill
    assert "Pure explanations must answer directly" in skill
    assert "For predefined Model work" in skill
    assert "generic Metadata mutation or assertion preparation" in skill
    assert "docs/USER_GUIDE.md" not in skill
    assert "references/getting-started.md" not in skill
    assert "references/prompt-guide.md" not in skill


def test_prompt_guide_covers_supported_routes_and_boundaries() -> None:
    guide_path = PLUGIN_ROOT / "docs" / "USER_GUIDE.md"
    guide = guide_path.read_text()

    assert guide_path.is_file()
    assert "human-readable documentation" in guide
    assert "agent does not load it as skill instructions" in guide
    assert '"chat.plugins.enabled": true' in guide
    assert "**Chat: Configure Skills**" in guide
    assert "**MCP: List Servers**" in guide
    assert "Codex" not in guide

    assert all(
        category in guide
        for category in (
            "Metadata",
            "Profiling",
            "Analysis",
            "Conceptual",
            "Logical",
            "Dimensional",
            "Mapping",
            "Code Generation",
            "QA",
            "Validation",
            "Ad Hoc",
        )
    )
    assert all(
        mode in guide for mode in ("Guided", "Automatic", "Custom", "Full", "Selected")
    )
    assert all(
        target in guide
        for target in (
            "Logical Build",
            "Silver Target Registration",
            "Logical Mapping",
            "Logical Code Generation",
            "Dimensional Build",
            "Gold Target Registration",
            "Dimensional Mapping",
            "Dimensional Code Generation",
            "QA",
        )
    )
    assert "Profiling is not a V2 execution target" in guide
    assert "Fresh Apply approval" in guide
    assert "never executed, uploaded, or deployed" in guide
    assert "Mutate Model Scope" in guide
    assert "`GeneratorDocumentV1`" in guide
    assert "four parts" in guide
    assert "one Tenant Code and one Model" in guide
    assert "download and unzip exactly one fresh" in guide
    assert "does not precede it with inspect" in guide
    assert "not unattended" in guide
    assert "Local Workbench" in guide
    assert "Gold target Object plus source System" in guide
    assert "if it is already `validated`" in guide
    assert "`<environment_code>`" in guide
    assert "`catalog.schema.table`" in guide
    assert "approval before acquiring an unowned lock" in guide
    assert "explicit user direction and a reason" in guide
    assert "exactly one row and one column" in guide
    assert "query-contract execution error, not an assertion failure" in guide
    assert "`ingestion_object_mapping`, `copy_group`, and `copy`" in guide
    assert "`scoped_attributes`, `profiled_attributes`, and `unprofiled_attributes`" in guide
    assert "`process_group` and `process`" in guide
    assert "one active pipeline per Tenant" in guide
    assert "several rows may reference the same target artifact" in guide
    assert "any failure blocks later orders" in guide


def test_qa_workflow_publishes_the_scalar_execution_contract() -> None:
    qa = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "workflows" / "qa.md"
    ).read_text()

    assert "exactly one row by one column" in qa
    assert "`validation_result_data_type`" in qa
    assert "query-contract execution error, not an assertion failure" in qa
    assert "`executes_successfully`" in qa
    assert "`catalog.schema.table`" in qa
    assert "declared earlier in the same SQL batch" in qa


def test_plugin_routes_writes_through_exact_dataset_contracts_and_server_validation() -> (
    None
):
    skill_root = PLUGIN_ROOT / "skills" / "gds"
    skill = (skill_root / "SKILL.md").read_text()
    changes = (skill_root / "references" / "change-sets.md").read_text()
    helper = (skill_root / "references" / "local-helper.md").read_text()
    handoff = (skill_root / "references" / "server-handoff.md").read_text()

    assert "load `references/change-sets.md` and `references/local-helper.md`" in skill
    assert "Before the first write to each dataset" in changes
    assert "`describe_metadata_dataset` or `describe_model_dataset`" in changes
    assert "local `describe`" in changes
    assert "Never author from memory" in changes
    assert "complete replacement array for that server-pending dataset" in changes
    assert "Missing datasets remain unchanged" in changes
    assert "Server Validate rechecks" in helper
    assert "Databricks" in helper and "SQL safety" in helper
    assert "database state" in helper
    assert "targeted `repairs`" in helper
    assert "defaults to compact" in helper

    target_root = skill_root / "references" / "workflows"
    for target in (
        "logical-build.md",
        "dimensional-build.md",
        "target-registration.md",
        "mapping.md",
        "code-generation.md",
        "qa.md",
    ):
        assert "dataset contract" in (target_root / target).read_text()

    for tool in (
        "begin_metadata_stage_batch",
        "put_metadata_stage_chunk",
        "commit_metadata_stage_batch",
        "begin_model_stage_batch",
        "put_model_stage_chunk",
        "commit_model_stage_batch",
    ):
        assert f"`{tool}`" in handoff
    assert "handles one dataset" in handoff
    assert "`records` mode" in handoff
    assert "`json_fragments`" in handoff
    assert "schema-normalized record array" in handoff
    assert "decoded fragment bytes" in handoff
    assert "ordered lowercase chunk SHA-256 hex digests" in handoff
    assert "returned revision" in handoff


def test_session_contract_is_compact_and_gate_driven() -> None:
    contract = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "session.md"
    ).read_text()

    assert '"current":"02"' in contract
    assert '["01","metadata","Add metadata","applied"]' in contract
    assert '"stale":["metadata"]' in contract
    assert '"cs":{"model":["uuid",2,"active","02","digest"]}' in contract
    assert '"sql":"never"' in contract
    assert "`never`, `essential`, or `as_needed`" in contract
    assert "accepted local digest" in contract
    assert "status.stashes" in contract
    assert "prevents same-area task unions" in contract
    assert "queued" in contract
    assert "overridden" in contract
    assert "applied" in contract
    assert "Never reuse" in contract
    assert "one Model per session" in contract
    assert "Download and unzip exactly one" in contract
    assert "The user downloads and unzips" in contract
    assert "First plan line is readiness proof" in contract
    assert "first waiting task" in contract


def test_workflow_router_has_exact_main_targets_and_apply_boundaries() -> None:
    router = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "workflow-targets.md"
    ).read_text()

    targets = [
        "Logical Build",
        "Silver Target Registration",
        "Logical Mapping",
        "Logical Code Generation",
        "Dimensional Build",
        "Gold Target Registration",
        "Dimensional Mapping",
        "Dimensional Code Generation",
        "QA",
    ]
    assert all(
        f"{index}. **{target}**" in router for index, target in enumerate(targets, 1)
    )
    assert "Never cross an Apply boundary automatically" in router
    assert "Applied Logical Mapping" in router
    assert "Dimensional is optional" in router
    assert "authorized scope owner" in router
    assert "never an output quota" in router
    assert "one pre-process, non-target Model custom task" in router


def test_plugin_carries_the_platform_lifecycle_and_default_orchestration_intent() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "gds"
    skill = (skill_root / "SKILL.md").read_text()
    journey = (skill_root / "references" / "automatic-journey.md").read_text()
    lifecycle = (skill_root / "references" / "platform-lifecycle.md").read_text()
    registration = (
        skill_root / "references" / "workflows" / "target-registration.md"
    ).read_text()
    logical = (skill_root / "references" / "workflows" / "logical-build.md").read_text()

    assert "platform lifecycle" in skill
    assert "Load `platform-lifecycle.md` once" in journey
    for text in (
        "Tenant owns Systems",
        "Connections locate physical Objects and Attributes",
        "Source → Bronze",
        "`ingestion_object_mapping`",
        "`copy_group` and `copy`",
        "authorized Model Scope",
        "Profiling, Analysis, and Conceptual",
        "Dimensional is optional",
        "Mapping is the executable truth source for Code",
        "QA uses applied Mapping and current relevant Code when present",
        "one active pipeline per",
        "selected Systems",
        "lower orders finish first",
        "same target",
        "External triggers",
        "same-session temporary views",
        "natural key and Process metadata",
        "another runtime",
    ):
        assert text in lifecycle
    assert "ask whether to include `process_group` and `process`" in registration
    assert "exact Copy Group, Process type, execution order, location, and executable" in registration
    assert "profiled_attributes" in logical
    assert "unprofiled_attributes" in logical
    assert "never blocks Logical Build by itself" in logical


def test_workflow_eligibility_uses_canonical_model_scope_flags() -> None:
    reference_root = PLUGIN_ROOT / "skills" / "gds" / "references"
    router = (reference_root / "workflow-targets.md").read_text()
    logical = (reference_root / "workflows" / "logical-build.md").read_text()
    dimensional = (reference_root / "workflows" / "dimensional-build.md").read_text()
    mapping = (reference_root / "workflows" / "mapping.md").read_text()

    for field in (
        "is_bronze_source_eligible",
        "is_dimensional_source_eligible",
        "is_logical_mapping_target_eligible",
        "is_dimensional_mapping_target_eligible",
    ):
        assert f"`{field}`" in router
    assert "Never infer eligibility from `zone_code` alone" in router
    assert "`is_bronze_source_eligible=true`" in logical
    assert "Profile, Analysis, Conceptual, and Logical" in logical
    assert "`is_dimensional_source_eligible=true`" in dimensional
    assert "active applied Logical Mapping contribution" in dimensional
    assert "`is_logical_mapping_target_eligible=true`" in mapping
    assert "`is_dimensional_mapping_target_eligible=true`" in mapping


def test_dimensional_build_requires_explicit_relationship_optionality() -> None:
    workflow = (
        PLUGIN_ROOT
        / "skills"
        / "gds"
        / "references"
        / "workflows"
        / "dimensional-build.md"
    ).read_text()

    assert "`dimensional_relationship_is_optional`" in workflow
    assert "projected foreign key may be null" in workflow
    assert "Never infer optionality from cardinality" in workflow


def test_registration_scope_and_mapping_are_separate_boundaries() -> None:
    reference_root = PLUGIN_ROOT / "skills" / "gds" / "references"
    router = (reference_root / "workflow-targets.md").read_text()
    registration = (reference_root / "workflows" / "target-registration.md").read_text()
    change_sets = (reference_root / "change-sets.md").read_text()

    assert "separate web-governed Model Scope path" in router
    assert "outside public MCP and this plugin" in router
    assert "Mapping remains a separate later task" in registration
    assert "never creates or stages `model_scope`" in registration
    assert (
        "`model_scope` is Snapshot-readable but never Change Set-writable"
        in change_sets
    )
    assert "model-change-set/model_scope.json" in change_sets


def test_target_registration_applies_independently_optional_model_policies() -> None:
    registration = (
        PLUGIN_ROOT
        / "skills"
        / "gds"
        / "references"
        / "workflows"
        / "target-registration.md"
    ).read_text()

    assert "independently optional" in registration
    assert "`silver_model_naming_instructions`" in registration
    assert "`gold_model_naming_instructions`" in registration
    assert "every configured audit/technical column exactly" in registration
    assert "Missing policy fields never block Target Registration" in registration
    assert "silver_model_naming_template" not in registration
    assert "gold_model_naming_template" not in registration


def test_analysis_allows_inference_without_fabricated_validation() -> None:
    workflow = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "workflows" / "logical-build.md"
    ).read_text()

    assert "An Analysis row may be inference-only" in workflow
    assert "all nine validation fields absent" in workflow
    assert "all nine fields together" in workflow
    assert "Never fabricate validation evidence" in workflow
    assert "separate deterministic validation step may populate" in workflow


def test_mapping_and_code_never_invent_missing_executable_contracts() -> None:
    workflow_root = PLUGIN_ROOT / "skills" / "gds" / "references" / "workflows"
    mapping = (workflow_root / "mapping.md").read_text()
    code = (workflow_root / "code-generation.md").read_text()

    assert "generic `mapping_package_document` object" in mapping
    assert "committed mapper/materializer contract" in mapping
    assert "never invent database IDs" in mapping
    assert "`GeneratorDocumentV1`" in code
    assert "Ask the platform owner" in code
    assert "never reconstruct it" in code
    assert "applied Mapping" in code
    assert "`sql_file`" in code
    assert "Python file or notebook" in code


def test_code_and_qa_are_governed_model_datasets_with_session_sql_policy() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "gds"
    router = (skill_root / "SKILL.md").read_text()
    code = (skill_root / "references" / "workflows" / "code-generation.md").read_text()
    qa = (skill_root / "references" / "workflows" / "qa.md").read_text()
    helper = (skill_root / "references" / "local-helper.md").read_text()

    for value in ("`never`", "`essential`", "`as_needed`"):
        assert value in router
    assert "sql-policy" in router and "execute_databricks_sql" in router
    assert "one complete `generated_code` record" in code
    assert "maximum size" not in code
    assert "target_mapping_context_digest" in code
    assert "target_source_context_digest" in code
    assert "semicolon-separated statements" in code
    assert "same-session" in code and "temporary views" in code
    assert "final statement must match the target shape" in code
    assert "target shape and natural key" in code
    assert "Process may contain one row per System" in code
    assert "one logical artifact" in code
    assert "one isolated temporary-view branch per System" in code
    assert "aligned `UNION ALL`" in code
    assert "Process may contain one row per System pointing to this same artifact" in code
    assert "runtime executes it once" in code
    assert "stops later orders on" in code
    assert "target self-read may be a prior-state" in code
    assert "`validation_group`" in qa and "`validation_check`" in qa
    assert "`qa_authoring_context`" in qa
    assert "never recompute either digest" in qa
    assert "authoritative allowlist" in qa
    assert "ignore every unreferenced or stale artifact" in qa
    assert "Snapshot-only and must never be staged" in qa
    assert "Code may be absent" in qa
    assert "current relevant active `generated_code` exists, QA must use it" in qa
    assert "`is_active=false`" in qa
    assert "1..1000" in qa
    assert "--system-codes" in helper and "case-insensitively unique" in helper


def test_local_authority_excludes_application_prompt_and_workflow_run_surfaces() -> (
    None
):
    skill = (PLUGIN_ROOT / "skills" / "gds" / "SKILL.md").read_text()
    workbench = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "workbench.md"
    ).read_text()

    assert "Local authority remains unchanged" in skill
    assert "`Application Prompt` and `Workflow Run` surfaces are out of scope" in skill
    assert "never discover, call, or depend on them" in skill
    assert "never calls MCP" in workbench
    assert "writes outside the selected session" in workbench


def test_logical_automatic_build_has_complete_ordered_coverage() -> None:
    workflow = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "workflows" / "logical-build.md"
    ).read_text()

    assert "Analysis → Conceptual → Logical" in workflow
    assert "covered, excluded with reason, or blocked" in workflow
    assert "Conceptual never drives Logical structure" in workflow
    assert "selected-section checkpoint" in workflow
    assert "Only the final complete digest is a human review boundary" in workflow
    assert "one Stage, server Validate, and Apply" in workflow


def test_automatic_build_has_one_final_human_review_and_a_deterministic_handoff() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "gds"
    router = (skill_root / "SKILL.md").read_text()
    journey = (skill_root / "references" / "automatic-journey.md").read_text()
    logical = (
        skill_root / "references" / "workflows" / "logical-build.md"
    ).read_text()
    helper = (skill_root / "references" / "local-helper.md").read_text()

    assert "internal checkpoints without human pauses" in router
    assert "one final local review" in router
    assert "Task `review` is not record `needs_review`" in router
    assert "`approve-reviewed` at most once" in router
    assert "then `validate` and `accept`" in router
    assert "do not ask for the same review again" in router

    assert "Profiling evidence → Analysis → Conceptual → Logical" in journey
    assert "Silver Target Registration" in journey
    assert "Logical Mapping" in journey
    assert "Code Generation" in journey
    assert "QA" in journey
    assert "queue the requested targets" in journey
    assert "ask one continue question" in journey
    assert "fresh Apply approval" in journey

    assert "do not ask the user at a section checkpoint" in logical
    assert "Only the final complete digest is a human review boundary" in logical
    assert "promoted digest" in helper
    assert "Never repeat `approve-reviewed`" in helper


def test_long_running_task_loops_start_immediately_and_resume_from_plan() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "gds"
    router = (skill_root / "SKILL.md").read_text()
    journey = (skill_root / "references" / "automatic-journey.md").read_text()
    session = (skill_root / "references" / "session.md").read_text()
    logical = (
        skill_root / "references" / "workflows" / "logical-build.md"
    ).read_text()

    assert "Every mutating mode creates its target task before work" in router
    assert "The first `task-add` returns `doing`; start it immediately" in journey
    assert "Do not create separate tasks for Profiling, Analysis, Conceptual" in journey
    assert "external scope activation is a prerequisite on the Mapping task" in journey
    assert "When `status.resume` is null, report the journey complete" in journey
    assert "if none, report completion" in router
    assert "`Loop: target=<target>; phase=<phase>" in session
    assert "Task state alone never identifies a final review" in session
    assert "recompute coverage from pending records before continuing" in session
    assert "transition `review` → `doing` and continue" in logical


def test_physical_object_identity_comes_from_scope_not_session_or_source_owner() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "gds"
    router = (skill_root / "SKILL.md").read_text()
    logical = (
        skill_root / "references" / "workflows" / "logical-build.md"
    ).read_text()
    registration = (
        skill_root / "references" / "workflows" / "target-registration.md"
    ).read_text()
    mapping = (skill_root / "references" / "workflows" / "mapping.md").read_text()

    assert "Session Tenant Code is never a physical Object key default" in router
    assert "Model ownership does not own or rewrite physical Object identity" in router
    assert "`tenant_code`, `system_code`, `connection_code`, `object_schema`, and `object_name`" in logical
    assert "copy them exactly from the eligible `model_scope` record" in logical
    assert "`tenant_metadata_discovery_scope`" in registration
    assert "`tenant_code=scope_tenant_code`" in registration
    assert "`system_code=connection_system_code`" in registration
    assert "never substitute the session, Model, or source Tenant/System" in registration
    assert "`source_system_code` is not the target physical Object's `system_code`" in mapping


def test_mapping_and_code_proof_preflight_is_not_a_terminal_blocker() -> None:
    workflow_root = PLUGIN_ROOT / "skills" / "gds" / "references" / "workflows"
    mapping = (workflow_root / "mapping.md").read_text()
    code = (workflow_root / "code-generation.md").read_text()

    for workflow in (mapping, code):
        assert "expected preflight action, not a terminal blocker" in workflow
        assert "final readiness" in workflow


def test_local_change_set_contract_never_confuses_pending_with_deletion() -> None:
    contract = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "change-sets.md"
    ).read_text()

    assert "Missing file" in contract
    assert "Present `[]`" in contract
    assert "never deletes applied data" in contract
    assert "exact bytes" in contract
    assert "conflict" in contract
    assert "never overwrite" in contract
    assert "classification is `exact`" in contract
    assert "`task-stash`" in contract
    assert "`task-restore`" in contract

    helper = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "local-helper.md"
    ).read_text()
    assert "upsert-batch" in helper
    assert "200 records maximum" in helper
    assert "Never write per field" in helper
    assert "newer `active` Stage" in helper
    assert "`cache_bound`" in helper
    command_contract = json.loads(
        (
            PLUGIN_ROOT
            / "skills"
            / "gds"
            / "contracts"
            / "local-helper.json"
        ).read_text()
    )
    assert "--expected-id <UUID> --expected-revision <n>" in command_contract[
        "commands"
    ]["draft-cache"]["usage"]
    assert command_contract["commands"]["approve-reviewed"] == {
        "usage": (
            "approve-reviewed --session <session> --area model --reviewed true "
            "--expected-digest <digest>"
        ),
        "session_required": True,
        "mutates": True,
    }
    assert "Never infer approval" in helper


def test_multi_system_sql_example_matches_the_orchestration_contract() -> None:
    skill_root = PLUGIN_ROOT / "skills" / "gds"
    lifecycle = (skill_root / "references" / "platform-lifecycle.md").read_text()
    example = (
        skill_root / "references" / "examples" / "multi-system-target.sql"
    ).read_text()

    assert "Process has one row per System" in lifecycle
    assert "runtime executes" in lifecycle and "artifact once" in lifecycle
    assert "any failure blocks later orders" in lifecycle
    assert example.count("CREATE OR REPLACE TEMPORARY VIEW") == 2
    assert "UNION ALL" in example
    assert "wid_GDSBatchID" in example
    assert "MERGE" not in example


def test_server_handoff_names_the_minimal_governed_sequence() -> None:
    """Contract the remote workflow without claiming to execute an MCP backend."""
    skill = (PLUGIN_ROOT / "skills" / "gds" / "SKILL.md").read_text()
    handoff = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "server-handoff.md"
    ).read_text()

    assert "server-handoff.md" in skill
    for tool in (
        "check_tenant_lock",
        "acquire_tenant_lock",
        "create_metadata_change_set",
        "create_model_change_set",
        "stage_metadata_change_set",
        "stage_model_change_set",
        "validate_metadata_change_set",
        "validate_model_change_set",
        "apply_metadata_change_set",
        "apply_model_change_set",
    ):
        assert f"`{tool}`" in handoff
    assert "one Stage call" in handoff
    assert "fresh Apply approval" in handoff
    assert "Cache is not server proof" in handoff
    assert "Minimal Stage, Validate, and Apply sequence" in handoff
    assert "local `task-state ... staged`" in handoff
    assert "cache its validated revision/status" in handoff
    assert "`exact` with `cache_bound=true`, skip Stage" in handoff
    assert "If Stage ran" in handoff
    assert "always call `validate_metadata_change_set`" in handoff
    assert "If Stage was skipped, first cache fresh verified revision/status" in handoff
    assert "Validate only if status is active" in handoff
    staged_branch, resumed_branch = handoff.split("If Stage was skipped", maxsplit=1)
    assert "always call `validate_metadata_change_set`" in staged_branch
    assert "Validate only if status is active" in resumed_branch

    stage_sequence, archive_sequence = handoff.split(
        "At an upstream archive boundary", maxsplit=1
    )
    ordered_gates = (
        "Call `check_tenant_lock`",
        "If `status.cs` contains this task",
        "For a resumed draft",
        "use the Stage intent already granted",
        "call `validate_metadata_change_set`",
        "fresh Apply approval",
    )
    offsets = [stage_sequence.index(gate) for gate in ordered_gates]
    assert offsets == sorted(offsets)
    assert "classification is `exact`" in archive_sequence
    assert "`cache_bound` is true" in archive_sequence
    assert "do not archive" in archive_sequence
    assert "Archive needs no Tenant Lock" in archive_sequence
    assert "Never create a draft merely to look" in archive_sequence
    assert "`task-stash`" in archive_sequence
    assert "`task-restore`" in archive_sequence


def test_workbench_contract_is_local_only_and_digest_bound() -> None:
    contract = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "workbench.md"
    ).read_text()

    assert "never calls MCP" in contract
    assert "never writes a Snapshot" in contract
    assert "Refresh" in contract
    assert "Validate" in contract
    assert "exact local Change Set digest" in contract
    assert "never override server validation" in contract
