"""Server contract fixture consumed by the VS Code Stage Runner tests.

`atlas/atlas-vs-code/test/fixtures/server-contract.json` is built here from the MCP
server's own models, dataset registries and the MCP SDK's real error formatting. The
extension tests read that file instead of hand-written server copies, so a server
change the extension does not follow fails one of the two suites.

After an intentional contract change, regenerate from the repository root:

    PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python \
        tests/atlas/test_stage_contract.py --write
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from gds_etl_workbench.adapters.mcp.stage_runner_gate import (
    STAGE_RUNNER_CLIENT,
    STAGE_RUNNER_HEADER,
    STAGE_UPLOAD_TOOLS,
    StageRunnerGate,
)
from gds_etl_workbench.application.change_sets.contracts import (
    STAGE_FINGERPRINT_VERSION,
    canonical_records_sha256,
    stage_fingerprint_sha256,
)
from gds_etl_workbench.application.change_sets.metadata import (
    CHANGE_SET_DATASETS as METADATA_DATASETS,
)
from gds_etl_workbench.application.change_sets.metadata import (
    GetMetadataChangeSetFingerprintResult,
    MetadataChangeSetDatasetFingerprint,
)
from gds_etl_workbench.application.change_sets.project import (
    GetProjectChangeSetFingerprintResult,
    ProjectChangeSetDatasetFingerprint,
)
from gds_etl_workbench.domain.errors import DraftRevisionConflictError, TenantLockRequiredError
from gds_etl_workbench.domain.snapshots.project import CHANGE_SET_DATASETS_BY_NAME
from gds_etl_workbench.tools.change_sets.metadata import MetadataChangeSetToolError
from gds_etl_workbench.tools.change_sets.project import ProjectChangeSetToolError
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "atlas/atlas-vs-code/test/fixtures/server-contract.json"
EXPIRES_AT = datetime(2099, 1, 1, tzinfo=UTC)
METADATA_CHANGE_SET_ID = UUID("30000000-0000-4000-8000-000000000050")
PROJECT_CHANGE_SET_ID = UUID("20000000-0000-4000-8000-000000000001")
# Synthetic records only; their content matters only for the hashes below.
METADATA_PENDING: dict[str, list[dict[str, object]]] = {
    "member": [
        {
            "tenant_code": "DEMO",
            "system_code": "CRM",
            "member_group_name": "REGIONS",
            "member_code": "EAST",
            "member_attribute_name": "region_code",
            "value": None,
            "is_active": True,
        }
    ]
}
PROJECT_PENDING: dict[str, list[dict[str, object]]] = {
    "logical_entity": [{"logical_entity_schema_name": "silver", "logical_entity_name": "Customer"}]
}


def _metadata_fingerprint() -> dict[str, Any]:
    datasets = [
        MetadataChangeSetDatasetFingerprint(
            dataset=name,
            record_count=len(records),
            sha256=canonical_records_sha256(records),
        )
        for name in METADATA_DATASETS
        for records in [METADATA_PENDING.get(name, [])]
    ]
    result = GetMetadataChangeSetFingerprintResult(
        tenant_id=17,
        metadata_change_set_id=METADATA_CHANGE_SET_ID,
        status="active",
        draft_revision=3,
        dataset_count=len(datasets),
        record_count=sum(item.record_count for item in datasets),
        datasets=datasets,
        fingerprint=stage_fingerprint_sha256(
            "metadata", [item.model_dump(mode="json") for item in datasets]
        ),
        expires_at=EXPIRES_AT,
    )
    return result.model_dump(mode="json")


def _project_fingerprint() -> dict[str, Any]:
    datasets = tuple(
        ProjectChangeSetDatasetFingerprint(
            dataset=name,  # pyright: ignore[reportArgumentType]
            record_count=len(records),
            sha256=canonical_records_sha256(records),
        )
        for name in sorted(CHANGE_SET_DATASETS_BY_NAME)
        for records in [PROJECT_PENDING.get(name, [])]
    )
    result = GetProjectChangeSetFingerprintResult(
        project_id=42,
        project_change_set_id=PROJECT_CHANGE_SET_ID,
        status="active",
        draft_revision=5,
        dataset_count=len(datasets),
        record_count=sum(item.record_count for item in datasets),
        datasets=datasets,
        fingerprint=stage_fingerprint_sha256(
            "project", [item.model_dump(mode="json") for item in datasets]
        ),
        expires_at=EXPIRES_AT,
    )
    return result.model_dump(mode="json")


async def _tool_error_examples() -> list[dict[str, str]]:
    """Capture the exact text the MCP SDK and Stage gate return when a tool fails."""
    server = MCPServer[None](name="stage-contract")
    failures: dict[str, Exception] = {
        "stage_project_change_set": ProjectChangeSetToolError(
            f"{DraftRevisionConflictError(4).code}: {DraftRevisionConflictError(4).message}"
        ),
        "begin_metadata_stage_batch": MetadataChangeSetToolError(
            f"{TenantLockRequiredError().code}: {TenantLockRequiredError().message}"
        ),
    }

    def register(name: str, failure: Exception) -> None:
        async def failing_tool() -> dict[str, object]:
            raise failure

        server.tool(name=name)(failing_tool)

    for name, failure in failures.items():
        register(name, failure)
    # An in-memory session outside development identity is an agent connection.
    gated = MCPServer[None](
        name="stage-contract-gate", middleware=[StageRunnerGate(allow_in_memory=False)]
    )
    calls = [(server, name, str(failure).split(":", 1)[0]) for name, failure in failures.items()]
    calls.append((gated, "put_project_stage_chunk", "stage_runner_required"))
    examples: list[dict[str, str]] = []
    for target, name, code in calls:
        async with Client(target) as client:
            result = await client.call_tool(name, {})
        assert result.is_error is True
        content = result.content[0]
        assert isinstance(content, TextContent)
        examples.append({"tool": name, "code": code, "text": content.text})
    return examples


def build_contract() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_by": "tests/atlas/test_stage_contract.py",
        "fingerprint_version": STAGE_FINGERPRINT_VERSION,
        "metadata": {
            "result_schema_version": GetMetadataChangeSetFingerprintResult.model_fields[
                "schema_version"
            ].default,
            "fingerprint_order": "declared",
            "datasets": list(METADATA_DATASETS),
            "fingerprint_example": _metadata_fingerprint(),
        },
        "project": {
            "result_schema_version": GetProjectChangeSetFingerprintResult.model_fields[
                "schema_version"
            ].default,
            "fingerprint_order": "sorted",
            "datasets": sorted(CHANGE_SET_DATASETS_BY_NAME),
            "fingerprint_example": _project_fingerprint(),
        },
        "stage_runner": {
            "header": STAGE_RUNNER_HEADER,
            "client": STAGE_RUNNER_CLIENT,
            "upload_tools": sorted(STAGE_UPLOAD_TOOLS),
        },
        "tool_error_examples": asyncio.run(_tool_error_examples()),
    }


def _encoded(contract: dict[str, Any]) -> str:
    return json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def test_stage_runner_contract_fixture_matches_the_server() -> None:
    expected = _encoded(build_contract())
    actual = FIXTURE.read_text(encoding="utf-8") if FIXTURE.is_file() else ""
    assert actual == expected, (
        "Stage Runner contract fixture is stale; regenerate it with "
        "`tests/atlas/test_stage_contract.py --write` and update the extension to match."
    )


def test_fingerprint_results_version_the_hashed_document() -> None:
    for model in (GetMetadataChangeSetFingerprintResult, GetProjectChangeSetFingerprintResult):
        assert model.model_fields["fingerprint_version"].default == STAGE_FINGERPRINT_VERSION


def test_tool_errors_keep_the_code_after_the_sdk_prefix() -> None:
    for example in asyncio.run(_tool_error_examples()):
        prefix = f"Error executing tool {example['tool']}: "
        assert example["text"].startswith(prefix + example["code"] + ": ")


if __name__ == "__main__":
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: test_stage_contract.py --write")
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(_encoded(build_contract()), encoding="utf-8")
    print(FIXTURE.relative_to(ROOT))
