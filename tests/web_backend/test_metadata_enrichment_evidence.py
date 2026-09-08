"""Synthetic connector evidence tests; no Databricks or physical rows are read."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

import pytest
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.databricks_sql import ValidatedDatabricksSql
from gds_etl_workbench.infrastructure.databricks_sql import DatabricksSqlExecutionResult
from gds_workbench_api.features.metadata_enrichment.contracts import EnrichmentObject
from gds_workbench_api.features.metadata_enrichment.evidence import (
    MetadataEvidenceReader,
    TypeEvidence,
)
from pydantic import JsonValue


def _object(
    *, columns: int = 1, registered: str = "STRING", source: bool = True
) -> EnrichmentObject:
    attributes: list[dict[str, Any]] = []
    for index in range(columns):
        name = f"column_{index:03}"
        source_evidence = {
            "object_id": 10,
            "object_name": "source_records",
            "object_schema": "source",
            "object_description": None,
            "source_tenant_id": 7,
            "system_code": "SOURCE",
            "attribute_id": 100 + index,
            "attribute_name": name,
            "attribute_data_type": registered,
            "attribute_inferred_data_type": None,
            "attribute_description": None,
            "is_active": True,
            "is_masking_required": False,
            "relation": {
                "connection_id": 1,
                "catalog": "source_catalog",
                "schema": "source",
                "table": "records",
            },
            "relation_column": name,
        }
        attributes.append(
            {
                "attribute_id": 1_000 + index,
                "attribute_name": name,
                "attribute_data_type": "STRING",
                "attribute_inferred_data_type": None,
                "attribute_description": None,
                "attribute_ordinal_position": index + 1,
                "is_active": True,
                "is_locked": False,
                "is_masking_required": False,
                "relation_column": name,
                "source_candidate_count": 1 if source else 2,
                "source": source_evidence if source else None,
            }
        )
    return EnrichmentObject.model_validate(
        {
            "object_id": 20,
            "object_name": "bronze_records",
            "object_schema": "bronze",
            "object_description": None,
            "is_active": True,
            "is_locked": False,
            "zone_code": "bronze",
            "source_tenant_id": 7,
            "tenant_id": 9,
            "tenant_catalog": "bronze_catalog",
            "system_code": "GDS",
            "connection_id": 1,
            "relation": {
                "connection_id": 1,
                "catalog": "bronze_catalog",
                "schema": "bronze",
                "table": "records",
            },
            "attributes": attributes,
        },
        strict=False,
    )


@dataclass
class _Executor:
    schema_types: dict[str, str | Exception]
    samples: dict[str, tuple[JsonValue, ...]] = field(
        default_factory=lambda: dict[str, tuple[JsonValue, ...]](), repr=False
    )
    transform: (
        Callable[[str, DatabricksSqlExecutionResult], DatabricksSqlExecutionResult] | None
    ) = None
    calls: list[tuple[str, str, tuple[str, ...]]] = field(
        default_factory=lambda: list[tuple[str, str, tuple[str, ...]]]()
    )

    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        batch: ValidatedDatabricksSql,
        max_rows: int,
        timeout_seconds: int,
    ) -> DatabricksSqlExecutionResult:
        assert max_rows == 50 and timeout_seconds == 30
        assert len(batch.statements) == 1 and batch.final_returns_rows
        sql = batch.statements[0].sql
        catalog = "source_catalog" if "`source_catalog`" in sql else "bronze_catalog"
        schema_query = ".information_schema.columns" in sql
        kind = "schema" if schema_query else "sample"
        columns = (
            tuple(re.findall(r"'([^']*)'", sql.split(" IN (", 1)[1]))
            if schema_query
            else tuple(re.findall(r"`([^`]+)` AS c\d+", sql))
        )
        self.calls.append((kind, catalog, columns))
        if schema_query:
            data_type = self.schema_types[catalog]
            if isinstance(data_type, Exception):
                raise data_type
            result = DatabricksSqlExecutionResult(
                columns=("column_name", "full_data_type", "comment"),
                rows=tuple((column, data_type, "Synthetic schema comment.") for column in columns),
                rows_truncated=False,
                cells_truncated=False,
            )
        else:
            result = DatabricksSqlExecutionResult(
                columns=tuple(f"c{index}" for index in range(len(columns))),
                rows=tuple(
                    tuple(value for _ in columns) for value in self.samples.get(catalog, ())
                ),
                rows_truncated=False,
                cells_truncated=False,
            )
        return self.transform(kind, result) if self.transform else result


def _reader(executor: _Executor | None) -> MetadataEvidenceReader:
    async def connection_loader(connection_id: int) -> DatabricksSqlConnection:
        assert connection_id == 1
        return DatabricksSqlConnection("synthetic.invalid", "/synthetic", "synthetic-test-value")

    return MetadataEvidenceReader(executor=executor, connection_loader=connection_loader)


@pytest.mark.asyncio
@pytest.mark.parametrize("registered", ["STRING", "BIGINT"])
async def test_actual_source_schema_overrides_registered_metadata(
    registered: str,
) -> None:
    item = _object(registered=registered)
    executor = _Executor({"source_catalog": "DECIMAL(18,2)", "bronze_catalog": "STRING"})
    reader = _reader(executor)
    await reader.collect((item,))
    assert reader.infer_type(item, item.attributes[0]) == TypeEvidence(
        "DECIMAL(18,2)", "source_schema"
    )
    assert all(kind == "schema" for kind, _, _ in executor.calls)
    source = reader.source_schema(item.attributes[0])
    assert source is not None and source.comment == "Synthetic schema comment."


@pytest.mark.asyncio
async def test_source_string_samples_override_conflicting_registered_numeric() -> None:
    item = _object(registered="BIGINT")
    executor = _Executor(
        {"source_catalog": "STRING", "bronze_catalog": "STRING"},
        {"source_catalog": ("1.25", "20.50"), "bronze_catalog": ("unusable",)},
    )
    reader = _reader(executor)
    await reader.collect((item,))
    assert reader.infer_type(item, item.attributes[0]) == TypeEvidence(
        "DECIMAL(4,2)", "source_sample", 2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("connector_available", [True, False])
async def test_unavailable_source_uses_registered_type_without_sampling(
    connector_available: bool,
) -> None:
    item = _object(registered="integer")
    executor = _Executor(
        {
            "source_catalog": RuntimeError("Synthetic failure"),
            "bronze_catalog": "STRING",
        }
    )
    reader = _reader(executor if connector_available else None)
    await reader.collect((item,))
    assert reader.infer_type(item, item.attributes[0]) == TypeEvidence("INT", "registered_type")
    assert all(kind == "schema" for kind, _, _ in executor.calls)


@pytest.mark.asyncio
async def test_leading_zero_source_identifiers_remain_string() -> None:
    item = _object()
    executor = _Executor(
        {"source_catalog": "STRING", "bronze_catalog": "BIGINT"},
        {"source_catalog": ("00123", "04567")},
    )
    reader = _reader(executor)
    await reader.collect((item,))
    assert reader.infer_type(item, item.attributes[0]) == TypeEvidence("STRING", "source_sample", 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("mask_location", ["target", "source"])
async def test_masked_attributes_never_enter_sample_queries(mask_location: str) -> None:
    item = _object()
    attribute = item.attributes[0]
    if mask_location == "source":
        assert attribute.source is not None
        attribute = attribute.model_copy(
            update={"source": attribute.source.model_copy(update={"is_masking_required": True})}
        )
    else:
        attribute = attribute.model_copy(update={"is_masking_required": True})
    item = item.model_copy(update={"attributes": (attribute,)})
    executor = _Executor({"source_catalog": "STRING", "bronze_catalog": "STRING"})
    reader = _reader(executor)
    await reader.collect((item,))
    assert all(kind == "schema" for kind, _, _ in executor.calls)
    assert reader.infer_type(item, attribute) == TypeEvidence("STRING", "source_schema")


@pytest.mark.asyncio
async def test_masked_target_does_not_consume_cached_unmasked_source_samples() -> None:
    unmasked = _object()
    masked_attribute = unmasked.attributes[0].model_copy(
        update={"attribute_id": 2_000, "is_masking_required": True}
    )
    masked = unmasked.model_copy(update={"object_id": 21, "attributes": (masked_attribute,)})
    executor = _Executor(
        {"source_catalog": "STRING", "bronze_catalog": "STRING"},
        {"source_catalog": ("10", "20"), "bronze_catalog": ("10", "20")},
    )
    reader = _reader(executor)
    await reader.collect((unmasked, masked))
    assert reader.infer_type(unmasked, unmasked.attributes[0]) == TypeEvidence(
        "BIGINT", "source_sample", 2
    )
    assert reader.infer_type(masked, masked_attribute) == TypeEvidence("STRING", "source_schema")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bronze_type,expected",
    [
        ("DATE", TypeEvidence("DATE", "bronze_schema")),
        ("STRING", TypeEvidence("BIGINT", "bronze_sample", 2)),
    ],
)
async def test_ambiguous_source_falls_back_to_bronze(
    bronze_type: str, expected: TypeEvidence
) -> None:
    item = _object(source=False)
    executor = _Executor({"bronze_catalog": bronze_type}, {"bronze_catalog": ("12", "34")})
    reader = _reader(executor)
    await reader.collect((item,))
    assert reader.source_schema(item.attributes[0]) is None
    assert reader.infer_type(item, item.attributes[0]) == expected
    assert all(catalog == "bronze_catalog" for _, catalog, _ in executor.calls)


@pytest.mark.asyncio
async def test_wide_object_uses_bounded_complete_schema_and_sample_batches() -> None:
    item = _object(columns=101, source=False)
    executor = _Executor({"bronze_catalog": "STRING"}, {"bronze_catalog": ("1", "2")})
    reader = _reader(executor)
    await reader.collect((item,))
    schema_batches = [columns for kind, _, columns in executor.calls if kind == "schema"]
    sample_batches = [columns for kind, _, columns in executor.calls if kind == "sample"]
    assert list(map(len, schema_batches)) == [50, 50, 1]
    assert list(map(len, sample_batches)) == [25, 25, 25, 25, 1]
    expected = {attribute.attribute_name for attribute in item.attributes}
    assert {column for batch in schema_batches for column in batch} == expected
    assert {column for batch in sample_batches for column in batch} == expected
    assert all(
        reader.infer_type(item, attribute) == TypeEvidence("BIGINT", "bronze_sample", 2)
        for attribute in item.attributes
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("truncation", ["schema_rows", "sample_cells"])
async def test_truncated_evidence_cannot_author_a_narrower_type(
    truncation: str,
) -> None:
    def truncate(kind: str, result: DatabricksSqlExecutionResult) -> DatabricksSqlExecutionResult:
        if truncation == "schema_rows" and kind == "schema":
            return replace(result, rows_truncated=True)
        if truncation == "sample_cells" and kind == "sample":
            return replace(result, cells_truncated=True)
        return result

    item = _object(source=False)
    executor = _Executor(
        {"bronze_catalog": "BIGINT" if truncation == "schema_rows" else "STRING"},
        {"bronze_catalog": ("123", "456") if truncation == "sample_cells" else ()},
        transform=truncate,
    )
    reader = _reader(executor)
    await reader.collect((item,))
    evidence = reader.infer_type(item, item.attributes[0])
    assert evidence.data_type in {None, "STRING"}


@pytest.mark.asyncio
async def test_truncated_schema_comment_is_not_used_as_a_complete_description() -> None:
    def truncate_comment(
        kind: str, result: DatabricksSqlExecutionResult
    ) -> DatabricksSqlExecutionResult:
        return replace(result, cells_truncated=True) if kind == "schema" else result

    item = _object()
    executor = _Executor(
        {"source_catalog": "BIGINT", "bronze_catalog": "STRING"},
        transform=truncate_comment,
    )
    reader = _reader(executor)
    await reader.collect((item,))
    schema = reader.source_schema(item.attributes[0])
    assert schema is not None and schema.comment is None
    # The bounded primitive type remains complete; the comment is omitted.
    assert reader.infer_type(item, item.attributes[0]) == TypeEvidence("BIGINT", "source_schema")


@pytest.mark.asyncio
async def test_legitimate_multiline_source_comment_is_retained_as_schema_evidence() -> None:
    comment = "Customer identifier.\nPreserve leading zeros.\tExternal reference."

    def multiline(kind: str, result: DatabricksSqlExecutionResult) -> DatabricksSqlExecutionResult:
        if kind == "schema":
            return replace(result, rows=tuple((row[0], row[1], comment) for row in result.rows))
        return result

    item = _object()
    reader = _reader(
        _Executor(
            {"source_catalog": "STRING", "bronze_catalog": "STRING"},
            transform=multiline,
        )
    )
    await reader.collect((item,))
    schema = reader.source_schema(item.attributes[0])
    assert schema is not None and schema.comment == comment
    assert comment not in repr(schema)


@pytest.mark.asyncio
async def test_raw_samples_are_not_retained_in_reader_evidence() -> None:
    sample = "synthetic_private_sample_avoid_retention"
    item = _object()
    executor = _Executor(
        {"source_catalog": "STRING", "bronze_catalog": "STRING"},
        {"source_catalog": (sample,), "bronze_catalog": (sample,)},
    )
    reader = _reader(executor)
    await reader.collect((item,))
    assert reader.infer_type(item, item.attributes[0]) == TypeEvidence("STRING", "source_sample", 1)
    assert reader._samples and all(
        isinstance(value, TypeEvidence) for value in reader._samples.values()
    )
    assert sample not in repr(reader._samples)
    assert sample not in repr(reader._schemas)
    assert sample not in item.model_dump_json()
