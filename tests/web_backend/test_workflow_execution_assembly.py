from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.features.workflows.execution.assembly import (
    create_workflow_runtime_services,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentRuntimeConfiguration,
)
from gds_workbench_api.integrations.databricks import (
    create_databricks_execution_adapters,
)


class AssemblyDatabase:
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]:
        del isolation
        raise AssertionError("Assembly must not open a transaction")

    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]:
        del isolation
        raise AssertionError("Assembly must not open a transaction")


def test_workflow_runtime_services_share_one_executor_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, dict[str, object]] = {}
    shared_agent_executor = object()

    def capture(name: str) -> Callable[..., object]:
        def create(**kwargs: object) -> object:
            captured[name] = kwargs
            return object()

        return create

    def create_agent_executor(**_kwargs: object) -> object:
        return shared_agent_executor

    monkeypatch.setattr(
        "gds_workbench_api.features.workflows.execution.assembly.create_agent_execution_router",
        create_agent_executor,
    )
    for executor_name in (
        "DatabaseAnalysisInferenceExecutor",
        "DatabaseConceptualExecutor",
        "DatabaseLogicalExecutor",
        "DatabaseDimensionalExecutor",
        "DatabaseMappingExecutor",
        "DatabaseCodeGenerationExecutor",
    ):
        monkeypatch.setattr(
            f"gds_workbench_api.features.workflows.execution.assembly.{executor_name}",
            capture(executor_name),
        )

    services = create_workflow_runtime_services(
        database=AssemblyDatabase(),
        authorizer=AuthorizationService(),
        agent_runtime=AgentRuntimeConfiguration.from_environment({}, production=False),
        agent_capability_registry=load_default_agent_capabilities(),
        databricks_environment_code="TEST",
        databricks_execution=create_databricks_execution_adapters("fake"),
    )

    authoring = tuple(
        captured[name]
        for name in (
            "DatabaseAnalysisInferenceExecutor",
            "DatabaseConceptualExecutor",
            "DatabaseLogicalExecutor",
            "DatabaseDimensionalExecutor",
            "DatabaseMappingExecutor",
        )
    )
    for dependency in ("agent_executor", "handoff", "no_op", "lifecycle"):
        expected = authoring[0][dependency]
        assert all(arguments[dependency] is expected for arguments in authoring)
    assert (
        captured["DatabaseCodeGenerationExecutor"]["agent_executor"]
        is shared_agent_executor
    )
    assert (
        captured["DatabaseCodeGenerationExecutor"]["lifecycle"]
        is authoring[0]["lifecycle"]
    )

    execution = services.execution_services()
    assert execution.profiling is services.profiling
    assert execution.analysis_inference is services.analysis_inference
    assert execution.analysis_validation is services.analysis_validation
    assert execution.conceptual is services.conceptual
    assert execution.logical is services.logical
    assert execution.dimensional is services.dimensional
    assert execution.mapping is services.mapping
    assert execution.code_generation is services.code_generation
