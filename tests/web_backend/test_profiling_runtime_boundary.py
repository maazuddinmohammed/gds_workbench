from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.tools.databricks.executor import (
    DatabricksSqlConnection as LegacyDatabricksSqlConnection,
)
from gds_workbench_api.features.profiling.execution import (
    ProfileObject as LegacyProfileObject,
)
from gds_workbench_api.features.profiling.workflow import (
    DatabaseProfilingWorkflowRepository,
    ExecuteProfilingRunRequest,
    create_profiling_workflow_router,
)
from gds_workbench_api.features.profiling.workflow import (
    ProfilingWorkflowOrchestrator as LegacyProfilingWorkflowOrchestrator,
)
from gds_workbench_runtime.profiling.execution import ProfileObject
from gds_workbench_runtime.profiling.workflow import ProfilingWorkflowOrchestrator

_ROOT = Path(__file__).resolve().parents[2]


def test_shared_profiling_runtime_imports_without_web_or_mcp_transports() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(_ROOT / "web_app" / "backend"),
            str(_ROOT / "mcp_server"),
        )
    )
    script = """
import sys
from gds_workbench_runtime.profiling.execution import ProfileObject
from gds_workbench_runtime.profiling.workflow import ProfilingWorkflowOrchestrator

assert ProfileObject.__module__ == "gds_workbench_runtime.profiling.execution"
assert ProfilingWorkflowOrchestrator.__module__ == (
    "gds_workbench_runtime.profiling.workflow"
)
for forbidden in ("fastapi", "mcp", "sqlglot"):
    assert forbidden not in sys.modules, forbidden
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr


def test_existing_profiling_and_connection_imports_are_compatible() -> None:
    assert LegacyProfileObject is ProfileObject
    assert LegacyProfilingWorkflowOrchestrator is ProfilingWorkflowOrchestrator
    assert LegacyDatabricksSqlConnection is DatabricksSqlConnection


def test_web_repository_request_and_router_remain_web_owned() -> None:
    assert DatabaseProfilingWorkflowRepository.__module__.startswith("gds_workbench_api.")
    assert ExecuteProfilingRunRequest.__module__.startswith("gds_workbench_api.")
    assert create_profiling_workflow_router.__module__.startswith("gds_workbench_api.")
