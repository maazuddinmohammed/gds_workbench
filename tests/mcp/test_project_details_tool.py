from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, LiteralString

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    ToolCallLogRecord,
)
from gds_etl_workbench.tools.modeling.project_details import (
    ListProjectsResult,
    register_list_projects_tool,
)


@dataclass
class FakeDatabase:
    projects: list[dict[str, Any]]
    audit_records: list[ToolCallLogRecord] = field(
        default_factory=lambda: list[ToolCallLogRecord]()
    )
    calls: list[tuple[Any, ...]] = field(
        default_factory=lambda: list[tuple[Any, ...]]()
    )
    isolations: list[ReadIsolation] = field(
        default_factory=lambda: list[ReadIsolation]()
    )

    async def open(self) -> None: ...

    async def close(self) -> None: ...

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
        self.isolations.append(isolation)
        yield FakeReadTransaction(self)


@dataclass
class FakeReadTransaction:
    database: FakeDatabase

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        raise AssertionError("development mode must not query Principal authorization")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "FROM project.project AS project" in query
        self.database.calls.append(parameters)
        limit, offset = parameters[-2:]
        return self.database.projects[offset : offset + limit]


def _server(database: FakeDatabase) -> MCPServer[None]:
    identity = IdentityProvider(AuthMode.DEV)
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
    )
    server = MCPServer[None](name="project-details-test", middleware=[audit])
    register_list_projects_tool(
        server,
        database=database,
        identity_provider=identity,
        authorizer=authorizer,
        audit=audit,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    return server


def _project(project_id: int = 7) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "project_name": "Northwind",
        "project_description": "Northwind analytics project",
        "project_revision": 4,
        "silver_model_naming_instructions": "Prefix Silver objects with slv_.",
        "silver_model_audit_columns_template": {"columns": ["loaded_at"]},
        "gold_model_naming_instructions": "Prefix Gold objects with gld_.",
        "gold_model_technical_columns_template": {"columns": ["row_hash"]},
        "gold_model_audit_columns_template": {"columns": ["loaded_at"]},
        "project_input_scope_object_count": 12,
        "total_project_count": 1,
    }


@pytest.mark.asyncio
async def test_list_projects_returns_headers_and_policy_without_audit_columns() -> None:
    database = FakeDatabase(projects=[_project()])

    async with Client(_server(database)) as client:
        call = await client.call_tool("list_projects", {"tenant_id": 3})

    result = ListProjectsResult.model_validate(call.structured_content)
    assert result.tenant_id == 3
    assert result.project_count == 1
    assert result.projects[0].project_name == "Northwind"
    assert (
        result.projects[0].silver_model_naming_instructions
        == "Prefix Silver objects with slv_."
    )
    assert "silver_model_naming_template" not in result.projects[0].model_dump()
    assert result.projects[0].silver_model_audit_columns_template == {
        "columns": ["loaded_at"]
    }
    assert result.projects[0].project_input_scope_object_count == 12
    rendered = repr(call.structured_content)
    for forbidden in ("created_time", "created_by", "updated_time", "updated_by"):
        assert forbidden not in rendered
    assert database.calls == [(3, 201, 0)]
    assert database.audit_records[0].input_metadata == {
        "tenant_id": 3,
        "schema_version": "1.0",
        "page_size": 200,
        "cursor_provided": False,
    }


@pytest.mark.asyncio
async def test_list_projects_reports_bounded_truncation() -> None:
    projects = [_project(project_id) for project_id in range(1, 202)]
    for row in projects:
        row["total_project_count"] = 201
    database = FakeDatabase(projects=projects)

    async with Client(_server(database)) as client:
        call = await client.call_tool("list_projects", {"tenant_id": 3})

    result = ListProjectsResult.model_validate(call.structured_content)
    assert len(result.projects) == 200
    assert result.project_count == 201
    assert result.projects_truncated is True


@pytest.mark.asyncio
async def test_list_projects_recovers_every_project_across_pages() -> None:
    projects = [_project(project_id) for project_id in range(1, 4)]
    for row in projects:
        row["total_project_count"] = 3
    database = FakeDatabase(projects=projects)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "list_projects",
            {"tenant_id": 3, "page_size": 1},
        )
        first = ListProjectsResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        second_call = await client.call_tool(
            "list_projects",
            {"tenant_id": 3, "page_size": 1, "cursor": first.next_cursor},
        )
        second = ListProjectsResult.model_validate(second_call.structured_content)
        assert second.next_cursor is not None
        third_call = await client.call_tool(
            "list_projects",
            {"tenant_id": 3, "page_size": 1, "cursor": second.next_cursor},
        )
        third = ListProjectsResult.model_validate(third_call.structured_content)

    assert [project.project_id for project in first.projects] == [1]
    assert [project.project_id for project in second.projects] == [2]
    assert [project.project_id for project in third.projects] == [3]
    assert third.next_cursor is None
    assert database.calls == [(3, 2, 0), (3, 2, 1), (3, 2, 2)]


@pytest.mark.asyncio
async def test_list_projects_rejects_a_tampered_cursor_before_querying_projects() -> (
    None
):
    projects = [_project(project_id) for project_id in range(1, 3)]
    for row in projects:
        row["total_project_count"] = 2
    database = FakeDatabase(projects=projects)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "list_projects",
            {"tenant_id": 3, "page_size": 1},
        )
        first = ListProjectsResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        replacement = "A" if first.next_cursor[0] != "A" else "B"
        rejected = await client.call_tool(
            "list_projects",
            {
                "tenant_id": 3,
                "page_size": 1,
                "cursor": f"{replacement}{first.next_cursor[1:]}",
            },
        )

    assert rejected.is_error is True
    assert database.calls == [(3, 2, 0)]


@pytest.mark.asyncio
async def test_list_projects_cursor_is_bound_to_tenant_and_page_size() -> None:
    projects = [_project(project_id) for project_id in range(1, 3)]
    for row in projects:
        row["total_project_count"] = 2
    database = FakeDatabase(projects=projects)

    async with Client(_server(database)) as client:
        first_call = await client.call_tool(
            "list_projects",
            {"tenant_id": 3, "page_size": 1},
        )
        first = ListProjectsResult.model_validate(first_call.structured_content)
        assert first.next_cursor is not None
        wrong_tenant = await client.call_tool(
            "list_projects",
            {"tenant_id": 4, "page_size": 1, "cursor": first.next_cursor},
        )
        wrong_page_size = await client.call_tool(
            "list_projects",
            {"tenant_id": 3, "page_size": 2, "cursor": first.next_cursor},
        )

    assert wrong_tenant.is_error is True
    assert wrong_page_size.is_error is True
    assert database.calls == [(3, 2, 0)]


@pytest.mark.asyncio
async def test_list_projects_advertises_bounded_pagination_inputs() -> None:
    async with Client(_server(FakeDatabase(projects=[]))) as client:
        tools = await client.list_tools()

    schema = next(
        tool.input_schema for tool in tools.tools if tool.name == "list_projects"
    )
    assert schema["properties"]["page_size"] == {
        "default": 200,
        "maximum": 200,
        "minimum": 1,
        "title": "Page Size",
        "type": "integer",
    }
    assert schema["properties"]["cursor"]["anyOf"] == [
        {"maxLength": 2048, "type": "string"},
        {"type": "null"},
    ]
