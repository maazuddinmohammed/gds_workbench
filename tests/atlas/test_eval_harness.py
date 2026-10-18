"""The Atlas evaluation harness itself: replay server, scenarios, sandboxes and scoring.

No model is called here. Live agent runs are opt-in; see tests/atlas/eval/README.md.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
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
    assert json.loads(harness_log.read_text())["argv"][0] == "status"


def _simulate(sandbox: harness.Sandbox, *, tools: list[str], helpers: list[list[str]]) -> None:
    with (sandbox.logs / "mcp_calls.jsonl").open("a") as handle:
        for index, tool in enumerate(tools, start=1):
            handle.write(json.dumps({"seq": index, "tool": tool, "arguments": {}}) + "\n")
    with (sandbox.logs / "helper_calls.jsonl").open("a") as handle:
        for argv in helpers:
            handle.write(json.dumps({"argv": argv}) + "\n")


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
