from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection

from gds_workbench_api.features.analysis.validation_execution import (
    AnalysisValidationQuery,
    ConnectorAnalysisValidationExecutor,
)
from gds_workbench_api.features.profiling.execution import (
    ConnectorProfilingExecutor,
    ProfileQuery,
)
from gds_workbench_api.integrations.databricks import (
    LocalFakeAnalysisValidationExecutor,
    LocalFakeProfilingExecutor,
    create_databricks_execution_adapters,
)


def _connection() -> DatabricksSqlConnection:
    return DatabricksSqlConnection(
        server_hostname="must-not-connect.invalid",
        http_path="/must-not-connect",
        access_token="must-not-leave-process",
    )


async def test_local_fake_databricks_adapters_return_valid_empty_evidence() -> None:
    profiling = LocalFakeProfilingExecutor()
    profiles = await profiling.execute(
        connection=_connection(),
        query=ProfileQuery(
            object_id=11,
            attribute_ids=(101, 102),
            sql="SELECT must_not_execute",
            parameters=(),
        ),
        timeout_seconds=30,
    )
    assert [profile.attribute_id for profile in profiles] == [101, 102]
    assert all(profile.row_count == 0 for profile in profiles)

    validation = LocalFakeAnalysisValidationExecutor()
    evidence = await validation.execute(
        connection=_connection(),
        query=AnalysisValidationQuery(
            analysis_result_id=12,
            sql="SELECT must_not_execute",
            parameters=(),
        ),
        timeout_seconds=30,
    )
    assert evidence.validation_result == "inconclusive"
    assert evidence.validation_source_non_null_count == 0


def test_databricks_adapter_factory_selects_only_explicit_mode() -> None:
    local = create_databricks_execution_adapters("fake")
    assert isinstance(local.profiling, LocalFakeProfilingExecutor)
    assert isinstance(
        local.analysis_validation,
        LocalFakeAnalysisValidationExecutor,
    )

    remote = create_databricks_execution_adapters("remote")
    assert isinstance(remote.profiling, ConnectorProfilingExecutor)
    assert isinstance(
        remote.analysis_validation,
        ConnectorAnalysisValidationExecutor,
    )
