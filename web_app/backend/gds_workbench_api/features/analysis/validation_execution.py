# pyright: reportMissingTypeStubs=false

"""Fixed aggregate-only Databricks execution for Analysis validation."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
from types import TracebackType
from typing import Any, Literal, Protocol, Self, cast

from databricks import sql as databricks_sql
from databricks.sql.exc import Error as DatabricksError
from gds_etl_workbench.domain.errors import (
    DatabricksConnectionFailedError,
    DatabricksStatementFailedError,
    InvalidRequestError,
    WorkbenchError,
)
from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_MAX_RELATIONSHIPS = 50_000
_MAX_SQL_CHARACTERS = 100_000
_MAX_TIMEOUT_SECONDS = 3_600

_SCALAR_TYPE = re.compile(
    r"^(?:BOOLEAN|BYTE|TINYINT|SHORT|SMALLINT|INT|INTEGER|LONG|BIGINT|FLOAT|REAL|"
    r"DOUBLE|DATE|TIMESTAMP(?:_NTZ|_LTZ)?|STRING|VARCHAR\(\d+\)|CHAR\(\d+\)|"
    r"DECIMAL\(\d+,\d+\)|NUMERIC\(\d+,\d+\))$"
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

type AnalysisValidationResult = Literal[
    "supported",
    "inconclusive",
    "unsupported",
]


class AnalysisValidationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    validation_policy_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    max_parallel_queries: int = Field(gt=0, le=32)
    max_progress_events: int = Field(gt=0, le=100)
    statement_timeout_seconds: int = Field(gt=0, le=_MAX_TIMEOUT_SECONDS)
    max_relationships: int = Field(gt=0, le=_MAX_RELATIONSHIPS)

    @property
    def validation_policy_digest(self) -> str:
        document = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return sha256(document.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def load_default_analysis_validation_policy() -> AnalysisValidationPolicy:
    resource = files("gds_workbench_api").joinpath(
        "config",
        "analysis_validation.json",
    )
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("Analysis validation policy is unavailable.") from error
    return AnalysisValidationPolicy.model_validate(payload, strict=True)


class AnalysisValidationEndpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    relation_catalog: str = Field(min_length=1, max_length=255)
    relation_schema: str = Field(min_length=1, max_length=400)
    relation_object: str = Field(min_length=1, max_length=400)
    object_id: int = Field(gt=0)
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    attribute_data_type: str = Field(min_length=1, max_length=100)
    batch_attribute_name: str | None = Field(default=None, max_length=400)
    batch_attribute_data_type: str | None = Field(default=None, max_length=100)

    @field_validator(
        "relation_catalog",
        "relation_schema",
        "relation_object",
        "attribute_name",
        "attribute_data_type",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Analysis validation metadata must be nonblank")
        return value

    @field_validator("batch_attribute_name", "batch_attribute_data_type")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("Batch Attribute metadata must be nonblank")
        return value

    @model_validator(mode="after")
    def validate_batch_metadata(self) -> AnalysisValidationEndpoint:
        if (self.batch_attribute_name is None) != (self.batch_attribute_data_type is None):
            raise ValueError("Batch Attribute name and data type must be provided together")
        return self


class AnalysisValidationRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    analysis_result_id: int = Field(gt=0)
    relationship_kind: str = Field(min_length=1, max_length=100)
    relationship_confidence: Literal["low", "medium", "high"]
    relationship_basis: str = Field(min_length=1, max_length=8_000)
    analysis_result_status: Literal["active", "needs_review"]
    analysis_result_is_locked: bool
    gds_connection_id: int = Field(gt=0)
    source_context_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    from_endpoint: AnalysisValidationEndpoint
    to_endpoint: AnalysisValidationEndpoint

    @field_validator("relationship_kind", "relationship_basis")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Analysis relationship text must be nonblank")
        return value

    @model_validator(mode="after")
    def validate_endpoints(self) -> AnalysisValidationRelationship:
        if self.from_endpoint.attribute_id == self.to_endpoint.attribute_id:
            raise ValueError("Analysis validation endpoints must be distinct")
        return self


class AnalysisValidationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    validation_source_non_null_count: int = Field(ge=0)
    validation_source_distinct_count: int = Field(ge=0)
    validation_target_non_null_count: int = Field(ge=0)
    validation_target_distinct_count: int = Field(ge=0)
    validation_source_missing_target_count: int = Field(ge=0)
    validation_unused_target_count: int = Field(ge=0)
    validation_duplicate_target_key_count: int = Field(ge=0)
    validation_result: AnalysisValidationResult

    @model_validator(mode="after")
    def validate_evidence(self) -> AnalysisValidationEvidence:
        if self.validation_source_distinct_count > self.validation_source_non_null_count:
            raise ValueError("Source validation counts do not reconcile")
        if (self.validation_source_non_null_count == 0) != (
            self.validation_source_distinct_count == 0
        ):
            raise ValueError("Source validation counts do not reconcile")
        if self.validation_target_distinct_count > self.validation_target_non_null_count:
            raise ValueError("Target validation counts do not reconcile")
        if (self.validation_target_non_null_count == 0) != (
            self.validation_target_distinct_count == 0
        ):
            raise ValueError("Target validation counts do not reconcile")
        if self.validation_source_missing_target_count > self.validation_source_distinct_count:
            raise ValueError("Missing-target count exceeds source distinct count")
        if self.validation_unused_target_count > self.validation_target_distinct_count:
            raise ValueError("Unused-target count exceeds target distinct count")
        expected_duplicate_count = (
            self.validation_target_non_null_count - self.validation_target_distinct_count
        )
        if self.validation_duplicate_target_key_count != expected_duplicate_count:
            raise ValueError("Duplicate-target count does not reconcile")

        expected_result: AnalysisValidationResult
        if self.validation_source_non_null_count == 0 or self.validation_target_non_null_count == 0:
            expected_result = "inconclusive"
        elif (
            self.validation_source_missing_target_count == 0
            and self.validation_duplicate_target_key_count == 0
        ):
            expected_result = "supported"
        else:
            expected_result = "unsupported"
        if self.validation_result != expected_result:
            raise ValueError("Analysis validation result does not match its evidence")
        return self


@dataclass(frozen=True, slots=True)
class AnalysisValidationQuery:
    analysis_result_id: int
    sql: str
    parameters: tuple[str, ...]


class AnalysisValidationResultInvalidError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="analysis_validation_result_invalid",
            message="Databricks returned invalid Analysis validation evidence.",
        )


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


class ConnectorAnalysisValidationExecutor:
    """Execute one fixed query and accept exactly one aggregate result row."""

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
        query: AnalysisValidationQuery,
        timeout_seconds: int,
    ) -> AnalysisValidationEvidence:
        if not 1 <= timeout_seconds <= _MAX_TIMEOUT_SECONDS:
            raise InvalidRequestError(
                "Analysis validation timeout must be between 1 and 3600 seconds."
            )
        return await asyncio.to_thread(
            self._execute_sync,
            connection,
            query,
            timeout_seconds,
        )

    def _execute_sync(
        self,
        connection_values: DatabricksSqlConnection,
        query: AnalysisValidationQuery,
        timeout_seconds: int,
    ) -> AnalysisValidationEvidence:
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
                    raise AnalysisValidationResultInvalidError()
                columns = tuple(str(column[0]) for column in description if column)
                if columns != _RESULT_COLUMNS or len(description) != len(_RESULT_COLUMNS):
                    raise AnalysisValidationResultInvalidError()
                rows = cursor.fetchmany(2)
        except DatabricksError:
            raise DatabricksStatementFailedError(1) from None

        if len(rows) != 1 or len(rows[0]) != len(_RESULT_COLUMNS):
            raise AnalysisValidationResultInvalidError()
        try:
            return AnalysisValidationEvidence.model_validate(
                dict(zip(_RESULT_COLUMNS, rows[0], strict=True)),
                strict=True,
            )
        except (TypeError, ValidationError):
            raise AnalysisValidationResultInvalidError() from None


def build_analysis_validation_query(
    relationship: AnalysisValidationRelationship,
    *,
    requested_batch_id: str | None,
) -> AnalysisValidationQuery:
    """Build one aggregate-only query for a registered relationship."""
    source_type = _validated_scalar_type(
        relationship.from_endpoint.attribute_data_type,
        label="Analysis Attribute",
    )
    target_type = _validated_scalar_type(
        relationship.to_endpoint.attribute_data_type,
        label="Analysis Attribute",
    )
    if source_type != target_type:
        raise InvalidRequestError(
            "Analysis validation requires matching registered Attribute data types."
        )
    if requested_batch_id is not None and (
        not requested_batch_id.strip()
        or "\x00" in requested_batch_id
        or len(requested_batch_id.encode("utf-8")) > 500
    ):
        raise InvalidRequestError("Analysis validation Batch ID is invalid.")

    source_relation = _qualified_relation(relationship.from_endpoint)
    target_relation = _qualified_relation(relationship.to_endpoint)
    source_attribute = _quote_identifier(relationship.from_endpoint.attribute_name)
    target_attribute = _quote_identifier(relationship.to_endpoint.attribute_name)
    source_batch = _batch_predicate(
        relationship.from_endpoint,
        requested_batch_id,
    )
    target_batch = _batch_predicate(
        relationship.to_endpoint,
        requested_batch_id,
    )

    sql = _build_query_sql(
        source_relation=source_relation,
        source_attribute=source_attribute,
        source_batch=source_batch,
        target_relation=target_relation,
        target_attribute=target_attribute,
        target_batch=target_batch,
    )
    if len(sql) > _MAX_SQL_CHARACTERS:
        raise InvalidRequestError("Generated Analysis validation SQL is too large.")
    parameters = tuple(
        requested_batch_id
        for batch in (source_batch, target_batch)
        if batch is not None and requested_batch_id is not None
    )
    return AnalysisValidationQuery(
        analysis_result_id=relationship.analysis_result_id,
        sql=sql,
        parameters=parameters,
    )


def _build_query_sql(
    *,
    source_relation: str,
    source_attribute: str,
    source_batch: str | None,
    target_relation: str,
    target_attribute: str,
    target_batch: str | None,
) -> str:
    source_filter = "" if source_batch is None else f"\n   AND {source_batch}"
    target_filter = "" if target_batch is None else f"\n   AND {target_batch}"
    return (
        "WITH source_values AS (\n"
        f"SELECT {source_attribute} AS comparison_value\n"
        f"  FROM {source_relation}\n"
        f" WHERE {source_attribute} IS NOT NULL{source_filter}\n"
        "),\n"
        "target_values AS (\n"
        f"SELECT {target_attribute} AS comparison_value\n"
        f"  FROM {target_relation}\n"
        f" WHERE {target_attribute} IS NOT NULL{target_filter}\n"
        "),\n"
        "source_value_counts AS (\n"
        "SELECT comparison_value, COUNT(*) AS value_count\n"
        "  FROM source_values\n"
        " GROUP BY comparison_value\n"
        "),\n"
        "target_value_counts AS (\n"
        "SELECT comparison_value, COUNT(*) AS value_count\n"
        "  FROM target_values\n"
        " GROUP BY comparison_value\n"
        "),\n"
        "source_summary AS (\n"
        "SELECT CAST(COALESCE(SUM(value_count), 0) AS BIGINT) AS non_null_count,\n"
        "       CAST(COUNT(*) AS BIGINT) AS distinct_count\n"
        "  FROM source_value_counts\n"
        "),\n"
        "target_summary AS (\n"
        "SELECT CAST(COALESCE(SUM(value_count), 0) AS BIGINT) AS non_null_count,\n"
        "       CAST(COUNT(*) AS BIGINT) AS distinct_count\n"
        "  FROM target_value_counts\n"
        "),\n"
        "missing_target AS (\n"
        "SELECT CAST(COUNT(*) AS BIGINT) AS missing_count\n"
        "  FROM source_value_counts AS source\n"
        "  LEFT ANTI JOIN target_value_counts AS target\n"
        "    ON source.comparison_value = target.comparison_value\n"
        "),\n"
        "duplicate_target AS (\n"
        "SELECT CAST(COALESCE(SUM(value_count - 1), 0) AS BIGINT) AS duplicate_count\n"
        "  FROM target_value_counts\n"
        "),\n"
        "unused_target AS (\n"
        "SELECT CAST(COUNT(*) AS BIGINT) AS unused_count\n"
        "  FROM target_value_counts AS target\n"
        "  LEFT ANTI JOIN source_value_counts AS source\n"
        "    ON target.comparison_value = source.comparison_value\n"
        ")\n"
        "SELECT source_summary.non_null_count AS validation_source_non_null_count,\n"
        "       source_summary.distinct_count AS validation_source_distinct_count,\n"
        "       target_summary.non_null_count AS validation_target_non_null_count,\n"
        "       target_summary.distinct_count AS validation_target_distinct_count,\n"
        "       missing_target.missing_count AS validation_source_missing_target_count,\n"
        "       unused_target.unused_count AS validation_unused_target_count,\n"
        "       duplicate_target.duplicate_count AS validation_duplicate_target_key_count,\n"
        "       CASE\n"
        "           WHEN source_summary.non_null_count = 0\n"
        "             OR target_summary.non_null_count = 0 THEN 'inconclusive'\n"
        "           WHEN missing_target.missing_count = 0\n"
        "            AND duplicate_target.duplicate_count = 0 THEN 'supported'\n"
        "           ELSE 'unsupported'\n"
        "       END AS validation_result\n"
        "  FROM source_summary\n"
        " CROSS JOIN target_summary\n"
        " CROSS JOIN missing_target\n"
        " CROSS JOIN duplicate_target\n"
        " CROSS JOIN unused_target"
    )


def _qualified_relation(endpoint: AnalysisValidationEndpoint) -> str:
    return ".".join(
        _quote_identifier(value)
        for value in (
            endpoint.relation_catalog,
            endpoint.relation_schema,
            endpoint.relation_object,
        )
    )


def _batch_predicate(
    endpoint: AnalysisValidationEndpoint,
    requested_batch_id: str | None,
) -> str | None:
    if requested_batch_id is None or endpoint.batch_attribute_name is None:
        return None
    data_type = _validated_scalar_type(
        cast(str, endpoint.batch_attribute_data_type),
        label="Batch Attribute",
    )
    return f"{_quote_identifier(endpoint.batch_attribute_name)} = CAST(? AS {data_type})"


def _validated_scalar_type(value: str, *, label: str) -> str:
    normalized = re.sub(r"\s+", "", value.strip().upper())
    if _SCALAR_TYPE.fullmatch(normalized) is None:
        raise InvalidRequestError(f"{label} data type must be a supported scalar type.")
    return normalized


def _quote_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"
