from __future__ import annotations

from typing import Any, LiteralString, Protocol, cast
from uuid import UUID

from psycopg import Connection

from gds_workbench_api.features.mapping import preparation_repository as preparation


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...


def _sql(name: str) -> LiteralString:
    value = vars(preparation).get(name)
    if not isinstance(value, str):
        raise AssertionError(f"missing Mapping preparation query {name}")
    return cast(LiteralString, value)


def test_mapping_preparation_queries_compile_against_disposable_postgres(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    correlation_id = UUID("33333333-3333-3333-3333-333333333333")
    queries: tuple[tuple[LiteralString, tuple[Any, ...]], ...] = (
        (_sql("_MAPPING_RUN_PLAN_SQL"), (7, 18, 1048, 7, 77)),
        (
            _sql("_MAPPING_CONTEXT_ANCHOR_SQL"),
            (
                7,
                18,
                1048,
                7,
                77,
                correlation_id,
                501,
                31,
                "logical_entity",
                "logical_to_silver",
                "build",
                "sql_file",
                "mapping.standard",
                "1.0.0",
                "c" * 64,
                None,
                None,
                None,
                None,
            ),
        ),
        (
            _sql("_MAPPING_DEPENDENCY_GRAPH_SQL"),
            (7, 18, 7, "logical_entity", "logical_entity"),
        ),
        (
            _sql("_MAPPING_TARGET_DEPENDENCY_GRAPH_SQL"),
            (7, 18, 7, "logical_entity", "logical_entity"),
        ),
        (_sql("_MAPPING_TARGET_CONTEXT_SQL"), (7, 18, 7, 501)),
        (
            _sql("_MAPPING_HEADER_CONTEXT_SQL"),
            (7, 18, 7, 501, 31, "logical_entity"),
        ),
        (
            _sql("_MAPPING_SOURCE_CONTEXT_SQL"),
            (7, 18, 7, 501, 31, "logical_entity", 18, 7, 7),
        ),
        (_sql("_MAPPING_OUTPUT_TEMPLATE_CONTEXT_SQL"), ([801, 802],)),
    )

    with web_postgres_database.connect_owner() as connection:
        for query, parameters in queries:
            connection.execute(
                f"EXPLAIN {query}",
                parameters,
            ).fetchall()
