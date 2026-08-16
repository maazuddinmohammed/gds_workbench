from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
    WriteTransaction,
)
from gds_etl_workbench.tools.change_sets.metadata import (
    register_metadata_change_set_tools,
)
from gds_etl_workbench.tools.snapshots.metadata.archive import encode_dataset
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS_BY_NAME
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    SelectedMetadataSnapshot,
)

ENTRA_TENANT_ID = UUID("10000000-0000-0000-0000-000000000050")
ENTRA_OBJECT_ID = UUID("20000000-0000-0000-0000-000000000050")
CHANGE_SET_ID = UUID("30000000-0000-4000-8000-000000000050")


class StaticIdentityProvider(IdentityProvider):
    def __init__(self) -> None:
        super().__init__(AuthMode.DEV)

    def request_principal(self, request: object | None) -> RequestPrincipal:
        del request
        return RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=ENTRA_TENANT_ID,
            entra_object_id=ENTRA_OBJECT_ID,
        )


class FakeTransaction:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "mcp.create_metadata_change_set" in query:
            assert parameters[:4] == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
            )
            assert isinstance(parameters[4], UUID)
            assert isinstance(parameters[5], UUID)
            return self._database.create_row
        if "mcp.stage_metadata_change_set" in query:
            assert parameters[:6] == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                CHANGE_SET_ID,
                1,
            )
            assert isinstance(parameters[7], UUID)
            return self._database.stage_row
        if "mcp.get_metadata_change_set" in query:
            assert parameters == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                CHANGE_SET_ID,
            )
            return self._database.get_row
        if "security.authorize_tenant_operation" in query:
            assert parameters == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
            )
            return {
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
            }
        if "mcp.record_metadata_change_set_validation" in query:
            assert parameters[:7] == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                CHANGE_SET_ID,
                1,
                True,
            )
            assert isinstance(parameters[9], UUID)
            assert isinstance(parameters[10], UUID)
            return self._database.validation_row
        if "mcp.apply_metadata_change_set" in query:
            assert parameters[:6] == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                CHANGE_SET_ID,
                1,
            )
            assert isinstance(parameters[6], str)
            assert len(parameters[6]) == 64
            assert isinstance(parameters[7], UUID)
            return self._database.apply_row
        if "mcp.archive_metadata_change_set" in query:
            assert parameters[:6] == (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                "user",
                123,
                CHANGE_SET_ID,
                1,
            )
            assert isinstance(parameters[6], UUID)
            return self._database.archive_row
        if "security.entra_principal_identity" in query:
            return {
                "principal_id": 51,
                "principal_display_name": "Change Set Developer",
                "is_super_admin": False,
            }
        raise AssertionError("unexpected query")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        del query, parameters
        raise AssertionError("unexpected multi-row query")


class FakeDatabase:
    def __init__(
        self,
        create_row: dict[str, Any] | None = None,
        stage_row: dict[str, Any] | None = None,
        get_row: dict[str, Any] | None = None,
        validation_row: dict[str, Any] | None = None,
        apply_row: dict[str, Any] | None = None,
        archive_row: dict[str, Any] | None = None,
    ) -> None:
        self.create_row = create_row
        self.stage_row = stage_row
        self.get_row = get_row
        self.validation_row = validation_row
        self.apply_row = apply_row
        self.archive_row = archive_row
        self.audit_records: list[ToolCallLogRecord] = []
        self.write_transaction_count = 0

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def readiness(self) -> ReadinessRecord:
        return ReadinessRecord(ready=True, code="ready")

    async def expire_tenant_locks(self) -> int:
        return 0

    async def append_tool_call_log(self, record: ToolCallLogRecord) -> None:
        self.audit_records.append(record)

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        assert isolation is ReadIsolation.READ_COMMITTED
        yield FakeTransaction(self)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        self.write_transaction_count += 1
        yield FakeTransaction(self)


def _server(database: FakeDatabase) -> MCPServer[None]:
    identity_provider = StaticIdentityProvider()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
    )
    server = MCPServer[None](name="metadata-change-set-test", middleware=[audit])
    register_metadata_change_set_tools(
        server,
        database=database,
        identity_provider=identity_provider,
        authorizer=AuthorizationService(),
        audit=audit,
    )
    return server


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("created", "denial_code"),
    [(True, None), (False, "metadata_change_set_exists")],
)
async def test_create_metadata_change_set_returns_new_or_existing_draft(
    created: bool,
    denial_code: str | None,
) -> None:
    database = FakeDatabase(
        {
            "created": created,
            "denial_code": denial_code,
            "metadata_change_set_id": CHANGE_SET_ID,
            "metadata_change_set_status": "active",
            "draft_revision": 1,
            "created_time": datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
            "expires_time": datetime(2026, 8, 13, 19, 0, tzinfo=UTC),
        }
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "create_metadata_change_set", {"tenant_id": 123}
        )

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "metadata_change_set_id": str(CHANGE_SET_ID),
        "created": created,
        "status": "active",
        "draft_revision": 1,
        "created_at": "2026-08-13T15:00:00Z",
        "expires_at": "2026-08-13T19:00:00Z",
    }
    assert database.write_transaction_count == 1
    assert database.audit_records[0].input_metadata == {
        "schema_version": "1.0",
        "tenant_id": 123,
    }


@pytest.mark.asyncio
async def test_stage_metadata_change_set_stages_multiple_datasets_with_one_revision() -> (
    None
):
    database = FakeDatabase(
        stage_row={
            "staged": True,
            "denial_code": None,
            "draft_revision": 2,
            "dataset_counts": {"copy_group": 1, "process_group": 1},
            "expires_time": datetime(2026, 8, 13, 19, 30, tzinfo=UTC),
        }
    )
    changes = [
        {
            "dataset": "copy_group",
            "records": [
                {
                    "tenant_code": "DEMO",
                    "system_code": "CRM",
                    "copy_group_name": "CUSTOMERS",
                    "copy_group_description": None,
                    "is_member_group_required": False,
                    "is_active": True,
                }
            ],
        },
        {
            "dataset": "process_group",
            "records": [
                {
                    "tenant_code": "DEMO",
                    "system_code": "CRM",
                    "zone_code": "bronze",
                    "process_group_name": "LOAD_CUSTOMERS",
                    "process_group_description": None,
                    "copy_group_name": "CUSTOMERS",
                    "is_active": True,
                }
            ],
        },
    ]

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "stage_metadata_change_set",
            {
                "tenant_id": 123,
                "metadata_change_set_id": str(CHANGE_SET_ID),
                "expected_draft_revision": 1,
                "changes": changes,
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["draft_revision"] == 2
    assert [item["dataset"] for item in result.structured_content["datasets"]] == [
        "copy_group",
        "process_group",
    ]
    assert [item["record_count"] for item in result.structured_content["datasets"]] == [
        1,
        1,
    ]
    assert database.write_transaction_count == 1
    assert database.audit_records[0].input_metadata == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "metadata_change_set_id": str(CHANGE_SET_ID),
        "expected_draft_revision": 1,
        "dataset_count": 2,
        "record_count": 2,
    }
    assert "changes" not in database.audit_records[0].input_metadata
    assert "CUSTOMERS" not in str(database.audit_records[0].input_metadata)


@pytest.mark.asyncio
async def test_stage_metadata_change_set_reports_safe_dynamic_schema_error() -> None:
    database = FakeDatabase()

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "stage_metadata_change_set",
            {
                "tenant_id": 123,
                "metadata_change_set_id": str(CHANGE_SET_ID),
                "expected_draft_revision": 1,
                "changes": [
                    {
                        "dataset": "copy_group",
                        "records": [
                            {
                                "tenant_code": "DEMO",
                                "system_code": "CRM",
                                "copy_group_name": "CUSTOMERS",
                                "copy_group_description": "must-not-appear",
                                "is_member_group_required": False,
                            }
                        ],
                    }
                ],
            },
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.endswith(
        "invalid_request: copy_group record 1 field is_active "
        "does not match its published schema."
    )
    assert "must-not-appear" not in result.content[0].text
    assert database.write_transaction_count == 0


@pytest.mark.asyncio
async def test_stage_metadata_change_set_input_schema_stays_compact() -> None:
    async with Client(_server(FakeDatabase())) as client:
        tools = await client.list_tools()

    stage = next(
        tool for tool in tools.tools if tool.name == "stage_metadata_change_set"
    )
    definitions = stage.input_schema["$defs"]
    stage_change = definitions["StageChange"]
    assert stage_change["properties"]["records"]["items"] == {
        "additionalProperties": True,
        "type": "object",
    }
    assert all(
        field not in str(stage.input_schema)
        for field in ("copy_group_name", "process_executable", "attribute_data_type")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("dataset", [None, "copy_group"])
async def test_get_metadata_change_set_returns_counts_or_one_dataset(
    dataset: str | None,
) -> None:
    documents: dict[str, list[dict[str, object]]] = {
        f"{name}_document": []
        for name in (
            "source_object",
            "source_attribute",
            "bronze_object",
            "bronze_attribute",
            "silver_object",
            "silver_attribute",
            "gold_object",
            "gold_attribute",
            "ingestion_object_mapping",
            "ingestion_attribute_mapping",
            "copy_group",
            "member_group",
            "copy_group_control",
            "copy",
            "process_group",
            "process",
        )
    }
    documents["copy_group_document"] = [
        {
            "tenant_code": "DEMO",
            "system_code": "CRM",
            "copy_group_name": "CUSTOMERS",
            "copy_group_description": None,
            "is_member_group_required": False,
            "is_active": True,
        }
    ]
    database = FakeDatabase(
        get_row={
            "found": True,
            "denial_code": None,
            "metadata_change_set_status": "active",
            "draft_revision": 2,
            "candidate_digest": None,
            "validation_outcome": None,
            **documents,
            "created_time": datetime(2026, 8, 13, 15, 0, tzinfo=UTC),
            "last_activity_time": datetime(2026, 8, 13, 15, 30, tzinfo=UTC),
            "expires_time": datetime(2026, 8, 13, 19, 30, tzinfo=UTC),
            "validated_time": None,
            "applied_time": None,
            "terminal_time": None,
        }
    )
    arguments: dict[str, object] = {
        "tenant_id": 123,
        "metadata_change_set_id": str(CHANGE_SET_ID),
    }
    if dataset is not None:
        arguments["dataset"] = dataset

    async with Client(_server(database)) as client:
        result = await client.call_tool("get_metadata_change_set", arguments)

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["dataset"] == dataset
    assert result.structured_content["records"] == (
        documents["copy_group_document"] if dataset == "copy_group" else None
    )
    counts = {
        item["dataset"]: item["record_count"]
        for item in result.structured_content["dataset_counts"]
    }
    assert counts["copy_group"] == 1
    assert len(counts) == 16
    assert database.audit_records[0].input_metadata["dataset"] == (dataset or "summary")
    assert database.write_transaction_count == 1


@pytest.mark.asyncio
async def test_validate_metadata_change_set_persists_bounded_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 13, 16, 0, tzinfo=UTC)
    documents: dict[str, list[dict[str, object]]] = {
        f"{name}_document": []
        for name in (
            "source_object",
            "source_attribute",
            "bronze_object",
            "bronze_attribute",
            "silver_object",
            "silver_attribute",
            "gold_object",
            "gold_attribute",
            "ingestion_object_mapping",
            "ingestion_attribute_mapping",
            "copy_group",
            "member_group",
            "copy_group_control",
            "copy",
            "process_group",
            "process",
        )
    }
    documents["copy_group_document"] = [
        {
            "tenant_code": "DEMO",
            "system_code": "CRM",
            "copy_group_name": "CUSTOMERS",
            "copy_group_description": None,
            "is_member_group_required": False,
            "is_active": True,
        }
    ]
    database = FakeDatabase(
        get_row={
            "found": True,
            "denial_code": None,
            "metadata_change_set_status": "active",
            "draft_revision": 1,
            "candidate_digest": None,
            "validation_outcome": None,
            **documents,
            "created_time": now,
            "last_activity_time": now,
            "expires_time": now,
            "validated_time": None,
            "applied_time": None,
            "terminal_time": None,
        },
        validation_row={
            "recorded": True,
            "denial_code": None,
            "metadata_change_set_status": "validated",
            "draft_revision": 1,
            "candidate_digest": "a" * 64,
            "validated_time": now,
            "expires_time": now,
        },
    )

    foundation = {
        "project": [
            {
                "project_code": "PROJECT",
                "project_name": "Project",
                "project_description": None,
                "is_active": True,
            }
        ],
        "tenant": [
            {
                "tenant_code": "DEMO",
                "project_code": "PROJECT",
                "tenant_name": "Demo",
                "tenant_description": None,
                "tenant_catalog": "demo",
                "gds_admin_catalog": "admin",
                "gds_connection_tenant_code": None,
                "gds_connection_system_code": None,
                "gds_connection_code": None,
                "tenant_visibility": "private",
                "is_active": True,
            }
        ],
        "system_type": [
            {
                "system_type_code": "DATABASE",
                "system_type_name": "Database",
                "system_type_description": None,
                "is_active": True,
            }
        ],
        "system": [
            {
                "system_code": "CRM",
                "system_name": "CRM",
                "system_description": None,
                "system_type_code": "DATABASE",
                "is_active": True,
            }
        ],
    }

    async def select_snapshot(
        *_args: object, **_kwargs: object
    ) -> SelectedMetadataSnapshot:
        return SelectedMetadataSnapshot(
            tenant_code="DEMO",
            datasets=tuple(
                encode_dataset(DATASETS_BY_NAME[name], rows)
                for name, rows in foundation.items()
            ),
        )

    monkeypatch.setattr(
        "gds_etl_workbench.tools.change_sets.metadata.select_snapshot_datasets",
        select_snapshot,
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "validate_metadata_change_set",
            {
                "tenant_id": 123,
                "metadata_change_set_id": str(CHANGE_SET_ID),
                "expected_draft_revision": 1,
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["valid"] is True
    assert result.structured_content["phase"] == "complete"
    assert result.structured_content["status"] == "validated"
    assert result.structured_content["errors"] == []
    assert result.structured_content["action_review"] == [
        {
            "dataset": "copy_group",
            "insert_count": 1,
            "update_count": 0,
            "deactivate_count": 0,
            "reactivate_count": 0,
            "no_change_count": 0,
            "keys": [
                {
                    "action": "insert",
                    "natural_key": {
                        "tenant_code": "DEMO",
                        "system_code": "CRM",
                        "copy_group_name": "CUSTOMERS",
                    },
                }
            ],
            "keys_truncated": False,
        }
    ]
    assert database.write_transaction_count == 1


@pytest.mark.asyncio
async def test_apply_metadata_change_set_revalidates_then_applies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 13, 16, 30, tzinfo=UTC)
    documents: dict[str, list[dict[str, object]]] = {
        f"{name}_document": []
        for name in (
            "source_object",
            "source_attribute",
            "bronze_object",
            "bronze_attribute",
            "silver_object",
            "silver_attribute",
            "gold_object",
            "gold_attribute",
            "ingestion_object_mapping",
            "ingestion_attribute_mapping",
            "copy_group",
            "member_group",
            "copy_group_control",
            "copy",
            "process_group",
            "process",
        )
    }
    database = FakeDatabase(
        get_row={
            "found": True,
            "denial_code": None,
            "metadata_change_set_status": "active",
            "draft_revision": 1,
            **documents,
        },
        validation_row={
            "recorded": True,
            "denial_code": None,
            "metadata_change_set_status": "validated",
            "draft_revision": 1,
            "candidate_digest": "a" * 64,
            "validated_time": now,
            "expires_time": now,
        },
        apply_row={
            "applied": True,
            "denial_code": None,
            "metadata_change_set_status": "applied",
            "draft_revision": 1,
            "applied_time": now,
            "action_count": 0,
        },
    )

    async def select_empty_snapshot(
        *_args: object, **_kwargs: object
    ) -> SelectedMetadataSnapshot:
        return SelectedMetadataSnapshot(tenant_code="DEMO", datasets=())

    monkeypatch.setattr(
        "gds_etl_workbench.tools.change_sets.metadata.select_snapshot_datasets",
        select_empty_snapshot,
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "apply_metadata_change_set",
            {
                "tenant_id": 123,
                "metadata_change_set_id": str(CHANGE_SET_ID),
                "expected_draft_revision": 1,
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["valid"] is True
    assert result.structured_content["applied"] is True
    assert result.structured_content["status"] == "applied"
    assert result.structured_content["action_count"] == 0
    assert database.write_transaction_count == 1


@pytest.mark.asyncio
async def test_apply_metadata_change_set_returns_safe_locked_object_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 13, 16, 30, tzinfo=UTC)
    documents: dict[str, list[dict[str, object]]] = {
        f"{name}_document": []
        for name in (
            "source_object",
            "source_attribute",
            "bronze_object",
            "bronze_attribute",
            "silver_object",
            "silver_attribute",
            "gold_object",
            "gold_attribute",
            "ingestion_object_mapping",
            "ingestion_attribute_mapping",
            "copy_group",
            "member_group",
            "copy_group_control",
            "copy",
            "process_group",
            "process",
        )
    }
    database = FakeDatabase(
        get_row={
            "found": True,
            "denial_code": None,
            "metadata_change_set_status": "active",
            "draft_revision": 1,
            **documents,
        },
        validation_row={
            "recorded": True,
            "denial_code": None,
            "metadata_change_set_status": "validated",
            "draft_revision": 1,
            "candidate_digest": "a" * 64,
            "validated_time": now,
            "expires_time": now,
        },
        apply_row={
            "applied": False,
            "denial_code": "object_locked",
            "metadata_change_set_status": "validated",
            "draft_revision": 1,
            "applied_time": None,
            "action_count": 0,
        },
    )

    async def select_empty_snapshot(
        *_args: object, **_kwargs: object
    ) -> SelectedMetadataSnapshot:
        return SelectedMetadataSnapshot(tenant_code="DEMO", datasets=())

    monkeypatch.setattr(
        "gds_etl_workbench.tools.change_sets.metadata.select_snapshot_datasets",
        select_empty_snapshot,
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "apply_metadata_change_set",
            {
                "tenant_id": 123,
                "metadata_change_set_id": str(CHANGE_SET_ID),
                "expected_draft_revision": 1,
            },
        )

    assert result.is_error is True
    assert isinstance(result.content[0], TextContent)
    assert result.content[0].text.endswith(
        "object_locked: Object is locked; neither it nor its Attributes can be changed."
    )


@pytest.mark.asyncio
async def test_archive_metadata_change_set_returns_retained_terminal_state() -> None:
    archived_at = datetime(2026, 8, 13, 17, 0, tzinfo=UTC)
    database = FakeDatabase(
        archive_row={
            "archived": True,
            "denial_code": None,
            "metadata_change_set_status": "archived",
            "draft_revision": 1,
            "terminal_time": archived_at,
        }
    )

    async with Client(_server(database)) as client:
        result = await client.call_tool(
            "archive_metadata_change_set",
            {
                "tenant_id": 123,
                "metadata_change_set_id": str(CHANGE_SET_ID),
                "expected_draft_revision": 1,
            },
        )

    assert result.is_error is False
    assert result.structured_content == {
        "schema_version": "1.0",
        "tenant_id": 123,
        "metadata_change_set_id": str(CHANGE_SET_ID),
        "archived": True,
        "status": "archived",
        "draft_revision": 1,
        "archived_at": "2026-08-13T17:00:00Z",
    }


@pytest.mark.asyncio
async def test_metadata_change_set_prompt_teaches_context_bounded_workflow() -> None:
    async with Client(_server(FakeDatabase())) as client:
        prompts = await client.list_prompts()
        result = await client.get_prompt(
            "work_with_metadata_change_set",
            {"tenant_id": "123"},
        )

    assert [prompt.name for prompt in prompts.prompts] == [
        "work_with_metadata_change_set"
    ]
    content = result.messages[0].content
    assert content.type == "text"
    assert "Never load the whole ZIP into chat" in content.text
    assert "describe_metadata_dataset only for datasets you will edit" in content.text
    assert "stage_metadata_change_set" in content.text
    assert "atomically with one new revision" in content.text
    assert "authoritative action_review" in content.text
    assert content.text.index("get_metadata_snapshot") < content.text.index(
        "check_tenant_lock"
    )
    assert "every dataset with a nonzero count" in content.text
