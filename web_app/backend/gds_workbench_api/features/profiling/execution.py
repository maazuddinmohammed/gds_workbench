# pyright: reportMissingTypeStubs=false

"""Deterministic Databricks profiling query planning and execution.

This module plans aggregate-only queries. It never selects or returns physical rows.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from types import TracebackType
from typing import Any, Protocol, Self, cast

from databricks import sql as databricks_sql
from databricks.sql.exc import Error as DatabricksError
from gds_etl_workbench.domain.errors import (
    DatabricksConnectionFailedError,
    DatabricksResultTooLargeError,
    DatabricksStatementFailedError,
    InvalidRequestError,
)
from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

_MAX_ATTRIBUTES = 2_000
_MAX_ATTRIBUTES_PER_QUERY = 50
_MAX_SQL_CHARACTERS = 100_000

_connector_logger = logging.getLogger("databricks.sql")
_connector_logger.handlers.clear()
_connector_logger.setLevel(logging.CRITICAL + 1)
_connector_logger.propagate = False
_connector_logger.disabled = True

_STRING_TYPE = re.compile(r"^(?:STRING|VARCHAR(?:\(\d+\))?|CHAR(?:\(\d+\))?)$")
_DISTINCT_TYPE = re.compile(
    r"^(?:BOOLEAN|BYTE|TINYINT|SHORT|SMALLINT|INT|INTEGER|LONG|BIGINT|FLOAT|REAL|"
    r"DOUBLE|DATE|TIMESTAMP(?:_NTZ|_LTZ)?|DECIMAL\(\d+,\d+\)|NUMERIC\(\d+,\d+\))$"
)
_BATCH_TYPE = re.compile(
    r"^(?:STRING|VARCHAR(?:\(\d+\))?|CHAR(?:\(\d+\))?|BOOLEAN|BYTE|TINYINT|SHORT|"
    r"SMALLINT|INT|INTEGER|LONG|BIGINT|FLOAT|REAL|DOUBLE|DATE|TIMESTAMP(?:_NTZ|_LTZ)?|"
    r"DECIMAL\(\d+,\d+\)|NUMERIC\(\d+,\d+\))$"
)


class ProfileAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attribute_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=400)
    data_type: str = Field(min_length=1, max_length=100)

    @field_validator("name", "data_type")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Profile Attribute text must be nonblank")
        return value


class ProfilingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    attributes_per_query: int = Field(gt=0, le=_MAX_ATTRIBUTES_PER_QUERY)
    max_parallel_queries: int = Field(gt=0, le=32)
    statement_timeout_seconds: int = Field(gt=0, le=3_600)
    max_attributes_per_object: int = Field(gt=0, le=_MAX_ATTRIBUTES)


@lru_cache(maxsize=1)
def load_default_profiling_policy() -> ProfilingPolicy:
    resource = files("gds_workbench_api").joinpath("config", "profiling.json")
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Profiling policy is unavailable.") from error
    return ProfilingPolicy.model_validate(payload, strict=True)


class ProfileObject(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object_id: int = Field(gt=0)
    connection_id: int = Field(gt=0)
    catalog: str = Field(min_length=1, max_length=255)
    schema_name: str = Field(alias="schema", min_length=1, max_length=400)
    table: str = Field(min_length=1, max_length=400)
    batch_attribute_name: str | None = Field(default=None, max_length=400)
    attributes: tuple[ProfileAttribute, ...] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTES,
    )

    @field_validator("catalog", "schema_name", "table")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Profile Object identifiers must be nonblank")
        return value

    @field_validator("batch_attribute_name")
    @classmethod
    def validate_optional_identifier(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("Batch Attribute name must be nonblank")
        return value

    @model_validator(mode="after")
    def validate_attributes(self) -> ProfileObject:
        attribute_ids = [attribute.attribute_id for attribute in self.attributes]
        attribute_names = [attribute.name.casefold() for attribute in self.attributes]
        if len(attribute_ids) != len(set(attribute_ids)):
            raise ValueError("Profile Attribute IDs must be unique")
        if len(attribute_names) != len(set(attribute_names)):
            raise ValueError("Profile Attribute names must be case-insensitively unique")
        return self


class ProfileMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attribute_id: int = Field(gt=0)
    row_count: int = Field(ge=0)
    non_null_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    blank_count: int | None = Field(default=None, ge=0)
    distinct_count: int | None = Field(default=None, ge=0)
    min_data_length: int | None = Field(default=None, ge=0)
    max_data_length: int | None = Field(default=None, ge=0)
    avg_data_length: float | None = Field(default=None, ge=0)
    percent_populated: float = Field(ge=0, le=100)
    percent_duplicates: float | None = Field(default=None, ge=0, le=100)
    percent_null: float = Field(ge=0, le=100)
    percent_blank: float | None = Field(default=None, ge=0, le=100)
    percent_distinct: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_metrics(self) -> ProfileMetric:
        if self.non_null_count + self.null_count != self.row_count:
            raise ValueError("Profile counts do not reconcile")
        if self.blank_count is not None and self.blank_count > self.non_null_count:
            raise ValueError("Profile blank count exceeds non-null count")
        if self.distinct_count is not None and self.distinct_count > self.non_null_count:
            raise ValueError("Profile distinct count exceeds non-null count")
        if (
            self.min_data_length is not None
            and self.max_data_length is not None
            and self.min_data_length > self.max_data_length
        ):
            raise ValueError("Profile length metrics do not reconcile")
        return self


@dataclass(frozen=True, slots=True)
class ProfileQuery:
    object_id: int
    attribute_ids: tuple[int, ...]
    sql: str
    parameters: tuple[str, ...]


class ProfilingExecutor(Protocol):
    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        query: ProfileQuery,
        timeout_seconds: int,
    ) -> tuple[ProfileMetric, ...]: ...


class _Cursor(Protocol):
    @property
    def description(self) -> Sequence[Sequence[Any]] | None: ...

    def execute(self, operation: str, parameters: Sequence[object]) -> object: ...

    def fetchmany(self, size: int) -> Sequence[Sequence[object]]: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> object: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> object: ...


type ConnectFunction = Callable[..., _Connection]

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


class ConnectorProfilingExecutor:
    """Run one generated aggregate query through the native Connector API."""

    def __init__(self, connect: ConnectFunction | None = None) -> None:
        default_connect = cast(
            ConnectFunction,
            databricks_sql.connect,  # pyright: ignore[reportUnknownMemberType]
        )
        self._connect = connect or default_connect

    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        query: ProfileQuery,
        timeout_seconds: int,
    ) -> tuple[ProfileMetric, ...]:
        if not 1 <= timeout_seconds <= 3_600:
            raise InvalidRequestError("Profiling timeout must be between 1 and 3600 seconds.")
        return await asyncio.to_thread(
            self._execute_sync,
            connection,
            query,
            timeout_seconds,
        )

    def _execute_sync(
        self,
        connection_values: DatabricksSqlConnection,
        query: ProfileQuery,
        timeout_seconds: int,
    ) -> tuple[ProfileMetric, ...]:
        try:
            connection = self._connect(
                server_hostname=connection_values.server_hostname,
                http_path=connection_values.http_path,
                access_token=connection_values.access_token,
                paramstyle="qmark",
                session_configuration={"STATEMENT_TIMEOUT": str(timeout_seconds)},
                user_agent_entry="gds-workbench-web",
                use_cloud_fetch=False,
                enable_telemetry=0,
                _socket_timeout=timeout_seconds,
                _retry_stop_after_attempts_count=3,
                _use_arrow_native_complex_types=False,
            )
        except DatabricksError:
            raise DatabricksConnectionFailedError() from None

        try:
            with connection, connection.cursor() as cursor:
                cursor.execute(query.sql, query.parameters)
                description = cursor.description
                if description is None:
                    raise DatabricksResultTooLargeError()
                columns = tuple(str(column[0]) for column in description if column)
                if columns != _RESULT_COLUMNS:
                    raise DatabricksResultTooLargeError()
                rows = cursor.fetchmany(len(query.attribute_ids) + 1)
        except DatabricksError:
            raise DatabricksStatementFailedError(1) from None

        if len(rows) != len(query.attribute_ids):
            raise DatabricksResultTooLargeError()
        try:
            metrics = tuple(
                ProfileMetric.model_validate(
                    dict(zip(_RESULT_COLUMNS, row, strict=True)),
                    strict=False,
                )
                for row in rows
            )
        except TypeError, ValidationError:
            raise DatabricksResultTooLargeError() from None
        if tuple(metric.attribute_id for metric in metrics) != query.attribute_ids:
            raise DatabricksResultTooLargeError()
        return metrics


def build_profile_queries(
    target: ProfileObject,
    *,
    requested_batch_id: str | None,
    attributes_per_query: int = _MAX_ATTRIBUTES_PER_QUERY,
) -> tuple[ProfileQuery, ...]:
    """Build complete aggregate queries for one registered Object."""
    if not 1 <= attributes_per_query <= _MAX_ATTRIBUTES_PER_QUERY:
        raise InvalidRequestError(
            f"attributes_per_query must be between 1 and {_MAX_ATTRIBUTES_PER_QUERY}."
        )

    batch = _batch_filter(target, requested_batch_id)
    relation = ".".join(
        _quote_identifier(value) for value in (target.catalog, target.schema_name, target.table)
    )
    planned: list[ProfileQuery] = []
    for offset in range(0, len(target.attributes), attributes_per_query):
        attributes = target.attributes[offset : offset + attributes_per_query]
        sql = _build_query(relation, attributes, batch)
        if len(sql) > _MAX_SQL_CHARACTERS:
            raise InvalidRequestError("Generated Profiling SQL exceeds the supported size.")
        planned.append(
            ProfileQuery(
                object_id=target.object_id,
                attribute_ids=tuple(attribute.attribute_id for attribute in attributes),
                sql=sql,
                parameters=() if batch is None else (batch[1],),
            )
        )
    return tuple(planned)


def _batch_filter(
    target: ProfileObject,
    requested_batch_id: str | None,
) -> tuple[str, str, str] | None:
    if requested_batch_id is None or target.batch_attribute_name is None:
        return None
    batch_attribute = next(
        (
            attribute
            for attribute in target.attributes
            if attribute.name.casefold() == target.batch_attribute_name.casefold()
        ),
        None,
    )
    if batch_attribute is None:
        raise InvalidRequestError(
            "Batch Attribute metadata does not match an active Object Attribute."
        )
    normalized_type = _normalized_type(batch_attribute.data_type)
    if _BATCH_TYPE.fullmatch(normalized_type) is None:
        raise InvalidRequestError("Batch Attribute data type is not supported for Profiling.")
    return batch_attribute.name, requested_batch_id, normalized_type


def _build_query(
    relation: str,
    attributes: tuple[ProfileAttribute, ...],
    batch: tuple[str, str, str] | None,
) -> str:
    selected = ",\n".join(f"       {_quote_identifier(attribute.name)}" for attribute in attributes)
    predicate = ""
    if batch is not None:
        predicate = f"\n WHERE {_quote_identifier(batch[0])} = CAST(? AS {batch[2]})"

    aggregates = ["       COUNT(*) AS row_count"]
    supports: list[tuple[bool, bool]] = []
    for index, attribute in enumerate(attributes):
        identifier = _quote_identifier(attribute.name)
        string, distinct = _metric_support(attribute.data_type)
        supports.append((string, distinct))
        prefix = f"p{index}"
        aggregates.append(f"       COUNT({identifier}) AS {prefix}_non_null_count")
        if distinct:
            aggregates.append(f"       COUNT(DISTINCT {identifier}) AS {prefix}_distinct_count")
        if string:
            aggregates.extend(
                (
                    "       CAST(COALESCE(SUM(CASE WHEN "
                    f"{identifier} IS NOT NULL AND TRIM({identifier}) = '' "
                    f"THEN 1 ELSE 0 END), 0) AS BIGINT) AS {prefix}_blank_count",
                    f"       MIN(LENGTH({identifier})) AS {prefix}_min_data_length",
                    f"       MAX(LENGTH({identifier})) AS {prefix}_max_data_length",
                    f"       AVG(CAST(LENGTH({identifier}) AS DOUBLE)) AS {prefix}_avg_data_length",
                )
            )

    projections = [
        _projection(attribute, index, *supports[index])
        for index, attribute in enumerate(attributes)
    ]
    return (
        "WITH scoped AS (\n"
        "SELECT\n"
        f"{selected}\n"
        f"  FROM {relation}{predicate}\n"
        "),\nsummary AS (\n"
        "SELECT\n"
        f"{',\n'.join(aggregates)}\n"
        "  FROM scoped\n"
        ")\n"
        f"{'\nUNION ALL\n'.join(projections)}"
    )


def _projection(
    attribute: ProfileAttribute,
    index: int,
    string: bool,
    distinct: bool,
) -> str:
    prefix = f"p{index}"
    non_null = f"{prefix}_non_null_count"
    null_count = f"(row_count - {non_null})"
    distinct_value = f"{prefix}_distinct_count" if distinct else None
    blank_value = f"{prefix}_blank_count" if string else None
    values = (
        f"       CAST({attribute.attribute_id} AS BIGINT) AS attribute_id",
        "       CAST(row_count AS BIGINT) AS row_count",
        f"       CAST({non_null} AS BIGINT) AS non_null_count",
        f"       CAST({null_count} AS BIGINT) AS null_count",
        (
            f"       CAST({blank_value} AS BIGINT) AS blank_count"
            if blank_value is not None
            else "       CAST(NULL AS BIGINT) AS blank_count"
        ),
        (
            f"       CAST({distinct_value} AS BIGINT) AS distinct_count"
            if distinct_value is not None
            else "       CAST(NULL AS BIGINT) AS distinct_count"
        ),
        (
            f"       CAST({prefix}_min_data_length AS INT) AS min_data_length"
            if string
            else "       CAST(NULL AS INT) AS min_data_length"
        ),
        (
            f"       CAST({prefix}_max_data_length AS INT) AS max_data_length"
            if string
            else "       CAST(NULL AS INT) AS max_data_length"
        ),
        (
            f"       CAST(ROUND({prefix}_avg_data_length, 6) AS DOUBLE) AS avg_data_length"
            if string
            else "       CAST(NULL AS DOUBLE) AS avg_data_length"
        ),
        f"       {_percentage(non_null, 'row_count')} AS percent_populated",
        (
            f"       {_percentage(f'({non_null} - {distinct_value})', non_null)} "
            "AS percent_duplicates"
            if distinct_value is not None
            else "       CAST(NULL AS DOUBLE) AS percent_duplicates"
        ),
        f"       {_percentage(null_count, 'row_count')} AS percent_null",
        (
            f"       {_percentage(blank_value, non_null)} AS percent_blank"
            if blank_value is not None
            else "       CAST(NULL AS DOUBLE) AS percent_blank"
        ),
        (
            f"       {_percentage(distinct_value, non_null)} AS percent_distinct"
            if distinct_value is not None
            else "       CAST(NULL AS DOUBLE) AS percent_distinct"
        ),
    )
    return f"SELECT\n{',\n'.join(values)}\n  FROM summary"


def _percentage(numerator: str, denominator: str) -> str:
    return (
        "CAST(CASE WHEN "
        f"{denominator} = 0 THEN 0.0 ELSE ROUND(CAST(100 AS DOUBLE) * "
        f"({numerator}) / {denominator}, 4) END AS DOUBLE)"
    )


def _metric_support(data_type: str) -> tuple[bool, bool]:
    normalized = _normalized_type(data_type)
    string = _STRING_TYPE.fullmatch(normalized) is not None
    return string, string or _DISTINCT_TYPE.fullmatch(normalized) is not None


def _normalized_type(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().upper())


def _quote_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"
