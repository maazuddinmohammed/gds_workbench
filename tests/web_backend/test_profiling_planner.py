from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection

from gds_workbench_api.features.profiling.execution import (
    ConnectorProfilingExecutor,
    ProfileAttribute,
    ProfileMetric,
    ProfileObject,
    build_profile_queries,
    load_default_profiling_policy,
)


def _object(*, with_batch: bool = True) -> ProfileObject:
    return ProfileObject(
        object_id=71,
        connection_id=12,
        catalog="tenant`catalog",
        schema="bronze_crm",
        table="customer_raw",
        batch_attribute_name="batch_id" if with_batch else None,
        attributes=(
            ProfileAttribute(attribute_id=801, name="customer_id", data_type="BIGINT"),
            ProfileAttribute(attribute_id=802, name="display_name", data_type="STRING"),
            ProfileAttribute(attribute_id=803, name="batch_id", data_type="BIGINT"),
        ),
    )


def test_default_profiling_policy_is_bounded_and_json_driven() -> None:
    policy = load_default_profiling_policy()

    assert policy.schema_version == "1.0"
    assert policy.attributes_per_query == 50
    assert policy.max_parallel_queries == 4
    assert policy.statement_timeout_seconds == 300
    assert policy.max_attributes_per_object == 2_000


def test_profile_query_scans_one_object_for_all_attributes_and_binds_batch() -> None:
    queries = build_profile_queries(
        _object(),
        requested_batch_id="10428",
        attributes_per_query=50,
    )

    assert len(queries) == 1
    query = queries[0]
    assert query.object_id == 71
    assert query.attribute_ids == (801, 802, 803)
    assert query.parameters == ("10428",)
    assert "`tenant``catalog`.`bronze_crm`.`customer_raw`" in query.sql
    assert "WHERE `batch_id` = CAST(? AS BIGINT)" in query.sql
    assert "10428" not in query.sql
    assert query.sql.count("FROM scoped") == 1
    assert "COUNT(DISTINCT `customer_id`)" in query.sql
    assert "TRIM(`display_name`)" in query.sql
    assert "AS attribute_id" in query.sql
    assert "SELECT *" not in query.sql.upper()
    assert "LIMIT" not in query.sql.upper()


@pytest.mark.parametrize(
    ("target", "requested_batch_id"),
    [
        (_object(), None),
        (_object(with_batch=False), "10428"),
    ],
)
def test_profile_query_omits_batch_filter_unless_both_inputs_exist(
    target: ProfileObject,
    requested_batch_id: str | None,
) -> None:
    query = build_profile_queries(
        target,
        requested_batch_id=requested_batch_id,
        attributes_per_query=50,
    )[0]

    assert " WHERE " not in query.sql
    assert query.parameters == ()


def test_profile_query_rejects_inconsistent_batch_metadata() -> None:
    target = ProfileObject(
        object_id=71,
        connection_id=12,
        catalog="tenant_catalog",
        schema="bronze_crm",
        table="customer_raw",
        batch_attribute_name="missing_batch_id",
        attributes=_object().attributes,
    )

    with pytest.raises(InvalidRequestError, match="Batch Attribute metadata"):
        build_profile_queries(
            target,
            requested_batch_id="10428",
            attributes_per_query=50,
        )


def test_profile_query_chunks_only_oversized_objects_without_omitting_attributes() -> None:
    target = ProfileObject(
        object_id=71,
        connection_id=12,
        catalog="tenant_catalog",
        schema="bronze_crm",
        table="wide_table",
        batch_attribute_name=None,
        attributes=tuple(
            ProfileAttribute(
                attribute_id=1_000 + index,
                name=f"attribute_{index}",
                data_type="INT",
            )
            for index in range(1, 53)
        ),
    )

    queries = build_profile_queries(
        target,
        requested_batch_id=None,
        attributes_per_query=50,
    )

    assert [len(query.attribute_ids) for query in queries] == [50, 2]
    assert tuple(
        attribute_id for query in queries for attribute_id in query.attribute_ids
    ) == tuple(range(1_001, 1_053))


@pytest.mark.parametrize(
    "data_type",
    ["MAP<STRING, STRING>", "ARRAY<INT>", "STRUCT<id: BIGINT>"],
)
def test_profile_query_leaves_unsupported_complex_metrics_null(data_type: str) -> None:
    target = ProfileObject(
        object_id=71,
        connection_id=12,
        catalog="tenant_catalog",
        schema="bronze_crm",
        table="complex_table",
        batch_attribute_name=None,
        attributes=(ProfileAttribute(attribute_id=901, name="payload", data_type=data_type),),
    )

    sql = build_profile_queries(
        target,
        requested_batch_id=None,
        attributes_per_query=50,
    )[0].sql

    assert "COUNT(DISTINCT `payload`)" not in sql
    assert "CAST(NULL AS BIGINT) AS distinct_count" in sql
    assert "CAST(NULL AS BIGINT) AS blank_count" in sql


_RESULT_COLUMNS = (
    "attribute_id",
    "row_count",
    "non_null_count",
    "null_count",
    "blank_count",
    "distinct_count",
    "min_data_length",
    "max_data_length",
    "avg_data_length",
    "percent_populated",
    "percent_duplicates",
    "percent_null",
    "percent_blank",
    "percent_distinct",
)


@dataclass
class _FakeCursor:
    rows: list[tuple[object, ...]]
    description: tuple[tuple[str], ...] = tuple((column,) for column in _RESULT_COLUMNS)
    executions: list[tuple[str, tuple[str, ...]]] = field(
        default_factory=lambda: list[tuple[str, tuple[str, ...]]]()
    )

    def execute(self, operation: str, parameters: Sequence[object]) -> object:
        self.executions.append((operation, tuple(str(value) for value in parameters)))
        return object()

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        return self.rows[:size]

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> object:
        del exception_type, exception, traceback
        return False


@dataclass
class _FakeConnection:
    cursor_value: _FakeCursor

    def cursor(self) -> _FakeCursor:
        return self.cursor_value

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> object:
        del exception_type, exception, traceback
        return False


@pytest.mark.asyncio
async def test_profiling_executor_uses_native_parameters_and_returns_only_metrics() -> None:
    cursor = _FakeCursor(
        rows=[
            (801, 10, 8, 2, None, 8, None, None, None, 80.0, 0.0, 20.0, None, 100.0),
            (802, 10, 7, 3, 1, 6, 2, 14, 7.5, 70.0, 14.2857, 30.0, 14.2857, 85.7143),
            (803, 10, 10, 0, None, 1, None, None, None, 100.0, 90.0, 0.0, None, 10.0),
        ]
    )
    connect_arguments: dict[str, Any] = {}

    def connect(**arguments: Any) -> _FakeConnection:
        connect_arguments.update(arguments)
        return _FakeConnection(cursor)

    query = build_profile_queries(
        _object(),
        requested_batch_id="10428",
        attributes_per_query=50,
    )[0]
    connection = DatabricksSqlConnection(
        server_hostname="sensitive-host",
        http_path="sensitive-path",
        access_token="sensitive-token",
    )

    result = await ConnectorProfilingExecutor(connect=connect).execute(
        connection=connection,
        query=query,
        timeout_seconds=300,
    )

    assert result == (
        ProfileMetric(
            attribute_id=801,
            row_count=10,
            non_null_count=8,
            null_count=2,
            blank_count=None,
            distinct_count=8,
            min_data_length=None,
            max_data_length=None,
            avg_data_length=None,
            percent_populated=80.0,
            percent_duplicates=0.0,
            percent_null=20.0,
            percent_blank=None,
            percent_distinct=100.0,
        ),
        ProfileMetric(
            attribute_id=802,
            row_count=10,
            non_null_count=7,
            null_count=3,
            blank_count=1,
            distinct_count=6,
            min_data_length=2,
            max_data_length=14,
            avg_data_length=7.5,
            percent_populated=70.0,
            percent_duplicates=14.2857,
            percent_null=30.0,
            percent_blank=14.2857,
            percent_distinct=85.7143,
        ),
        ProfileMetric(
            attribute_id=803,
            row_count=10,
            non_null_count=10,
            null_count=0,
            blank_count=None,
            distinct_count=1,
            min_data_length=None,
            max_data_length=None,
            avg_data_length=None,
            percent_populated=100.0,
            percent_duplicates=90.0,
            percent_null=0.0,
            percent_blank=None,
            percent_distinct=10.0,
        ),
    )
    assert cursor.executions == [(query.sql, ("10428",))]
    assert connect_arguments["paramstyle"] == "qmark"
    assert connect_arguments["session_configuration"] == {"STATEMENT_TIMEOUT": "300"}
    assert "sensitive-host" not in repr(connection)
    assert "sensitive-path" not in repr(connection)
    assert "sensitive-token" not in repr(connection)
