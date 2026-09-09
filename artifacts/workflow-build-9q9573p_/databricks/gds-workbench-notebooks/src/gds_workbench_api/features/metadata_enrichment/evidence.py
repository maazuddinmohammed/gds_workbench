"""Bounded physical evidence. Only inferred types and schema comments leave here."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.databricks_sql import validate_databricks_sql
from gds_etl_workbench.infrastructure.databricks_sql import DatabricksSqlExecutor

from .contracts import EnrichmentAttribute, EnrichmentObject, EvidenceMethod, PhysicalRelation
from .inference import infer_sample_data_type, normalize_data_type


@dataclass(frozen=True, slots=True)
class TypeEvidence:
    data_type: str | None
    method: EvidenceMethod = "none"
    sample_count: int = 0


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    data_type: str | None
    comment: str | None = field(repr=False)


class MetadataEvidenceReader:
    def __init__(
        self,
        *,
        executor: DatabricksSqlExecutor | None,
        connection_loader: Callable[[int], Awaitable[DatabricksSqlConnection | None]],
    ) -> None:
        self._executor = executor
        self._connection_loader = connection_loader
        self._connections: dict[int, DatabricksSqlConnection | None] = {}
        self._schemas: dict[tuple[PhysicalRelation, str], ColumnSchema] = {}
        self._samples: dict[tuple[PhysicalRelation, str], TypeEvidence] = {}

    async def collect(self, objects: tuple[EnrichmentObject, ...]) -> None:
        if self._executor is None:
            return
        schema_columns: dict[PhysicalRelation, set[str]] = defaultdict(set)
        candidates: list[tuple[EnrichmentObject, EnrichmentAttribute]] = []
        for item in objects:
            if not item.is_active or item.is_locked:
                continue
            for attribute in item.attributes:
                if not attribute.is_active or attribute.is_locked:
                    continue
                if (
                    attribute.attribute_description or ""
                ).strip() and attribute.attribute_inferred_data_type:
                    continue
                source = attribute.source
                if source and source.is_active and source.relation and source.relation_column:
                    schema_columns[source.relation].add(source.relation_column)
                if item.relation and attribute.relation_column:
                    schema_columns[item.relation].add(attribute.relation_column)
                if not attribute.attribute_inferred_data_type:
                    candidates.append((item, attribute))

        for relation, selected in schema_columns.items():
            connection = await self._connection(relation.connection_id)
            if connection is None:
                continue
            columns = sorted(selected)
            for offset in range(0, len(columns), 50):
                batch_columns = columns[offset : offset + 50]
                names = ",".join(
                    "'" + value.lower().replace("'", "''") + "'" for value in batch_columns
                )
                schema = relation.schema_name.replace("'", "''")
                table = relation.table.replace("'", "''")
                sql = (
                    "SELECT column_name, full_data_type, comment FROM "
                    f"{_quote_identifier(relation.catalog)}.information_schema.columns "
                    f"WHERE lower(table_schema) = lower('{schema}') "
                    f"AND lower(table_name) = lower('{table}') "
                    f"AND lower(column_name) IN ({names}) LIMIT 50"
                )
                try:
                    result = await self._executor.execute(
                        connection=connection,
                        batch=validate_databricks_sql(sql),
                        max_rows=50,
                        timeout_seconds=30,
                    )
                    if result.rows_truncated:
                        continue
                    if tuple(name.casefold() for name in result.columns) != (
                        "column_name",
                        "full_data_type",
                        "comment",
                    ):
                        continue
                    requested = {value.casefold() for value in batch_columns}
                    for row in result.rows:
                        if (
                            len(row) != 3
                            or not isinstance(row[0], str)
                            or row[0].casefold() not in requested
                        ):
                            continue
                        self._schemas[(relation, row[0].casefold())] = ColumnSchema(
                            data_type=normalize_data_type(
                                row[1] if isinstance(row[1], str) else None
                            ),
                            comment=row[2]
                            if not result.cells_truncated
                            and isinstance(row[2], str)
                            and row[2].strip()
                            else None,
                        )
                except Exception:
                    # Connector details and schema/tool rows never enter diagnostics.
                    continue

        sample_columns: dict[PhysicalRelation, set[str]] = defaultdict(set)
        for item, attribute in candidates:
            source = attribute.source
            if attribute.is_masking_required or (source is not None and source.is_masking_required):
                continue
            source_schema = self.source_schema(attribute)
            if source_schema and source_schema.data_type not in {None, "STRING"}:
                continue
            if source_schema is None and self._registered_source_type(attribute) not in {
                None,
                "STRING",
            }:
                continue
            if source and source.is_active and source.relation and source.relation_column:
                sample_columns[source.relation].add(source.relation_column)
            if item.relation and attribute.relation_column:
                bronze_schema = self._schemas.get(
                    (item.relation, attribute.relation_column.casefold())
                )
                if not bronze_schema or bronze_schema.data_type in {None, "STRING"}:
                    sample_columns[item.relation].add(attribute.relation_column)

        for relation, selected in sample_columns.items():
            connection = await self._connection(relation.connection_id)
            if connection is None:
                continue
            columns = sorted(selected)
            for offset in range(0, len(columns), 25):
                batch_columns = columns[offset : offset + 25]
                projected = ",".join(
                    f"{_quote_identifier(column)} AS c{index}"
                    for index, column in enumerate(batch_columns)
                )
                qualified = ".".join(
                    _quote_identifier(value)
                    for value in (relation.catalog, relation.schema_name, relation.table)
                )
                try:
                    result = await self._executor.execute(
                        connection=connection,
                        batch=validate_databricks_sql(
                            f"SELECT {projected} FROM {qualified} LIMIT 50"
                        ),
                        max_rows=50,
                        timeout_seconds=30,
                    )
                    if (
                        result.cells_truncated
                        or len(result.rows) > 50
                        or any(len(row) != len(batch_columns) for row in result.rows)
                    ):
                        continue
                    if tuple(name.casefold() for name in result.columns) != tuple(
                        f"c{index}" for index in range(len(batch_columns))
                    ):
                        continue
                    for index, column in enumerate(batch_columns):
                        values = tuple(row[index] for row in result.rows)
                        self._samples[(relation, column.casefold())] = TypeEvidence(
                            data_type=infer_sample_data_type(values),
                            sample_count=len(values),
                        )
                    # Neither raw rows nor individual samples are retained in this reader.
                except Exception:
                    continue

    async def _connection(self, connection_id: int) -> DatabricksSqlConnection | None:
        if connection_id not in self._connections:
            # Authorization failures propagate. Only unavailable physical execution falls back.
            self._connections[connection_id] = await self._connection_loader(connection_id)
        return self._connections[connection_id]

    def source_schema(self, attribute: EnrichmentAttribute) -> ColumnSchema | None:
        source = attribute.source
        if (
            source is None
            or not source.is_active
            or not source.relation
            or not source.relation_column
        ):
            return None
        return self._schemas.get((source.relation, source.relation_column.casefold()))

    def _registered_source_type(self, attribute: EnrichmentAttribute) -> str | None:
        source = attribute.source
        if source is None or not source.is_active:
            return None
        return normalize_data_type(source.attribute_inferred_data_type) or normalize_data_type(
            source.attribute_data_type
        )

    def infer_type(self, item: EnrichmentObject, attribute: EnrichmentAttribute) -> TypeEvidence:
        source = attribute.source
        source_schema = self.source_schema(attribute)
        if source_schema and source_schema.data_type not in {None, "STRING"}:
            return TypeEvidence(source_schema.data_type, "source_schema")
        registered = self._registered_source_type(attribute)
        if source_schema is None and registered not in {None, "STRING"}:
            return TypeEvidence(registered, "registered_type")
        allow_samples = not attribute.is_masking_required and not (
            source and source.is_masking_required
        )
        if allow_samples and source and source.relation and source.relation_column:
            sampled = self._samples.get((source.relation, source.relation_column.casefold()))
            if sampled and sampled.data_type is not None:
                return TypeEvidence(sampled.data_type, "source_sample", sampled.sample_count)
        bronze_schema = None
        if item.relation and attribute.relation_column:
            key = (item.relation, attribute.relation_column.casefold())
            bronze_schema = self._schemas.get(key)
            if bronze_schema and bronze_schema.data_type not in {None, "STRING"}:
                return TypeEvidence(bronze_schema.data_type, "bronze_schema")
            sampled = self._samples.get(key) if allow_samples else None
            if sampled and sampled.data_type is not None:
                return TypeEvidence(sampled.data_type, "bronze_sample", sampled.sample_count)
        if source_schema and source_schema.data_type == "STRING":
            return TypeEvidence("STRING", "source_schema")
        if bronze_schema and bronze_schema.data_type == "STRING":
            return TypeEvidence("STRING", "bronze_schema")
        # Registered STRING is a storage representation, insufficient semantic evidence.
        return TypeEvidence(None)


def _quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"
