"""Fully wired web API process factory."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Protocol

from atlas_mcp.application.authorization import AuthorizationService
from atlas_mcp.configuration import Environment
from fastapi import FastAPI

from atlas_platform.authentication import (
    DatabricksUserResolver,
    LocalUserResolver,
    WebAuthenticationMiddleware,
    WebIdentityProvider,
)
from atlas_platform.capabilities import (
    load_default_agent_capabilities,
    select_agent_runtime_capabilities,
)
from atlas_platform.configuration import RuntimeSettings
from atlas_platform.database import WebPostgresDatabase
from atlas_platform.features.analysis import DatabaseAnalysisReviewService
from atlas_platform.features.code_generation import DatabaseCodeGenerationService
from atlas_platform.features.context import DatabaseContextService
from atlas_platform.features.dimensional import DatabaseDimensionalService
from atlas_platform.features.logical import DatabaseLogicalService
from atlas_platform.features.mapping import DatabaseMappingReviewService
from atlas_platform.features.metadata import (
    DatabaseMetadataService,
    PostgresMetadataRepository,
)
from atlas_platform.features.metadata_change_sets import DatabaseMetadataChangeSetService
from atlas_platform.features.metadata_enrichment.dictionary import (
    DatabaseEnrichmentDictionaryService,
)
from atlas_platform.features.metadata_enrichment.read_service import (
    DatabaseMetadataEnrichmentReadService,
)
from atlas_platform.features.metadata_enrichment.review import DatabaseEnrichmentReviewService
from atlas_platform.features.output_templates import DatabaseOutputTemplateService
from atlas_platform.features.profiling import DatabaseProfilingReviewService
from atlas_platform.features.project_change_sets.service import DatabaseProjectChangeSetService
from atlas_platform.features.project_input_scope import DatabaseProjectInputScopeService
from atlas_platform.features.project_targets.service import DatabaseProjectTargetsService
from atlas_platform.features.projects import (
    DatabaseProjectCommandService,
    DatabaseProjectService,
)
from atlas_platform.features.prompts import DatabasePromptService
from atlas_platform.features.session import DatabaseSessionService
from atlas_platform.features.subject_areas import DatabaseSubjectAreaService
from atlas_platform.features.tenant_locks import DatabaseTenantLockService
from atlas_platform.features.tenants import DatabaseTenantService
from atlas_platform.features.validation import DatabaseValidationReadService
from atlas_platform.features.workflows.authoring.change_set_apply import (
    DatabaseWorkflowDraftApplyService,
)
from atlas_platform.features.workflows.commands import DatabaseWorkflowCommandService
from atlas_platform.features.workflows.execution.assembly import (
    WorkflowRuntimeDatabase,
    create_workflow_runtime_services,
)
from atlas_platform.features.workflows.overview import DatabaseWorkflowOverviewService
from atlas_platform.features.workflows.runs import DatabaseWorkflowRunService
from atlas_platform.frontend import (
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
    mount_frontend,
)
from atlas_platform.integrations.databricks import create_databricks_execution_adapters
from atlas_platform.main import ReadinessDependency, create_app
from atlas_platform.runtime_diagnostics import RuntimeDiagnostics


class RuntimeDatabase(ReadinessDependency, WorkflowRuntimeDatabase, Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...


def create_runtime_app(
    *,
    settings: RuntimeSettings | None = None,
    database: RuntimeDatabase | None = None,
    diagnostics: RuntimeDiagnostics | None = None,
) -> FastAPI:
    """Build one local-testable and container-ready API process."""
    runtime_settings = settings or RuntimeSettings.from_environment()
    runtime_database = database or WebPostgresDatabase(
        dsn=runtime_settings.database_dsn,
        pool_min=runtime_settings.pool_min,
        pool_max=runtime_settings.pool_max,
        pool_timeout_seconds=runtime_settings.pool_timeout_seconds,
    )
    authorizer = AuthorizationService()
    all_agent_capabilities = load_default_agent_capabilities()
    agent_capability_registry = (
        all_agent_capabilities
        if runtime_settings.agent_runtime.mode == "fake"
        else select_agent_runtime_capabilities(
            all_agent_capabilities,
            configured_models={
                (connection.provider_code, connection.model_code)
                for connection in runtime_settings.agent_runtime.connections
            },
        )
    )
    workflow_services = create_workflow_runtime_services(
        database=runtime_database,
        authorizer=authorizer,
        agent_runtime=runtime_settings.agent_runtime,
        agent_capability_registry=agent_capability_registry,
        databricks_environment_code=runtime_settings.databricks_environment_code,
        databricks_execution=create_databricks_execution_adapters(
            runtime_settings.databricks_execution_mode
        ),
    )
    identity_provider = WebIdentityProvider()
    if runtime_settings.environment is Environment.LOCAL:
        if runtime_settings.local_principal_object_id is None:
            raise RuntimeError("the validated local web identity is unavailable")
        identity_resolver = LocalUserResolver(
            entra_tenant_id=runtime_settings.entra_tenant_id,
            entra_object_id=runtime_settings.local_principal_object_id,
        )
    else:
        if runtime_settings.databricks_host is None:
            raise RuntimeError("the validated Databricks host is unavailable")
        identity_resolver = DatabricksUserResolver(
            host=runtime_settings.databricks_host,
            entra_tenant_id=runtime_settings.entra_tenant_id,
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        await runtime_database.open()
        try:
            yield
        finally:
            try:
                await workflow_services.close()
            finally:
                await runtime_database.close()

    app = create_app(
        runtime_diagnostics=diagnostics or RuntimeDiagnostics.capture_installed_sources(),
        readiness=runtime_database,
        identity_provider=identity_provider,
        session_service=DatabaseSessionService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        tenant_service=DatabaseTenantService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        project_service=DatabaseProjectService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        project_command_service=DatabaseProjectCommandService(
            database=runtime_database,
            authorizer=authorizer,
            agent_capability_registry=agent_capability_registry,
        ),
        project_change_set_service=DatabaseProjectChangeSetService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        workflow_draft_apply_service=DatabaseWorkflowDraftApplyService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        project_input_scope_service=DatabaseProjectInputScopeService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        agent_capability_registry=agent_capability_registry,
        tenant_lock_service=DatabaseTenantLockService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        metadata_service=DatabaseMetadataService(
            database=runtime_database,
            repository=PostgresMetadataRepository(),
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        metadata_change_set_service=DatabaseMetadataChangeSetService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        output_template_service=DatabaseOutputTemplateService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        prompt_service=DatabasePromptService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        profiling_review_service=DatabaseProfilingReviewService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        profiling_workflow_service=workflow_services.profiling,
        analysis_review_service=DatabaseAnalysisReviewService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        analysis_inference_workflow_service=workflow_services.analysis_inference,
        analysis_validation_workflow_service=workflow_services.analysis_validation,
        context_service=DatabaseContextService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        subject_area_service=DatabaseSubjectAreaService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        subject_area_workflow_service=workflow_services.subject_area,
        project_targets_service=DatabaseProjectTargetsService(
            database=runtime_database, authorizer=authorizer
        ),
        logical_service=DatabaseLogicalService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        logical_workflow_service=workflow_services.logical,
        dimensional_service=DatabaseDimensionalService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        dimensional_workflow_service=workflow_services.dimensional,
        mapping_review_service=DatabaseMappingReviewService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        mapping_workflow_service=workflow_services.mapping,
        code_generation_service=DatabaseCodeGenerationService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        code_generation_workflow_service=workflow_services.code_generation,
        validation_read_service=DatabaseValidationReadService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        enrichment_dictionary_service=DatabaseEnrichmentDictionaryService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
            enrichment=True,
        ),
        enrichment_review_service=DatabaseEnrichmentReviewService(database=runtime_database),
        metadata_enrichment_workflow_service=workflow_services.metadata_enrichment,
        metadata_enrichment_read_service=DatabaseMetadataEnrichmentReadService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        validation_workflow_service=workflow_services.validation,
        workflow_overview_service=DatabaseWorkflowOverviewService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        workflow_run_service=DatabaseWorkflowRunService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        workflow_command_service=DatabaseWorkflowCommandService(
            database=runtime_database,
            authorizer=authorizer,
            agent_capability_registry=agent_capability_registry,
        ),
        lifespan=lifespan,
    )
    if runtime_settings.static_directory is not None:
        mount_frontend(app, runtime_settings.static_directory)
    app.add_middleware(
        WebAuthenticationMiddleware,
        identity_provider=identity_provider,
        resolver=identity_resolver,
    )
    app.add_middleware(RequestBodyLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    return app
