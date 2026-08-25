from collections.abc import Iterator

import pytest
from tests.mcp.conftest import DisposablePostgres, disposable_postgres


@pytest.fixture(scope="session")
def web_postgres_database() -> Iterator[DisposablePostgres]:
    yield from disposable_postgres()
