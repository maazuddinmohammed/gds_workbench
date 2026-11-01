"""Shared Workflow executor assembly for API and worker processes."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from atlas_mcp.application.authorization import AuthorizationService
from atlas_mcp.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from atlas_platform.capabilities import AgentCapabilityRegistry
from atlas_platform.features.analysis import (
    AnalysisInferenceWorkflow,
    AnalysisValidationWorkflow,
    DatabaseAnalysisValidationRepository,
)
from atlas_platform.features.code_generation import CodeGenerationWorkflow
from atlas_platform.features.dimensional import DimensionalWorkflow
from atlas_platform.features.logical import LogicalWorkflow
from atlas_platform.features.mapping import (
    MappingReadinessService,
    MappingWorkflow,
    PostgresMappingRunContextRepository,
    PostgresMappingRunPlanRepository,
)
from atlas_platform.features.metadata_enrichment.repository import MetadataEnrichmentRepository
from atlas_platform.features.metadata_enrichment.service import (
    DatabaseMetadataEnrichmentExecutor,
)
from atlas_platform.features.profiling import DatabaseProfilingWorkflowRepository
from atlas_platform.features.profiling.workflow import ProfilingWorkflowOrchestrator
from atlas_platform.features.subject_areas import SubjectAreaWorkflow
from atlas_platform.features.validation import ValidationWorkflow
from atlas_platform.features.workflows.authoring.agent_execution import (
    AgentExecutionRouter,
)
from atlas_platform.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
)
from atlas_platform.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from atlas_platform.features.workflows.authoring.no_op import (
    DatabaseAuthoringNoOpService,
)
from atlas_platform.features.workflows.usage.service import DatabaseWorkflowUsageRecorder
from atlas_platform.integrations.databricks import DatabricksExecutionAdapters

from .dispatcher import WorkflowExecutionServices

if TYPE_CHECKING:
    from atlas_platform.integrations.agents import ManagedModelAuthentication
    from atlas_platform.integrations.agents.configuration import (
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


@dataclass(frozen=True, slots=True)
class WorkflowRuntimeServices:
    usage_recorder: DatabaseWorkflowUsageRecorder
    lifecycle: DatabaseAgentWorkflowLifecycle
    agent_executor: AgentExecutionRouter
    profiling: ProfilingWorkflowOrchestrator
    analysis_inference: AnalysisInferenceWorkflow
    analysis_validation: AnalysisValidationWorkflow
    subject_area: SubjectAreaWorkflow
    logical: LogicalWorkflow
    dimensional: DimensionalWorkflow
    mapping: MappingWorkflow
    code_generation: CodeGenerationWorkflow
    validation: ValidationWorkflow
    metadata_enrichment: DatabaseMetadataEnrichmentExecutor

    async def close(self) -> None:
        await self.agent_executor.close()

    def execution_services(self) -> WorkflowExecutionServices:
        return WorkflowExecutionServices(
            usage_recorder=self.usage_recorder,
            lifecycle=self.lifecycle,
            profiling=self.profiling,
            analysis_inference=self.analysis_inference,
            analysis_validation=self.analysis_validation,
            subject_area=self.subject_area,
            logical=self.logical,
            dimensional=self.dimensional,
            mapping=self.mapping,
            code_generation=self.code_generation,
            validation=self.validation,
            metadata_enrichment=self.metadata_enrichment,
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
    from atlas_platform.integrations.agents import create_agent_execution_router

    usage_recorder = DatabaseWorkflowUsageRecorder(
        database=database,
        pricing_by_model={
            connection.model_code: connection.pricing
            for connection in agent_runtime.connections
            if connection.pricing is not None
        },
    )
    agent_executor = create_agent_execution_router(
        usage_recorder=usage_recorder,
        configuration=agent_runtime,
        capabilities=agent_capability_registry,
        provider_authentications=provider_authentications,
    )
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    handoff = WorkflowChangeSetHandoff(database=database, authorizer=authorizer)
    no_op = DatabaseAuthoringNoOpService(database=database)

    analysis_inference_workflow = AnalysisInferenceWorkflow(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    subject_area_workflow = SubjectAreaWorkflow(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    logical_workflow = LogicalWorkflow(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    dimensional_workflow = DimensionalWorkflow(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    mapping_workflow = MappingWorkflow(
        preparation_service=MappingReadinessService(
            database=database,
            authorizer=authorizer,
            plan_repository=PostgresMappingRunPlanRepository(),
            context_repository=PostgresMappingRunContextRepository(),
        ),
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    code_generation_workflow = CodeGenerationWorkflow(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )
    validation_workflow = ValidationWorkflow(
        database=database,
        authorizer=authorizer,
        agent_executor=agent_executor,
        handoff=handoff,
        no_op=no_op,
        lifecycle=lifecycle,
    )

    return WorkflowRuntimeServices(
        usage_recorder=usage_recorder,
        lifecycle=lifecycle,
        agent_executor=agent_executor,
        profiling=ProfilingWorkflowOrchestrator(
            repository=DatabaseProfilingWorkflowRepository(
                database=database,
                environment_code=databricks_environment_code,
            ),
            executor=databricks_execution.profiling,
        ),
        analysis_inference=analysis_inference_workflow,
        analysis_validation=AnalysisValidationWorkflow(
            lifecycle=lifecycle,
            repository=DatabaseAnalysisValidationRepository(
                database=database,
                environment_code=databricks_environment_code,
            ),
            executor=databricks_execution.analysis_validation,
        ),
        subject_area=subject_area_workflow,
        logical=logical_workflow,
        dimensional=dimensional_workflow,
        mapping=mapping_workflow,
        code_generation=code_generation_workflow,
        validation=validation_workflow,
        metadata_enrichment=DatabaseMetadataEnrichmentExecutor(
            repository=MetadataEnrichmentRepository(
                database, environment_code=databricks_environment_code
            ),
            agent_executor=agent_executor,
            lifecycle=lifecycle,
            sql_executor=databricks_execution.metadata_enrichment_sql,
        ),
    )


__all__ = [
    "WorkflowRuntimeDatabase",
    "WorkflowRuntimeServices",
    "create_workflow_runtime_services",
]
