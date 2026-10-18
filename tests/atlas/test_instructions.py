"""Lint the packaged Atlas instructions against the code they describe.

Skills and references are runtime instructions for the agent, so drift from the helper
contract, MCP tool inventory or backend defaults makes the agent fail in practice.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from gds_etl_workbench.application.change_sets.metadata import (
    CHANGE_SET_DATASETS as METADATA_CHANGE_SET_DATASETS,
)
from gds_etl_workbench.domain.snapshots.project import DATASETS as PROJECT_DATASETS
from gds_workbench_api.features.workflows.authoring.audit_policy import effective_audit_template
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates

from tests.mcp.test_tool_schema_contracts import EXPECTED_PUBLIC_TOOLS

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "atlas/atlas-plugin"
INSTRUCTIONS = sorted(
    path
    for folder in ("skills", "references", "templates", "docs")
    for path in (PLUGIN / folder).rglob("*.md")
)
EXTENSION_TOOLS = {
    tool["name"]
    for tool in json.loads((ROOT / "atlas/atlas-vs-code/package.json").read_text())["contributes"][
        "languageModelTools"
    ]
}
HELPER_COMMANDS = set(
    json.loads((PLUGIN / "contracts/local-helper.json").read_text(encoding="utf-8"))["commands"]
)
_PRIORITY = re.search(
    r"const NEXT_PRIORITY = \[(.*?)\];",
    (PLUGIN / "scripts/atlas-local.js").read_text(encoding="utf-8"),
    re.DOTALL,
)
assert _PRIORITY is not None
# Every state `next` can report; several share a tool verb prefix.
NEXT_STATES = set(re.findall(r'"([a-z_]+)"', _PRIORITY.group(1))) | {"error_recovery", "no_session"}
TOOL_VERBS = (
    "list_|get_|create_|stage_|begin_|put_|commit_|validate_|apply_|archive_|read_|"
    "describe_|inspect_|start_|cancel_|check_|acquire_|renew_|release_|override_|execute_"
)
# Names that instructions mention only to say they do not exist.
DOCUMENTED_ABSENT_TOOLS = {"get_project_details"}
# Response and manifest fields shaped like tool names.
# Field names and server error codes that share a tool verb prefix.
NON_TOOL_IDENTIFIERS = {"stage_manifest_path", "stage_runner_required"}
# Phrases from superseded designs. Each one previously contradicted current behavior.
STALE_PHRASES = (
    "Codex",
    "atlas-connector",
    "remain to be defined",
    "for later implementation",
    "No paging",
    "neither view adds an offset/cursor",
    "Source pointers",
    "Development provenance",
    "not parity-tested",
    "cannot read/write the web workflow's Project-owned enrichment",
    "EffectiveFrom",
    "IsCurrent`",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prose(path: Path) -> str:
    """Instruction text outside fenced examples."""
    return re.sub(r"```.*?```", "", _text(path), flags=re.DOTALL)


def test_instructions_do_not_point_at_server_source_files() -> None:
    pattern = re.compile(r"mcp_server/|web_app/|database/\d\d_|database/seed/|[\w/-]+\.py\b")
    offenders = [
        f"{path.relative_to(PLUGIN)}: {match.group(0)}"
        for path in INSTRUCTIONS
        for match in pattern.finditer(_text(path))
    ]
    assert not offenders, "Packaged instructions must not depend on unpackaged source files"


def test_instructions_contain_no_superseded_phrases() -> None:
    offenders = [
        f"{path.relative_to(PLUGIN)}: {phrase}"
        for path in INSTRUCTIONS
        for phrase in STALE_PHRASES
        if phrase in _text(path)
    ]
    assert not offenders


def test_helper_commands_named_in_instructions_exist() -> None:
    pattern = re.compile(
        r"atlas-local\.(?:js|ps1)\s+([a-z][a-z-]*)|`([a-z][a-z-]+) --(?:session|root|command)\b"
    )
    named = {
        (path.relative_to(PLUGIN).as_posix(), command)
        for path in INSTRUCTIONS
        for match in pattern.finditer(_text(path))
        for command in [match.group(1) or match.group(2)]
        if command not in {"command"}
    }
    unknown = sorted(item for item in named if item[1] not in HELPER_COMMANDS)
    assert not unknown


def test_tools_named_in_instructions_exist() -> None:
    pattern = re.compile(rf"`((?:{TOOL_VERBS})[a-z0-9_]+)`|\b((?:{TOOL_VERBS})[a-z0-9_]+)\(")
    known = EXPECTED_PUBLIC_TOOLS | DOCUMENTED_ABSENT_TOOLS | NON_TOOL_IDENTIFIERS | NEXT_STATES
    named = {
        (path.relative_to(PLUGIN).as_posix(), name)
        for path in INSTRUCTIONS
        for match in pattern.finditer(_prose(path))
        for name in [match.group(1) or match.group(2)]
    }
    unknown = sorted(item for item in named if item[1] not in known)
    assert not unknown
    for path in INSTRUCTIONS:
        for name in re.findall(r"\batlas_[a-z]+[A-Z][A-Za-z]*\b", _text(path)):
            assert name in EXTENSION_TOOLS, (path.relative_to(PLUGIN), name)


def test_documented_dataset_counts_match_the_server() -> None:
    metadata_index = _text(PLUGIN / "references/metadata/index.md")
    assert f"All {len(METADATA_CHANGE_SET_DATASETS)} accepted Metadata Change Set datasets" in (
        metadata_index
    )
    assert f"{len(METADATA_CHANGE_SET_DATASETS)} operational datasets" in metadata_index
    project_snapshot = _text(PLUGIN / "references/snapshots/project.md")
    assert f"Current Project catalogs contain {len(PROJECT_DATASETS)} datasets" in project_snapshot


def test_documented_gold_defaults_match_backend_projection() -> None:
    keys, _ = effective_gold_templates(None, None)
    type_2 = keys["type_2"]
    assert isinstance(type_2, dict)
    names = [
        entry["semantic_name"]  # pyright: ignore[reportUnknownVariableType]
        for entry in type_2.values()  # pyright: ignore[reportUnknownMemberType]
    ]
    for reference in ("references/dimensional-build/history.md", "references/project/settings.md"):
        text = _text(PLUGIN / reference)
        assert all(f"`{name}`" in text or f'"{name}"' in text for name in names), reference
    audit = effective_audit_template(None)["columns"]
    assert isinstance(audit, list)
    settings = _text(PLUGIN / "references/project/settings.md")
    for column in audit:  # pyright: ignore[reportUnknownVariableType]
        assert f'"{column["semantic_name"]}"' in settings  # pyright: ignore[reportUnknownArgumentType]


def test_lifecycle_explains_every_next_state() -> None:
    lifecycle = _text(PLUGIN / "references/change-set-lifecycle.md")
    table = lifecycle[lifecycle.index("| State | Meaning |") :]
    documented = set(re.findall(r"^\| ([^|]+) \|", table, re.MULTILINE))
    named = {name for row in documented for name in re.findall(r"`([a-z_]+)`", row)}
    assert named == NEXT_STATES


SKILL_SECTIONS = ["When to use", "What you need", "Steps", "Done when", "Ask the user when", "Next"]
HELPER_USAGES = {
    name: spec["usage"]
    for name, spec in json.loads((PLUGIN / "contracts/local-helper.json").read_text())[
        "commands"
    ].items()
}


def test_skills_follow_one_short_step_template() -> None:
    for skill in sorted((PLUGIN / "skills").glob("*/SKILL.md")):
        body = _text(skill).split("---", 2)[2]
        assert re.findall(r"^## (.+)$", body, re.MULTILINE) == SKILL_SECTIONS, skill
        assert len(_prose(skill).split("---", 2)[2].split()) <= 450, skill
        # Skill-to-skill links route; reference links are what the agent must read.
        assert len(re.findall(r"\]\((?:\.\./)+(?:references|templates)/", body)) <= 5, skill
        assert "references/working-method.md" in body, skill
        steps = body.split("## Steps", 1)[1].split("## Done when", 1)[0]
        assert 3 <= len(re.findall(r"^\d+\. ", steps, re.MULTILINE)) <= 9, skill


def test_helper_command_examples_use_contract_flags() -> None:
    for path in INSTRUCTIONS:
        for span in re.findall(r"`([a-z][a-z-]+ --[^`]*)`", _text(path)):
            command = span.split()[0]
            if command not in HELPER_USAGES:
                continue
            allowed = set(re.findall(r"--([a-z0-9-]+)", HELPER_USAGES[command]))
            used = set(re.findall(r"(?<!\S)--([a-z0-9-]+)", span))
            assert used <= allowed | {"output-file", "task"}, (path.relative_to(PLUGIN), span)
