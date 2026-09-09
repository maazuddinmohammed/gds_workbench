"""Local deterministic SQL preserves the established server measurement contract."""

import json
import subprocess
from pathlib import Path

from gds_workbench_runtime.profiling.execution import (
    ProfileObject,
    build_profile_queries,
)


def test_local_profile_aggregates_match_server_generator() -> None:
    target = ProfileObject.model_validate(
        {
            "object_id": 1,
            "connection_id": 2,
            "catalog": "demo",
            "schema": "bronze",
            "table": "odd`table",
            "attributes": tuple(
                {"attribute_id": i + 1, "name": f"column`{i}", "data_type": kind}
                for i, kind in enumerate(("STRING", "BIGINT", "DECIMAL(18,2)", "ARRAY<STRING>"))
            ),
        }
    )
    module = Path(__file__).resolve().parents[2] / "plugins/v2/gds/skills/gds/scripts/profiling.js"
    result = subprocess.run(
        [
            "node",
            "-e",
            'const fs=require("node:fs"); const {buildQuery}=require(process.argv[1]);'
            'const a=JSON.parse(fs.readFileSync(0,"utf8"));'
            'process.stdout.write(buildQuery("`demo`.`bronze`.`odd``table`",a,null));',
            str(module),
        ],
        input=json.dumps(
            [
                {"index": a.attribute_id, "name": a.name, "data_type": a.data_type}
                for a in target.attributes
            ]
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    expected = build_profile_queries(target, requested_batch_id=None)[0].sql
    assert result.stdout == expected.replace(" AS attribute_id", " AS attribute_index")
