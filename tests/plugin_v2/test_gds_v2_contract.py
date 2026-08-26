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
    assert manifest["version"] == "0.2.1"
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


def test_session_contract_is_compact_and_gate_driven() -> None:
    contract = (
        PLUGIN_ROOT / "skills" / "gds" / "references" / "session.md"
    ).read_text()

    assert '"current":"02"' in contract
    assert '["01","metadata","Add metadata","applied"]' in contract
    assert '"stale":["metadata"]' in contract
    assert '"cs":{"model":["uuid",2,"active","02","digest"]}' in contract
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
    assert "first waiting task without mutation" in contract


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
    assert "do not call `review` again" in workflow
    assert "one Stage, server Validate, and Apply" in workflow


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
    assert "at most 200 records" in helper
    assert "Never write per field" in helper
    assert "newer `active` Stage revision" in helper
    assert "`cache_bound`" in helper
    assert "--expected-id <UUID> --expected-revision <n>" in helper


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
        "ask for Stage approval",
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
