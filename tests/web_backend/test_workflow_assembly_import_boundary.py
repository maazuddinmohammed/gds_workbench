from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_workflow_assembly_imports_without_mcp_sdk() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(_ROOT / "web_app" / "backend"),
            str(_ROOT / "mcp_server"),
        )
    )
    script = """
import builtins
import sys

real_import = builtins.__import__

def reject_mcp(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "mcp" or name.startswith("mcp."):
        raise AssertionError(f"workflow assembly imported MCP SDK: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = reject_mcp

from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_workbench_api.features.workflows.execution.assembly import (
    WorkflowRuntimeServices,
    create_workflow_runtime_services,
)

assert StageModelChange.__module__ == "gds_etl_workbench.tools.change_sets.model"
assert WorkflowRuntimeServices.__module__.endswith("workflows.execution.assembly")
assert callable(create_workflow_runtime_services)
assert not any(name == "mcp" or name.startswith("mcp.") for name in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
