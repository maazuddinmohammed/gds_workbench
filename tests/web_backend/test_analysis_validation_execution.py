from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from types import TracebackType
from typing import Any, Self

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection
from pydantic import ValidationError

from gds_workbench_api.features.analysis.validation_execution import (
    AnalysisValidationEndpoint,
    AnalysisValidationEvidence,
    AnalysisValidationRelationship,
    AnalysisValidationResultInvalidError,
    ConnectorAnalysisValidationExecutor,
    build_analysis_validation_query,
    load_default_analysis_validation_policy,
)

_RESULT_COLUMNS = (
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
    "validation_result",
)


def _endpoint(
    *,
    object_id: int,
    attribute_id: int,
    catalog: str,
    schema: str,
    table: str,
    attribute: str,
    data_type: str = "BIGINT",
    batch_attribute_name: str | None = "batch_id",
    batch_attribute_data_type: str | None = "BIGINT",
) -> AnalysisValidationEndpoint:
    return AnalysisValidationEndpoint(
        relation_catalog=catalog,
        relation_schema=schema,
        relation_object=table,
        object_id=object_id,
        attribute_id=attribute_id,
        attribute_name=attribute,
        attribute_data_type=data_type,
        batch_attribute_name=batch_attribute_name,
        batch_attribute_data_type=batch_attribute_data_type,
    )


def _relationship(
    *,
    from_type: str = "BIGINT",
    to_type: str = "BIGINT",
    from_batch_name: str | None = "batch`id",
    from_batch_type: str | None = "BIGINT",
    to_batch_name: str | None = "batch_id",
    to_batch_type: str | None = "BIGINT",
) -> AnalysisValidationRelationship:
    return AnalysisValidationRelationship(
        analysis_result_id=401,
        relationship_kind="reference",
        relationship_confidence="high",
        relationship_basis="Registered metadata and aggregate value evidence.",
        analysis_result_status="needs_review",
        analysis_result_is_locked=True,
        gds_connection_id=91,
        from_endpoint=_endpoint(
            object_id=101,
            attribute_id=1001,
            catalog="tenant`catalog",
            schema="bronze_crm",
            table="order`raw",
            attribute="customer`id",
            data_type=from_type,
            batch_attribute_name=from_batch_name,
            batch_attribute_data_type=from_batch_type,
        ),
        to_endpoint=_endpoint(
            object_id=102,
            attribute_id=1002,
            catalog="tenant_catalog",
            schema="bronze_crm",
            table="customer_raw",
            attribute="customer_id",
            data_type=to_type,
            batch_attribute_name=to_batch_name,
            batch_attribute_data_type=to_batch_type,
        ),
    )


def test_default_analysis_validation_policy_is_canonical_bounded_and_stable() -> None:
    policy = load_default_analysis_validation_policy()
    expected_document = {
        "schema_version": "1.0",
        "validation_policy_version": "1.0.0",
        "max_parallel_queries": 4,
        "max_progress_events": 20,
        "statement_timeout_seconds": 300,
        "max_relationships": 50_000,
    }
    expected_digest = sha256(
        json.dumps(
            expected_document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    assert policy.model_dump(mode="json") == expected_document
    assert policy.validation_policy_digest == expected_digest
    assert load_default_analysis_validation_policy() is policy


def test_context_models_are_strict_and_secret_free() -> None:
    relationship = _relationship()

    assert relationship.analysis_result_is_locked is True
    assert relationship.from_endpoint.attribute_id == 1001
    assert "host" not in repr(relationship).casefold()
    assert "token" not in repr(relationship).casefold()

    invalid = relationship.model_dump(mode="python")
    invalid["analysis_result_id"] = "401"
    invalid["unexpected"] = True
    with pytest.raises(ValidationError):
        AnalysisValidationRelationship.model_validate(invalid, strict=True)

    with pytest.raises(ValidationError, match="Batch Attribute"):
        _endpoint(
            object_id=101,
            attribute_id=1001,
            catalog="tenant_catalog",
            schema="bronze_crm",
            table="order_raw",
            attribute="customer_id",
            batch_attribute_name="batch_id",
            batch_attribute_data_type=None,
        )


def test_query_is_fixed_aggregate_only_and_binds_each_batch() -> None:
    query = build_analysis_validation_query(
        _relationship(),
        requested_batch_id="10428",
    )

    assert query.analysis_result_id == 401
    assert query.parameters == ("10428", "10428")
    assert "`tenant``catalog`.`bronze_crm`.`order``raw`" in query.sql
    assert "`tenant_catalog`.`bronze_crm`.`customer_raw`" in query.sql
    assert "SELECT `customer``id` AS comparison_value" in query.sql
    assert "WHERE `customer``id` IS NOT NULL" in query.sql
    assert "AND `batch``id` = CAST(? AS BIGINT)" in query.sql
    assert "AND `batch_id` = CAST(? AS BIGINT)" in query.sql
    assert query.sql.index("`batch``id` = CAST(? AS BIGINT)") < query.sql.index(
        "`batch_id` = CAST(? AS BIGINT)"
    )
    assert "10428" not in query.sql
    assert "LEFT ANTI JOIN" in query.sql
    assert "SUM(value_count - 1)" in query.sql
    assert all(f"AS {column}" in query.sql for column in _RESULT_COLUMNS)
    assert "SELECT *" not in query.sql.upper()
    assert "LIMIT" not in query.sql.upper()
    assert query.sql.rstrip().endswith("CROSS JOIN unused_target")


def test_query_accepts_maximum_registered_identifier_sizes() -> None:
    relationship = AnalysisValidationRelationship(
        analysis_result_id=401,
        relationship_kind="reference",
        relationship_confidence="high",
        relationship_basis="Registered metadata and aggregate value evidence.",
        analysis_result_status="needs_review",
        analysis_result_is_locked=True,
        gds_connection_id=91,
        from_endpoint=_endpoint(
            object_id=101,
            attribute_id=1001,
            catalog="`" * 255,
            schema="`" * 400,
            table="`" * 400,
            attribute="`" * 400,
            batch_attribute_name="`" * 400,
        ),
        to_endpoint=_endpoint(
            object_id=102,
            attribute_id=1002,
            catalog="c" * 255,
            schema="s" * 400,
            table="t" * 400,
            attribute="a" * 400,
            batch_attribute_name="b" * 400,
        ),
    )

    query = build_analysis_validation_query(
        relationship,
        requested_batch_id="x" * 500,
    )

    assert len(query.sql) <= 100_000
    assert query.parameters == ("x" * 500, "x" * 500)


@pytest.mark.parametrize(
    ("requested_batch_id", "from_batch_name", "from_batch_type", "expected_parameters"),
    [
        (None, "batch_id", "BIGINT", ()),
        ("10428", None, None, ("10428",)),
    ],
)
def test_analysis_validation_query_uses_only_explicit_available_batch_filters(
    requested_batch_id: str | None,
    from_batch_name: str | None,
    from_batch_type: str | None,
    expected_parameters: tuple[str, ...],
) -> None:
    query = build_analysis_validation_query(
        _relationship(
            from_batch_name=from_batch_name,
            from_batch_type=from_batch_type,
        ),
        requested_batch_id=requested_batch_id,
    )

    assert query.parameters == expected_parameters
    assert query.sql.count("CAST(? AS BIGINT)") == len(expected_parameters)


@pytest.mark.parametrize(
    "data_type",
    [
        "BOOLEAN",
        "TINYINT",
        "SMALLINT",
        "INT",
        "BIGINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL(18, 0)",
        "STRING",
        "VARCHAR(255)",
        "CHAR(12)",
        "DATE",
        "TIMESTAMP",
        "TIMESTAMP_NTZ",
        "TIMESTAMP_LTZ",
    ],
)
def test_analysis_validation_query_accepts_matching_scalar_types(
    data_type: str,
) -> None:
    query = build_analysis_validation_query(
        _relationship(
            from_type=data_type,
            to_type=data_type.lower(),
            from_batch_name=None,
            from_batch_type=None,
            to_batch_name=None,
            to_batch_type=None,
        ),
        requested_batch_id=None,
    )

    assert query.analysis_result_id == 401


def test_analysis_validation_query_normalizes_only_type_syntax_not_values() -> None:
    query = build_analysis_validation_query(
        _relationship(
            from_type=" decimal ( 18 , 0 ) ",
            to_type="DECIMAL(18,0)",
            from_batch_name=None,
            from_batch_type=None,
            to_batch_name=None,
            to_batch_type=None,
        ),
        requested_batch_id=None,
    )

    assert "TRIM(" not in query.sql
    assert "LOWER(" not in query.sql
    assert "TRY_CAST(" not in query.sql


@pytest.mark.parametrize(
    ("relationship", "message"),
    [
        (
            _relationship(
                from_type="BIGINT",
                to_type="STRING",
                from_batch_name=None,
                from_batch_type=None,
                to_batch_name=None,
                to_batch_type=None,
            ),
            "matching",
        ),
        (
            _relationship(
                from_type="ARRAY<BIGINT>",
                to_type="ARRAY<BIGINT>",
                from_batch_name=None,
                from_batch_type=None,
                to_batch_name=None,
                to_batch_type=None,
            ),
            "scalar",
        ),
        (
            _relationship(from_batch_type="ARRAY<BIGINT>"),
            "Batch Attribute",
        ),
    ],
)
def test_analysis_validation_query_rejects_unsafe_type_or_batch_metadata(
    relationship: AnalysisValidationRelationship,
    message: str,
) -> None:
    with pytest.raises(InvalidRequestError, match=message):
        build_analysis_validation_query(
            relationship,
            requested_batch_id="10428",
        )


@dataclass
class _FakeCursor:
    rows: list[tuple[object, ...]]
    description: tuple[tuple[str], ...] = tuple((column,) for column in _RESULT_COLUMNS)
    executions: list[tuple[str, tuple[str, ...]]] = field(
        default_factory=lambda: list[tuple[str, tuple[str, ...]]]()
    )
    fetch_sizes: list[int] = field(default_factory=lambda: list[int]())

    def execute(self, operation: str, parameters: Sequence[object]) -> object:
        self.executions.append((operation, tuple(str(value) for value in parameters)))
        return object()

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        self.fetch_sizes.append(size)
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


def _valid_row() -> tuple[object, ...]:
    return (100, 90, 120, 120, 0, 30, 0, "supported")


@pytest.mark.asyncio
async def test_connector_returns_one_validated_aggregate_row() -> None:
    cursor = _FakeCursor(rows=[_valid_row()])
    connect_arguments: dict[str, Any] = {}

    def connect(**arguments: Any) -> _FakeConnection:
        connect_arguments.update(arguments)
        return _FakeConnection(cursor)

    query = build_analysis_validation_query(
        _relationship(),
        requested_batch_id="10428",
    )
    connection = DatabricksSqlConnection(
        server_hostname="sensitive-host",
        http_path="sensitive-path",
        access_token="sensitive-token",
    )

    evidence = await ConnectorAnalysisValidationExecutor(connect=connect).execute(
        connection=connection,
        query=query,
        timeout_seconds=300,
    )

    assert evidence == AnalysisValidationEvidence(
        validation_source_non_null_count=100,
        validation_source_distinct_count=90,
        validation_target_non_null_count=120,
        validation_target_distinct_count=120,
        validation_source_missing_target_count=0,
        validation_unused_target_count=30,
        validation_duplicate_target_key_count=0,
        validation_result="supported",
    )
    assert cursor.executions == [(query.sql, ("10428", "10428"))]
    assert cursor.fetch_sizes == [2]
    assert connect_arguments["paramstyle"] == "qmark"
    assert connect_arguments["session_configuration"] == {"STATEMENT_TIMEOUT": "300"}
    assert connect_arguments["use_cloud_fetch"] is False
    assert "sensitive-host" not in repr(connection)
    assert "sensitive-path" not in repr(connection)
    assert "sensitive-token" not in repr(connection)


@pytest.mark.parametrize(
    "rows",
    [
        [],
        [_valid_row(), _valid_row()],
        [(-1, 0, 0, 0, 0, 0, 0, "inconclusive")],
        [(100, 101, 120, 120, 0, 30, 0, "supported")],
        [(100, 90, 120, 120, 91, 30, 0, "unsupported")],
        [(100, 90, 120, 110, 0, 20, 9, "supported")],
        [(100, 90, 120, 120, 1, 31, 0, "supported")],
    ],
)
@pytest.mark.asyncio
async def test_analysis_validation_connector_rejects_invalid_count_or_result_contract(
    rows: list[tuple[object, ...]],
) -> None:
    cursor = _FakeCursor(rows=rows)

    def connect(**_arguments: Any) -> _FakeConnection:
        return _FakeConnection(cursor)

    connection = DatabricksSqlConnection(
        server_hostname="sensitive-host",
        http_path="sensitive-path",
        access_token="sensitive-token",
    )
    query = build_analysis_validation_query(
        _relationship(),
        requested_batch_id=None,
    )

    with pytest.raises(AnalysisValidationResultInvalidError) as raised:
        await ConnectorAnalysisValidationExecutor(connect=connect).execute(
            connection=connection,
            query=query,
            timeout_seconds=300,
        )

    assert "sensitive-host" not in str(raised.value)
    assert "sensitive-path" not in str(raised.value)
    assert "sensitive-token" not in str(raised.value)


@pytest.mark.asyncio
async def test_analysis_validation_connector_requires_exact_ordered_columns() -> None:
    cursor = _FakeCursor(
        rows=[_valid_row()],
        description=tuple((column,) for column in reversed(_RESULT_COLUMNS)),
    )

    def connect(**_arguments: Any) -> _FakeConnection:
        return _FakeConnection(cursor)

    with pytest.raises(AnalysisValidationResultInvalidError):
        await ConnectorAnalysisValidationExecutor(connect=connect).execute(
            connection=DatabricksSqlConnection(
                server_hostname="sensitive-host",
                http_path="sensitive-path",
                access_token="sensitive-token",
            ),
            query=build_analysis_validation_query(
                _relationship(),
                requested_batch_id=None,
            ),
            timeout_seconds=300,
        )
