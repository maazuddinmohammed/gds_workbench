"""Fully wired web API process factory."""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol

from fastapi import FastAPI
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    WriteTransaction,
)
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.analysis import (
    AnalysisReviewDatabase,
    DatabaseAnalysisReviewService,
)
from gds_workbench_api.features.assertions import (
    AssertionsReadDatabase,
    DatabaseAssertionsService,
)
from gds_workbench_api.features.code_generation import (
    CodeGenerationReadDatabase,
    DatabaseCodeGenerationService,
)
from gds_workbench_api.features.conceptual import (
    ConceptualReadDatabase,
    DatabaseConceptualService,
)
from gds_workbench_api.features.dimensional import (
    DatabaseDimensionalService,
    DimensionalReadDatabase,
)
from gds_workbench_api.features.logical import DatabaseLogicalService, LogicalReadDatabase
from gds_workbench_api.features.mapping import (
    DatabaseMappingReviewService,
    MappingReadDatabase,
)
from gds_workbench_api.features.metadata import (
    DatabaseMetadataService,
    MetadataDatabase,
    PostgresMetadataRepository,
)
from gds_workbench_api.features.metadata_change_sets import (
    DatabaseMetadataChangeSetService,
    MetadataChangeSetDatabase,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
    ModelChangeSetDatabase,
)
from gds_workbench_api.features.model_scope import (
    DatabaseModelScopeService,
    ModelScopeReadDatabase,
)
from gds_workbench_api.features.models import (
    DatabaseModelCommandService,
    DatabaseModelService,
    ModelCommandDatabase,
    ModelReadDatabase,
)
from gds_workbench_api.features.output_templates import (
    DatabaseOutputTemplateService,
    OutputTemplateDatabase,
)
from gds_workbench_api.features.profiling import (
    DatabaseProfilingReviewService,
    ProfilingReviewDatabase,
)
from gds_workbench_api.features.prompts import DatabasePromptService, PromptDatabase
from gds_workbench_api.features.session import (
    DatabaseSessionService,
    SessionReadDatabase,
)
from gds_workbench_api.features.sql_generation_guides import (
    DatabaseSqlGenerationGuideService,
    SqlGenerationGuideDatabase,
)
from gds_workbench_api.features.tenant_locks import (
    DatabaseTenantLockService,
    TenantLockDatabase,
)
from gds_workbench_api.features.tenants import DatabaseTenantService, TenantDatabase
from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    DatabaseWorkflowDraftApplyService,
    WorkflowDraftApplyDatabase,
)
from gds_workbench_api.features.workflows.commands import (
    DatabaseWorkflowCommandService,
    WorkflowCommandDatabase,
)
from gds_workbench_api.features.workflows.execution.assembly import (
    WorkflowRuntimeDatabase,
    create_workflow_runtime_services,
)
from gds_workbench_api.features.workflows.overview import (
    DatabaseWorkflowOverviewService,
    WorkflowOverviewDatabase,
)
from gds_workbench_api.features.workflows.runs import (
    DatabaseWorkflowRunService,
    WorkflowRunDatabase,
)
from gds_workbench_api.integrations.databricks import create_databricks_execution_adapters
from gds_workbench_api.main import ReadinessDependency, create_app


class RuntimeDatabase(
    ReadinessDependency,
    SessionReadDatabase,
    TenantDatabase,
    ModelReadDatabase,
    ModelCommandDatabase,
    ModelChangeSetDatabase,
    WorkflowDraftApplyDatabase,
    ModelScopeReadDatabase,
    TenantLockDatabase,
    MetadataDatabase,
    MetadataChangeSetDatabase,
    OutputTemplateDatabase,
    PromptDatabase,
    SqlGenerationGuideDatabase,
    ProfilingReviewDatabase,
    AnalysisReviewDatabase,
    ConceptualReadDatabase,
    LogicalReadDatabase,
    DimensionalReadDatabase,
    MappingReadDatabase,
    CodeGenerationReadDatabase,
    WorkflowOverviewDatabase,
    WorkflowRunDatabase,
    WorkflowCommandDatabase,
    WorkflowRuntimeDatabase,
    AssertionsReadDatabase,
    Protocol,
):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


def create_runtime_app(
    *,
    settings: RuntimeSettings | None = None,
    database: RuntimeDatabase | None = None,
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
    agent_capability_registry = load_default_agent_capabilities()
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
    identity_provider = IdentityProvider(
        runtime_settings.auth_mode,
        local_tenant_id=runtime_settings.local_entra_tenant_id,
        local_principal_object_id=runtime_settings.local_principal_object_id,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        await runtime_database.open()
        try:
            yield
        finally:
            await runtime_database.close()

    app = create_app(
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
        model_service=DatabaseModelService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        model_command_service=DatabaseModelCommandService(
            database=runtime_database,
            authorizer=authorizer,
            agent_capability_registry=agent_capability_registry,
        ),
        model_change_set_service=DatabaseModelChangeSetService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        workflow_draft_apply_service=DatabaseWorkflowDraftApplyService(
            database=runtime_database,
            authorizer=authorizer,
        ),
        model_scope_service=DatabaseModelScopeService(
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
        sql_generation_guide_service=DatabaseSqlGenerationGuideService(
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
        assertions_service=DatabaseAssertionsService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        conceptual_service=DatabaseConceptualService(
            database=runtime_database,
            authorizer=authorizer,
            cursor_signing_key=runtime_settings.cursor_signing_key,
        ),
        conceptual_workflow_service=workflow_services.conceptual,
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[runtime_settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "X-Correlation-ID",
        ],
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(runtime_settings.allowed_hosts),
    )
    if runtime_settings.require_https:
        app.add_middleware(HTTPSRedirectMiddleware)
    return app
