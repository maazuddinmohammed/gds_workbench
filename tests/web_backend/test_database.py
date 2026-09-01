from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import ClassVar

import pytest
from psycopg.errors import InsufficientPrivilege

import gds_workbench_api.database as database_module
from gds_workbench_api.database import WebPostgresDatabase


class Result:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row or {"active": True}

    async def fetchone(self) -> dict[str, object]:
        return self.row


class Connection:
    def __init__(self) -> None:
        self.role_active = False
        self.queries: list[str] = []

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            self.role_active = False

    async def execute(self, query: object, _parameters: object = ()) -> Result:
        sql = str(query).strip()
        self.queries.append(sql)
        if sql == "SET LOCAL ROLE gds_web_write":
            self.role_active = True
        elif sql.startswith("SELECT") and not self.role_active:
            raise InsufficientPrivilege("web runtime role is not active")
        if "server_version_num" in sql:
            return Result(
                {
                    "postgres_major": 18,
                    "schema_ready": True,
                    "role_ready": True,
                    "privileges_ready": True,
                    "workflow_guard_ready": True,
                    "application_reference_ready": True,
                }
            )
        return Result()


class Pool:
    last_instance: ClassVar[Pool | None] = None

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.connection_instance = Connection()
        Pool.last_instance = self

    async def open(self, *, wait: bool) -> None:
        assert wait is False

    async def close(self) -> None:
        pass

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[Connection]:
        self.connection_instance.role_active = False
        yield self.connection_instance


@pytest.mark.asyncio
async def test_every_web_transaction_activates_the_least_privilege_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database_module, "AsyncConnectionPool", Pool)
    database = WebPostgresDatabase(
        dsn="postgresql://runtime@example.invalid/workbench",
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=1,
    )
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            first = await transaction.fetch_one("SELECT TRUE AS active")
        async with database.read_transaction() as transaction:
            second = await transaction.fetch_one("SELECT TRUE AS active")
    finally:
        await database.close()

    assert first == {"active": True}
    assert second == {"active": True}


@pytest.mark.asyncio
async def test_readiness_checks_the_web_schema_and_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database_module, "AsyncConnectionPool", Pool)
    database = WebPostgresDatabase(
        dsn="postgresql://runtime@example.invalid/workbench",
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=1,
    )
    await database.open()
    try:
        readiness = await database.readiness()
    finally:
        await database.close()

    assert readiness.ready is True
    assert readiness.code == "ready"
    assert Pool.last_instance is not None
    readiness_sql = "\n".join(Pool.last_instance.connection_instance.queries)
    assert "application.workflow_run_object_selection" in readiness_sql
    assert "application.generated_sql_artifact" in readiness_sql
    assert "application.create_model" in readiness_sql
    assert "workflow.list_tenant_visible_objects" in readiness_sql
    assert "workflow.list_model_object_eligibility" in readiness_sql
    assert "workflow.list_model_attribute_eligibility" in readiness_sql
    assert "workflow.list_code_generation_target_context" in readiness_sql
    assert "mcp.get_databricks_sql_connection_values" in readiness_sql
    assert "uq_workflow_run_running_tenant" in readiness_sql
    assert "fk_workflow_run_model" in readiness_sql
    assert "count(*) = 49" in readiness_sql
    assert "count(*) = 80" in readiness_sql
    assert "pg_auth_members" in readiness_sql
    assert "mcp.model_change_set" in readiness_sql
    assert "workflow.conceptual_object" in readiness_sql
    assert "workflow.attribute_profile" in readiness_sql
