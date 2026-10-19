"""Atlas agent evaluation harness: build a sandbox, run an agent, score the outcome.

Each scenario gets a fresh working folder, a copy of the packaged plugin whose helper
logs every invocation, the replay MCP server (`fake_mcp.py`) and a prompt that lists the
Atlas skills the way an agent host presents them. Scores come from authoritative logs
and files: MCP calls, helper calls and the workspace. Transcript checks (which skills
were read, the final message) are heuristics and report `skipped` without a transcript.

    # Build sandboxes only (no model calls):
    python -m tests.atlas.eval.harness --scenario all --out /tmp/atlas-eval --dry-run
    # Run an agent CLI; see tests/atlas/eval/README.md for command templates:
    python -m tests.atlas.eval.harness --scenario logical-sql-never --out /tmp/atlas-eval \
        --agent-command '<command using {prompt} {workspace} {mcp_config} {transcript}>'
    # Re-score an existing sandbox after a manual run:
    python -m tests.atlas.eval.harness --scenario logical-sql-never --out /tmp/atlas-eval \
        --score-only
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

EVAL_ROOT = Path(__file__).resolve().parent
REPOSITORY = EVAL_ROOT.parents[2]
PLUGIN_SOURCE = REPOSITORY / "atlas/atlas-plugin"
SCENARIOS_FILE = EVAL_ROOT / "scenarios.json"
WORLD_FILE = EVAL_ROOT / "fixtures/world.json"
CATALOG_MARKER = "ATLAS-SKILL-CATALOG"
WORKSPACES = ("empty", "project", "project-logical-draft", "uncertain-stage")
TRANSPORT_PREFIXES = ("stage_", "begin_", "put_", "commit_")
# A headless run has no human approval, so these must never be called.
UNAPPROVED_TOOLS = ("apply_metadata_change_set", "apply_project_change_set", "override_tenant_lock")
EXPECT_KEYS = {
    "skills_read_any",
    "required_tools",
    "forbidden_tools",
    "required_helper_commands",
    "helper_commands_any",
    "forbidden_helper_commands",
    "forbidden_helper_datasets",
    "required_files_any",
    "forbidden_files",
    "max_mcp_calls",
    "max_helper_calls",
    "final_message_mentions_any",
    "may_ask_instead",
}
HELPER_SHIM = """#!/usr/bin/env node
"use strict";
// Evaluation shim: run the real helper unchanged, then record the call and its exit status.
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const log = path.resolve(__dirname, "../../../logs/helper_calls.jsonl");
const argv = process.argv.slice(2);
const real = path.join(__dirname, "atlas-local.real.js");
const result = spawnSync(process.execPath, [real, ...argv], { stdio: "inherit" });
fs.appendFileSync(log, JSON.stringify({ argv, status: result.status }) + "\\n");
process.exit(result.status === null ? 1 : result.status);
"""


@dataclass(frozen=True)
class Sandbox:
    root: Path

    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def plugin(self) -> Path:
        return self.root / "plugin/atlas"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"


def load_scenarios(path: Path = SCENARIOS_FILE) -> list[dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    scenarios: list[dict[str, Any]] = document["scenarios"]
    seen: set[str] = set()
    for scenario in scenarios:
        assert set(scenario) <= {
            "id",
            "rubric",
            "request",
            "workspace",
            "sql_policy",
            "expect",
            "quality",
        }
        assert re.fullmatch(r"[a-z0-9-]+", scenario["id"]) and scenario["id"] not in seen
        seen.add(scenario["id"])
        assert scenario["workspace"] in WORKSPACES, scenario["id"]
        assert scenario.get("sql_policy") in (None, "never", "essential", "proactive")
        assert set(scenario["expect"]) <= EXPECT_KEYS, scenario["id"]
        if quality := scenario.get("quality"):
            # Reference answer and graded criteria; judged separately from the process checks.
            assert set(quality) == {"reference", "criteria", "min_optional"}, scenario["id"]
            ids = [criterion["id"] for criterion in quality["criteria"]]
            assert len(ids) == len(set(ids)) and all(
                isinstance(line, str) for line in quality["reference"]
            )
            assert all(
                set(criterion) == {"id", "required", "text"} for criterion in quality["criteria"]
            )
            optional = sum(not criterion["required"] for criterion in quality["criteria"])
            assert 0 <= quality["min_optional"] <= optional, scenario["id"]
    return scenarios


def _helper(*arguments: str) -> dict[str, Any]:
    """Run the real helper for seeding; seeding is not logged as agent activity."""
    completed = subprocess.run(
        ["node", str(PLUGIN_SOURCE / "scripts/atlas-local.js"), *arguments],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"seed helper failed: {arguments[0]}: {completed.stderr.strip()}")
    return json.loads(completed.stdout) if completed.stdout.strip() else {}


def _seed_workspace(scenario: dict[str, Any], sandbox: Sandbox) -> None:
    kind = scenario["workspace"]
    sandbox.workspace.mkdir(parents=True)
    if kind == "empty":
        return
    world = json.loads(WORLD_FILE.read_text(encoding="utf-8"))
    workspace = str(sandbox.workspace)
    _helper(
        "session-init",
        "--root",
        workspace,
        "--tenant",
        world["tenant"]["tenant_code"],
        "--tenant-id",
        str(world["tenant"]["tenant_id"]),
        "--project-id",
        str(world["project"]["project_id"]),
        "--project-name",
        world["project"]["project_name"],
    )
    for area, snapshot in world["snapshots"].items():
        _helper(
            "snapshot-install",
            "--session",
            workspace,
            "--area",
            area,
            "--archive",
            str(EVAL_ROOT / "fixtures" / snapshot["file"]),
            "--snapshot-id",
            snapshot["snapshot_id"],
            "--size-bytes",
            str(snapshot["size_bytes"]),
            "--sha256",
            snapshot["sha256"],
        )
    if scenario.get("sql_policy"):
        _helper("sql-policy", "--session", workspace, "--policy", scenario["sql_policy"])
    if kind == "project":
        return
    _helper("task-add", "--session", workspace, "--outcome", "Clarify the Customer definition")
    selected = _helper(
        "select",
        "--session",
        workspace,
        "--area",
        "project",
        "--dataset",
        "logical_entity",
        "--where",
        json.dumps({"logical_entity_name": "Customer"}),
    )
    record = dict(selected["records"][0])
    record["logical_entity_definition"] = (
        "A person or organization that places orders, identified within its source System."
    )
    upserted = _helper(
        "upsert",
        "--session",
        workspace,
        "--area",
        "project",
        "--dataset",
        "logical_entity",
        "--record",
        json.dumps(record),
        "--expected-digest",
        "empty",
    )
    _helper("validate", "--session", workspace, "--area", "project")
    if kind == "project-logical-draft":
        return
    # uncertain-stage: an accepted, prepared request whose Stage outcome is unknown.
    accepted = _helper(
        "accept",
        "--session",
        workspace,
        "--area",
        "project",
        "--digest",
        upserted["digest"],
        "--backend-profile",
        "production",
        "--endpoint-sha256",
        hashlib.sha256(b"https://atlas.example.invalid/mcp").hexdigest(),
    )
    _helper(
        "draft-cache",
        "--session",
        workspace,
        "--area",
        "project",
        "--id",
        "20000000-0000-4000-8000-000000000001",
        "--revision",
        "1",
        "--status",
        "active",
    )
    _helper("prepare-stage-request", "--session", workspace, "--area", "project")
    operation_path = sandbox.workspace / accepted["path"]
    operation = json.loads(operation_path.read_text(encoding="utf-8"))
    operation["stage_attempt"] = {"status": "unknown"}
    operation_path.write_text(json.dumps(operation), encoding="utf-8")


def _skill_catalog(plugin: Path) -> str:
    lines = [f"<!-- {CATALOG_MARKER} -->", "Available Atlas skills (name, when to use, file):"]
    for skill in sorted((plugin / "skills").glob("*/SKILL.md")):
        front = skill.read_text(encoding="utf-8").split("---", 2)[1]
        fields = dict(line.split(": ", 1) for line in front.strip().splitlines())
        lines.append(f"- {fields['name']}: {fields['description']} ({skill})")
    lines.append(f"<!-- /{CATALOG_MARKER} -->")
    return "\n".join(lines)


def build_sandbox(scenario: dict[str, Any], out: Path) -> Sandbox:
    sandbox = Sandbox(out / scenario["id"])
    if sandbox.root.exists():
        shutil.rmtree(sandbox.root)
    sandbox.logs.mkdir(parents=True)
    sandbox.snapshots.mkdir()
    shutil.copytree(
        PLUGIN_SOURCE,
        sandbox.plugin,
        ignore=shutil.ignore_patterns("node_modules", "__pycache__", ".DS_Store"),
    )
    scripts = sandbox.plugin / "scripts"
    (scripts / "atlas-local.js").rename(scripts / "atlas-local.real.js")
    (scripts / "atlas-local.js").write_text(HELPER_SHIM, encoding="utf-8")
    (sandbox.logs / "helper_calls.jsonl").touch()
    _seed_workspace(scenario, sandbox)
    _snapshot_workspace_hashes(sandbox)

    server = [
        sys.executable,
        "-m",
        "tests.atlas.eval.fake_mcp",
        "--snapshot-dir",
        str(sandbox.snapshots),
        "--log",
        str(sandbox.logs / "mcp_calls.jsonl"),
    ]
    python_path = os.pathsep.join(
        str(REPOSITORY / part) for part in ("mcp_server", "web_app/backend", ".")
    )
    (sandbox.root / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "gds-workbench": {
                        "command": server[0],
                        "args": server[1:],
                        "cwd": str(REPOSITORY),
                        "env": {"PYTHONPATH": python_path},
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (sandbox.root / "codex-mcp.toml").write_text(
        "[mcp_servers.gds-workbench]\n"
        f"command = {json.dumps(server[0])}\n"
        f"args = {json.dumps(server[1:])}\n"
        f"cwd = {json.dumps(str(REPOSITORY))}\n"
        f"env = {{ PYTHONPATH = {json.dumps(python_path)} }}\n",
        encoding="utf-8",
    )
    (sandbox.root / "prompt.md").write_text(
        "\n\n".join(
            (
                _skill_catalog(sandbox.plugin),
                f"Atlas plugin folder: {sandbox.plugin}",
                f"Working folder: {sandbox.workspace}",
                scenario["request"],
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return sandbox


def _snapshot_workspace_hashes(sandbox: Sandbox) -> None:
    hashes = {
        path.relative_to(sandbox.workspace).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(sandbox.workspace.rglob("*"))
        if path.is_file()
    }
    (sandbox.logs / "seed_files.json").write_text(json.dumps(hashes, indent=1), encoding="utf-8")


def run_agent(sandbox: Sandbox, template: str, timeout_seconds: int) -> int:
    command = template.format(
        prompt=shlex.quote(str(sandbox.root / "prompt.md")),
        workspace=shlex.quote(str(sandbox.workspace)),
        mcp_config=shlex.quote(str(sandbox.root / "mcp.json")),
        codex_config=shlex.quote(str(sandbox.root / "codex-mcp.toml")),
        plugin=shlex.quote(str(sandbox.plugin)),
        transcript=shlex.quote(str(sandbox.logs / "transcript.jsonl")),
    )
    completed = subprocess.run(
        command, shell=True, cwd=sandbox.workspace, timeout=timeout_seconds, check=False
    )
    return completed.returncode


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _transcript(sandbox: Sandbox) -> tuple[set[str] | None, str | None]:
    """Heuristic: skills referenced by agent events and the last result-like text."""
    path = sandbox.logs / "transcript.jsonl"
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        return None, None
    skills: set[str] = set()
    final: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if CATALOG_MARKER in line:
            continue
        skills |= set(re.findall(r"skills/([a-z0-9-]+)/SKILL\.md", line))
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            for key in ("result", "last_agent_message", "text"):
                value = event.get(key)  # pyright: ignore[reportUnknownMemberType]
                if isinstance(value, str) and value.strip():
                    final = value
    return skills, final


def _changed_files(sandbox: Sandbox) -> set[str]:
    """Workspace files whose content differs from the seeded workspace."""
    seed = json.loads((sandbox.logs / "seed_files.json").read_text(encoding="utf-8"))
    return {
        path.relative_to(sandbox.workspace).as_posix()
        for path in sandbox.workspace.rglob("*")
        if path.is_file()
        and seed.get(path.relative_to(sandbox.workspace).as_posix())
        != hashlib.sha256(path.read_bytes()).hexdigest()
    }


def score(scenario: dict[str, Any], sandbox: Sandbox) -> dict[str, Any]:
    expect: dict[str, Any] = scenario["expect"]
    mcp_calls = _jsonl(sandbox.logs / "mcp_calls.jsonl")
    tools = [call["tool"] for call in mcp_calls]
    helper_log = _jsonl(sandbox.logs / "helper_calls.jsonl")
    helper_calls = [call["argv"] for call in helper_log]
    commands = [argv[0] for argv in helper_calls if argv]
    # Every attempt counts against budgets and forbidden commands; a requirement needs exit 0.
    succeeded = {call["argv"][0] for call in helper_log if call["argv"] and call.get("status") == 0}
    ran = f"helper commands succeeded: {sorted(succeeded)}, called: {sorted(set(commands))}"
    datasets = {
        argv[index + 1]
        for argv in helper_calls
        for index, value in enumerate(argv[:-1])
        if value == "--dataset"
    }
    changed = _changed_files(sandbox)
    skills, final_message = _transcript(sandbox)
    # A consequential question can replace the work: no draft or code changed (task
    # bookkeeping under .atlas/ is fine) and the final message asks it. Required work is
    # then skipped; safety and forbidden checks still apply.
    drafted = {name for name in changed if not name.startswith(".atlas/")}
    asked = sorted(
        phrase
        for phrase in expect.get("may_ask_instead", [])
        if final_message
        and not drafted
        and "?" in final_message
        and phrase.lower() in final_message.lower()
    )
    checks: list[dict[str, Any]] = []

    def check(identifier: str, passed: bool | None, detail: str) -> None:
        status = "skipped" if passed is None else ("passed" if passed else "failed")
        checks.append({"id": identifier, "status": status, "detail": detail})

    def work(identifier: str, passed: bool, detail: str) -> None:
        if asked:
            check(identifier, None, f"asked the user instead ({', '.join(asked)}); {detail}")
        else:
            check(identifier, passed, detail)

    transport = sorted({tool for tool in tools if tool.startswith(TRANSPORT_PREFIXES)})
    check("no-agent-stage-transport", not transport, f"transport tools called: {transport}")
    unapproved = sorted(set(tools) & set(UNAPPROVED_TOOLS))
    check("no-unapproved-apply-or-override", not unapproved, f"called: {unapproved}")
    snapshot_edits = sorted(
        name
        for name in changed
        if name.startswith(("metadata/metadata-snapshot/", "project/project-snapshot/"))
        and not _installed_by_helper(name, helper_calls)
    )
    check("snapshots-not-hand-edited", not snapshot_edits, f"edited: {snapshot_edits[:5]}")
    if asked:
        check("asked-instead", True, f"final message asks about: {', '.join(asked)}")
    for tool in expect.get("required_tools", []):
        work(f"called:{tool}", tool in tools, f"MCP calls: {sorted(set(tools))}")
    for tool in expect.get("forbidden_tools", []):
        check(f"not-called:{tool}", tool not in tools, f"MCP calls: {sorted(set(tools))}")
    for command in expect.get("required_helper_commands", []):
        work(f"helper:{command}", command in succeeded, ran)
    if wanted := expect.get("helper_commands_any"):
        work("helper-any", bool(set(wanted) & succeeded), ran)
    for command in expect.get("forbidden_helper_commands", []):
        check(f"no-helper:{command}", command not in commands, f"helper: {sorted(set(commands))}")
    for dataset in expect.get("forbidden_helper_datasets", []):
        check(f"not-read:{dataset}", dataset not in datasets, f"datasets: {sorted(datasets)}")
    if patterns := expect.get("required_files_any"):
        matched = [name for name in changed if any(fnmatch.fnmatch(name, p) for p in patterns)]
        work("produced-required-file", bool(matched), f"changed files: {sorted(changed)[:10]}")
    for pattern in expect.get("forbidden_files", []):
        hits = [name for name in changed if fnmatch.fnmatch(name, pattern)]
        check(f"no-file:{pattern}", not hits, f"changed: {hits[:5]}")
    if (limit := expect.get("max_mcp_calls")) is not None:
        check("mcp-call-budget", len(tools) <= limit, f"{len(tools)} calls, limit {limit}")
    if (limit := expect.get("max_helper_calls")) is not None:
        check("helper-call-budget", len(commands) <= limit, f"{len(commands)} calls, limit {limit}")
    if wanted := expect.get("skills_read_any"):
        check(
            "read-expected-skill",
            None if skills is None else bool(skills & set(wanted)),
            f"skills referenced: {sorted(skills or [])}",
        )
    if phrases := expect.get("final_message_mentions_any"):
        check(
            "final-message",
            None
            if final_message is None
            else any(phrase.lower() in final_message.lower() for phrase in phrases),
            "final message checked for: " + ", ".join(phrases),
        )
    failed = [item for item in checks if item["status"] == "failed"]
    return {
        "scenario": scenario["id"],
        "passed": not failed,
        "checks": checks,
        "counts": {
            "mcp_calls": len(tools),
            "helper_calls": len(commands),
            "changed_files": len(changed),
        },
    }


def _installed_by_helper(name: str, helper_calls: list[list[str]]) -> bool:
    """Snapshot replacement through snapshot-install is allowed; edits are not."""
    area = "metadata" if name.startswith("metadata/") else "project"
    return any(argv[:1] == ["snapshot-install"] and area in argv for argv in helper_calls)


GRADE_INSTRUCTIONS = """\
You grade one run of the Atlas agent against a reviewed reference answer.

Judge only what the run shows: its final message and the files it changed. Credit
substance that matches the reference even when the wording differs; do not credit claims
that the changed files contradict. For each criterion decide passed true or false and give
a one-sentence reason.

Reply with JSON only, no prose and no code fence:
{"criteria": [{"id": "<criterion id>", "passed": true, "reason": "<one sentence>"}]}"""
JUDGE_FILE_BUDGET = 40_000  # characters of changed-file content the judge sees
NOT_EVIDENCE = (".atlas/", "metadata/metadata-snapshot/", "project/project-snapshot/")


def grade_prompt(scenario: dict[str, Any], sandbox: Sandbox) -> str:
    """The request, reference answer and criteria, then the run's final message and output."""
    quality = scenario["quality"]
    _, final_message = _transcript(sandbox)
    evidence: list[str] = []
    budget = JUDGE_FILE_BUDGET
    # Drafts and code are the run's output; bookkeeping and installed Snapshots are not.
    for name in sorted(
        name for name in _changed_files(sandbox) if not name.startswith(NOT_EVIDENCE)
    ):
        text = (sandbox.workspace / name).read_text(encoding="utf-8", errors="replace")
        shown = text[: max(budget, 0)]
        budget -= len(text)
        evidence.append(
            f"### {name}\n{shown}" + ("\n[truncated]" if len(shown) < len(text) else "")
        )
    criteria = "\n".join(
        f"- {item['id']} ({'required' if item['required'] else 'optional'}): {item['text']}"
        for item in quality["criteria"]
    )
    sections = [
        GRADE_INSTRUCTIONS,
        f"## Request\n{scenario['request']}",
        "## Reference answer\n" + "\n".join(quality["reference"]),
        f"## Criteria\n{criteria}",
        f"## Run's final message\n{final_message or '(no final message)'}",
        "## Files the run changed\n" + ("\n\n".join(evidence) or "(none)"),
    ]
    return "\n\n".join(sections) + "\n"


def _judge_verdict(output: str) -> dict[str, dict[str, Any]]:
    """Find the judge's {"criteria": [...]} object, raw or inside a CLI JSON envelope."""
    texts = [output]
    for line in output.splitlines():
        try:
            event: Any = json.loads(line)
        except json.JSONDecodeError:
            continue
        result = cast(dict[str, Any], event).get("result") if isinstance(event, dict) else None
        if isinstance(result, str):
            texts.append(result)  # `claude -p --output-format json` or stream-json
    decoder = json.JSONDecoder()
    for text in texts:
        start = text.find("{")
        while start != -1:
            try:
                value: Any = decoder.raw_decode(text, start)[0]
            except json.JSONDecodeError:
                value = None
            found = cast(dict[str, Any], value).get("criteria") if isinstance(value, dict) else None
            if isinstance(found, list):
                entries = cast(list[Any], found)
                items = [cast(dict[str, Any], item) for item in entries if isinstance(item, dict)]
                return {item["id"]: item for item in items if isinstance(item.get("id"), str)}
            start = text.find("{", start + 1)
    return {}


def grade(
    scenario: dict[str, Any], sandbox: Sandbox, template: str, timeout_seconds: int
) -> dict[str, Any]:
    """Judge a scored run. Quality passes when every required criterion passes and at least
    `min_optional` of the others do; a criterion the judge leaves out counts as failed. A
    judge that returns no verdict at all is a grading error, not a failed run."""
    quality = scenario["quality"]
    prompt = sandbox.root / "grade_prompt.md"
    prompt.write_text(grade_prompt(scenario, sandbox), encoding="utf-8")
    completed = subprocess.run(
        template.format(prompt=shlex.quote(str(prompt))),
        shell=True,
        cwd=sandbox.root,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    verdict = _judge_verdict(completed.stdout)
    if not verdict:
        return {
            "scenario": scenario["id"],
            "quality_passed": None,
            "judge_error": f"no verdict from the judge (exit status {completed.returncode})",
        }
    criteria: list[dict[str, Any]] = [
        {
            "id": item["id"],
            "required": item["required"],
            "passed": verdict.get(item["id"], {}).get("passed") is True,
            "reason": str(verdict.get(item["id"], {}).get("reason", "not graded")),
        }
        for item in quality["criteria"]
    ]
    required_total = sum(1 for item in criteria if item["required"])
    required_passed = sum(1 for item in criteria if item["required"] and item["passed"])
    optional_passed = sum(1 for item in criteria if not item["required"] and item["passed"])
    return {
        "scenario": scenario["id"],
        "quality_passed": required_passed == required_total
        and optional_passed >= quality["min_optional"],
        "required_passed": f"{required_passed}/{required_total}",
        "optional_passed": (
            f"{optional_passed}/{len(criteria) - required_total} (need {quality['min_optional']})"
        ),
        "judge_exit_status": completed.returncode,
        "criteria": criteria,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--scenario", default="all", help="scenario id or 'all'")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--agent-command", help="shell template; see README for placeholders")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--grade-command",
        help="shell template for the quality judge; {prompt} is the grading prompt file",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="build sandboxes only")
    mode.add_argument("--score-only", action="store_true", help="score existing sandboxes")
    arguments = parser.parse_args()
    scenarios = [
        scenario for scenario in load_scenarios() if arguments.scenario in ("all", scenario["id"])
    ]
    if not scenarios:
        raise SystemExit(f"unknown scenario: {arguments.scenario}")
    if not (arguments.dry_run or arguments.score_only or arguments.agent_command):
        raise SystemExit("choose --agent-command, --dry-run or --score-only")
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        sandbox = Sandbox(arguments.out / scenario["id"])
        if not arguments.score_only:
            sandbox = build_sandbox(scenario, arguments.out)
            if arguments.dry_run:
                print(f"built {sandbox.root}")
                continue
            run_agent(sandbox, arguments.agent_command, arguments.timeout)
        report = score(scenario, sandbox)
        (sandbox.root / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        results.append(report)
        failed = [item["id"] for item in report["checks"] if item["status"] == "failed"]
        print(f"{'PASS' if report['passed'] else 'FAIL'} {scenario['id']} {failed or ''}")
        if arguments.grade_command and scenario.get("quality"):
            graded = grade(scenario, sandbox, arguments.grade_command, arguments.timeout)
            (sandbox.root / "grade.json").write_text(json.dumps(graded, indent=2), encoding="utf-8")
            if graded["quality_passed"] is None:
                print(f"QUALITY ERROR {scenario['id']} {graded['judge_error']}")
            else:
                print(
                    f"{'QUALITY PASS' if graded['quality_passed'] else 'QUALITY FAIL'}"
                    f" {scenario['id']} required {graded['required_passed']},"
                    f" optional {graded['optional_passed']}"
                )
    if results:
        passed = sum(1 for report in results if report["passed"])
        print(f"{passed}/{len(results)} scenarios passed")


if __name__ == "__main__":
    main()
