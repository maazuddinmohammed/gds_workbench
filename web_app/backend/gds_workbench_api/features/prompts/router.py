"""Governed Prompt Library HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.prompts.contracts import (
    CreatePromptTemplateRequest,
    ModelPromptAssignments,
    ModelPromptAssignmentState,
    ModelWorkflow,
    PromptPreview,
    PromptStageCatalog,
    PromptTemplateDetail,
    PromptTemplateFilters,
    PromptTemplateHeader,
    PromptTemplatePage,
    PromptTemplateVersion,
    PromptVersionStatus,
    SavePromptDraftRequest,
    SetModelPromptAssignmentRequest,
    UpdatePromptTemplateRequest,
    WorkflowExecutionMode,
)
from gds_workbench_api.features.prompts.service import PromptService
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
    render_prompt,
)


def create_prompts_router(
    *,
    identity_provider: IdentityProvider,
    service: PromptService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/prompts",
        tags=["prompts"],
    )
    tenant_path = Path(gt=0)
    id_path = Path(gt=0)

    async def list_stages(
        tenant_id: Annotated[int, tenant_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptStageCatalog:
        return await service.list_stages(principal, tenant_id=tenant_id)

    async def list_templates(
        tenant_id: Annotated[int, tenant_path],
        workflow: ModelWorkflow | None = None,
        mode: WorkflowExecutionMode | None = None,
        stage_code: Annotated[
            str | None, Query(min_length=1, max_length=100, pattern="^[a-z][a-z0-9_]{0,99}$")
        ] = None,
        status: PromptVersionStatus | None = None,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptTemplatePage:
        return await service.list_templates(
            principal,
            tenant_id=tenant_id,
            filters=PromptTemplateFilters(
                model_workflow=workflow,
                workflow_execution_mode=mode,
                workflow_stage_code=stage_code,
                version_status=status,
            ),
            page_size=page_size,
            cursor=cursor,
        )

    async def read_template(
        tenant_id: Annotated[int, tenant_path],
        prompt_template_id: Annotated[int, id_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptTemplateDetail:
        return await service.read_template(
            principal,
            tenant_id=tenant_id,
            prompt_template_id=prompt_template_id,
        )

    async def create_template(
        tenant_id: Annotated[int, tenant_path],
        body: CreatePromptTemplateRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptTemplateHeader:
        return await service.create_template(
            principal,
            tenant_id=tenant_id,
            body=body,
        )

    async def update_template(
        tenant_id: Annotated[int, tenant_path],
        prompt_template_id: Annotated[int, id_path],
        body: UpdatePromptTemplateRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptTemplateHeader:
        return await service.update_template(
            principal,
            tenant_id=tenant_id,
            prompt_template_id=prompt_template_id,
            body=body,
        )

    async def save_draft(
        tenant_id: Annotated[int, tenant_path],
        prompt_template_id: Annotated[int, id_path],
        body: SavePromptDraftRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptTemplateVersion:
        return await service.save_draft(
            principal,
            tenant_id=tenant_id,
            prompt_template_id=prompt_template_id,
            body=body,
        )

    async def preview_prompt(
        response: Response,
        tenant_id: Annotated[int, tenant_path],
        prompt_template_id: Annotated[int, id_path],
        body: SavePromptDraftRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptPreview:
        detail = await service.read_template(
            principal, tenant_id=tenant_id, prompt_template_id=prompt_template_id
        )
        response.headers["Cache-Control"] = "no-store"
        rendered = render_prompt(
            templates=PromptComponentTemplates(
                system=body.system_prompt_template,
                instruction=body.instruction_prompt_template,
                tool_instruction=body.tool_instruction_prompt_template,
            ),
            variables=tuple(
                PromptVariableDefinition(
                    name=v.name,
                    resolver_key=v.resolver_key,
                    data_type=v.data_type,
                    is_required=False,
                )
                for v in detail.allowed_variables
            ),
            resolver_values={v.resolver_key: v.example for v in detail.allowed_variables},
        )
        return PromptPreview(
            rendered_system_prompt=rendered.system,
            rendered_instruction_prompt=rendered.instruction,
            rendered_tool_instruction_prompt=rendered.tool_instruction,
        )

    async def publish_version(
        tenant_id: Annotated[int, tenant_path],
        prompt_template_id: Annotated[int, id_path],
        prompt_template_version_id: Annotated[int, id_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptTemplateVersion:
        return await service.publish_version(
            principal,
            tenant_id=tenant_id,
            prompt_template_id=prompt_template_id,
            prompt_template_version_id=prompt_template_version_id,
        )

    async def retire_version(
        tenant_id: Annotated[int, tenant_path],
        prompt_template_id: Annotated[int, id_path],
        prompt_template_version_id: Annotated[int, id_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> PromptTemplateVersion:
        return await service.retire_version(
            principal,
            tenant_id=tenant_id,
            prompt_template_id=prompt_template_id,
            prompt_template_version_id=prompt_template_version_id,
        )

    async def list_model_assignments(
        tenant_id: Annotated[int, tenant_path],
        model_id: Annotated[int, id_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelPromptAssignments:
        return await service.list_model_assignments(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
        )

    async def set_model_assignment(
        tenant_id: Annotated[int, tenant_path],
        model_id: Annotated[int, id_path],
        workflow_stage_id: Annotated[int, id_path],
        body: SetModelPromptAssignmentRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelPromptAssignmentState:
        return await service.set_model_assignment(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_stage_id=workflow_stage_id,
            body=body,
        )

    router.add_api_route(
        "/stages",
        list_stages,
        methods=["GET"],
        response_model=PromptStageCatalog,
    )
    router.add_api_route(
        "/templates",
        list_templates,
        methods=["GET"],
        response_model=PromptTemplatePage,
    )
    router.add_api_route(
        "/templates",
        create_template,
        methods=["POST"],
        response_model=PromptTemplateHeader,
        status_code=201,
    )
    router.add_api_route(
        "/templates/{prompt_template_id}",
        read_template,
        methods=["GET"],
        response_model=PromptTemplateDetail,
    )
    router.add_api_route(
        "/templates/{prompt_template_id}",
        update_template,
        methods=["PUT"],
        response_model=PromptTemplateHeader,
    )
    router.add_api_route(
        "/templates/{prompt_template_id}/preview",
        preview_prompt,
        methods=["POST"],
        response_model=PromptPreview,
    )
    router.add_api_route(
        "/templates/{prompt_template_id}/draft",
        save_draft,
        methods=["PUT"],
        response_model=PromptTemplateVersion,
    )
    router.add_api_route(
        "/templates/{prompt_template_id}/versions/{prompt_template_version_id}/publish",
        publish_version,
        methods=["POST"],
        response_model=PromptTemplateVersion,
    )
    router.add_api_route(
        "/templates/{prompt_template_id}/versions/{prompt_template_version_id}/retire",
        retire_version,
        methods=["POST"],
        response_model=PromptTemplateVersion,
    )
    router.add_api_route(
        "/models/{model_id}/assignments",
        list_model_assignments,
        methods=["GET"],
        response_model=ModelPromptAssignments,
    )
    router.add_api_route(
        "/models/{model_id}/assignments/{workflow_stage_id}",
        set_model_assignment,
        methods=["PUT"],
        response_model=ModelPromptAssignmentState,
    )
    return router
