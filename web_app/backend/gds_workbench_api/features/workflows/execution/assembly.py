"""Shared Workflow executor assembly for API and worker processes."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from gds_workbench_api.capabilities import AgentCapabilityRegistry
from gds_workbench_api.features.analysis import (
    AnalysisInferenceWorkflow,
    AnalysisValidationWorkflow,
    DatabaseAnalysisInferenceExecutor,
    DatabaseAnalysisValidationRepository,
)
from gds_workbench_api.features.code_generation import (
    CodeGenerationWorkflow,
    DatabaseCodeGenerationExecutor,
)
from gds_workbench_api.features.conceptual import (
    ConceptualWorkflow,
    DatabaseConceptualExecutor,
)
from gds_workbench_api.features.dimensional import (
    DatabaseDimensionalExecutor,
    DimensionalWorkflow,
)
from gds_workbench_api.features.logical import DatabaseLogicalExecutor, LogicalWorkflow
from gds_workbench_api.features.mapping import (
    DatabaseMappingExecutor,
    MappingReadinessService,
    MappingWorkflow,
    PostgresMappingRunContextRepository,
    PostgresMappingRunPlanRepository,
)
from gds_workbench_api.features.mapping.profile_registry import (
    MappingProfileRegistration,
    load_mapping_profile_registry,
)
from gds_workbench_api.features.profiling import DatabaseProfilingWorkflowRepository
from gds_workbench_api.features.qa import DatabaseQAExecutor, QAWorkflow
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRouter,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    DatabaseAuthoringNoOpService,
)
from gds_workbench_api.integrations.databricks import DatabricksExecutionAdapters
from gds_workbench_runtime.profiling.workflow import ProfilingWorkflowOrchestrator

from .dispatcher import WorkflowExecutionServices

if TYPE_CHECKING:
    from gds_workbench_api.integrations.agents import ManagedModelAuthentication
    from gds_workbench_api.integrations.agents.configuration import (
        AgentRuntimeConfiguration,
    )


class WorkflowRuntimeDatabase(Protocol):
    """Database behavior needed by the shared execution graph."""

    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...

    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class RegisteredMappingProfileResolver:
    """Resolve only the verified Mapping profile deployed with this process."""

    def __init__(self, registration: MappingProfileRegistration) -> None:
        self._registration = registration

    def resolve(
        self,
        *,
        key: str,
        version: str,
        schema_digest: str,
    ) -> MappingProfileRegistration | None:
        registration = self._registration
        if (key, version, schema_digest) != (
            registration.key,
            registration.version,
            registration.schema_digest,
        ):
            return None
        return registration


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeServices:
    agent_executor: AgentExecutionRouter
    profiling: ProfilingWorkflowOrchestrator
    analysis_inference: AnalysisInferenceWorkflow
    analysis_validation: AnalysisValidationWorkflow
    conceptual: ConceptualWorkflow
    logical: LogicalWorkflow
    dimensional: DimensionalWorkflow
    mapping: MappingWorkflow
    code_generation: CodeGenerationWorkflow
    qa: QAWorkflow

    async def close(self) -> None:
        await self.agent_executor.close()

    def execution_services(self) -> WorkflowExecutionServices:
        return WorkflowExecutionServices(
            profiling=self.profiling,
            analysis_inference=self.analysis_inference,
            analysis_validation=self.analysis_validation,
            conceptual=self.conceptual,
            logical=self.logical,
            dimensional=self.dimensional,
            mapping=self.mapping,
            code_generation=self.code_generation,
            qa=self.qa,
        )


def create_workflow_runtime_services(
    *,
    database: WorkflowRuntimeDatabase,
    authorizer: AuthorizationService,
    agent_runtime: AgentRuntimeConfiguration,
    agent_capability_registry: AgentCapabilityRegistry,
    databricks_environment_code: str,
    databricks_execution: DatabricksExecutionAdapters,
    provider_authentications: Mapping[str, ManagedModelAuthentication] | None = None,
) -> WorkflowRuntimeServices:
    """Assemble one cohesive executor graph shared by both process types."""
    from gds_workbench_api.integrations.agents import create_agent_execution_router

    agent_executor = create_agent_execution_router(
        configuration=agent_runtime,
        capabilities=agent_capability_registry,
        provider_authentications=provider_authentications,
    )
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    handoff = WorkflowChangeSetHandoff(database=database, authorizer=authorizer)
    no_op = DatabaseAuthoringNoOpService(database=database)

    analysis_inference_executor = DatabaseAnalysisInferenceExecutor(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    conceptual_executor = DatabaseConceptualExecutor(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    logical_executor = DatabaseLogicalExecutor(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    dimensional_executor = DatabaseDimensionalExecutor(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    mapping_executor = DatabaseMappingExecutor(
        preparation_service=MappingReadinessService(
            database=database,
            authorizer=authorizer,
            plan_repository=PostgresMappingRunPlanRepository(),
            context_repository=PostgresMappingRunContextRepository(),
            profile_resolver=RegisteredMappingProfileResolver(load_mapping_profile_registry()),
        ),
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    code_generation_executor = DatabaseCodeGenerationExecutor(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    qa_executor = DatabaseQAExecutor(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )

    return WorkflowRuntimeServices(
        agent_executor=agent_executor,
        profiling=ProfilingWorkflowOrchestrator(
            repository=DatabaseProfilingWorkflowRepository(
                database=database,
                environment_code=databricks_environment_code,
            ),
            executor=databricks_execution.profiling,
        ),
        analysis_inference=AnalysisInferenceWorkflow(
            lifecycle=lifecycle,
            executor=analysis_inference_executor,
        ),
        analysis_validation=AnalysisValidationWorkflow(
            lifecycle=lifecycle,
            repository=DatabaseAnalysisValidationRepository(
                database=database,
                environment_code=databricks_environment_code,
            ),
            executor=databricks_execution.analysis_validation,
        ),
        conceptual=ConceptualWorkflow(lifecycle=lifecycle, executor=conceptual_executor),
        logical=LogicalWorkflow(lifecycle=lifecycle, executor=logical_executor),
        dimensional=DimensionalWorkflow(lifecycle=lifecycle, executor=dimensional_executor),
        mapping=MappingWorkflow(lifecycle=lifecycle, executor=mapping_executor),
        code_generation=CodeGenerationWorkflow(
            lifecycle=lifecycle,
            executor=code_generation_executor,
        ),
        qa=QAWorkflow(lifecycle=lifecycle, executor=qa_executor),
    )


__all__ = [
    "RegisteredMappingProfileResolver",
    "WorkflowRuntimeDatabase",
    "WorkflowRuntimeServices",
    "create_workflow_runtime_services",
]
