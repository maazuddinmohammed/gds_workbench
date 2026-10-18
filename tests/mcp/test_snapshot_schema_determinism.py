from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = """
import json
from gds_etl_workbench.domain.snapshots.project import DATASETS, build_project_dataset_schema
print(json.dumps([build_project_dataset_schema(definition) for definition in DATASETS]))
"""


def test_project_dataset_schemas_do_not_depend_on_hash_randomization() -> None:
    """Snapshot archives must encode identically across server processes."""
    outputs = {
        subprocess.run(
            [sys.executable, "-c", SCRIPT],
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT / "mcp_server")},
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2", "3", "4")
    }
    assert len(outputs) == 1
