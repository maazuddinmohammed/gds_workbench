"""Published Code schemas remain usable by the local plugin validator."""

import json
import subprocess
from pathlib import Path

from gds_etl_workbench.domain.snapshots.model import (
    DATASETS_BY_NAME,
    build_model_dataset_schema,
)

from tests.mcp.model_test_fixtures import complete_model_graph


def test_plugin_accepts_git_metadata_with_the_published_schema(tmp_path: Path) -> None:
    record = {
        **complete_model_graph()["generated_code"][0],
        "code_storage_type": "git",
        "generated_code_content": None,
        "code_repository_url": "any repository",
        "code_commit_path": "anything \\ branch/ref\nreference",
        "code_entry_point": "",
    }
    parameters = [None, {}, {"nested": [False, {"batch": 42}]}, ["--full"], "", 0, True]
    records = [{**record, "code_parameters": value} for value in parameters]
    records.append({**record, "code_storage_type": "table"})
    source = tmp_path / "code-cases.json"
    source.write_text(
        json.dumps(
            {
                "schema": build_model_dataset_schema(
                    DATASETS_BY_NAME["generated_code"]
                ),
                "records": records,
            }
        )
    )
    validator = Path(__file__).resolve().parents[2] / (
        "atlas/atlas-plugin/workbench/validation/common.js"
    )
    result = subprocess.run(
        [
            "node",
            "-e",
            "const fs=require('node:fs'); const api=require(process.argv[1]); "
            "const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8')); "
            "process.stdout.write(JSON.stringify(data.records.map(record=>"
            "api.validateSchema(record,data.schema).length)));",
            str(validator),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, "Plugin schema validation failed; output withheld"
    failures = json.loads(result.stdout)
    assert failures[:-1] == [0] * len(parameters)
    assert failures[-1] > 0
