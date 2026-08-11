from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gds_etl_workbench.domain.errors import TenantNotFoundError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

if TYPE_CHECKING:
    from conftest import DisposablePostgres


@pytest.mark.asyncio
async def test_read_transaction_supports_repeatable_read_snapshot_boundary(
    postgres_database: DisposablePostgres,
) -> None:
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            posture = await transaction.fetch_one(
                """
                SELECT current_setting('transaction_isolation') AS isolation,
                       current_setting('transaction_read_only') AS read_only
                """
            )
    finally:
        await database.close()

    assert posture == {"isolation": "repeatable read", "read_only": "on"}


@pytest.mark.asyncio
async def test_read_transaction_preserves_workbench_errors(
    postgres_database: DisposablePostgres,
) -> None:
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        with pytest.raises(TenantNotFoundError):
            async with database.read_transaction():
                raise TenantNotFoundError()
    finally:
        await database.close()
