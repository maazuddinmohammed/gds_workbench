"""Bounded Databricks SQL Connector adapter."""

# The connector does not publish complete type information.
# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from math import isfinite
from types import TracebackType
from typing import Any, Protocol, Self, cast

from pydantic import JsonValue

from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.databricks_sql import ValidatedDatabricksSql
from gds_etl_workbench.domain.errors import (
    DatabricksConnectionFailedError,
    DatabricksResultTooLargeError,
    DatabricksStatementFailedError,
)

# The connector logs host and HTTP path at debug level. Connection values must
# never enter application logs, regardless of deployment logging configuration.
_connector_logger = logging.getLogger("databricks.sql")
_connector_logger.handlers.clear()
_connector_logger.setLevel(logging.CRITICAL + 1)
_connector_logger.propagate = False
_connector_logger.disabled = True

from databricks import sql as databricks_sql  # noqa: E402
from databricks.sql.exc import Error as DatabricksError  # noqa: E402

_MAX_COLUMNS = 500
_MAX_ROWS = 50
_MAX_CELL_CHARACTERS = 20_000
_MAX_COLLECTION_ITEMS = 1_000
_MAX_RESULT_BYTES = 1_000_000


@dataclass(frozen=True, slots=True)
class DatabricksSqlExecutionResult:
    columns: tuple[str, ...]
    rows: tuple[tuple[JsonValue, ...], ...]
    rows_truncated: bool
    cells_truncated: bool


class DatabricksSqlExecutor(Protocol):
    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        batch: ValidatedDatabricksSql,
        max_rows: int,
        timeout_seconds: int,
    ) -> DatabricksSqlExecutionResult: ...


class _Cursor(Protocol):
    @property
    def description(self) -> Sequence[Sequence[Any]] | None: ...

    def execute(self, operation: str) -> object: ...

    def fetchmany(self, size: int) -> Sequence[Sequence[Any]]: ...

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


class ConnectorDatabricksSqlExecutor:
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
        batch: ValidatedDatabricksSql,
        max_rows: int,
        timeout_seconds: int,
    ) -> DatabricksSqlExecutionResult:
        return await asyncio.to_thread(
            self._execute_sync,
            connection,
            batch,
            max_rows,
            timeout_seconds,
        )

    def _execute_sync(
        self,
        connection_values: DatabricksSqlConnection,
        batch: ValidatedDatabricksSql,
        max_rows: int,
        timeout_seconds: int,
    ) -> DatabricksSqlExecutionResult:
        if not 1 <= max_rows <= _MAX_ROWS:
            raise DatabricksResultTooLargeError()
        try:
            connection = self._connect(
                server_hostname=connection_values.server_hostname,
                http_path=connection_values.http_path,
                access_token=connection_values.access_token,
                session_configuration={"STATEMENT_TIMEOUT": str(timeout_seconds)},
                user_agent_entry="gds-etl-workbench",
                use_cloud_fetch=False,
                enable_telemetry=0,
                _socket_timeout=timeout_seconds,
                _retry_stop_after_attempts_count=3,
                _use_arrow_native_complex_types=False,
            )
        except DatabricksError:
            raise DatabricksConnectionFailedError() from None

        statement_index = 0
        try:
            with connection, connection.cursor() as cursor:
                for current_statement_index, statement in enumerate(
                    batch.statements,
                    start=1,
                ):
                    statement_index = current_statement_index
                    cursor.execute(statement.sql)

                description = cursor.description
                if description is None:
                    return DatabricksSqlExecutionResult(
                        columns=(),
                        rows=(),
                        rows_truncated=False,
                        cells_truncated=False,
                    )
                if len(description) > _MAX_COLUMNS:
                    raise DatabricksResultTooLargeError()

                columns: list[str] = []
                cells_truncated = False
                for column in description:
                    if not column:
                        raise DatabricksResultTooLargeError()
                    name, truncated = _bounded_string(str(column[0]))
                    columns.append(name)
                    cells_truncated = cells_truncated or truncated

                fetched_rows = cursor.fetchmany(max_rows + 1)
                rows: list[tuple[JsonValue, ...]] = []
                for source_row in fetched_rows[:max_rows]:
                    if len(source_row) != len(columns):
                        raise DatabricksResultTooLargeError()
                    converted_row: list[JsonValue] = []
                    for value in source_row:
                        converted, truncated = _json_value(value)
                        converted_row.append(converted)
                        cells_truncated = cells_truncated or truncated
                    rows.append(tuple(converted_row))

                encoded_size = len(
                    json.dumps(
                        {"columns": columns, "rows": rows},
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                if encoded_size > _MAX_RESULT_BYTES:
                    raise DatabricksResultTooLargeError()

                return DatabricksSqlExecutionResult(
                    columns=tuple(columns),
                    rows=tuple(rows),
                    rows_truncated=len(fetched_rows) > max_rows,
                    cells_truncated=cells_truncated,
                )
        except DatabricksError:
            if statement_index == 0:
                raise DatabricksConnectionFailedError() from None
            raise DatabricksStatementFailedError(statement_index) from None


def _bounded_string(value: str) -> tuple[str, bool]:
    if len(value) <= _MAX_CELL_CHARACTERS:
        return value, False
    return value[:_MAX_CELL_CHARACTERS], True


def _json_value(value: Any) -> tuple[JsonValue, bool]:
    if value is None or isinstance(value, (bool, int)):
        return value, False
    if isinstance(value, float):
        return (value if isfinite(value) else str(value)), False
    if isinstance(value, str):
        return _bounded_string(value)
    if isinstance(value, Decimal):
        return str(value), False
    if isinstance(value, (datetime, date, time)):
        return value.isoformat(), False
    if isinstance(value, bytes):
        encoded = base64.b64encode(value).decode("ascii")
        bounded, truncated = _bounded_string(encoded)
        return f"base64:{bounded}", truncated
    if isinstance(value, Mapping):
        mapping_value = cast(Mapping[object, object], value)
        converted_mapping: dict[str, JsonValue] = {}
        truncated = len(mapping_value) > _MAX_COLLECTION_ITEMS
        for index, (key, item) in enumerate(mapping_value.items()):
            if index >= _MAX_COLLECTION_ITEMS:
                break
            converted_key, key_truncated = _bounded_string(str(key))
            converted_item, item_truncated = _json_value(item)
            converted_mapping[converted_key] = converted_item
            truncated = truncated or key_truncated or item_truncated
        return converted_mapping, truncated
    if isinstance(value, Sequence):
        sequence_value = cast(Sequence[object], value)
        converted_items: list[JsonValue] = []
        truncated = len(sequence_value) > _MAX_COLLECTION_ITEMS
        for item in sequence_value[:_MAX_COLLECTION_ITEMS]:
            converted_item, item_truncated = _json_value(item)
            converted_items.append(converted_item)
            truncated = truncated or item_truncated
        return converted_items, truncated

    converted_text, truncated = _bounded_string(str(value))
    return converted_text, truncated
