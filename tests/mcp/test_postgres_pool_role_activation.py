from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

import pytest
from psycopg.errors import InsufficientPrivilege

import gds_etl_workbench.infrastructure.postgres as postgres_module
from gds_etl_workbench.infrastructure.postgres import PostgresDatabase


class _Result:
    def __init__(self, row: dict[str, object]) -> None:
        self.row = row

    async def fetchone(self) -> dict[str, object]:
        return self.row


class _Connection:
    def __init__(self) -> None:
        self.role_active = False

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            self.role_active = False

    async def execute(self, query: object, _parameters: object = ()) -> _Result:
        sql = str(query)
        if sql == "SET ROLE gds_app_write" or sql == "SET LOCAL ROLE gds_app_write":
            self.role_active = True
        elif sql.startswith("SELECT") and not self.role_active:
            raise InsufficientPrivilege("runtime role is not active")
        if "server_version_num" in sql:
            return _Result({"postgres_major": 18, "contract_exists": True})
        if "FROM mcp.runtime_readiness()" in sql:
            return _Result(
                {
                    "schema_version": "1.0.0",
                    "postgres_major": 18,
                    "schema_shape_ok": True,
                    "runtime_role_ok": True,
                    "runtime_privileges_ok": True,
                    "runtime_query_contract_ok": True,
                }
            )
        return _Result({"active": True})


class _Pool:
    def __init__(
        self,
        *_args: object,
        configure: Callable[[_Connection], Awaitable[None]] | None = None,
        **_kwargs: object,
    ) -> None:
        self.connection_instance = _Connection()
        self.configure = configure

    async def open(self, *, wait: bool) -> None:
        assert wait is False
        if self.configure is not None:
            await self.configure(self.connection_instance)
        self.connection_instance.role_active = False

    async def close(self) -> None:
        pass

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[_Connection]:
        self.connection_instance.role_active = False
        yield self.connection_instance


@pytest.mark.asyncio
async def test_read_transaction_reactivates_role_after_pool_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(postgres_module, "AsyncConnectionPool", _Pool)
    database = PostgresDatabase(
        dsn="postgresql://runtime@example.invalid/workbench",
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=1,
        require_runtime_role=True,
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
async def test_readiness_reactivates_role_after_pool_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(postgres_module, "AsyncConnectionPool", _Pool)
    database = PostgresDatabase(
        dsn="postgresql://runtime@example.invalid/workbench",
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=1,
        require_runtime_role=True,
    )
    await database.open()
    try:
        readiness = await database.readiness()
    finally:
        await database.close()

    assert readiness.ready is True
    assert readiness.code == "ready"
