from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_WEB_PACKAGE = _ROOT / "web_app" / "backend" / "gds_workbench_api"
_SHARED_PACKAGE = _ROOT / "mcp_server" / "gds_etl_workbench"


def test_web_and_shared_rules_do_not_import_mcp_tool_or_identity_adapters() -> None:
    forbidden = (
        "gds_etl_workbench.adapters.auth",
        "gds_etl_workbench.adapters.mcp",
        "gds_etl_workbench.tools",
    )
    violations: list[str] = []
    packages = [
        _WEB_PACKAGE,
        *(_SHARED_PACKAGE / name for name in ("application", "domain", "infrastructure")),
    ]
    for path in sorted(path for package in packages for path in package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        ]
        imported.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        for module in imported:
            if any(module == root or module.startswith(f"{root}.") for root in forbidden):
                violations.append(f"{path.relative_to(_ROOT)}: {module}")

    assert violations == []


def test_workflows_and_change_sets_import_without_mcp_transport() -> None:
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

forbidden = (
    "mcp",
    "gds_etl_workbench.adapters.auth",
    "gds_etl_workbench.adapters.mcp",
    "gds_etl_workbench.tools",
)

def reject_mcp(name, globals=None, locals=None, fromlist=(), level=0):
    if any(name == root or name.startswith(root + ".") for root in forbidden):
        raise AssertionError(f"shared application imported MCP transport: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = reject_mcp

from gds_etl_workbench.application.change_sets.metadata import CHANGE_SET_DATASETS
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_workbench_api.features.metadata_change_sets.service import (
    DatabaseMetadataChangeSetService,
)
from gds_workbench_api.features.model_change_sets.service import DatabaseModelChangeSetService
from gds_workbench_api.features.workflows.execution.assembly import (
    WorkflowRuntimeServices,
    create_workflow_runtime_services,
)

assert StageModelChange.__module__ == "gds_etl_workbench.application.change_sets.model"
assert "source_object" in CHANGE_SET_DATASETS
assert WorkflowRuntimeServices.__module__.endswith("workflows.execution.assembly")
assert callable(create_workflow_runtime_services)
assert DatabaseMetadataChangeSetService and DatabaseModelChangeSetService
assert not any(
    name == root or name.startswith(root + ".")
    for name in sys.modules for root in forbidden
)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
