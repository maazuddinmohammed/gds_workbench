"""FastAPI process entry point."""

from typing import Protocol

from atlas_mcp.application.identity import IdentityProvider
from atlas_mcp.domain.errors import AtlasError, AuthenticationError
from atlas_mcp.infrastructure.postgres import ReadinessRecord as ReadinessResult
from fastapi import Depends, FastAPI, Response, status
from starlette.types import Lifespan

from atlas_platform.capabilities import AgentCapabilityRegistry
from atlas_platform.dependencies import principal_dependency
from atlas_platform.errors import (
    atlas_error_response,
    authentication_error_response,
)
from atlas_platform.features.analysis import (
    AnalysisReviewService,
    create_analysis_review_router,
)
from atlas_platform.features.analysis.router import (
    AnalysisInferenceWorkflowService,
    create_analysis_inference_workflow_router,
)
from atlas_platform.features.analysis.validation_router import (
    AnalysisValidationWorkflowService,
    create_analysis_validation_workflow_router,
)
from atlas_platform.features.code_generation import (
    CodeGenerationService,
    create_code_generation_router,
)
from atlas_platform.features.code_generation.router import (
    CodeGenerationWorkflowService,
    create_code_generation_workflow_router,
)
from atlas_platform.features.context import (
    ContextService,
    create_context_router,
)
from atlas_platform.features.dimensional import (
    DimensionalService,
    create_dimensional_router,
)
from atlas_platform.features.dimensional.router import (
    DimensionalWorkflowService,
    create_dimensional_workflow_router,
)
from atlas_platform.features.logical import LogicalService, create_logical_router
from atlas_platform.features.logical.router import (
    LogicalWorkflowService,
    create_logical_workflow_router,
)
from atlas_platform.features.mapping import (
    MappingReviewService,
    create_mapping_review_router,
)
from atlas_platform.features.mapping.router import (
    MappingWorkflowService,
    create_mapping_workflow_router,
)
from atlas_platform.features.metadata import MetadataService, create_metadata_router
from atlas_platform.features.metadata_change_sets import (
    MetadataChangeSetService,
    create_metadata_change_sets_router,
)
from atlas_platform.features.metadata_enrichment.dictionary import (
    DatabaseEnrichmentDictionaryService,
    create_enrichment_dictionary_router,
)
from atlas_platform.features.metadata_enrichment.read_router import (
    create_metadata_enrichment_read_router,
)
from atlas_platform.features.metadata_enrichment.read_service import (
    MetadataEnrichmentReadService,
)
from atlas_platform.features.metadata_enrichment.review import (
    DatabaseEnrichmentReviewService,
    create_enrichment_review_router,
)
from atlas_platform.features.metadata_enrichment.router import (
    MetadataEnrichmentWorkflowService,
    create_metadata_enrichment_workflow_router,
)
from atlas_platform.features.output_templates import (
    OutputTemplateService,
    create_output_templates_router,
)
from atlas_platform.features.profiling import (
    ProfilingReviewService,
    ProfilingWorkflowService,
    create_profiling_router,
    create_profiling_workflow_router,
)
from atlas_platform.features.project_change_sets.router import (
    ProjectChangeSetService,
    create_project_change_sets_router,
)
from atlas_platform.features.project_input_scope import (
    ProjectInputScopeService,
    create_input_scope_router,
)
from atlas_platform.features.project_targets.router import (
    ProjectTargetsService,
    create_project_targets_router,
)
from atlas_platform.features.projects import (
    ProjectCommandService,
    ProjectService,
    create_project_commands_router,
    create_projects_router,
)
from atlas_platform.features.prompts import PromptService, create_prompts_router
from atlas_platform.features.session import SessionService, create_session_router
from atlas_platform.features.subject_areas import (
    SubjectAreaService,
    SubjectAreaWorkflowService,
    create_subject_area_router,
    create_subject_area_workflow_router,
)
from atlas_platform.features.tenant_locks import (
    TenantLockService,
    create_tenant_lock_router,
)
from atlas_platform.features.tenants import TenantService, create_tenants_router
from atlas_platform.features.validation import (
    ValidationReadService,
    ValidationWorkflowService,
    create_validation_read_router,
    create_validation_workflow_router,
)
from atlas_platform.features.workflows.authoring.change_set_apply_router import (
    WorkflowDraftApplyService,
    create_workflow_draft_apply_router,
)
from atlas_platform.features.workflows.commands import (
    WorkflowCommandService,
    create_workflow_commands_router,
)
from atlas_platform.features.workflows.overview import (
    WorkflowOverviewService,
    create_workflow_overview_router,
)
from atlas_platform.features.workflows.runs import (
    WorkflowRunService,
    create_workflow_runs_router,
)
from atlas_platform.runtime_diagnostics import RuntimeDiagnostics, RuntimeDiagnosticsSnapshot


class ReadinessDependency(Protocol):
    async def readiness(self) -> ReadinessResult: ...


def create_app(
    *,
    readiness: ReadinessDependency | None = None,
    identity_provider: IdentityProvider | None = None,
    session_service: SessionService | None = None,
    tenant_service: TenantService | None = None,
    project_service: ProjectService | None = None,
    project_command_service: ProjectCommandService | None = None,
    project_change_set_service: ProjectChangeSetService | None = None,
    workflow_draft_apply_service: WorkflowDraftApplyService | None = None,
    project_input_scope_service: ProjectInputScopeService | None = None,
    enrichment_dictionary_service: DatabaseEnrichmentDictionaryService | None = None,
    enrichment_review_service: DatabaseEnrichmentReviewService | None = None,
    agent_capability_registry: AgentCapabilityRegistry | None = None,
    tenant_lock_service: TenantLockService | None = None,
    metadata_service: MetadataService | None = None,
    metadata_enrichment_read_service: MetadataEnrichmentReadService | None = None,
    metadata_enrichment_workflow_service: MetadataEnrichmentWorkflowService | None = None,
    metadata_change_set_service: MetadataChangeSetService | None = None,
    output_template_service: OutputTemplateService | None = None,
    prompt_service: PromptService | None = None,
    profiling_review_service: ProfilingReviewService | None = None,
    profiling_workflow_service: ProfilingWorkflowService | None = None,
    analysis_review_service: AnalysisReviewService | None = None,
    analysis_inference_workflow_service: AnalysisInferenceWorkflowService | None = None,
    analysis_validation_workflow_service: AnalysisValidationWorkflowService | None = None,
    context_service: ContextService | None = None,
    subject_area_service: SubjectAreaService | None = None,
    subject_area_workflow_service: SubjectAreaWorkflowService | None = None,
    logical_service: LogicalService | None = None,
    project_targets_service: ProjectTargetsService | None = None,
    logical_workflow_service: LogicalWorkflowService | None = None,
    dimensional_service: DimensionalService | None = None,
    dimensional_workflow_service: DimensionalWorkflowService | None = None,
    mapping_review_service: MappingReviewService | None = None,
    mapping_workflow_service: MappingWorkflowService | None = None,
    code_generation_service: CodeGenerationService | None = None,
    code_generation_workflow_service: CodeGenerationWorkflowService | None = None,
    validation_read_service: ValidationReadService | None = None,
    validation_workflow_service: ValidationWorkflowService | None = None,
    workflow_overview_service: WorkflowOverviewService | None = None,
    workflow_run_service: WorkflowRunService | None = None,
    workflow_command_service: WorkflowCommandService | None = None,
    runtime_diagnostics: RuntimeDiagnostics | None = None,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Create one independently testable Atlas Platform API process."""

    app = FastAPI(
        title="Atlas Platform API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_exception_handler(AuthenticationError, authentication_error_response)
    app.add_exception_handler(AtlasError, atlas_error_response)

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

    if identity_provider is None:
        return app

    if runtime_diagnostics is not None:

        async def read_runtime_diagnostics(response: Response) -> RuntimeDiagnosticsSnapshot:
            response.headers["Cache-Control"] = "no-store"
            return runtime_diagnostics.snapshot()

        app.add_api_route(
            "/api/v1/config/runtime-diagnostics",
            read_runtime_diagnostics,
            methods=["GET"],
            response_model=RuntimeDiagnosticsSnapshot,
            dependencies=[Depends(principal_dependency(identity_provider))],
            tags=["configuration"],
        )

    if session_service is not None:
        app.include_router(
            create_session_router(
                identity_provider=identity_provider,
                service=session_service,
            )
        )

    if tenant_service is not None:
        app.include_router(
            create_tenants_router(
                identity_provider=identity_provider,
                service=tenant_service,
            )
        )

    if project_service is not None:
        app.include_router(
            create_projects_router(
                identity_provider=identity_provider,
                service=project_service,
            )
        )
    if project_command_service is not None:
        app.include_router(
            create_project_commands_router(
                identity_provider=identity_provider,
                service=project_command_service,
            )
        )
    if project_change_set_service is not None:
        app.include_router(
            create_project_change_sets_router(
                identity_provider=identity_provider,
                service=project_change_set_service,
            )
        )
    if workflow_draft_apply_service is not None:
        app.include_router(
            create_workflow_draft_apply_router(
                identity_provider=identity_provider,
                service=workflow_draft_apply_service,
            )
        )
    if project_input_scope_service is not None:
        app.include_router(
            create_input_scope_router(
                identity_provider=identity_provider,
                service=project_input_scope_service,
            )
        )
    if agent_capability_registry is not None:

        async def agent_capabilities() -> AgentCapabilityRegistry:
            return agent_capability_registry

        app.add_api_route(
            "/api/v1/config/agent-capabilities",
            agent_capabilities,
            methods=["GET"],
            response_model=AgentCapabilityRegistry,
            dependencies=[Depends(principal_dependency(identity_provider))],
            tags=["configuration"],
        )
    if tenant_lock_service is not None:
        app.include_router(
            create_tenant_lock_router(
                identity_provider=identity_provider,
                service=tenant_lock_service,
            )
        )
    if metadata_service is not None:
        app.include_router(
            create_metadata_router(
                identity_provider=identity_provider,
                service=metadata_service,
            )
        )
    if metadata_change_set_service is not None:
        app.include_router(
            create_metadata_change_sets_router(
                identity_provider=identity_provider,
                service=metadata_change_set_service,
            )
        )
    if output_template_service is not None:
        app.include_router(
            create_output_templates_router(
                identity_provider=identity_provider,
                service=output_template_service,
            )
        )
    if prompt_service is not None:
        app.include_router(
            create_prompts_router(
                identity_provider=identity_provider,
                service=prompt_service,
            )
        )
    if profiling_review_service is not None:
        app.include_router(
            create_profiling_router(
                identity_provider=identity_provider,
                service=profiling_review_service,
            )
        )
    if analysis_review_service is not None:
        app.include_router(
            create_analysis_review_router(
                identity_provider=identity_provider,
                service=analysis_review_service,
            )
        )
    if profiling_workflow_service is not None:
        app.include_router(
            create_profiling_workflow_router(
                identity_provider=identity_provider,
                service=profiling_workflow_service,
            )
        )
    if analysis_inference_workflow_service is not None:
        app.include_router(
            create_analysis_inference_workflow_router(
                identity_provider=identity_provider,
                service=analysis_inference_workflow_service,
            )
        )
    if analysis_validation_workflow_service is not None:
        app.include_router(
            create_analysis_validation_workflow_router(
                identity_provider=identity_provider,
                service=analysis_validation_workflow_service,
            )
        )
    if context_service is not None:
        app.include_router(
            create_context_router(
                identity_provider=identity_provider,
                service=context_service,
            )
        )
    if subject_area_service is not None:
        app.include_router(
            create_subject_area_router(
                identity_provider=identity_provider,
                service=subject_area_service,
            )
        )
    if subject_area_workflow_service is not None:
        app.include_router(
            create_subject_area_workflow_router(
                identity_provider=identity_provider,
                service=subject_area_workflow_service,
            )
        )
    if project_targets_service is not None:
        app.include_router(
            create_project_targets_router(
                identity_provider=identity_provider, service=project_targets_service
            )
        )
    if logical_service is not None:
        app.include_router(
            create_logical_router(
                identity_provider=identity_provider,
                service=logical_service,
            )
        )
    if logical_workflow_service is not None:
        app.include_router(
            create_logical_workflow_router(
                identity_provider=identity_provider,
                service=logical_workflow_service,
            )
        )
    if dimensional_service is not None:
        app.include_router(
            create_dimensional_router(
                identity_provider=identity_provider,
                service=dimensional_service,
            )
        )
    if dimensional_workflow_service is not None:
        app.include_router(
            create_dimensional_workflow_router(
                identity_provider=identity_provider,
                service=dimensional_workflow_service,
            )
        )
    if mapping_review_service is not None:
        app.include_router(
            create_mapping_review_router(
                identity_provider=identity_provider,
                service=mapping_review_service,
            )
        )
    if mapping_workflow_service is not None:
        app.include_router(
            create_mapping_workflow_router(
                identity_provider=identity_provider,
                service=mapping_workflow_service,
            )
        )
    if code_generation_service is not None:
        app.include_router(
            create_code_generation_router(
                identity_provider=identity_provider,
                service=code_generation_service,
            )
        )
    if code_generation_workflow_service is not None:
        app.include_router(
            create_code_generation_workflow_router(
                identity_provider=identity_provider,
                service=code_generation_workflow_service,
            )
        )
    if validation_read_service is not None:
        app.include_router(
            create_validation_read_router(
                identity_provider=identity_provider,
                service=validation_read_service,
            )
        )
    if metadata_enrichment_workflow_service is not None:
        app.include_router(
            create_metadata_enrichment_workflow_router(
                identity_provider=identity_provider,
                service=metadata_enrichment_workflow_service,
            )
        )
    if enrichment_dictionary_service is not None:
        app.include_router(
            create_enrichment_dictionary_router(
                identity_provider=identity_provider,
                service=enrichment_dictionary_service,
            )
        )
    if enrichment_review_service is not None:
        app.include_router(
            create_enrichment_review_router(
                identity_provider=identity_provider,
                service=enrichment_review_service,
            )
        )
    if metadata_enrichment_read_service is not None:
        app.include_router(
            create_metadata_enrichment_read_router(
                identity_provider=identity_provider,
                service=metadata_enrichment_read_service,
            )
        )
    if validation_workflow_service is not None:
        app.include_router(
            create_validation_workflow_router(
                identity_provider=identity_provider,
                service=validation_workflow_service,
            )
        )
    if workflow_overview_service is not None:
        app.include_router(
            create_workflow_overview_router(
                identity_provider=identity_provider,
                service=workflow_overview_service,
            )
        )
    if workflow_run_service is not None:
        app.include_router(
            create_workflow_runs_router(
                identity_provider=identity_provider,
                service=workflow_run_service,
            )
        )
    if workflow_command_service is not None:
        app.include_router(
            create_workflow_commands_router(
                identity_provider=identity_provider,
                service=workflow_command_service,
            )
        )
    return app
