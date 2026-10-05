"""Profiling SQL/results are no longer authored through local CLI commands."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "atlas/atlas-plugin"


def test_profiling_uses_backend_runs_only() -> None:
    commands = json.loads((ROOT / "contracts/local-helper.json").read_text())[
        "commands"
    ]
    assert "profile-plan" not in commands
    assert "profile-results" not in commands
    assert "analysis-plan" in commands
    guide = (ROOT / "references/logical-build/profiling.md").read_text()
    for tool in (
        "start_profiling_run",
        "get_profiling_run_status",
        "cancel_profiling_run",
    ):
        assert tool in guide
    assert "agent-written SQL fallback" not in guide
