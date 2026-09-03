from __future__ import annotations

import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"
SKILL_ROOT = PLUGIN_ROOT / "skills" / "gds"
REFERENCES = SKILL_ROOT / "references"
WORKFLOWS = REFERENCES / "workflows"
MARKETPLACE = REPOSITORY_ROOT / ".github" / "plugin" / "marketplace.json"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_plugin_keeps_the_portable_agent_plugins_manifest() -> None:
    manifest = json.loads(read(PLUGIN_ROOT / "plugin.json"))
    mcp = json.loads(read(PLUGIN_ROOT / "mcp.json"))
    marketplace = json.loads(read(MARKETPLACE))

    assert manifest["$schema"] == (
        "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    )
    assert manifest["name"] == "gds"
    assert mcp["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    assert mcp["mcpServers"]["gds-workbench"]["type"] == "streamable-http"
    assert not (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").exists()
    assert not (PLUGIN_ROOT / ".mcp.json").exists()
    assert not (PLUGIN_ROOT / "tool-contract.json").exists()
    assert [path.name for path in (PLUGIN_ROOT / "skills").iterdir()] == ["gds"]
    assert any(
        item["source"] == "./plugins/v2/gds" and item["version"] == manifest["version"]
        for item in marketplace["plugins"]
    )


def test_router_has_simple_modes_and_no_server_contract_preflight() -> None:
    router = read(SKILL_ROOT / "SKILL.md")

    for mode in ("Quick", "Guided", "Automatic", "Custom", "Grill With Docs"):
        assert f"**{mode}**" in router
    assert "Open Workbench only when the session is first created" in router
    assert "Read `references/workflow-targets.md` and only the active guide" in router
    assert "For Automatic, also read `references/automatic-journey.md`" in router
    assert "ask them to Refresh Workbench" in router
    assert "Any unambiguous positive acknowledgement" in router
    assert "There is no packaged server-contract hash preflight" in router
    assert "inspect_metadata" in router
    assert "read_model_section" in router
    assert "default `environment_code` to lowercase `dev`" in router
    for removed in (
        "get_server_contract",
        "contract-check",
        "mapping-proof",
        "generator-proof",
        "approve-reviewed",
    ):
        assert removed not in router


def test_workflow_router_names_current_targets_and_validation_terms() -> None:
    router = read(REFERENCES / "workflow-targets.md")

    for target in (
        "Metadata Authoring",
        "Model Input Scope Authoring",
        "Logical Build",
        "Silver Target Registration",
        "Logical Model Binding",
        "Logical Mapping",
        "Logical Code Generation",
        "Dimensional Build",
        "Gold Target Registration",
        "Dimensional Model Binding",
        "Dimensional Mapping",
        "Dimensional Code Generation",
        "Validation Authoring",
        "Process Registration",
    ):
        assert f"**{target}**" in router
    assert "Grill With Docs is an interaction mode, never a target" in router
    assert not (WORKFLOWS / "qa.md").exists()
    assert (WORKFLOWS / "validation.md").exists()


def test_visible_lifecycle_is_refresh_acknowledge_and_proceed() -> None:
    router = read(SKILL_ROOT / "SKILL.md")
    session = read(REFERENCES / "session.md")
    workbench = read(REFERENCES / "workbench.md")
    handoff = read(REFERENCES / "server-handoff.md")

    assert "Open Workbench once" in session
    assert "no approval button or review ceremony" in workbench
    assert "acknowledge in chat" in workbench
    assert "positive acknowledgement" in router
    assert "exact current digest" in router
    assert "authorizes an ordinary free Tenant Lock" in router
    assert "Load only after a positive acknowledgement" in handoff
    assert "ask separately for Apply approval" in router
    assert "Never ask separately for review acceptance and handoff approval" in router
    assert "Do not run `review` unless the user asks for an action summary" in router


def test_resume_continues_from_recorded_state_without_rebuilding() -> None:
    session = read(REFERENCES / "session.md")
    local_helper = read(REFERENCES / "local-helper.md")

    assert "Treat `status.acceptance` as authoritative" in session
    assert "do not rerun authoring, generators, validation, or review" in session
    assert "Never inspect helper source to rediscover a command" in local_helper


def test_revision_change_forces_fresh_snapshot_and_reassessment() -> None:
    documents = "\n".join(
        read(path)
        for path in (
            SKILL_ROOT / "SKILL.md",
            REFERENCES / "session.md",
            REFERENCES / "change-sets.md",
            REFERENCES / "server-handoff.md",
            WORKFLOWS / "revision-recovery.md",
        )
    )

    assert "fresh Model Snapshot" in documents
    assert "Metadata has no tenant-wide revision" in documents
    assert "reassess" in documents
    assert "byte-identical" in documents
    assert "never auto-merge" in documents or "never merge automatically" in documents


def test_metadata_and_model_change_set_boundary_is_explicit() -> None:
    lifecycle = read(REFERENCES / "platform-lifecycle.md")
    changes = read(REFERENCES / "change-sets.md")
    binding = read(WORKFLOWS / "model-binding.md")

    assert "Metadata registration uses only a Metadata Change Set" in changes
    assert "Model Input Scope, Model Binding" in changes
    assert "Metadata registration must succeed before Model Binding" in lifecycle
    assert "Binding must succeed before Mapping or Code" in lifecycle
    assert "model_object_binding" in binding
    assert "model_attribute_binding" in binding


def test_source_bronze_precedence_and_profiling_coordinates_are_exact() -> None:
    scope = read(WORKFLOWS / "model-input-scope.md")
    profiling = read(WORKFLOWS / "profiling.md")

    assert "use Bronze by default" in scope
    for coordinate in (
        "Connection `foreign_catalog`",
        "Object `fc_object_schema`",
        "Object `fc_object_name`",
        "Attribute `fc_attribute_name`",
    ):
        assert coordinate in profiling
    assert "Never connect directly to a Source" in profiling
    assert "tenant_catalog" in profiling
    assert "object_schema" in profiling
    assert "attribute_name" in profiling


def test_target_metadata_placement_keeps_source_tenant_separate() -> None:
    combined = read(WORKFLOWS / "metadata-authoring.md") + read(
        WORKFLOWS / "target-registration.md"
    )

    assert "source_tenant_id" in combined
    assert "is_tenant_gds_connection=true" in combined
    assert "is_global_data_store=true" in combined
    assert "data-owning Tenant" in combined
    assert "Multiple Systems or Connections" in combined
    assert "No Object may contain data from multiple source Tenants" in combined


def test_silver_schema_is_confirmed_before_authoring_and_binding_needs_no_pause() -> None:
    registration = read(WORKFLOWS / "target-registration.md")
    binding = read(WORKFLOWS / "model-binding.md")

    gate = registration.index("confirm the exact target schema name")
    authoring = registration.index("Use PascalCase")
    assert gate < authoring
    assert "Do not begin authoring until the user confirms" in registration
    assert "every interaction mode" in registration
    assert "Do not add an optional design-confirmation pause" in binding
    assert "missing or more than one compatible match" in binding


def test_conceptual_is_compact_and_naming_is_defaulted() -> None:
    router = read(SKILL_ROOT / "SKILL.md")
    conceptual = read(WORKFLOWS / "conceptual.md")
    logical = read(WORKFLOWS / "logical-build.md")
    dimensional = read(WORKFLOWS / "dimensional-build.md")

    phases = ["**Profile**", "**Analyze relationships**", "**Build Conceptual**", "**Build Logical**"]
    assert [logical.index(phase) for phase in phases] == sorted(
        logical.index(phase) for phase in phases
    )
    assert "table-by-table pass" in conceptual
    assert "required Logical Build phase" in conceptual
    assert "Conceptual-to-Logical copy" in conceptual
    assert "one-concept-per-Object" in conceptual
    assert "business-process-first" in conceptual
    assert "process-to-concept matrix" in conceptual
    assert "One Object may support several concepts" in conceptual
    for state in ("represented", "context-only", "excluded", "blocked"):
        assert state in conceptual
    assert "PascalCase" in conceptual
    assert "PascalCase" in logical and "CustomerID" in logical
    assert "PascalCase" in dimensional and "CustomerKey" in dimensional
    for policy in ("`never`", "`essential`", "`as_needed`"):
        assert policy in router
        assert policy in logical
    assert "never persist raw query output" in logical
    for decision in (
        "functional dependencies",
        "1NF",
        "2NF",
        "3NF",
        "source-projection challenge",
        "same business concept at the same grain",
    ):
        assert decision in logical
    assert "Do not finalize a metadata-only result when a query can resolve it" in logical
    assert "do not turn this layer into a star schema" in logical
    assert "Kimball's four decisions" in dimensional
    assert "process-to-dimension bus matrix" in dimensional
    assert "true to the declared grain" in dimensional


def test_mapping_is_flexible_but_has_a_standard_default() -> None:
    mapping = read(WORKFLOWS / "mapping.md")

    assert mapping.index("wait for user confirmation") < mapping.index(
        "The work unit is"
    )
    assert "object-level and attribute-level JSON shape" in mapping
    assert "One confirmation may cover every selected target" in mapping
    assert "structural change requires confirmation again" in mapping
    assert "advisory default" in mapping
    assert "target `model_object_binding`" in mapping
    assert "source System" in mapping
    assert "transformation_document" in mapping
    assert "authoring guidance" in mapping
    assert "JSON storage is flexible" in mapping


def test_code_generation_confirms_a_small_layout_preview_before_authoring() -> None:
    code = read(WORKFLOWS / "code-generation.md")
    example = read(REFERENCES / "examples" / "multi-system-target.sql")

    assert code.index("Before authoring code") < code.index(
        "Code Generation decides artifact/file grouping"
    )
    assert "small representative preview" in code
    assert "wait for user confirmation" in code
    assert "reconfirm if the layout changes" in code
    assert "CREATE OR REPLACE TEMPORARY VIEW" in example
    assert "UNION ALL" in example


def test_validation_confirms_broad_categories_before_authoring_checks() -> None:
    validation = read(WORKFLOWS / "validation.md")

    assert validation.index("broad validation coverage plan") < validation.index(
        "Use applied Mapping"
    )
    for category in ("Technical", "Reconciliation", "Functional/business"):
        assert f"**{category}**" in validation
    assert "representative examples, not every final query" in validation
    assert "wait for user confirmation" in validation
    assert "material coverage change requires confirmation again" in validation


def test_process_registration_collects_missing_details_before_authoring() -> None:
    process = read(WORKFLOWS / "process-registration.md")

    assert process.index("Before authoring") < process.index("Do not infer triggers")
    assert "Ask one consolidated question" in process
    assert "only the missing required details" in process
    assert "artifact-to-Process assignment" in process
    assert "wait for confirmation" in process


def test_grill_with_docs_is_lazy_and_may_promote_decisions() -> None:
    router = read(SKILL_ROOT / "SKILL.md")
    grill = read(REFERENCES / "grill-with-docs.md")

    frontmatter = router.split("---", maxsplit=2)[1]
    assert "Grill With Docs" in frontmatter
    assert "Read `references/grill-with-docs.md` only when requested" in router
    assert "not a target itself" in grill
    assert "Do not force a fixed document template" in grill
    for destination in (
        "Assertions",
        "Conceptual",
        "Logical",
        "Dimensional",
        "Mapping",
        "Code",
        "Validation",
    ):
        assert destination in grill


def test_workbench_opens_once_and_chat_acknowledgement_stays_user_facing() -> None:
    router = read(SKILL_ROOT / "SKILL.md")
    session = read(REFERENCES / "session.md")
    local_helper = read(REFERENCES / "local-helper.md")
    guide = read(PLUGIN_ROOT / "docs" / "USER_GUIDE.md")

    assert "only when the session is first created or the user asks" in router
    assert "do not reopen Workbench unless asked" in session
    assert "never relaunch it after every update" in local_helper
    assert "There is no separate user review command" in guide
    assert "positive acknowledgement accepts the exact current content" in guide
    assert "downloads its ZIP to a temporary file" in guide
    assert "asks for the working directory only when no session path is known" in guide


def test_dbml_is_an_explicit_opt_in_display_export() -> None:
    router = read(SKILL_ROOT / "SKILL.md")
    local_helper = read(REFERENCES / "local-helper.md")
    workbench = read(REFERENCES / "workbench.md")

    rule = (
        "Never generate, regenerate, read, or inspect DBML unless the user "
        "explicitly asks"
    )
    assert rule in router
    assert rule in local_helper
    assert "DBML is a display export, not validation or review evidence" in router
    assert "DBML generation never runs automatically after a Model edit" in workbench


def test_user_guide_explains_vs_code_and_the_simple_workflow() -> None:
    guide = read(PLUGIN_ROOT / "docs" / "USER_GUIDE.md")

    assert "Agent Plugins 1.0" in guide
    assert "VS Code" in guide
    assert '"chat.plugins.enabled": true' in guide
    assert "Workbench opens once" in guide
    assert "Refresh" in guide
    assert "proceed" in guide
    assert "Validation Authoring" in guide
    assert "SQL Preflight" in guide
    assert "## Work targets" in guide
    assert "Tenant, System, and Connection setup is an external" in guide
    assert "Tenant Intake" not in guide
    assert "Users never calculate chunks or hashes manually" in guide
    for target in (
        "Metadata Authoring",
        "Model Input Scope Authoring",
        "Logical Build",
        "Silver Target Registration",
        "Logical Model Binding",
        "Logical Mapping",
        "Logical Code Generation",
        "Dimensional Build",
        "Gold Target Registration",
        "Dimensional Model Binding",
        "Dimensional Mapping",
        "Dimensional Code Generation",
        "Validation Authoring",
        "Process Registration",
    ):
        assert target in guide
