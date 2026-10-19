"""The Atlas evaluation harness itself: replay server, scenarios, sandboxes and scoring.

No model is called here. Live agent runs are opt-in; see tests/atlas/eval/README.md.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import shlex
import shutil
import zipfile
from pathlib import Path
from typing import Any

import pytest
from gds_etl_workbench.adapters.mcp.stage_runner_gate import STAGE_UPLOAD_TOOLS
from gds_etl_workbench.domain.snapshots.metadata import DATASETS_BY_NAME as METADATA_DATASETS
from gds_etl_workbench.domain.snapshots.project import DATASETS_BY_NAME as PROJECT_DATASETS
from mcp import Client

from tests.atlas.eval import harness
from tests.atlas.eval.fake_mcp import create_replay_server, load_world
from tests.mcp.test_tool_schema_contracts import EXPECTED_PUBLIC_TOOLS

FIXTURES = harness.EVAL_ROOT / "fixtures"
HELPER_COMMANDS = set(
    json.loads((harness.PLUGIN_SOURCE / "contracts/local-helper.json").read_text())["commands"]
)
SKILLS = {path.parent.name for path in (harness.PLUGIN_SOURCE / "skills").glob("*/SKILL.md")}
# Every scripted or replayed tool, with arguments the recorded world can answer.
SCRIPTED_CALLS: list[tuple[str, dict[str, Any]]] = [
    ("list_tenants", {}),
    ("get_tenant_details", {"tenant_id": 1}),
    ("list_projects", {"tenant_id": 1}),
    ("get_project_input_scope", {"project_id": 1}),
    ("check_tenant_lock", {"tenant_id": 1}),
    ("acquire_tenant_lock", {"tenant_id": 1, "purpose": "evaluation"}),
    ("renew_tenant_lock", {"tenant_id": 1}),
    ("create_project_change_set", {"project_id": 1}),
    ("create_metadata_change_set", {"tenant_id": 1}),
    (
        "get_project_change_set_fingerprint",
        {"project_id": 1, "project_change_set_id": "20000000-0000-4000-8000-000000000001"},
    ),
    (
        "get_metadata_change_set_fingerprint",
        {"tenant_id": 1, "metadata_change_set_id": "20000000-0000-4000-8000-000000000001"},
    ),
    ("create_metadata_snapshot", {"tenant_id": 1}),
    ("create_project_snapshot", {"project_id": 1}),
    (
        "start_profiling_run",
        {
            "project_id": 1,
            "selected_object_ids": [1],
            "expected_project_revision": 1,
            "request_id": "20000000-0000-4000-8000-000000000009",
        },
    ),
    ("get_profiling_run_status", {"run_id": 9001}),
    ("inspect_metadata", {"tenant_id": 1, "view": "objects", "zone": "bronze"}),
    ("read_project_section", {"project_id": 1, "dataset": "logical_entity", "page_size": 25}),
    (
        "read_mapping_context",
        {
            "project_id": 1,
            "modeled_entity_type": "logical_entity",
            "modeled_entity_schema_name": "silver_demo",
            "modeled_entity_name": "Customer",
            "component": "target_metadata",
            "expected_project_revision": 1,
            "page_size": 100,
        },
    ),
    ("describe_project_dataset", {"dataset": "logical_entity", "detail": "compact"}),
    ("release_tenant_lock", {"tenant_id": 1}),
]


def _calls(tmp_path: Path, calls: list[tuple[str, dict[str, Any]]]) -> list[Any]:
    async def run() -> list[Any]:
        world = load_world(FIXTURES / "world.json", tmp_path / "snapshots", tmp_path / "log.jsonl")
        async with Client(create_replay_server(world)) as client:
            return [await client.call_tool(name, arguments) for name, arguments in calls]

    return asyncio.run(run())


def test_scenarios_reference_real_tools_helpers_skills_and_datasets() -> None:
    datasets = set(METADATA_DATASETS) | set(PROJECT_DATASETS)
    scenarios = harness.load_scenarios()
    assert len(scenarios) >= 10
    for scenario in scenarios:
        expect = scenario["expect"]
        for tool in [*expect.get("required_tools", []), *expect.get("forbidden_tools", [])]:
            assert tool in EXPECTED_PUBLIC_TOOLS, (scenario["id"], tool)
        for command in [
            *expect.get("required_helper_commands", []),
            *expect.get("helper_commands_any", []),
            *expect.get("forbidden_helper_commands", []),
        ]:
            assert command in HELPER_COMMANDS, (scenario["id"], command)
        for skill in expect.get("skills_read_any", []):
            assert skill in SKILLS, (scenario["id"], skill)
        for dataset in expect.get("forbidden_helper_datasets", []):
            assert dataset in datasets, (scenario["id"], dataset)


def test_replay_server_exposes_the_real_tool_surface(tmp_path: Path) -> None:
    async def tools() -> set[str]:
        world = load_world(FIXTURES / "world.json", tmp_path / "snapshots", tmp_path / "log.jsonl")
        async with Client(create_replay_server(world)) as client:
            return {tool.name for tool in (await client.list_tools()).tools}

    # Evaluated agents connect like Copilot, not the Stage Runner.
    assert asyncio.run(tools()) == EXPECTED_PUBLIC_TOOLS - STAGE_UPLOAD_TOOLS


def test_replayed_and_scripted_results_satisfy_the_real_output_schemas(tmp_path: Path) -> None:
    # The MCP client validates structured content against each tool's output schema.
    results = _calls(tmp_path, SCRIPTED_CALLS)
    assert [result.is_error for result in results] == [False] * len(SCRIPTED_CALLS)
    snapshot = results[12].structured_content
    assert snapshot["download_url"].startswith("file://")
    assert Path(snapshot["download_url"].removeprefix("file://")).is_file()
    logged = [
        json.loads(line)["tool"] for line in (tmp_path / "log.jsonl").read_text().splitlines()
    ]
    assert logged == [name for name, _ in SCRIPTED_CALLS]


def test_governed_writes_are_refused_and_logged(tmp_path: Path) -> None:
    refused = [
        ("stage_project_change_set", {"project_id": 1}, "stage_runner_required"),
        ("begin_metadata_stage_batch", {"tenant_id": 1}, "stage_runner_required"),
        ("apply_project_change_set", {"project_id": 1}, "evaluation_requires_stage_runner"),
        ("override_tenant_lock", {"tenant_id": 1, "reason": "x"}, "authorization_denied"),
        ("execute_databricks_sql", {"connection_id": 1, "sql": "SELECT 1"}, "databricks"),
        ("create_project_change_set", {"project_id": 1}, "tenant_lock_required"),
        ("read_project_section", {"project_id": 99, "dataset": "logical_entity"}, "evaluation"),
    ]
    results = _calls(tmp_path, [(name, arguments) for name, arguments, _ in refused])
    for result, (name, _, code) in zip(results, refused, strict=True):
        assert result.is_error is True, name
        assert f"Error executing tool {name}: {code}" in result.content[0].text
    outcomes = [
        json.loads(line)["outcome"] for line in (tmp_path / "log.jsonl").read_text().splitlines()
    ]
    assert outcomes == ["error"] * len(refused)


def test_mapping_replay_skips_omitted_fences_and_refuses_stale_ones(tmp_path: Path) -> None:
    # The real reader checks expected_* fences only when supplied, against current values.
    world = json.loads((FIXTURES / "world.json").read_text())
    digest = next(
        response["result"]["context_digest"]
        for response in world["responses"]
        if response["arguments"].get("modeled_entity_name") == "Customer"
    )
    target = {
        "project_id": 1,
        "modeled_entity_type": "logical_entity",
        "modeled_entity_schema_name": "silver_demo",
        "modeled_entity_name": "Customer",
    }
    current = [
        {"component": "target_metadata"},
        {"component": "source_metadata", "expected_project_revision": None},
        {"component": "source_systems", "expected_project_revision": 1},
        {"component": "target_metadata", "expected_context_digest": digest},
    ]
    stale = [
        {"component": "target_metadata", "expected_project_revision": 2},
        {"component": "source_metadata", "expected_context_digest": "0" * 64},
    ]
    results = _calls(
        tmp_path, [("read_mapping_context", {**target, **fences}) for fences in current + stale]
    )
    assert [result.is_error for result in results] == [False] * len(current) + [True] * len(stale)
    replayed = results[: len(current)]
    assert {result.structured_content["context_digest"] for result in replayed} == {digest}
    assert "invalid_request: Project revision changed" in results[-2].content[0].text
    assert "invalid_request: Mapping context changed" in results[-1].content[0].text


def test_dry_run_sandboxes_seed_real_workspaces_and_isolate_the_plugin(tmp_path: Path) -> None:
    scenarios = {scenario["id"]: scenario for scenario in harness.load_scenarios()}
    sandbox = harness.build_sandbox(scenarios["resume-uncertain-stage"], tmp_path)
    prompt = (sandbox.root / "prompt.md").read_text()
    assert prompt.count("/SKILL.md)") == len(SKILLS)
    assert scenarios["resume-uncertain-stage"]["request"] in prompt
    server = json.loads((sandbox.root / "mcp.json").read_text())["mcpServers"]["gds-workbench"]
    assert server["args"][:2] == ["-m", "tests.atlas.eval.fake_mcp"]
    assert "[mcp_servers.gds-workbench]" in (sandbox.root / "codex-mcp.toml").read_text()
    assert not list(sandbox.plugin.rglob("node_modules"))
    session = json.loads((sandbox.workspace / ".atlas/session.json").read_text())
    operation = json.loads((sandbox.workspace / session["operations"]["project"]).read_text())
    assert operation["stage_attempt"] == {"status": "unknown"}
    harness_log = sandbox.logs / "helper_calls.jsonl"
    assert harness_log.read_text() == ""  # Seeding is not agent activity.
    shim = sandbox.plugin / "scripts/atlas-local.js"
    import subprocess

    status = subprocess.run(
        ["node", str(shim), "status", "--session", str(sandbox.workspace)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(status.stdout)["task_count"] == 1
    unknown = subprocess.run(["node", str(shim), "no-such-command"], capture_output=True)
    assert unknown.returncode == 1
    logged = [json.loads(line) for line in harness_log.read_text().splitlines()]
    assert [(call["argv"][0], call["status"]) for call in logged] == [
        ("status", 0),
        ("no-such-command", 1),
    ]


def _simulate(
    sandbox: harness.Sandbox,
    *,
    tools: list[str],
    helpers: list[list[str]],
    failed_helpers: tuple[list[str], ...] = (),
) -> None:
    with (sandbox.logs / "mcp_calls.jsonl").open("a") as handle:
        for index, tool in enumerate(tools, start=1):
            handle.write(json.dumps({"seq": index, "tool": tool, "arguments": {}}) + "\n")
    with (sandbox.logs / "helper_calls.jsonl").open("a") as handle:
        for argv in helpers:
            handle.write(json.dumps({"argv": argv, "status": 0}) + "\n")
        for argv in failed_helpers:
            handle.write(json.dumps({"argv": argv, "status": 1}) + "\n")


def test_scorer_passes_a_compliant_run_and_names_each_violation(tmp_path: Path) -> None:
    scenario = next(item for item in harness.load_scenarios() if item["id"] == "logical-sql-never")
    good = harness.build_sandbox(scenario, tmp_path / "good")
    _simulate(
        good,
        tools=["create_project_snapshot"],
        helpers=[
            ["select", "--dataset", "logical_entity"],
            ["validate", "--area", "project"],
            ["coverage", "--layer", "logical"],
        ],
    )
    (good.workspace / "project-change-set").mkdir(exist_ok=True)
    (good.workspace / "project-change-set/logical_entity.json").write_text("[]")
    (good.logs / "transcript.jsonl").write_text(
        json.dumps({"type": "tool_use", "input": {"path": "skills/atlas-logical-model/SKILL.md"}})
        + "\n"
    )
    report = harness.score(scenario, good)
    assert report["passed"], report["checks"]
    assert {item["id"] for item in report["checks"]} >= {
        "no-agent-stage-transport",
        "snapshots-not-hand-edited",
        "read-expected-skill",
        "produced-required-file",
    }

    bad = harness.build_sandbox(scenario, tmp_path / "bad")
    _simulate(
        bad,
        tools=["stage_project_change_set", "execute_databricks_sql", "apply_project_change_set"],
        helpers=[["select", "--dataset", "conceptual_object"]],
        failed_helpers=(["validate", "--area", "project"],),  # A failed run is not a pass.
    )
    manifest = bad.workspace / "project/project-snapshot/manifest.json"
    manifest.write_text(manifest.read_text() + " ")
    failed = {
        item["id"] for item in harness.score(scenario, bad)["checks"] if item["status"] == "failed"
    }
    assert failed == {
        "no-agent-stage-transport",
        "no-unapproved-apply-or-override",
        "snapshots-not-hand-edited",
        "not-called:execute_databricks_sql",
        "helper:validate",
        "helper:coverage",
        "not-read:conceptual_object",
        "produced-required-file",
    }


def test_scorer_accepts_a_needed_question_only_when_nothing_changed(tmp_path: Path) -> None:
    scenario = next(
        item for item in harness.load_scenarios() if item["id"] == "dimension-from-logical"
    )
    question = (
        "Dim Customer has no history rule. Should it overwrite (Type 1) or keep history (Type 2)?"
    )

    def run(name: str, final: str, *, edit: bool = False, task: bool = False) -> dict[str, str]:
        sandbox = harness.build_sandbox(scenario, tmp_path / name)
        _simulate(
            sandbox, tools=[], helpers=[["inspect"], ["select", "--dataset", "dimensional_entity"]]
        )
        if edit:
            (sandbox.workspace / "project-change-set").mkdir(exist_ok=True)
            (sandbox.workspace / "project-change-set/dimensional_entity.json").write_text("[]")
        if task:  # Task bookkeeping is not a draft change.
            (sandbox.workspace / ".atlas/tasks").mkdir(parents=True, exist_ok=True)
            (sandbox.workspace / ".atlas/tasks/dimension.json").write_text("{}")
        (sandbox.logs / "transcript.jsonl").write_text(
            json.dumps(
                {"type": "tool_use", "input": {"path": "skills/atlas-dimensional-model/SKILL.md"}}
            )
            + "\n"
            + json.dumps({"type": "result", "result": final})
            + "\n"
        )
        report = harness.score(scenario, sandbox)
        return {item["id"]: item["status"] for item in report["checks"]} | {
            "passed": str(report["passed"])
        }

    asked = run("asked", question)
    assert asked["passed"] == "True"
    assert asked["asked-instead"] == "passed"
    assert asked["helper:validate"] == asked["produced-required-file"] == "skipped"
    assert run("asked-with-task", question, task=True)["asked-instead"] == "passed"
    # A statement is not a question, and a question does not excuse a partial edit.
    assert run("statement", "Dim Customer uses Type 1.")["helper:validate"] == "failed"
    edited = run("edited", question, edit=True)
    assert "asked-instead" not in edited and edited["helper:validate"] == "failed"


def test_seed_files_land_in_the_workspace_and_unsafe_paths_are_rejected(tmp_path: Path) -> None:
    scenario = next(item for item in harness.load_scenarios() if item["id"] == "code-error-fix")
    sandbox = harness.build_sandbox(scenario, tmp_path / "run")
    seeded = sandbox.workspace / "code/silver_customer.sql"
    assert seeded.read_text() == scenario["seed_files"]["code/silver_customer.sql"]
    assert not harness._changed_files(sandbox)  # Seeded files are the starting point.
    for unsafe in ("../escape.sql", "/tmp/escape.sql", ".atlas/session.json", "project/x.json"):
        path = tmp_path / "unsafe.json"
        path.write_text(json.dumps({"scenarios": [{**scenario, "seed_files": {unsafe: "x"}}]}))
        with pytest.raises(AssertionError):
            harness.load_scenarios(path)


def test_judge_verdict_reads_raw_fenced_and_cli_wrapped_json() -> None:
    raw = json.dumps({"criteria": [{"id": "asks", "passed": True, "reason": "It asks."}]})
    fenced = "Verdict:\n```json\n" + raw + "\n```"
    envelope = json.dumps({"type": "result", "result": fenced})
    stream = json.dumps({"type": "system", "subtype": "init"}) + "\n" + envelope + "\n"
    for output in (raw, fenced, envelope, stream):
        assert harness._judge_verdict(output)["asks"]["passed"] is True, output
    assert harness._judge_verdict("I could not decide.") == {}


def test_grader_builds_its_prompt_and_applies_the_pass_rule(tmp_path: Path) -> None:
    scenario = next(
        item for item in harness.load_scenarios() if item["id"] == "change-request-country"
    )
    quality = scenario["quality"]
    sandbox = harness.build_sandbox(scenario, tmp_path / "run")
    final = "No source has country. Where does it come from?"
    (sandbox.logs / "transcript.jsonl").write_text(
        json.dumps({"type": "result", "result": final}) + "\n"
    )
    (sandbox.workspace / "code").mkdir()
    (sandbox.workspace / "code/dim_customer.sql").write_text("select 1")
    ids = [item["id"] for item in quality["criteria"]]
    required = [item["id"] for item in quality["criteria"] if item["required"]]
    optional = [item for item in ids if item not in required]

    def judge(passed: set[str], name: str = "verdict.json") -> dict[str, Any]:
        verdict = tmp_path / name
        verdict.write_text(
            json.dumps({"criteria": [{"id": i, "passed": i in passed, "reason": "r"} for i in ids]})
        )
        # A stand-in judge that ignores the prompt and prints a fixed verdict.
        return harness.grade(scenario, sandbox, f"cat {shlex.quote(str(verdict))}", 30)

    need = quality["min_optional"]
    assert judge({*required, *optional[:need]})["quality_passed"] is True
    assert judge({*required, *optional[: need - 1]})["quality_passed"] is False
    assert judge({*required[1:], *optional})["quality_passed"] is False
    prompt = (sandbox.root / "grade_prompt.md").read_text()
    assert scenario["request"] in prompt and final in prompt
    assert quality["reference"][0] in prompt and "### code/dim_customer.sql\nselect 1" in prompt
    assert all(f"- {identifier} (" in prompt for identifier in ids)
    assert ".atlas/" not in prompt.split("## Files the run changed")[1]
    # A criterion the judge leaves out counts as failed.
    partial = tmp_path / "partial.json"
    partial.write_text(
        json.dumps({"criteria": [{"id": i, "passed": True, "reason": "r"} for i in required]})
    )
    unanswered = harness.grade(scenario, sandbox, f"cat {shlex.quote(str(partial))}", 30)
    assert unanswered["quality_passed"] is False
    assert {i["reason"] for i in unanswered["criteria"] if not i["required"]} == {"not graded"}
    # No verdict at all, such as a judge that cannot run, is a grading error, not a failed run.
    failed_judge = harness.grade(scenario, sandbox, "echo 'API Error: 400' && exit 1", 30)
    assert failed_judge["quality_passed"] is None
    assert failed_judge["judge_error"] == "no verdict from the judge (exit status 1)"


_RANDOM = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|\b[0-9a-f]{64}\b"
)


def _canonical(value: Any) -> Any:
    """Seeds create random UUIDs (and digests over them), which also change sort order."""
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        items = [_canonical(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, str):
        return _RANDOM.sub("<random>", value)
    return value


def _comparable_world(world: dict[str, Any]) -> list[str]:
    volatile = {"snapshot_id", "download_url", "download_url_expires_at", "sha256", "size_bytes"}
    return sorted(
        json.dumps(
            _canonical(
                {
                    "tool": response["tool"],
                    "arguments": response["arguments"],
                    "result": {
                        key: value
                        for key, value in response["result"].items()
                        if key not in volatile
                    },
                }
            ),
            sort_keys=True,
        )
        for response in world["responses"]
    )


def _archive_members(path: Path) -> dict[str, list[str]]:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        return {
            name: sorted(_RANDOM.sub("<random>", archive.read(name).decode()).splitlines())
            for name in archive.namelist()
            if not name.endswith(("manifest.json", "catalog.json"))
        }


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is required")
def test_eval_world_matches_current_server(tmp_path: Path) -> None:
    """Fails when schema, seeds or Snapshot encoding changed; rerun build_fixtures."""
    from tests.atlas.eval.build_fixtures import build

    build(tmp_path)
    committed = json.loads((FIXTURES / "world.json").read_text())
    rebuilt = json.loads((tmp_path / "world.json").read_text())
    assert _comparable_world(rebuilt) == _comparable_world(committed)
    for kind in ("metadata", "project"):
        name = committed["snapshots"][kind]["file"]
        assert _archive_members(tmp_path / name) == _archive_members(FIXTURES / name), kind
