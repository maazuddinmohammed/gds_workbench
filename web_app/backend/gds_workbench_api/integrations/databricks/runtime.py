"""Small runtime boundary for native and deterministic local Databricks execution."""

from dataclasses import dataclass
from typing import Literal

from gds_etl_workbench.domain.databricks import DatabricksSqlConnection

from gds_workbench_api.features.analysis.validation_execution import (
    AnalysisValidationEvidence,
    AnalysisValidationQuery,
    ConnectorAnalysisValidationExecutor,
)
from gds_workbench_api.features.analysis.validation_service import (
    AnalysisValidationQueryExecutor,
)
from gds_workbench_runtime.profiling.execution import (
    ConnectorProfilingExecutor,
    ProfileMetric,
    ProfileQuery,
    ProfilingExecutor,
)


class LocalFakeProfilingExecutor:
    """Return valid empty aggregates locally without opening a physical connection."""

    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        query: ProfileQuery,
        timeout_seconds: int,
    ) -> tuple[ProfileMetric, ...]:
        del connection, timeout_seconds
        return tuple(
            ProfileMetric(
                attribute_id=attribute_id,
                row_count=0,
                non_null_count=0,
                null_count=0,
                blank_count=0,
                distinct_count=0,
                min_data_length=None,
                max_data_length=None,
                avg_data_length=None,
                percent_populated=0,
                percent_duplicates=0,
                percent_null=0,
                percent_blank=0,
                percent_distinct=0,
            )
            for attribute_id in query.attribute_ids
        )


class LocalFakeAnalysisValidationExecutor:
    """Return deterministic inconclusive evidence without reading physical data."""

    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        query: AnalysisValidationQuery,
        timeout_seconds: int,
    ) -> AnalysisValidationEvidence:
        del connection, query, timeout_seconds
        return AnalysisValidationEvidence(
            validation_source_non_null_count=0,
            validation_source_distinct_count=0,
            validation_target_non_null_count=0,
            validation_target_distinct_count=0,
            validation_source_missing_target_count=0,
            validation_unused_target_count=0,
            validation_duplicate_target_key_count=0,
            validation_result="inconclusive",
        )


@dataclass(frozen=True, slots=True)
class DatabricksExecutionAdapters:
    profiling: ProfilingExecutor
    analysis_validation: AnalysisValidationQueryExecutor


def create_databricks_execution_adapters(
    mode: Literal["fake", "remote"],
) -> DatabricksExecutionAdapters:
    if mode == "fake":
        return DatabricksExecutionAdapters(
            profiling=LocalFakeProfilingExecutor(),
            analysis_validation=LocalFakeAnalysisValidationExecutor(),
        )
    return DatabricksExecutionAdapters(
        profiling=ConnectorProfilingExecutor(),
        analysis_validation=ConnectorAnalysisValidationExecutor(),
    )
