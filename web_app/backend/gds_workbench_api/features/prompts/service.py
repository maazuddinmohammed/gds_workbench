"""Governed Prompt Library persistence."""

from collections.abc import AsyncGenerator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Literal, Never, Protocol
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from gds_workbench_api.features.prompts.contracts import (
    CreatePromptTemplateRequest,
    EffectivePromptSource,
    ModelPromptAssignments,
    ModelPromptAssignmentState,
    PromptAssignmentConflictError,
    PromptAssignmentTarget,
    PromptConflictError,
    PromptModelNotFoundError,
    PromptOwnershipScope,
    PromptStage,
    PromptStageCatalog,
    PromptStageVariable,
    PromptTemplateDetail,
    PromptTemplateFilters,
    PromptTemplateHeader,
    PromptTemplateMutationContext,
    PromptTemplateNotFoundError,
    PromptTemplatePage,
    PromptTemplateSummary,
    PromptTemplateVersion,
    SavePromptDraftRequest,
    SetModelPromptAssignmentRequest,
    UpdatePromptTemplateRequest,
)

_MAX_STAGE_VARIABLE_ROWS = 2000
_MAX_STAGE_VARIABLES = 100
_MAX_TEMPLATE_VERSIONS = 200

_STAGE_CATALOG_SQL = """
SELECT stage.workflow_stage_id,
       stage.model_workflow,
       stage.workflow_execution_mode,
       stage.workflow_stage_code,
       stage.workflow_stage_name,
       left(stage.workflow_stage_description, 2000) AS workflow_stage_description,
       stage.workflow_stage_order,
       variable.workflow_stage_variable_name AS variable_name,
       variable.workflow_stage_variable_resolver_key AS variable_resolver_key,
       variable.workflow_stage_variable_data_type AS variable_data_type,
       variable.workflow_stage_variable_is_required AS variable_is_required,
       left(variable.workflow_stage_variable_description, 2000) AS variable_description,
       variable.workflow_stage_variable_example AS variable_example,
       variable.workflow_stage_variable_order AS variable_order
  FROM application.workflow_stage AS stage
  LEFT JOIN application.workflow_stage_variable AS variable
    ON variable.workflow_stage_id = stage.workflow_stage_id
   AND variable.is_active
 WHERE stage.workflow_stage_is_agentic
   AND stage.is_active
 ORDER BY stage.model_workflow,
          stage.workflow_execution_mode NULLS FIRST,
          stage.workflow_stage_order,
          stage.workflow_stage_id,
          variable.workflow_stage_variable_order NULLS LAST,
          variable.workflow_stage_variable_id
 LIMIT %s
"""

_TEMPLATE_LIST_SQL = """
SELECT template.prompt_template_id,
       template.workflow_stage_id,
       stage.model_workflow,
       stage.workflow_execution_mode,
       stage.workflow_stage_code,
       stage.workflow_stage_name,
       template.prompt_template_ownership_scope,
       template.owner_tenant_id,
       template.prompt_template_code,
       template.prompt_template_name,
       left(template.prompt_template_description, 2000) AS prompt_template_description,
       template.is_active,
       latest.prompt_template_version_id AS latest_version_id,
       latest.prompt_template_version_number AS latest_version_number,
       latest.prompt_template_version_status AS latest_version_status,
       latest.prompt_template_digest AS latest_version_digest,
       latest.updated_time AS latest_version_updated_at,
       template.updated_time AS updated_at
  FROM application.prompt_template AS template
  JOIN application.workflow_stage AS stage
    ON stage.workflow_stage_id = template.workflow_stage_id
   AND stage.workflow_stage_is_agentic
   AND stage.is_active
  LEFT JOIN LATERAL (
       SELECT version.prompt_template_version_id,
              version.prompt_template_version_number,
              version.prompt_template_version_status,
              version.prompt_template_digest,
              version.updated_time
         FROM application.prompt_template_version AS version
        WHERE version.prompt_template_id = template.prompt_template_id
        ORDER BY version.prompt_template_version_number DESC,
                 version.prompt_template_version_id DESC
        LIMIT 1
  ) AS latest ON TRUE
 WHERE (
           (
               template.prompt_template_ownership_scope = 'global'
               AND template.owner_tenant_id IS NULL
           )
           OR (
               template.prompt_template_ownership_scope = 'tenant'
               AND template.owner_tenant_id = %s
           )
       )
   AND (%s::VARCHAR IS NULL OR stage.model_workflow = %s)
   AND (%s::VARCHAR IS NULL OR stage.workflow_execution_mode = %s)
   AND (%s::VARCHAR IS NULL OR stage.workflow_stage_code = %s)
   AND (%s::VARCHAR IS NULL OR latest.prompt_template_version_status = %s)
 ORDER BY stage.model_workflow,
          stage.workflow_execution_mode NULLS FIRST,
          stage.workflow_stage_order,
          lower(template.prompt_template_name),
          template.prompt_template_id
 LIMIT %s OFFSET %s
"""

_TEMPLATE_DETAIL_SQL = """
SELECT template.prompt_template_id,
       template.workflow_stage_id,
       stage.model_workflow,
       stage.workflow_execution_mode,
       stage.workflow_stage_code,
       stage.workflow_stage_name,
       template.prompt_template_ownership_scope,
       template.owner_tenant_id,
       template.prompt_template_code,
       template.prompt_template_name,
       left(template.prompt_template_description, 2000) AS prompt_template_description,
       template.is_active,
       latest.prompt_template_version_id AS latest_version_id,
       latest.prompt_template_version_number AS latest_version_number,
       latest.prompt_template_version_status AS latest_version_status,
       latest.prompt_template_digest AS latest_version_digest,
       latest.updated_time AS latest_version_updated_at,
       template.updated_time AS updated_at
  FROM application.prompt_template AS template
  JOIN application.workflow_stage AS stage
    ON stage.workflow_stage_id = template.workflow_stage_id
   AND stage.workflow_stage_is_agentic
   AND stage.is_active
  LEFT JOIN LATERAL (
       SELECT version.prompt_template_version_id,
              version.prompt_template_version_number,
              version.prompt_template_version_status,
              version.prompt_template_digest,
              version.updated_time
         FROM application.prompt_template_version AS version
        WHERE version.prompt_template_id = template.prompt_template_id
        ORDER BY version.prompt_template_version_number DESC,
                 version.prompt_template_version_id DESC
        LIMIT 1
  ) AS latest ON TRUE
 WHERE template.prompt_template_id = %s
   AND (
           (
               template.prompt_template_ownership_scope = 'global'
               AND template.owner_tenant_id IS NULL
           )
           OR (
               template.prompt_template_ownership_scope = 'tenant'
               AND template.owner_tenant_id = %s
           )
       )
"""

_STAGE_VARIABLES_SQL = """
SELECT variable.workflow_stage_variable_name AS name,
       variable.workflow_stage_variable_resolver_key AS resolver_key,
       variable.workflow_stage_variable_data_type AS data_type,
       variable.workflow_stage_variable_is_required AS is_required,
       left(variable.workflow_stage_variable_description, 2000) AS description,
       variable.workflow_stage_variable_example AS example,
       variable.workflow_stage_variable_order AS "order"
  FROM application.workflow_stage_variable AS variable
 WHERE variable.workflow_stage_id = %s
   AND variable.is_active
 ORDER BY variable.workflow_stage_variable_order,
          variable.workflow_stage_variable_id
 LIMIT %s
"""

_TEMPLATE_VERSIONS_SQL = """
SELECT version.prompt_template_version_id,
       version.prompt_template_id,
       version.workflow_stage_id,
       version.prompt_template_version_number,
       version.system_prompt_template,
       version.instruction_prompt_template,
       version.tool_instruction_prompt_template,
       version.prompt_template_digest,
       version.prompt_template_version_status,
       version.published_time AS published_at,
       version.retired_time AS retired_at,
       version.created_time AS created_at,
       version.updated_time AS updated_at
  FROM application.prompt_template_version AS version
 WHERE version.prompt_template_id = %s
 ORDER BY version.prompt_template_version_number DESC,
          version.prompt_template_version_id DESC
 LIMIT %s
"""

_SAVE_TEMPLATE_SQL = """
SELECT saved.prompt_template_id,
       saved.workflow_stage_id,
       saved.prompt_template_ownership_scope,
       saved.owner_tenant_id,
       saved.prompt_template_code,
       saved.prompt_template_name,
       left(saved.prompt_template_description, 2000) AS prompt_template_description,
       saved.is_active,
       saved.created_time AS created_at,
       saved.updated_time AS updated_at
  FROM application.save_prompt_template(
       %s::UUID,
       %s::UUID,
       %s::VARCHAR,
       %s::BIGINT,
       %s::BIGINT,
       %s::VARCHAR,
       %s::BIGINT,
       %s::VARCHAR,
       %s::VARCHAR,
       %s::TEXT,
       %s::BOOLEAN,
       %s::TIMESTAMPTZ
  ) AS saved
"""

_TEMPLATE_MUTATION_CONTEXT_SQL = """
SELECT template.prompt_template_id,
       template.workflow_stage_id,
       template.prompt_template_ownership_scope,
       template.owner_tenant_id,
       template.prompt_template_code
  FROM application.prompt_template AS template
 WHERE template.prompt_template_id = %s
   AND (
           (
               template.prompt_template_ownership_scope = 'global'
               AND template.owner_tenant_id IS NULL
           )
           OR (
               template.prompt_template_ownership_scope = 'tenant'
               AND template.owner_tenant_id = %s
           )
       )
"""

_SAVE_DRAFT_SQL = """
SELECT saved.prompt_template_version_id,
       saved.prompt_template_id,
       saved.workflow_stage_id,
       saved.prompt_template_version_number,
       saved.system_prompt_template,
       saved.instruction_prompt_template,
       saved.tool_instruction_prompt_template,
       saved.prompt_template_digest,
       saved.prompt_template_version_status,
       saved.published_time AS published_at,
       saved.retired_time AS retired_at,
       saved.created_time AS created_at,
       saved.updated_time AS updated_at
  FROM application.save_prompt_template_draft(
       %s::UUID,
       %s::UUID,
       %s::VARCHAR,
       %s::BIGINT,
       %s::BIGINT,
       %s::TEXT,
       %s::TEXT,
       %s::TEXT,
       %s::TIMESTAMPTZ
  ) AS saved
"""

_VERSION_BINDING_SQL = """
SELECT version.prompt_template_version_id
  FROM application.prompt_template_version AS version
 WHERE version.prompt_template_version_id = %s
   AND version.prompt_template_id = %s
   AND version.workflow_stage_id = %s
"""

_TRANSITION_VERSION_SQL = """
SELECT saved.prompt_template_version_id,
       saved.prompt_template_id,
       saved.workflow_stage_id,
       saved.prompt_template_version_number,
       saved.system_prompt_template,
       saved.instruction_prompt_template,
       saved.tool_instruction_prompt_template,
       saved.prompt_template_digest,
       saved.prompt_template_version_status,
       saved.published_time AS published_at,
       saved.retired_time AS retired_at,
       saved.created_time AS created_at,
       saved.updated_time AS updated_at
  FROM application.transition_prompt_template_version(
       %s::UUID,
       %s::UUID,
       %s::VARCHAR,
       %s::BIGINT,
       %s::VARCHAR,
       %s::VARCHAR
  ) AS saved
"""

_MODEL_BINDING_SQL = """
SELECT target_model.model_id,
       target_model.tenant_id
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_EFFECTIVE_ASSIGNMENTS_SQL = """
SELECT stage.workflow_stage_id,
       stage.model_workflow,
       stage.workflow_execution_mode,
       stage.workflow_stage_code,
       stage.workflow_stage_name,
       stage.workflow_stage_order,
       model_assignment.prompt_assignment_id AS model_assignment_id,
       model_assignment.prompt_assignment_scope AS model_assignment_scope,
       model_version.prompt_template_version_id AS model_version_id,
       model_version.prompt_template_version_number AS model_version_number,
       model_version.prompt_template_digest AS model_version_digest,
       model_template.prompt_template_id AS model_template_id,
       model_template.prompt_template_ownership_scope AS model_template_ownership_scope,
       model_template.owner_tenant_id AS model_owner_tenant_id,
       model_template.prompt_template_code AS model_template_code,
       model_template.prompt_template_name AS model_template_name,
       model_assignment.created_time AS model_assigned_at,
       global_assignment.prompt_assignment_id AS global_assignment_id,
       global_assignment.prompt_assignment_scope AS global_assignment_scope,
       global_version.prompt_template_version_id AS global_version_id,
       global_version.prompt_template_version_number AS global_version_number,
       global_version.prompt_template_digest AS global_version_digest,
       global_template.prompt_template_id AS global_template_id,
       global_template.prompt_template_ownership_scope AS global_template_ownership_scope,
       global_template.owner_tenant_id AS global_owner_tenant_id,
       global_template.prompt_template_code AS global_template_code,
       global_template.prompt_template_name AS global_template_name,
       global_assignment.created_time AS global_assigned_at
  FROM application.workflow_stage AS stage
  LEFT JOIN application.prompt_assignment AS model_assignment
    ON model_assignment.workflow_stage_id = stage.workflow_stage_id
   AND model_assignment.prompt_assignment_scope = 'model_default'
   AND model_assignment.model_id = %s
   AND model_assignment.is_active
  LEFT JOIN application.prompt_template_version AS model_version
    ON model_version.prompt_template_version_id =
       model_assignment.prompt_template_version_id
  LEFT JOIN application.prompt_template AS model_template
    ON model_template.prompt_template_id = model_version.prompt_template_id
  LEFT JOIN application.prompt_assignment AS global_assignment
    ON global_assignment.workflow_stage_id = stage.workflow_stage_id
   AND global_assignment.prompt_assignment_scope = 'global_default'
   AND global_assignment.model_id IS NULL
   AND global_assignment.is_active
  LEFT JOIN application.prompt_template_version AS global_version
    ON global_version.prompt_template_version_id =
       global_assignment.prompt_template_version_id
  LEFT JOIN application.prompt_template AS global_template
    ON global_template.prompt_template_id = global_version.prompt_template_id
 WHERE stage.workflow_stage_is_agentic
   AND stage.is_active
 ORDER BY stage.model_workflow,
          stage.workflow_execution_mode NULLS FIRST,
          stage.workflow_stage_order,
          stage.workflow_stage_id
 LIMIT %s
"""

_SET_MODEL_ASSIGNMENT_SQL = """
SELECT saved.prompt_assignment_id
  FROM application.set_prompt_assignment(
       %s::UUID,
       %s::UUID,
       %s::VARCHAR,
       %s::BIGINT,
       %s::VARCHAR,
       %s::BIGINT,
       %s::BIGINT,
       %s::BIGINT
  ) AS saved
"""


class PromptDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class PromptService(Protocol):
    async def list_stages(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> PromptStageCatalog: ...

    async def list_templates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        filters: PromptTemplateFilters,
        page_size: int,
        cursor: str | None,
    ) -> PromptTemplatePage: ...

    async def read_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
    ) -> PromptTemplateDetail: ...

    async def create_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        body: CreatePromptTemplateRequest,
    ) -> PromptTemplateHeader: ...

    async def update_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        body: UpdatePromptTemplateRequest,
    ) -> PromptTemplateHeader: ...

    async def save_draft(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        body: SavePromptDraftRequest,
    ) -> PromptTemplateVersion: ...

    async def publish_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        prompt_template_version_id: int,
    ) -> PromptTemplateVersion: ...

    async def retire_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        prompt_template_version_id: int,
    ) -> PromptTemplateVersion: ...

    async def list_model_assignments(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelPromptAssignments: ...

    async def set_model_assignment(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_stage_id: int,
        body: SetModelPromptAssignmentRequest,
    ) -> ModelPromptAssignmentState: ...


class DatabasePromptService:
    def __init__(
        self,
        *,
        database: PromptDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_stages(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> PromptStageCatalog:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            rows = await transaction.fetch_all(
                _STAGE_CATALOG_SQL,
                (_MAX_STAGE_VARIABLE_ROWS + 1,),
            )
        if len(rows) > _MAX_STAGE_VARIABLE_ROWS:
            raise InvalidRequestError("The Prompt Stage catalog exceeds its safe bound.")

        stages: list[PromptStage] = []
        stage_rows: dict[int, tuple[Mapping[str, Any], list[PromptStageVariable]]] = {}
        for row in rows:
            stage_id = row["workflow_stage_id"]
            current = stage_rows.get(stage_id)
            if current is None:
                current = (row, list[PromptStageVariable]())
                stage_rows[stage_id] = current
            if row["variable_name"] is not None:
                current[1].append(
                    PromptStageVariable(
                        name=row["variable_name"],
                        resolver_key=row["variable_resolver_key"],
                        data_type=row["variable_data_type"],
                        is_required=row["variable_is_required"],
                        description=row["variable_description"],
                        example=row["variable_example"],
                        order=row["variable_order"],
                    )
                )
        for row, variables in stage_rows.values():
            stages.append(
                PromptStage(
                    workflow_stage_id=row["workflow_stage_id"],
                    model_workflow=row["model_workflow"],
                    workflow_execution_mode=row["workflow_execution_mode"],
                    workflow_stage_code=row["workflow_stage_code"],
                    workflow_stage_name=row["workflow_stage_name"],
                    workflow_stage_description=row["workflow_stage_description"],
                    workflow_stage_order=row["workflow_stage_order"],
                    allowed_variables=tuple(variables),
                )
            )
        return PromptStageCatalog(tenant_id=tenant_id, items=tuple(stages))

    async def list_templates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        filters: PromptTemplateFilters,
        page_size: int,
        cursor: str | None,
    ) -> PromptTemplatePage:
        collection = ":".join(
            (
                "web_prompt_templates",
                str(tenant_id),
                filters.model_workflow or "-",
                filters.workflow_execution_mode or "-",
                filters.workflow_stage_code or "-",
                filters.version_status or "-",
                str(page_size),
            )
        )
        offset = self._cursors.decode(cursor, collection=collection)
        filter_parameters = (
            filters.model_workflow,
            filters.workflow_execution_mode,
            filters.workflow_stage_code,
            filters.version_status,
        )
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            rows = await transaction.fetch_all(
                _TEMPLATE_LIST_SQL,
                (
                    tenant_id,
                    filter_parameters[0],
                    filter_parameters[0],
                    filter_parameters[1],
                    filter_parameters[1],
                    filter_parameters[2],
                    filter_parameters[2],
                    filter_parameters[3],
                    filter_parameters[3],
                    page_size + 1,
                    offset,
                ),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return PromptTemplatePage(
            tenant_id=tenant_id,
            items=tuple(PromptTemplateSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
    ) -> PromptTemplateDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            template_row = await transaction.fetch_one(
                _TEMPLATE_DETAIL_SQL,
                (prompt_template_id, tenant_id),
            )
            if template_row is None:
                raise PromptTemplateNotFoundError()
            variable_rows = await transaction.fetch_all(
                _STAGE_VARIABLES_SQL,
                (template_row["workflow_stage_id"], _MAX_STAGE_VARIABLES + 1),
            )
            version_rows = await transaction.fetch_all(
                _TEMPLATE_VERSIONS_SQL,
                (prompt_template_id, _MAX_TEMPLATE_VERSIONS + 1),
            )
        if len(variable_rows) > _MAX_STAGE_VARIABLES or len(version_rows) > _MAX_TEMPLATE_VERSIONS:
            raise InvalidRequestError("The Prompt Library result exceeds its safe bound.")
        return PromptTemplateDetail(
            tenant_id=tenant_id,
            template=PromptTemplateSummary.model_validate(template_row),
            allowed_variables=tuple(
                PromptStageVariable.model_validate(row) for row in variable_rows
            ),
            versions=tuple(PromptTemplateVersion.model_validate(row) for row in version_rows),
        )

    async def create_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        body: CreatePromptTemplateRequest,
    ) -> PromptTemplateHeader:
        identity = _identity_arguments(principal)
        owner_tenant_id = tenant_id if body.prompt_template_ownership_scope == "tenant" else None
        async with self._write_transaction() as transaction:
            await self._authorize_mutation(
                transaction,
                principal,
                tenant_id=tenant_id,
                ownership_scope=body.prompt_template_ownership_scope,
            )
            row = await transaction.fetch_one(
                _SAVE_TEMPLATE_SQL,
                (
                    *identity,
                    None,
                    body.workflow_stage_id,
                    body.prompt_template_ownership_scope,
                    owner_tenant_id,
                    body.prompt_template_code,
                    body.prompt_template_name,
                    body.prompt_template_description,
                    body.is_active,
                    None,
                ),
            )
        if row is None:
            raise InvalidRequestError("The Prompt Template could not be saved.")
        return PromptTemplateHeader.model_validate(row)

    async def update_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        body: UpdatePromptTemplateRequest,
    ) -> PromptTemplateHeader:
        identity = _identity_arguments(principal)
        async with self._write_transaction() as transaction:
            context = await self._load_mutation_context(
                transaction,
                principal,
                tenant_id=tenant_id,
                prompt_template_id=prompt_template_id,
            )
            row = await transaction.fetch_one(
                _SAVE_TEMPLATE_SQL,
                (
                    *identity,
                    context.prompt_template_id,
                    context.workflow_stage_id,
                    context.prompt_template_ownership_scope,
                    context.owner_tenant_id,
                    context.prompt_template_code,
                    body.prompt_template_name,
                    body.prompt_template_description,
                    body.is_active,
                    body.expected_updated_at,
                ),
            )
        if row is None:
            raise InvalidRequestError("The Prompt Template could not be saved.")
        return PromptTemplateHeader.model_validate(row)

    async def save_draft(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        body: SavePromptDraftRequest,
    ) -> PromptTemplateVersion:
        identity = _identity_arguments(principal)
        async with self._write_transaction() as transaction:
            context = await self._load_mutation_context(
                transaction,
                principal,
                tenant_id=tenant_id,
                prompt_template_id=prompt_template_id,
            )
            row = await transaction.fetch_one(
                _SAVE_DRAFT_SQL,
                (
                    *identity,
                    context.prompt_template_id,
                    body.expected_prompt_template_version_id,
                    body.system_prompt_template,
                    body.instruction_prompt_template,
                    body.tool_instruction_prompt_template,
                    body.expected_updated_at,
                ),
            )
        if row is None:
            raise InvalidRequestError("The Prompt Template draft could not be saved.")
        return PromptTemplateVersion.model_validate(row)

    async def publish_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        prompt_template_version_id: int,
    ) -> PromptTemplateVersion:
        return await self._transition_version(
            principal,
            tenant_id=tenant_id,
            prompt_template_id=prompt_template_id,
            prompt_template_version_id=prompt_template_version_id,
            expected_status="draft",
            target_status="published",
        )

    async def retire_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        prompt_template_version_id: int,
    ) -> PromptTemplateVersion:
        return await self._transition_version(
            principal,
            tenant_id=tenant_id,
            prompt_template_id=prompt_template_id,
            prompt_template_version_id=prompt_template_version_id,
            expected_status="published",
            target_status="retired",
        )

    async def _transition_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
        prompt_template_version_id: int,
        expected_status: Literal["draft", "published"],
        target_status: Literal["published", "retired"],
    ) -> PromptTemplateVersion:
        identity = _identity_arguments(principal)
        async with self._write_transaction() as transaction:
            context = await self._load_mutation_context(
                transaction,
                principal,
                tenant_id=tenant_id,
                prompt_template_id=prompt_template_id,
            )
            version_binding = await transaction.fetch_one(
                _VERSION_BINDING_SQL,
                (
                    prompt_template_version_id,
                    context.prompt_template_id,
                    context.workflow_stage_id,
                ),
            )
            if version_binding is None:
                raise PromptTemplateNotFoundError()
            row = await transaction.fetch_one(
                _TRANSITION_VERSION_SQL,
                (
                    *identity,
                    prompt_template_version_id,
                    expected_status,
                    target_status,
                ),
            )
        if row is None:
            raise InvalidRequestError("The Prompt Template version could not be changed.")
        return PromptTemplateVersion.model_validate(row)

    async def list_model_assignments(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelPromptAssignments:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            model_row = await transaction.fetch_one(
                _MODEL_BINDING_SQL,
                (tenant_id, model_id),
            )
            if model_row is None:
                raise PromptModelNotFoundError()
            rows = await transaction.fetch_all(
                _EFFECTIVE_ASSIGNMENTS_SQL,
                (model_id, 201),
            )
        if len(rows) > 200:
            raise InvalidRequestError("The Prompt assignment result exceeds its safe bound.")
        return ModelPromptAssignments(
            tenant_id=tenant_id,
            model_id=model_id,
            items=tuple(_assignment_state(row) for row in rows),
        )

    async def set_model_assignment(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_stage_id: int,
        body: SetModelPromptAssignmentRequest,
    ) -> ModelPromptAssignmentState:
        identity = _identity_arguments(principal)
        async with self._write_transaction() as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            model_row = await transaction.fetch_one(
                _MODEL_BINDING_SQL,
                (tenant_id, model_id),
            )
            if model_row is None:
                raise PromptModelNotFoundError()
            await transaction.fetch_one(
                _SET_MODEL_ASSIGNMENT_SQL,
                (
                    *identity,
                    workflow_stage_id,
                    "model_default",
                    model_id,
                    body.prompt_template_version_id,
                    body.expected_prompt_assignment_id,
                ),
            )
            rows = await transaction.fetch_all(
                _EFFECTIVE_ASSIGNMENTS_SQL,
                (model_id, 201),
            )
        if len(rows) > 200:
            raise InvalidRequestError("The Prompt assignment result exceeds its safe bound.")
        for row in rows:
            if row["workflow_stage_id"] == workflow_stage_id:
                return _assignment_state(row)
        raise InvalidRequestError("The Prompt assignment Workflow Stage is unavailable.")

    @asynccontextmanager
    async def _write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        try:
            async with self._database.write_transaction() as transaction:
                yield transaction
        except DependencyUnavailableError as error:
            _raise_prompt_database_error(error)

    async def _load_mutation_context(
        self,
        transaction: ReadTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        prompt_template_id: int,
    ) -> PromptTemplateMutationContext:
        read_authorization = await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=ToolPolicy.TENANT_READ,
        )
        row = await transaction.fetch_one(
            _TEMPLATE_MUTATION_CONTEXT_SQL,
            (prompt_template_id, tenant_id),
        )
        if row is None:
            raise PromptTemplateNotFoundError()
        context = PromptTemplateMutationContext.model_validate(row)
        if context.prompt_template_ownership_scope == "global":
            if not read_authorization.principal.is_super_admin:
                raise AuthorizationDeniedError()
        else:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=context.owner_tenant_id or tenant_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
        return context

    async def _authorize_mutation(
        self,
        transaction: ReadTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        ownership_scope: PromptOwnershipScope,
    ) -> None:
        policy = (
            ToolPolicy.TENANT_MODEL_WRITE if ownership_scope == "tenant" else ToolPolicy.TENANT_READ
        )
        authorization = await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=policy,
        )
        if ownership_scope == "global" and not authorization.principal.is_super_admin:
            raise AuthorizationDeniedError()


def _identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    if principal.actor_kind is ActorKind.HUMAN:
        expected_type = "user"
    elif principal.actor_kind is ActorKind.WORKLOAD:
        expected_type = "service_principal"
    else:
        raise AuthorizationDeniedError()
    return principal.entra_tenant_id, principal.entra_object_id, expected_type


def _assignment_target(
    row: Mapping[str, Any],
    *,
    prefix: Literal["model", "global"],
) -> PromptAssignmentTarget | None:
    assignment_id = row[f"{prefix}_assignment_id"]
    if assignment_id is None:
        return None
    return PromptAssignmentTarget(
        prompt_assignment_id=assignment_id,
        prompt_assignment_scope=row[f"{prefix}_assignment_scope"],
        prompt_template_version_id=row[f"{prefix}_version_id"],
        prompt_template_version_number=row[f"{prefix}_version_number"],
        prompt_template_digest=row[f"{prefix}_version_digest"],
        prompt_template_id=row[f"{prefix}_template_id"],
        prompt_template_ownership_scope=row[f"{prefix}_template_ownership_scope"],
        owner_tenant_id=row[f"{prefix}_owner_tenant_id"],
        prompt_template_code=row[f"{prefix}_template_code"],
        prompt_template_name=row[f"{prefix}_template_name"],
        assigned_at=row[f"{prefix}_assigned_at"],
    )


def _assignment_state(row: Mapping[str, Any]) -> ModelPromptAssignmentState:
    model_assignment = _assignment_target(row, prefix="model")
    global_assignment = _assignment_target(row, prefix="global")
    effective = model_assignment or global_assignment
    source: EffectivePromptSource = (
        "model_default"
        if model_assignment is not None
        else "global_default"
        if global_assignment is not None
        else "none"
    )
    return ModelPromptAssignmentState(
        workflow_stage_id=row["workflow_stage_id"],
        model_workflow=row["model_workflow"],
        workflow_execution_mode=row["workflow_execution_mode"],
        workflow_stage_code=row["workflow_stage_code"],
        workflow_stage_name=row["workflow_stage_name"],
        workflow_stage_order=row["workflow_stage_order"],
        model_assignment=model_assignment,
        global_assignment=global_assignment,
        effective_source=source,
        effective_assignment=effective,
    )


def _raise_prompt_database_error(error: DependencyUnavailableError) -> Never:
    cause = error.__cause__
    diagnostic = getattr(cause, "diag", None)
    message = getattr(diagnostic, "message_primary", None)
    if not isinstance(message, str):
        raise error

    if "tenant_lock_required" in message:
        raise TenantLockRequiredError() from error
    if "tenant_locked" in message:
        raise TenantLockedError("another Principal") from error
    if "tenant_not_found" in message:
        raise TenantNotFoundError() from error
    if "requires Super Admin" in message or " denied:" in message:
        raise AuthorizationDeniedError() from error
    if (
        "stale_prompt_template" in message
        or "Prompt Template version transition conflict" in message
        or "Prompt Template code conflict" in message
        or "active assignments" in message
        or "Prompt Template draft does not exist" in message
    ):
        raise PromptConflictError() from error
    if (
        "stale_prompt_assignment" in message
        or "Prompt assignment does not exist" in message
        or "Prompt assignment requires a published active Prompt" in message
        or "Prompt does not belong to the Model owner Tenant" in message
        or "Prompt assignment scope is invalid" in message
        or "Global default requires a global Prompt" in message
    ):
        raise PromptAssignmentConflictError() from error
    if "Prompt assignment Model is unavailable" in message:
        raise PromptModelNotFoundError() from error
    if "Prompt Template" in message and "unavailable" in message:
        raise PromptTemplateNotFoundError() from error
    if (
        "Prompt Template content is invalid" in message
        or "Prompt Template ownership is invalid" in message
        or "requires an active agentic Workflow Stage" in message
        or "Prompt assignment requires an active agentic Workflow Stage" in message
    ):
        raise InvalidRequestError() from error
    raise error
