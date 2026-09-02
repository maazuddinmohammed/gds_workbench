"""Read-only stored SQL Code Generation database service."""

from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.models import ModelNotFoundError

from .contracts import (
    MAX_BULK_SQL_BYTES,
    MAX_SELECTED_ARTIFACTS,
    CodeGenerationTargetFilters,
    CodeGenerationTargetPage,
    CodeGenerationTargetSummary,
    GeneratedSqlArtifactDetail,
    GeneratedSqlArtifactNotFoundError,
    SqlArtifactBundleLimitExceededError,
    SqlArtifactDownload,
)

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_CODE_GENERATION_TARGETS_SQL: LiteralString = """
WITH target_model AS (
    SELECT target_model.model_id,
           target_model.model_revision
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
), requested_layer AS (
    SELECT layer.modeled_entity_type
      FROM (VALUES
               ('logical_entity'::VARCHAR(30)),
               ('dimensional_entity'::VARCHAR(30))
           ) AS layer(modeled_entity_type)
     WHERE %s::VARCHAR IS NULL
        OR layer.modeled_entity_type = %s
), current_context AS MATERIALIZED (
    SELECT context.*
      FROM target_model
      CROSS JOIN requested_layer AS layer
      CROSS JOIN LATERAL workflow.list_code_generation_target_context(
          target_model.model_id,
          layer.modeled_entity_type
      ) AS context
)
SELECT context.source_context -> 'target' AS target,
       context.modeled_entity_type AS entity_type,
       mapping_support.mapping_supports,
       mapping_support.mapping_support_count,
       mapping_support.mapping_support_count > 200 AS mapping_supports_truncated,
       source_system.source_systems,
       context.source_system_count,
       artifact.artifacts,
       artifact.artifact_count
  FROM target_model
  JOIN current_context AS context
    ON context.model_id = target_model.model_id
  CROSS JOIN LATERAL (
      SELECT coalesce(
                 jsonb_agg(support.document ORDER BY support.position)
                     FILTER (WHERE support.position <= 200),
                 '[]'::JSONB
             ) AS mapping_supports,
             count(*)::INTEGER AS mapping_support_count
        FROM (
            SELECT mapping_entry.position,
                   jsonb_build_object(
                       'mapping_object_id',
                           (mapping_entry.document ->> 'mapping_object_id')::BIGINT,
                       'source', jsonb_build_object(
                           'entity_type', context.modeled_entity_type,
                           'entity_id',
                               (mapping_entry.document -> 'entity' ->>
                                'entity_id')::BIGINT,
                           'entity_name',
                               mapping_entry.document -> 'entity' ->> 'entity_name'
                       ),
                       'source_system', jsonb_build_object(
                           'system_id', source.system_id,
                           'system_code', source.system_code,
                           'system_name', source.system_name
                       ),
                       'dependency_order',
                           (mapping_entry.document ->>
                            'object_dependency_order')::INTEGER
                   ) AS document
              FROM jsonb_array_elements(
                       context.source_context -> 'object_mappings'
                   ) WITH ORDINALITY AS mapping_entry(document, position)
              JOIN LATERAL (
                  SELECT (entry.document ->> 'source_system_id')::BIGINT AS system_id,
                         entry.document ->> 'system_code' AS system_code,
                         entry.document ->> 'system_name' AS system_name
                    FROM jsonb_array_elements(
                             context.source_context -> 'source_systems'
                         ) AS entry(document)
                   WHERE (entry.document ->> 'source_system_id')::BIGINT =
                         (mapping_entry.document ->> 'source_system_id')::BIGINT
                   LIMIT 1
              ) AS source ON TRUE
        ) AS support
  ) AS mapping_support
  CROSS JOIN LATERAL (
      SELECT coalesce(
                 jsonb_agg(
                     jsonb_build_object(
                         'system_id',
                             (entry.document ->> 'source_system_id')::BIGINT,
                         'system_code', entry.document ->> 'system_code',
                         'system_name', entry.document ->> 'system_name'
                     ) ORDER BY entry.position
                 ),
                 '[]'::JSONB
             ) AS source_systems
        FROM jsonb_array_elements(
                 context.source_context -> 'source_systems'
             ) WITH ORDINALITY AS entry(document, position)
  ) AS source_system
  CROSS JOIN LATERAL (
      SELECT coalesce(
                 jsonb_agg(
                     jsonb_build_object(
                         'generated_sql_artifact_id', generated.generated_code_id,
                         'artifact_name', generated.artifact_name,
                         'workflow_run_id', generated.workflow_run_id,
                         'generated_at', generated.updated_time,
                         'generated_code_status', generated.generated_code_status,
                         'source_system_codes', association.source_system_codes,
                         'artifact_is_current',
                             generated.generated_code_status = 'active'
                             AND generated.code_input_digest = context.code_input_digest
                     ) ORDER BY lower(btrim(generated.artifact_name)),
                                generated.generated_code_id
                 ),
                 '[]'::JSONB
             ) AS artifacts,
             count(*)::INTEGER AS artifact_count
        FROM workflow.generated_code AS generated
       CROSS JOIN LATERAL (
           SELECT coalesce(
                      jsonb_agg(
                          system.system_code
                          ORDER BY lower(btrim(system.system_code)), system.system_id
                      ) FILTER (
                          WHERE assignment.generated_code_source_system_status = 'active'
                      ),
                      '[]'::JSONB
                  ) AS source_system_codes
             FROM workflow.generated_code_source_system AS assignment
             JOIN core.system AS system
               ON system.system_id = assignment.source_system_id
            WHERE assignment.generated_code_id = generated.generated_code_id
       ) AS association
       WHERE generated.model_object_binding_id = (
                 context.source_context -> 'object_mappings' -> 0
                 ->> 'model_object_binding_id'
             )::BIGINT
         AND generated.artifact_type = 'sql_file'
  ) AS artifact
 WHERE (%s::BIGINT IS NULL
        OR (context.source_context -> 'target' ->> 'system_id')::BIGINT = %s)
   AND (
       %s::VARCHAR IS NULL
       OR lower(btrim(context.source_context -> 'target' ->> 'system_code')) = %s
   )
   AND (
       %s::BIGINT IS NULL
       OR EXISTS (
           SELECT 1
             FROM jsonb_array_elements(
                      context.source_context -> 'source_systems'
                  ) AS entry(document)
            WHERE (entry.document ->> 'source_system_id')::BIGINT = %s
       )
   )
   AND (
       %s::VARCHAR IS NULL
       OR EXISTS (
           SELECT 1
             FROM jsonb_array_elements(
                      context.source_context -> 'source_systems'
                  ) AS entry(document)
            WHERE lower(btrim(entry.document ->> 'system_code')) = %s
       )
   )
 ORDER BY lower(btrim(context.source_context -> 'target' ->> 'tenant_code')),
          lower(btrim(context.source_context -> 'target' ->> 'system_code')),
          lower(btrim(context.source_context -> 'target' ->> 'object_schema')),
          lower(btrim(context.source_context -> 'target' ->> 'object_name')),
          context.object_id,
          context.modeled_entity_type
 LIMIT %s OFFSET %s
"""

_GENERATED_SQL_ARTIFACT_DETAIL_SQL: LiteralString = """
SELECT artifact.generated_code_id AS generated_sql_artifact_id,
       artifact.artifact_name,
       target_model.model_id,
       coalesce(
           current_context.source_context -> 'target',
           jsonb_build_object(
               'object_id', target_object.object_id,
               'source_tenant_id', target_source_tenant.tenant_id,
               'source_tenant_code', target_source_tenant.tenant_code,
               'source_tenant_name', target_source_tenant.tenant_name,
               'tenant_id', target_tenant.tenant_id,
               'tenant_code', target_tenant.tenant_code,
               'tenant_name', target_tenant.tenant_name,
               'system_id', target_system.system_id,
               'system_code', target_system.system_code,
               'system_name', target_system.system_name,
               'connection_id', target_connection.connection_id,
               'connection_code', target_connection.connection_code,
               'object_schema', target_object.object_schema,
               'object_name', target_object.object_name,
               'zone_code', lower(btrim(target_zone.zone_code))
           )
       ) AS target,
       binding.modeled_entity_type AS entity_type,
       source_system.source_systems,
       source_system.source_system_count,
       mapping_support.mapping_supports,
       mapping_support.mapping_support_count,
       mapping_support.mapping_support_count > 200 AS mapping_supports_truncated,
       coalesce(
           artifact.generated_code_status = 'active'
           AND current_context.code_input_digest = artifact.code_input_digest,
           FALSE
       ) AS artifact_is_current,
       artifact.generated_code_status,
       CASE
           WHEN guide_version.sql_generation_guide_version_id IS NULL THEN NULL
           ELSE jsonb_build_object(
               'sql_generation_guide_id', guide.sql_generation_guide_id,
               'sql_generation_guide_code', guide.sql_generation_guide_code,
               'sql_generation_guide_name', guide.sql_generation_guide_name,
               'guide_is_active', guide.is_active,
               'sql_generation_guide_version_id',
                   guide_version.sql_generation_guide_version_id,
               'sql_generation_guide_version_number',
                   guide_version.sql_generation_guide_version_number,
               'sql_generation_guide_version_status',
                   guide_version.sql_generation_guide_version_status,
               'sql_generation_guide_digest',
                   guide_version.sql_generation_guide_digest
           )
       END AS guide,
       artifact.workflow_run_id,
       CASE
           WHEN generator.principal_id IS NULL THEN NULL
           ELSE jsonb_build_object(
               'generator_code', generating_run.agent_sdk_code,
               'generator_version', NULL,
               'generated_by_display_name', generator.principal_display_name
           )
       END AS generator,
       artifact.updated_time AS generated_at,
       artifact.generated_code_content AS generated_sql,
       octet_length(artifact.generated_code_content)::INTEGER
           AS generated_sql_byte_count
  FROM workflow.generated_code AS artifact
  JOIN workflow.model_object_binding AS binding
    ON binding.model_object_binding_id = artifact.model_object_binding_id
  JOIN model.model AS target_model
    ON target_model.model_id = binding.model_id
  JOIN core.object AS target_object
    ON target_object.object_id = binding.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN reference.zone AS target_zone
    ON target_zone.zone_id = target_object.zone_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_connection.tenant_id
  JOIN core.tenant AS target_source_tenant
    ON target_source_tenant.tenant_id = target_object.source_tenant_id
  LEFT JOIN LATERAL workflow.list_code_generation_target_context(
      binding.model_id,
      binding.modeled_entity_type
  ) AS current_context
    ON current_context.object_id = binding.object_id
  LEFT JOIN application.workflow_run AS generating_run
    ON generating_run.workflow_run_id = artifact.workflow_run_id
   AND generating_run.model_id = binding.model_id
   AND generating_run.model_workflow = 'code_generation'
  LEFT JOIN application.sql_generation_guide AS guide
    ON guide.sql_generation_guide_id = generating_run.sql_generation_guide_id
  LEFT JOIN application.sql_generation_guide_version AS guide_version
    ON guide_version.sql_generation_guide_version_id =
       generating_run.sql_generation_guide_version_id
   AND guide_version.sql_generation_guide_id = generating_run.sql_generation_guide_id
   AND guide_version.sql_generation_guide_digest =
       generating_run.sql_generation_guide_digest
  LEFT JOIN security.principal AS generator
    ON generator.principal_id = generating_run.actor_principal_id
  CROSS JOIN LATERAL (
      SELECT coalesce(
                 jsonb_agg(support.document ORDER BY support.position)
                     FILTER (WHERE support.position <= 200),
                 '[]'::JSONB
             ) AS mapping_supports,
             count(*)::INTEGER AS mapping_support_count
        FROM (
            SELECT mapping_entry.position,
                   jsonb_build_object(
                       'mapping_object_id',
                           (mapping_entry.document ->> 'mapping_object_id')::BIGINT,
                       'source', jsonb_build_object(
                           'entity_type', binding.modeled_entity_type,
                           'entity_id',
                               (mapping_entry.document -> 'entity' ->>
                                'entity_id')::BIGINT,
                           'entity_name',
                               mapping_entry.document -> 'entity' ->> 'entity_name'
                       ),
                       'source_system', jsonb_build_object(
                           'system_id', source.system_id,
                           'system_code', source.system_code,
                           'system_name', source.system_name
                       ),
                       'dependency_order',
                           (mapping_entry.document ->>
                            'object_dependency_order')::INTEGER
                   ) AS document
              FROM jsonb_array_elements(
                       coalesce(
                           current_context.source_context -> 'object_mappings',
                           '[]'::JSONB
                       )
                   ) WITH ORDINALITY AS mapping_entry(document, position)
              JOIN LATERAL (
                  SELECT (entry.document ->> 'source_system_id')::BIGINT AS system_id,
                         entry.document ->> 'system_code' AS system_code,
                         entry.document ->> 'system_name' AS system_name
                    FROM jsonb_array_elements(
                             current_context.source_context -> 'source_systems'
                         ) AS entry(document)
                   WHERE (entry.document ->> 'source_system_id')::BIGINT =
                         (mapping_entry.document ->> 'source_system_id')::BIGINT
                   LIMIT 1
              ) AS source ON TRUE
        ) AS support
  ) AS mapping_support
  CROSS JOIN LATERAL (
      SELECT coalesce(
                 jsonb_agg(
                     jsonb_build_object(
                         'system_id', system.system_id,
                         'system_code', system.system_code,
                         'system_name', system.system_name
                     ) ORDER BY lower(btrim(system.system_code)), system.system_id
                 ) FILTER (
                     WHERE assignment.generated_code_source_system_status = 'active'
                 ),
                 '[]'::JSONB
             ) AS source_systems,
             count(*) FILTER (
                 WHERE assignment.generated_code_source_system_status = 'active'
             )::INTEGER AS source_system_count
        FROM workflow.generated_code_source_system AS assignment
        JOIN core.system AS system
          ON system.system_id = assignment.source_system_id
       WHERE assignment.generated_code_id = artifact.generated_code_id
  ) AS source_system
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND artifact.generated_code_id = %s
   AND artifact.artifact_type = 'sql_file'
"""

_GENERATED_SQL_DOWNLOAD_BOUNDS_SQL: LiteralString = """
SELECT count(*)::INTEGER AS artifact_count,
       coalesce(sum(octet_length(artifact.generated_code_content)), 0)::BIGINT
           AS total_sql_bytes
  FROM workflow.generated_code AS artifact
  JOIN workflow.model_object_binding AS binding
    ON binding.model_object_binding_id = artifact.model_object_binding_id
  JOIN model.model AS target_model
    ON target_model.model_id = binding.model_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND artifact.generated_code_id = ANY(%s::BIGINT[])
   AND artifact.artifact_type = 'sql_file'
"""

_GENERATED_SQL_DOWNLOAD_SQL: LiteralString = """
SELECT artifact.generated_code_id AS generated_sql_artifact_id,
       artifact.artifact_name,
       jsonb_build_object(
           'object_id', target_object.object_id,
           'source_tenant_id', target_source_tenant.tenant_id,
           'source_tenant_code', target_source_tenant.tenant_code,
           'source_tenant_name', target_source_tenant.tenant_name,
           'tenant_id', target_tenant.tenant_id,
           'tenant_code', target_tenant.tenant_code,
           'tenant_name', target_tenant.tenant_name,
           'system_id', target_system.system_id,
           'system_code', target_system.system_code,
           'system_name', target_system.system_name,
           'connection_id', target_connection.connection_id,
           'connection_code', target_connection.connection_code,
           'object_schema', target_object.object_schema,
           'object_name', target_object.object_name,
           'zone_code', lower(btrim(target_zone.zone_code))
       ) AS target,
       binding.modeled_entity_type AS entity_type,
       artifact.generated_code_content AS generated_sql,
       octet_length(artifact.generated_code_content)::INTEGER
           AS generated_sql_byte_count
  FROM workflow.generated_code AS artifact
  JOIN workflow.model_object_binding AS binding
    ON binding.model_object_binding_id = artifact.model_object_binding_id
  JOIN model.model AS target_model
    ON target_model.model_id = binding.model_id
  JOIN core.object AS target_object
    ON target_object.object_id = binding.object_id
  JOIN core.connection AS target_connection
    ON target_connection.connection_id = target_object.connection_id
  JOIN core.system AS target_system
    ON target_system.system_id = target_connection.system_id
  JOIN reference.zone AS target_zone
    ON target_zone.zone_id = target_object.zone_id
  JOIN core.tenant AS target_tenant
    ON target_tenant.tenant_id = target_connection.tenant_id
  JOIN core.tenant AS target_source_tenant
    ON target_source_tenant.tenant_id = target_object.source_tenant_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND artifact.generated_code_id = ANY(%s::BIGINT[])
   AND artifact.artifact_type = 'sql_file'
 ORDER BY array_position(%s::BIGINT[], artifact.generated_code_id)
"""


class CodeGenerationService(Protocol):
    async def list_targets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: CodeGenerationTargetFilters,
        page_size: int,
        cursor: str | None,
    ) -> CodeGenerationTargetPage: ...

    async def read_artifact(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_id: int,
    ) -> GeneratedSqlArtifactDetail: ...

    async def read_artifacts_for_download(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_ids: tuple[int, ...],
    ) -> tuple[SqlArtifactDownload, ...]: ...


class CodeGenerationReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseCodeGenerationService:
    def __init__(
        self,
        *,
        database: CodeGenerationReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_targets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: CodeGenerationTargetFilters,
        page_size: int,
        cursor: str | None,
    ) -> CodeGenerationTargetPage:
        filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
        collection = (
            f"web_code_generation_targets:{tenant_id}:{model_id}:{page_size}:{filter_digest}"
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _CODE_GENERATION_TARGETS_SQL,
                (
                    tenant_id,
                    model_id,
                    filters.entity_type,
                    filters.entity_type,
                    filters.system_id,
                    filters.system_id,
                    filters.system_code,
                    filters.system_code,
                    filters.source_system_id,
                    filters.source_system_id,
                    filters.source_system_code,
                    filters.source_system_code,
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
        return CodeGenerationTargetPage(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                CodeGenerationTargetSummary.model_validate(row, strict=False)
                for row in rows[:page_size]
            ),
            next_cursor=next_cursor,
        )

    async def read_artifact(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_id: int,
    ) -> GeneratedSqlArtifactDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await transaction.fetch_one(
                _GENERATED_SQL_ARTIFACT_DETAIL_SQL,
                (tenant_id, model_id, generated_sql_artifact_id),
            )
        if row is None:
            raise GeneratedSqlArtifactNotFoundError()
        return GeneratedSqlArtifactDetail.model_validate(row, strict=False)

    async def read_artifacts_for_download(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_ids: tuple[int, ...],
    ) -> tuple[SqlArtifactDownload, ...]:
        if (
            not 1 <= len(generated_sql_artifact_ids) <= MAX_SELECTED_ARTIFACTS
            or any(identifier <= 0 for identifier in generated_sql_artifact_ids)
            or len(set(generated_sql_artifact_ids)) != len(generated_sql_artifact_ids)
        ):
            raise InvalidRequestError(
                "Generated SQL artifact IDs must be unique positive integers."
            )
        selected_ids = list(generated_sql_artifact_ids)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            bounds = await transaction.fetch_one(
                _GENERATED_SQL_DOWNLOAD_BOUNDS_SQL,
                (tenant_id, model_id, selected_ids),
            )
            if bounds is None or bounds["artifact_count"] != len(selected_ids):
                raise GeneratedSqlArtifactNotFoundError()
            if bounds["total_sql_bytes"] > MAX_BULK_SQL_BYTES:
                raise SqlArtifactBundleLimitExceededError()
            rows = await transaction.fetch_all(
                _GENERATED_SQL_DOWNLOAD_SQL,
                (tenant_id, model_id, selected_ids, selected_ids),
            )
        if tuple(row["generated_sql_artifact_id"] for row in rows) != (generated_sql_artifact_ids):
            raise GeneratedSqlArtifactNotFoundError()
        return tuple(SqlArtifactDownload.model_validate(row, strict=False) for row in rows)
