"""Profiling lives in the web feature with explicit HTTP and storage seams."""

import ast
from importlib.resources import files
from pathlib import Path

from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.infrastructure.databricks_sql import (
    DatabricksSqlConnection as AdapterDatabricksSqlConnection,
)
from gds_workbench_api.features.profiling.execution import load_default_profiling_policy
from gds_workbench_api.features.profiling.repository import (
    DatabaseProfilingWorkflowRepository,
)
from gds_workbench_api.features.profiling.router import (
    ExecuteProfilingRunRequest,
    create_profiling_workflow_router,
)
from gds_workbench_api.features.profiling.workflow import ProfilingWorkflowOrchestrator

_ROOT = Path(__file__).resolve().parents[2]


def test_profiling_workflow_does_not_depend_on_http_or_storage_adapters() -> None:
    feature = _ROOT / "web_app/backend/gds_workbench_api/features/profiling"
    for name in ("execution.py", "workflow.py"):
        imports = {
            node.module or ""
            for node in ast.walk(ast.parse((feature / name).read_text()))
            if isinstance(node, ast.ImportFrom)
        }
        assert not any(
            module.startswith(("fastapi", "mcp", "gds_workbench_runtime"))
            or module.endswith((".repository", ".router"))
            for module in imports
        )
    assert ProfilingWorkflowOrchestrator.__module__.endswith("profiling.workflow")


def test_profiling_policy_is_packaged_with_the_web_application() -> None:
    assert files("gds_workbench_api").joinpath("config", "profiling.json").is_file()
    assert load_default_profiling_policy().attributes_per_query > 0


def test_existing_connection_import_is_compatible() -> None:
    assert AdapterDatabricksSqlConnection is DatabricksSqlConnection


def test_profiling_http_and_storage_have_explicit_owners() -> None:
    assert DatabaseProfilingWorkflowRepository.__module__.endswith("profiling.repository")
    assert ExecuteProfilingRunRequest.__module__.endswith("profiling.router")
    assert create_profiling_workflow_router.__module__.endswith("profiling.router")
