"""FastAPI process entry point."""

from typing import Protocol

from fastapi import FastAPI, Response, status
from fastapi.requests import Request
from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import ReadinessRecord as ReadinessResult
from starlette.types import Lifespan

from gds_workbench_api.capabilities import AgentCapabilityRegistry
from gds_workbench_api.errors import (
    authentication_error_response,
    workbench_error_response,
)
from gds_workbench_api.features.analysis import (
    AnalysisReviewService,
    create_analysis_review_router,
)
from gds_workbench_api.features.analysis.router import (
    AnalysisInferenceWorkflowService,
    create_analysis_inference_workflow_router,
)
from gds_workbench_api.features.analysis.validation_router import (
    AnalysisValidationWorkflowService,
    create_analysis_validation_workflow_router,
)
from gds_workbench_api.features.assertions import (
    AssertionsService,
    create_assertions_router,
)
from gds_workbench_api.features.code_generation import (
    CodeGenerationService,
    create_code_generation_router,
)
from gds_workbench_api.features.code_generation.router import (
    CodeGenerationWorkflowService,
    create_code_generation_workflow_router,
)
from gds_workbench_api.features.conceptual import ConceptualService, create_conceptual_router
from gds_workbench_api.features.conceptual.router import (
    ConceptualWorkflowService,
    create_conceptual_workflow_router,
)
from gds_workbench_api.features.dimensional import (
    DimensionalService,
    create_dimensional_router,
)
from gds_workbench_api.features.dimensional.router import (
    DimensionalWorkflowService,
    create_dimensional_workflow_router,
)
from gds_workbench_api.features.logical import LogicalService, create_logical_router
from gds_workbench_api.features.logical.router import (
    LogicalWorkflowService,
    create_logical_workflow_router,
)
from gds_workbench_api.features.mapping import (
    MappingReviewService,
    create_mapping_review_router,
)
from gds_workbench_api.features.mapping.router import (
    MappingWorkflowService,
    create_mapping_workflow_router,
)
from gds_workbench_api.features.metadata import MetadataService, create_metadata_router
from gds_workbench_api.features.metadata_change_sets import (
    MetadataChangeSetService,
    create_metadata_change_sets_router,
)
from gds_workbench_api.features.model_change_sets.router import (
    ModelChangeSetService,
    create_model_change_sets_router,
)
from gds_workbench_api.features.model_scope import ModelScopeService, create_scope_router
from gds_workbench_api.features.models import (
    ModelCommandService,
    ModelService,
    create_model_commands_router,
    create_models_router,
)
from gds_workbench_api.features.output_templates import (
    OutputTemplateService,
    create_output_templates_router,
)
from gds_workbench_api.features.profiling import (
    ProfilingReviewService,
    ProfilingWorkflowService,
    create_profiling_router,
    create_profiling_workflow_router,
)
from gds_workbench_api.features.prompts import PromptService, create_prompts_router
from gds_workbench_api.features.session import SessionService, create_session_router
from gds_workbench_api.features.sql_generation_guides import (
    SqlGenerationGuideService,
    create_sql_generation_guides_router,
)
from gds_workbench_api.features.tenant_locks import (
    TenantLockService,
    create_tenant_lock_router,
)
from gds_workbench_api.features.tenants import TenantService, create_tenants_router
from gds_workbench_api.features.workflows.authoring.change_set_apply_router import (
    WorkflowDraftApplyService,
    create_workflow_draft_apply_router,
)
from gds_workbench_api.features.workflows.commands import (
    WorkflowCommandService,
    create_workflow_commands_router,
)
from gds_workbench_api.features.workflows.overview import (
    WorkflowOverviewService,
    create_workflow_overview_router,
)
from gds_workbench_api.features.workflows.runs import (
    WorkflowRunService,
    create_workflow_runs_router,
)


class ReadinessDependency(Protocol):
    async def readiness(self) -> ReadinessResult: ...


def create_app(
    *,
    readiness: ReadinessDependency | None = None,
    identity_provider: IdentityProvider | None = None,
    session_service: SessionService | None = None,
    tenant_service: TenantService | None = None,
    model_service: ModelService | None = None,
    model_command_service: ModelCommandService | None = None,
    model_change_set_service: ModelChangeSetService | None = None,
    workflow_draft_apply_service: WorkflowDraftApplyService | None = None,
    model_scope_service: ModelScopeService | None = None,
    agent_capability_registry: AgentCapabilityRegistry | None = None,
    tenant_lock_service: TenantLockService | None = None,
    metadata_service: MetadataService | None = None,
    metadata_change_set_service: MetadataChangeSetService | None = None,
    output_template_service: OutputTemplateService | None = None,
    prompt_service: PromptService | None = None,
    sql_generation_guide_service: SqlGenerationGuideService | None = None,
    profiling_review_service: ProfilingReviewService | None = None,
    profiling_workflow_service: ProfilingWorkflowService | None = None,
    analysis_review_service: AnalysisReviewService | None = None,
    analysis_inference_workflow_service: AnalysisInferenceWorkflowService | None = None,
    analysis_validation_workflow_service: AnalysisValidationWorkflowService | None = None,
    assertions_service: AssertionsService | None = None,
    conceptual_service: ConceptualService | None = None,
    conceptual_workflow_service: ConceptualWorkflowService | None = None,
    logical_service: LogicalService | None = None,
    logical_workflow_service: LogicalWorkflowService | None = None,
    dimensional_service: DimensionalService | None = None,
    dimensional_workflow_service: DimensionalWorkflowService | None = None,
    mapping_review_service: MappingReviewService | None = None,
    mapping_workflow_service: MappingWorkflowService | None = None,
    code_generation_service: CodeGenerationService | None = None,
    code_generation_workflow_service: CodeGenerationWorkflowService | None = None,
    workflow_overview_service: WorkflowOverviewService | None = None,
    workflow_run_service: WorkflowRunService | None = None,
    workflow_command_service: WorkflowCommandService | None = None,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Create one independently testable Workbench API process."""

    app = FastAPI(
        title="GDS Workbench API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.add_exception_handler(AuthenticationError, authentication_error_response)
    app.add_exception_handler(WorkbenchError, workbench_error_response)

    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def ready(response: Response) -> dict[str, str]:
        result = (
            await readiness.readiness()
            if readiness is not None
            else ReadinessResult(ready=False, code="dependency_not_configured")
        )
        if not result.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "ready" if result.ready else "not_ready", "code": result.code}

    app.add_api_route("/healthz", health, methods=["GET"], tags=["health"])
    app.add_api_route("/readyz", ready, methods=["GET"], tags=["health"])

    if identity_provider is not None and session_service is not None:
        app.include_router(
            create_session_router(
                identity_provider=identity_provider,
                service=session_service,
            )
        )

    if identity_provider is not None and tenant_service is not None:
        app.include_router(
            create_tenants_router(
                identity_provider=identity_provider,
                service=tenant_service,
            )
        )

    if identity_provider is not None and model_service is not None:
        app.include_router(
            create_models_router(
                identity_provider=identity_provider,
                service=model_service,
            )
        )
    if identity_provider is not None and model_command_service is not None:
        app.include_router(
            create_model_commands_router(
                identity_provider=identity_provider,
                service=model_command_service,
            )
        )
    if identity_provider is not None and model_change_set_service is not None:
        app.include_router(
            create_model_change_sets_router(
                identity_provider=identity_provider,
                service=model_change_set_service,
            )
        )
    if identity_provider is not None and workflow_draft_apply_service is not None:
        app.include_router(
            create_workflow_draft_apply_router(
                identity_provider=identity_provider,
                service=workflow_draft_apply_service,
            )
        )
    if identity_provider is not None and model_scope_service is not None:
        app.include_router(
            create_scope_router(
                identity_provider=identity_provider,
                service=model_scope_service,
            )
        )
    if identity_provider is not None and agent_capability_registry is not None:

        async def agent_capabilities(request: Request) -> AgentCapabilityRegistry:
            identity_provider.authenticate(request.headers)
            return agent_capability_registry

        app.add_api_route(
            "/api/v1/config/agent-capabilities",
            agent_capabilities,
            methods=["GET"],
            response_model=AgentCapabilityRegistry,
            tags=["configuration"],
        )
    if identity_provider is not None and tenant_lock_service is not None:
        app.include_router(
            create_tenant_lock_router(
                identity_provider=identity_provider,
                service=tenant_lock_service,
            )
        )
    if identity_provider is not None and metadata_service is not None:
        app.include_router(
            create_metadata_router(
                identity_provider=identity_provider,
                service=metadata_service,
            )
        )
    if identity_provider is not None and metadata_change_set_service is not None:
        app.include_router(
            create_metadata_change_sets_router(
                identity_provider=identity_provider,
                service=metadata_change_set_service,
            )
        )
    if identity_provider is not None and output_template_service is not None:
        app.include_router(
            create_output_templates_router(
                identity_provider=identity_provider,
                service=output_template_service,
            )
        )
    if identity_provider is not None and prompt_service is not None:
        app.include_router(
            create_prompts_router(
                identity_provider=identity_provider,
                service=prompt_service,
            )
        )
    if identity_provider is not None and sql_generation_guide_service is not None:
        app.include_router(
            create_sql_generation_guides_router(
                identity_provider=identity_provider,
                service=sql_generation_guide_service,
            )
        )
    if (
        identity_provider is not None
        and profiling_review_service is not None
        and analysis_review_service is not None
    ):
        app.include_router(
            create_profiling_router(
                identity_provider=identity_provider,
                service=profiling_review_service,
            )
        )
        app.include_router(
            create_analysis_review_router(
                identity_provider=identity_provider,
                service=analysis_review_service,
            )
        )
    if identity_provider is not None and profiling_workflow_service is not None:
        app.include_router(
            create_profiling_workflow_router(
                identity_provider=identity_provider,
                service=profiling_workflow_service,
            )
        )
    if identity_provider is not None and analysis_inference_workflow_service is not None:
        app.include_router(
            create_analysis_inference_workflow_router(
                identity_provider=identity_provider,
                service=analysis_inference_workflow_service,
            )
        )
    if identity_provider is not None and analysis_validation_workflow_service is not None:
        app.include_router(
            create_analysis_validation_workflow_router(
                identity_provider=identity_provider,
                service=analysis_validation_workflow_service,
            )
        )
    if identity_provider is not None and assertions_service is not None:
        app.include_router(
            create_assertions_router(
                identity_provider=identity_provider,
                service=assertions_service,
            )
        )
    if identity_provider is not None and conceptual_service is not None:
        app.include_router(
            create_conceptual_router(
                identity_provider=identity_provider,
                service=conceptual_service,
            )
        )
    if identity_provider is not None and conceptual_workflow_service is not None:
        app.include_router(
            create_conceptual_workflow_router(
                identity_provider=identity_provider,
                service=conceptual_workflow_service,
            )
        )
    if identity_provider is not None and logical_service is not None:
        app.include_router(
            create_logical_router(
                identity_provider=identity_provider,
                service=logical_service,
            )
        )
    if identity_provider is not None and logical_workflow_service is not None:
        app.include_router(
            create_logical_workflow_router(
                identity_provider=identity_provider,
                service=logical_workflow_service,
            )
        )
    if identity_provider is not None and dimensional_service is not None:
        app.include_router(
            create_dimensional_router(
                identity_provider=identity_provider,
                service=dimensional_service,
            )
        )
    if identity_provider is not None and dimensional_workflow_service is not None:
        app.include_router(
            create_dimensional_workflow_router(
                identity_provider=identity_provider,
                service=dimensional_workflow_service,
            )
        )
    if identity_provider is not None and mapping_review_service is not None:
        app.include_router(
            create_mapping_review_router(
                identity_provider=identity_provider,
                service=mapping_review_service,
            )
        )
    if identity_provider is not None and mapping_workflow_service is not None:
        app.include_router(
            create_mapping_workflow_router(
                identity_provider=identity_provider,
                service=mapping_workflow_service,
            )
        )
    if identity_provider is not None and code_generation_service is not None:
        app.include_router(
            create_code_generation_router(
                identity_provider=identity_provider,
                service=code_generation_service,
            )
        )
    if identity_provider is not None and code_generation_workflow_service is not None:
        app.include_router(
            create_code_generation_workflow_router(
                identity_provider=identity_provider,
                service=code_generation_workflow_service,
            )
        )
    if identity_provider is not None and workflow_overview_service is not None:
        app.include_router(
            create_workflow_overview_router(
                identity_provider=identity_provider,
                service=workflow_overview_service,
            )
        )
    if identity_provider is not None and workflow_run_service is not None:
        app.include_router(
            create_workflow_runs_router(
                identity_provider=identity_provider,
                service=workflow_run_service,
            )
        )
    if identity_provider is not None and workflow_command_service is not None:
        app.include_router(
            create_workflow_commands_router(
                identity_provider=identity_provider,
                service=workflow_command_service,
            )
        )
    return app
