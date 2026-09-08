from collections.abc import Iterator

import pytest

from tests.mcp.conftest import DisposablePostgres, disposable_postgres


@pytest.fixture(scope="module")
def web_postgres_database() -> Iterator[DisposablePostgres]:
    # Worker claims scan all Tenants; each module needs its own pending Run queue.
    yield from disposable_postgres()
