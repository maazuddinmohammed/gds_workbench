"""Prompt Studio round-trips the default prompts exactly and scores agent test results."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

_STUDIO_PATH = Path(__file__).resolve().parents[2] / "web_app" / "prompt_studio" / "studio.py"


def _studio() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prompt_studio", _STUDIO_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_then_build_reproduces_the_seed_byte_for_byte(tmp_path: Path) -> None:
    studio = _studio()
    head, items, tail = studio.read_seed()
    for item in items:
        stage = studio.stage_id(item)
        (tmp_path / f"{stage}.md").write_text(
            studio.stage_file_text(
                stage,
                item["system_prompt"],
                item["instruction_prompt"],
                item.get("agent_tool_names"),
            ),
            encoding="utf-8",
        )

    merged = studio.merge_items(items, studio.load_studio(tmp_path))

    assert studio.seed_text(head, merged, tail) == studio.SEED.read_text(encoding="utf-8")


def test_section_numbers_are_added_renumbered_and_removed_exactly() -> None:
    studio = _studio()
    text = "Intro\n## Role\nx\n### Detail\n```\n## not a heading\n```\n## Output\ny"

    numbered = studio.number_sections(text, "S")
    moved = numbered.replace("## [S2] Output", "## [S9] Output")

    assert numbered.split("\n")[1:4] == ["## [S1] Role", "x", "### [S1.1] Detail"]
    assert "## not a heading" in numbered and "## [S2] Output" in numbered
    assert studio.number_sections(moved, "S") == numbered
    assert studio.strip_numbers(numbered) == text


def test_every_seed_stage_renders_with_its_registered_variables() -> None:
    studio = _studio()
    _, items, _ = studio.read_seed()
    variables = studio.read_variables()

    problems = {
        studio.stage_id(item): studio.stage_problems(item, variables.get(studio.stage_id(item), []))
        for item in items
    }

    assert {stage: found for stage, found in problems.items() if found} == {}
    assert [
        variable["name"] for variable in variables["analysis.one_shot.per_table_authoring"]
    ] == [
        "source_context",
        "gds_context",
        "context_records",
        "key_directory",
        "focus_table",
        "ingestion_mapping",
        "saved_relationships",
    ]


def test_fixtures_match_their_stage_inputs() -> None:
    studio = _studio()
    variables = studio.read_variables()
    fixtures = sorted(studio.FIXTURES.glob("*/*.json"))

    assert fixtures
    for path in fixtures:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        assert studio.fixture_problems(fixture, variables[path.parent.name]) == [], path.name


def test_score_counts_expected_forbidden_and_other_items_in_valid_answers() -> None:
    studio = _studio()
    fixture = {
        "output_schema": {
            "type": "object",
            "properties": {"relationships": {"type": "array", "items": {"type": "object"}}},
            "required": ["relationships"],
        },
        "expect": {
            "list": "relationships",
            "key": ["from_attribute_name", "to"],
            "expected": [{"from_attribute_name": "EmployeeId", "to": "t1.employeeid"}],
            "forbidden": [{"from_attribute_name": "employeeid", "to": "t4.employeeid"}],
        },
    }
    result = {
        "answer": {
            "relationships": [
                {"from_attribute_name": "employeeid", "to": "T1.EmployeeId "},
                {"from_attribute_name": "employeeid", "to": "t4.employeeid"},
                {"from_attribute_name": "postcode", "to": "t1.postcode"},
            ]
        },
        "review": {
            "clarity": 4,
            "confidence": 9,
            "blockers": [{"section": "S6", "issue": "repeating key"}],
            "comment": "ok",
        },
    }

    score = studio.score_run(result, fixture)
    invalid = studio.score_run({"answer": {"links": []}}, fixture)
    summary = studio.summarize([score, invalid, studio.score_run(None, fixture)], 1)

    assert (score["valid"], score["expected"], score["forbidden"], score["other"]) == (
        True,
        1,
        1,
        1,
    )
    assert (score["clarity"], score["confidence"]) == (4, None)
    assert (invalid["valid"], invalid["expected"]) == (False, 0)
    assert (summary["runs"], summary["returned"], summary["valid"], summary["recall"]) == (
        3,
        2,
        1,
        1.0,
    )
    assert summary["blockers"] == {"S6": 1}
