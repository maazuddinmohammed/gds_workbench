"""Bounded, read-only Mapping authoring preparation and materialization."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.mapping_contracts import (
    AttributeMappingTransformationDocumentV1,
    MappingPackageDocumentV1,
    ObjectMappingTransformationDocumentV1,
    reject_secret_shaped_values,
)
from gds_etl_workbench.domain.mapping_profiles import (
    MAPPING_STANDARD_PROFILE_KEY,
    MAPPING_STANDARD_PROFILE_VERSION,
    mapping_package_digest,
    resolve_mapping_profile_schema_digest,
)
from gds_etl_workbench.domain.modeling_records import (
    MappingAttributeRecord,
    MappingObjectRecord,
)
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation, ReadTransaction

from .common import POLICY, authorize_model_read

type ModeledEntityType = Literal["logical_entity", "dimensional_entity"]
type Route = Literal["logical_to_silver", "dimensional_to_gold"]
type Zone = Literal["bronze", "silver", "gold"]

_MAX_HEADERS = 64
_MAX_ATTRIBUTES = 5_000
_MAX_SOURCES = 128

# This is intentionally one repeatable-read projection. It never touches the
# Application schema and uses only the existing MCP runtime SELECT surface.
_AUTHORING_CONTEXT_SQL: LiteralString = r"""
/* mapping_authoring_context_v1 */
WITH requested AS MATERIALIZED (
    SELECT %s::BIGINT AS model_id,
           %s::BIGINT AS tenant_id,
           %s::BIGINT AS model_revision,
           %s::VARCHAR(30) AS modeled_entity_type,
           %s::BIGINT AS target_object_id,
           %s::BIGINT AS source_system_id
), eligible_object AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested
      CROSS JOIN LATERAL workflow.list_model_object_eligibility(
          requested.model_id
      ) AS eligibility
), eligible_target AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested
      JOIN eligible_object AS eligibility
        ON eligibility.model_id = requested.model_id
     WHERE eligibility.object_id = requested.target_object_id
       AND CASE requested.modeled_entity_type
               WHEN 'logical_entity'
                   THEN eligibility.is_logical_mapping_target_eligible
               WHEN 'dimensional_entity'
                   THEN eligibility.is_dimensional_mapping_target_eligible
               ELSE FALSE
           END
), target_document AS MATERIALIZED (
    SELECT jsonb_build_object(
               'object_id', physical_object.object_id,
               'tenant_code', object_tenant.tenant_code,
               'tenant_catalog', object_tenant.tenant_catalog,
               'system_code', target_system.system_code,
               'connection_code', target_connection.connection_code,
               'object_schema', physical_object.object_schema,
               'object_name', physical_object.object_name,
               'object_description', physical_object.object_description,
               'zone', lower(btrim(zone.zone_code)),
               'is_locked', physical_object.is_locked,
               'attributes', attributes.documents
           ) AS document
      FROM requested
      JOIN eligible_target
        ON eligible_target.model_id = requested.model_id
      JOIN core.object AS physical_object
        ON physical_object.object_id = eligible_target.object_id
       AND physical_object.is_active
      JOIN core.connection AS target_connection
        ON target_connection.connection_id = physical_object.connection_id
       AND target_connection.is_active
      JOIN core.system AS target_system
        ON target_system.system_id = target_connection.system_id
       AND target_system.is_active
      JOIN core.tenant AS object_tenant
        ON object_tenant.tenant_id = eligible_target.object_tenant_id
       AND object_tenant.is_active
      JOIN reference.zone AS zone
        ON zone.zone_id = physical_object.zone_id
       AND zone.is_active
      CROSS JOIN LATERAL (
          SELECT coalesce(
                     jsonb_agg(
                         jsonb_build_object(
                             'attribute_id', attribute.attribute_id,
                             'attribute_name', attribute.attribute_name,
                             'data_type', attribute.attribute_data_type,
                             'nullable', attribute.attribute_nullability,
                             'ordinal', attribute.attribute_ordinal_position,
                             'definition', attribute.attribute_description
                         ) ORDER BY attribute.attribute_ordinal_position,
                                    attribute.attribute_id
                     ),
                     '[]'::JSONB
                 ) AS documents
            FROM (
                SELECT *
                  FROM core.attribute
                 WHERE object_id = physical_object.object_id
                   AND is_active
                 ORDER BY attribute_ordinal_position, attribute_id
                 LIMIT 5001
            ) AS attribute
      ) AS attributes
), source_dependency AS MATERIALIZED (
    SELECT dependency.mapping_source_system_dependency_id,
           dependency.source_system_dependency_order,
           dependency.mapping_source_system_dependency_status,
           dependency.mapping_source_system_dependency_is_locked,
           source_system.system_id,
           source_system.system_code,
           source_system.system_name
      FROM requested
      JOIN workflow.mapping_source_system_dependency AS dependency
        ON dependency.model_id = requested.model_id
       AND dependency.modeled_entity_type = requested.modeled_entity_type
       AND dependency.source_system_id = requested.source_system_id
       AND dependency.mapping_source_system_dependency_status = 'active'
      JOIN core.system AS source_system
        ON source_system.system_id = dependency.source_system_id
       AND source_system.is_active
), entity_candidate AS MATERIALIZED (
    SELECT logical_entity.logical_entity_id AS modeled_entity_id,
           logical_entity.logical_entity_name AS modeled_entity_name,
           logical_entity.logical_entity_definition AS modeled_entity_definition,
           logical_entity.logical_entity_type AS modeled_entity_kind,
           logical_entity.logical_entity_grain AS grain,
           logical_entity.logical_entity_dependency_order AS dependency_order,
           logical_entity.logical_entity_is_locked AS is_locked
      FROM requested
      JOIN workflow.logical_entity AS logical_entity
        ON logical_entity.model_id = requested.model_id
       AND requested.modeled_entity_type = 'logical_entity'
       AND logical_entity.logical_entity_status = 'active'
     WHERE EXISTS (
           SELECT 1
             FROM workflow.logical_entity_source_mapping AS source_binding
             JOIN core.object AS source_object
               ON source_object.object_id = source_binding.source_object_id
              AND source_object.is_active
             JOIN eligible_object AS source_eligibility
               ON source_eligibility.model_id = requested.model_id
              AND source_eligibility.object_id = source_object.object_id
              AND source_eligibility.is_bronze_source_eligible
             JOIN core.connection AS source_connection
               ON source_connection.connection_id = source_object.connection_id
              AND source_connection.is_active
            WHERE source_binding.model_id = requested.model_id
              AND source_binding.logical_entity_id = logical_entity.logical_entity_id
              AND source_binding.support_source_type = 'object'
              AND source_binding.logical_entity_source_mapping_status = 'active'
              AND (
                  source_connection.system_id = requested.source_system_id
                  OR EXISTS (
                      SELECT 1
                        FROM core.ingestion_object_mapping AS ingestion
                        JOIN core.object AS original_object
                          ON original_object.object_id = ingestion.source_object_id
                         AND original_object.is_active
                        JOIN core.connection AS original_connection
                          ON original_connection.connection_id =
                             original_object.connection_id
                         AND original_connection.is_active
                       WHERE ingestion.target_object_id = source_object.object_id
                         AND ingestion.is_active
                         AND original_connection.system_id =
                             requested.source_system_id
                  )
              )
       )
    UNION ALL
    SELECT dimensional_entity.dimensional_entity_id,
           dimensional_entity.dimensional_entity_name,
           dimensional_entity.dimensional_entity_definition,
           dimensional_entity.dimensional_entity_type,
           dimensional_entity.dimensional_entity_grain_definition,
           dimensional_entity.dimensional_entity_dependency_order,
           dimensional_entity.dimensional_entity_is_locked
      FROM requested
      JOIN workflow.dimensional_entity AS dimensional_entity
        ON dimensional_entity.model_id = requested.model_id
       AND requested.modeled_entity_type = 'dimensional_entity'
       AND dimensional_entity.dimensional_entity_status = 'active'
     WHERE EXISTS (
           SELECT 1
             FROM workflow.dimensional_entity_source_mapping AS source_binding
             JOIN workflow.mapping_object AS prior_mapping
               ON prior_mapping.model_id = requested.model_id
              AND prior_mapping.modeled_entity_type = 'logical_entity'
              AND prior_mapping.object_id = source_binding.source_object_id
              AND prior_mapping.source_system_id = requested.source_system_id
              AND prior_mapping.object_mapping_status = 'active'
              AND prior_mapping.mapping_package_document IS NOT NULL
              AND prior_mapping.object_mapping_transformation_document IS NOT NULL
             JOIN eligible_object AS source_eligibility
               ON source_eligibility.model_id = requested.model_id
              AND source_eligibility.object_id = source_binding.source_object_id
              AND source_eligibility.is_dimensional_source_eligible
            WHERE source_binding.model_id = requested.model_id
              AND source_binding.dimensional_entity_id =
                  dimensional_entity.dimensional_entity_id
              AND source_binding.support_source_type = 'object'
              AND source_binding.dimensional_entity_source_mapping_status = 'active'
       )
), header_document AS MATERIALIZED (
    SELECT jsonb_build_object(
               'header_ref', 'header_' || candidate.modeled_entity_id::TEXT,
               'mapping_object_id', existing.mapping_object_id,
               'modeled_entity_id', candidate.modeled_entity_id,
               'modeled_entity_name', candidate.modeled_entity_name,
               'modeled_entity_definition', candidate.modeled_entity_definition,
               'modeled_entity_kind', candidate.modeled_entity_kind,
               'grain', candidate.grain,
               'dependency_order', candidate.dependency_order,
               'is_locked', candidate.is_locked OR coalesce(
                   existing.object_mapping_is_locked,
                   FALSE
               ),
               'attributes', modeled_attributes.documents,
               'sources', sources.documents,
               'existing', CASE WHEN existing.mapping_object_id IS NULL THEN NULL
                   ELSE jsonb_build_object(
                       'object_dependency_order', existing.object_dependency_order,
                       'artifact_type', existing.artifact_type,
                       'artifact_generation_instructions',
                           existing.artifact_generation_instructions,
                       'mapping_profile_key', existing.mapping_profile_key,
                       'mapping_profile_version', existing.mapping_profile_version,
                       'mapping_package_document', existing.mapping_package_document,
                       'object_mapping_transformation_document',
                           existing.object_mapping_transformation_document,
                       'status', existing.object_mapping_status,
                       'is_locked', existing.object_mapping_is_locked,
                       'attributes', existing_attributes.documents
                   )
               END
           ) AS document,
           candidate.modeled_entity_id
      FROM requested
      JOIN entity_candidate AS candidate ON TRUE
      LEFT JOIN workflow.mapping_object AS existing
        ON existing.model_id = requested.model_id
       AND existing.object_id = requested.target_object_id
       AND existing.source_system_id = requested.source_system_id
       AND existing.modeled_entity_type = requested.modeled_entity_type
       AND (
           (requested.modeled_entity_type = 'logical_entity'
            AND existing.logical_entity_id = candidate.modeled_entity_id)
           OR
           (requested.modeled_entity_type = 'dimensional_entity'
            AND existing.dimensional_entity_id = candidate.modeled_entity_id)
       )
      CROSS JOIN LATERAL (
          SELECT coalesce(jsonb_agg(item.document ORDER BY item.ordinal), '[]'::JSONB)
                     AS documents
            FROM (
                SELECT logical_attribute.logical_attribute_ordinal_position AS ordinal,
                       jsonb_build_object(
                           'modeled_attribute_id',
                               logical_attribute.logical_attribute_id,
                           'name', logical_attribute.logical_attribute_name,
                           'definition', logical_attribute.logical_attribute_definition,
                           'data_type', logical_attribute.logical_attribute_data_type,
                           'nullable', logical_attribute.logical_attribute_is_nullable,
                           'ordinal', logical_attribute.logical_attribute_ordinal_position
                       ) AS document
                  FROM workflow.logical_attribute AS logical_attribute
                 WHERE requested.modeled_entity_type = 'logical_entity'
                   AND logical_attribute.model_id = requested.model_id
                   AND logical_attribute.logical_entity_id =
                       candidate.modeled_entity_id
                   AND logical_attribute.logical_attribute_status = 'active'
                UNION ALL
                SELECT dimensional_attribute.dimensional_attribute_ordinal_position,
                       jsonb_build_object(
                           'modeled_attribute_id',
                               dimensional_attribute.dimensional_attribute_id,
                           'name', dimensional_attribute.dimensional_attribute_name,
                           'definition',
                               dimensional_attribute.dimensional_attribute_definition,
                           'data_type',
                               dimensional_attribute.dimensional_attribute_data_type,
                           'nullable',
                               dimensional_attribute.dimensional_attribute_is_nullable,
                           'ordinal',
                               dimensional_attribute.dimensional_attribute_ordinal_position
                       )
                  FROM workflow.dimensional_attribute AS dimensional_attribute
                 WHERE requested.modeled_entity_type = 'dimensional_entity'
                   AND dimensional_attribute.model_id = requested.model_id
                   AND dimensional_attribute.dimensional_entity_id =
                       candidate.modeled_entity_id
                   AND dimensional_attribute.dimensional_attribute_status = 'active'
                 ORDER BY ordinal
                 LIMIT 5001
            ) AS item
      ) AS modeled_attributes
      CROSS JOIN LATERAL (
          SELECT coalesce(
                     jsonb_agg(source_item.document ORDER BY source_item.source_mapping_id),
                     '[]'::JSONB
                 ) AS documents
            FROM (
                SELECT source.source_mapping_id,
                       jsonb_build_object(
                           'source_mapping_id', source.source_mapping_id,
                           'role', source.role,
                           'rationale', source.rationale,
                           'object', jsonb_build_object(
                               'object_id', source_object.object_id,
                               'tenant_code', source_tenant.tenant_code,
                               'tenant_catalog', source_tenant.tenant_catalog,
                               'system_code', source_system.system_code,
                               'connection_code', source_connection.connection_code,
                               'object_schema', source_object.object_schema,
                               'object_name', source_object.object_name,
                               'zone', lower(btrim(source_zone.zone_code)),
                               'batch_attribute_id', batch_attribute.attribute_id,
                               'attributes', source_attributes.documents,
                               'ingestion_mapping_ids', lineage.ingestion_ids,
                               'prior_mapping_ids', lineage.prior_ids
                           )
                       ) AS document
                  FROM (
                      SELECT logical_source.logical_entity_source_mapping_id
                                 AS source_mapping_id,
                             logical_source.source_object_id,
                             'support'::TEXT AS role,
                             logical_source.logical_entity_source_mapping_rationale
                                 AS rationale
                        FROM workflow.logical_entity_source_mapping AS logical_source
                       WHERE requested.modeled_entity_type = 'logical_entity'
                         AND logical_source.model_id = requested.model_id
                         AND logical_source.logical_entity_id =
                             candidate.modeled_entity_id
                         AND logical_source.support_source_type = 'object'
                         AND logical_source.logical_entity_source_mapping_status = 'active'
                      UNION ALL
                      SELECT dimensional_source.dimensional_entity_source_mapping_id,
                             dimensional_source.source_object_id,
                             dimensional_source.dimensional_entity_source_role,
                             dimensional_source.dimensional_entity_source_mapping_rationale
                        FROM workflow.dimensional_entity_source_mapping
                             AS dimensional_source
                       WHERE requested.modeled_entity_type = 'dimensional_entity'
                         AND dimensional_source.model_id = requested.model_id
                         AND dimensional_source.dimensional_entity_id =
                             candidate.modeled_entity_id
                         AND dimensional_source.support_source_type = 'object'
                         AND dimensional_source.dimensional_entity_source_mapping_status =
                             'active'
                  ) AS source
                  JOIN core.object AS source_object
                    ON source_object.object_id = source.source_object_id
                   AND source_object.is_active
                  JOIN eligible_object AS source_eligibility
                    ON source_eligibility.model_id = requested.model_id
                   AND source_eligibility.object_id = source_object.object_id
                   AND CASE requested.modeled_entity_type
                           WHEN 'logical_entity'
                               THEN source_eligibility.is_bronze_source_eligible
                           WHEN 'dimensional_entity'
                               THEN source_eligibility.is_dimensional_source_eligible
                           ELSE FALSE
                       END
                  JOIN core.connection AS source_connection
                    ON source_connection.connection_id = source_object.connection_id
                   AND source_connection.is_active
                  JOIN core.system AS source_system
                    ON source_system.system_id = source_connection.system_id
                   AND source_system.is_active
                  JOIN reference.zone AS source_zone
                    ON source_zone.zone_id = source_object.zone_id
                   AND source_zone.is_active
                  JOIN core.tenant AS source_tenant
                    ON source_tenant.tenant_id = source_eligibility.object_tenant_id
                   AND source_tenant.is_active
                  LEFT JOIN core.attribute AS batch_attribute
                    ON batch_attribute.object_id = source_object.object_id
                   AND batch_attribute.attribute_name = source_object.batch_attribute_name
                   AND batch_attribute.is_active
                  CROSS JOIN LATERAL (
                      SELECT coalesce(
                                 jsonb_agg(
                                     jsonb_build_object(
                                         'attribute_id', attribute.attribute_id,
                                         'attribute_name', attribute.attribute_name,
                                         'data_type', attribute.attribute_data_type,
                                         'nullable', attribute.attribute_nullability,
                                         'ordinal',
                                             attribute.attribute_ordinal_position,
                                         'definition', attribute.attribute_description
                                     ) ORDER BY attribute.attribute_ordinal_position,
                                                attribute.attribute_id
                                 ),
                                 '[]'::JSONB
                             ) AS documents
                        FROM (
                            SELECT *
                              FROM core.attribute
                             WHERE object_id = source_object.object_id
                               AND is_active
                             ORDER BY attribute_ordinal_position, attribute_id
                             LIMIT 5001
                        ) AS attribute
                  ) AS source_attributes
                  CROSS JOIN LATERAL (
                      SELECT ARRAY(
                                 SELECT ingestion.ingestion_object_mapping_id
                                   FROM core.ingestion_object_mapping AS ingestion
                                   JOIN core.object AS ingestion_source_object
                                     ON ingestion_source_object.object_id =
                                        ingestion.source_object_id
                                    AND ingestion_source_object.is_active
                                   JOIN core.connection AS ingestion_source_connection
                                     ON ingestion_source_connection.connection_id =
                                        ingestion_source_object.connection_id
                                    AND ingestion_source_connection.is_active
                                    AND ingestion_source_connection.system_id =
                                        requested.source_system_id
                                  WHERE ingestion.target_object_id = source_object.object_id
                                    AND ingestion.is_active
                                  ORDER BY ingestion.ingestion_object_mapping_id
                                  LIMIT 129
                             )::BIGINT[] AS ingestion_ids,
                             ARRAY(
                                 SELECT prior.mapping_object_id
                                   FROM workflow.mapping_object AS prior
                                  WHERE prior.model_id = requested.model_id
                                    AND prior.modeled_entity_type = 'logical_entity'
                                    AND prior.object_id = source_object.object_id
                                    AND prior.source_system_id = requested.source_system_id
                                    AND prior.object_mapping_status = 'active'
                                  ORDER BY prior.mapping_object_id
                                  LIMIT 129
                             )::BIGINT[] AS prior_ids
                  ) AS lineage
                 WHERE (
                     requested.modeled_entity_type = 'logical_entity'
                     AND lower(btrim(source_zone.zone_code)) = 'bronze'
                     AND (
                         source_connection.system_id = requested.source_system_id
                         OR EXISTS (
                             SELECT 1
                               FROM core.ingestion_object_mapping AS source_ingestion
                               JOIN core.object AS original_source
                                 ON original_source.object_id =
                                    source_ingestion.source_object_id
                                AND original_source.is_active
                               JOIN core.connection AS original_connection
                                 ON original_connection.connection_id =
                                    original_source.connection_id
                                AND original_connection.is_active
                              WHERE source_ingestion.target_object_id =
                                    source_object.object_id
                                AND source_ingestion.is_active
                                AND original_connection.system_id =
                                    requested.source_system_id
                         )
                     )
                 ) OR (
                     requested.modeled_entity_type = 'dimensional_entity'
                     AND lower(btrim(source_zone.zone_code)) = 'silver'
                     AND EXISTS (
                         SELECT 1
                           FROM workflow.mapping_object AS source_mapping
                          WHERE source_mapping.model_id = requested.model_id
                            AND source_mapping.modeled_entity_type = 'logical_entity'
                            AND source_mapping.object_id = source_object.object_id
                            AND source_mapping.source_system_id =
                                requested.source_system_id
                            AND source_mapping.object_mapping_status = 'active'
                            AND source_mapping.mapping_package_document IS NOT NULL
                            AND source_mapping.object_mapping_transformation_document
                                IS NOT NULL
                     )
                 )
                 ORDER BY source.source_mapping_id
                 LIMIT 129
            ) AS source_item
      ) AS sources
      CROSS JOIN LATERAL (
          SELECT coalesce(
                     jsonb_agg(
                         jsonb_build_object(
                             'mapping_attribute_id', child.mapping_attribute_id,
                             'modeled_attribute_id', CASE requested.modeled_entity_type
                                 WHEN 'logical_entity' THEN child.logical_attribute_id
                                 ELSE child.dimensional_attribute_id
                             END,
                             'target_attribute_id', child.attribute_id,
                             'transformation',
                                 child.attribute_mapping_transformation_document,
                             'status', child.attribute_mapping_status,
                             'is_locked', child.attribute_mapping_is_locked
                         ) ORDER BY child.mapping_attribute_id
                     ),
                     '[]'::JSONB
                 ) AS documents
            FROM (
                SELECT bounded_child.*
                  FROM workflow.mapping_attribute AS bounded_child
                 WHERE bounded_child.mapping_object_id = existing.mapping_object_id
                   AND bounded_child.model_id = requested.model_id
                   AND bounded_child.modeled_entity_type = requested.modeled_entity_type
                 ORDER BY bounded_child.mapping_attribute_id
                 LIMIT 5001
            ) AS child
      ) AS existing_attributes
     ORDER BY candidate.modeled_entity_id
     LIMIT 65
), source_predecessors AS MATERIALIZED (
    SELECT coalesce(
               jsonb_agg(reference.value ORDER BY reference.sort_key),
               '[]'::JSONB
           ) AS documents
      FROM (
          SELECT DISTINCT dependency.value,
                 dependency.value::TEXT AS sort_key
            FROM requested
            JOIN workflow.mapping_object AS mapping
              ON mapping.model_id = requested.model_id
             AND mapping.modeled_entity_type = requested.modeled_entity_type
             AND mapping.source_system_id = requested.source_system_id
             AND mapping.mapping_package_document IS NOT NULL
            CROSS JOIN LATERAL jsonb_array_elements(
                coalesce(
                    mapping.mapping_package_document -> 'source_system_dependencies',
                    '[]'::JSONB
                )
            ) AS dependency(value)
           ORDER BY sort_key
           LIMIT 257
      ) AS reference
), target_predecessors AS MATERIALIZED (
    SELECT coalesce(
               jsonb_agg(reference.value ORDER BY reference.sort_key),
               '[]'::JSONB
           ) AS documents
      FROM (
          SELECT DISTINCT dependency.value,
                 dependency.value::TEXT AS sort_key
            FROM requested
            JOIN workflow.mapping_object AS mapping
              ON mapping.model_id = requested.model_id
             AND mapping.modeled_entity_type = requested.modeled_entity_type
             AND mapping.object_id = requested.target_object_id
             AND mapping.mapping_package_document IS NOT NULL
            CROSS JOIN LATERAL jsonb_array_elements(
                coalesce(
                    mapping.mapping_package_document -> 'target_dependencies',
                    '[]'::JSONB
                )
            ) AS dependency(value)
           ORDER BY sort_key
           LIMIT 257
      ) AS reference
)
SELECT jsonb_build_object(
           'target', (SELECT document FROM target_document),
           'source_system', jsonb_build_object(
               'system_id', source_dependency.system_id,
               'system_code', source_dependency.system_code,
               'system_name', source_dependency.system_name,
               'dependency_order',
                   source_dependency.source_system_dependency_order
           ),
           'headers', coalesce(
               (SELECT jsonb_agg(document ORDER BY modeled_entity_id)
                  FROM header_document),
               '[]'::JSONB
           ),
           'source_dependencies', source_predecessors.documents,
           'target_dependencies', target_predecessors.documents
       ) AS context
  FROM requested
  JOIN source_dependency ON TRUE
  JOIN source_predecessors ON TRUE
  JOIN target_predecessors ON TRUE
 WHERE EXISTS (SELECT 1 FROM target_document)
   AND EXISTS (SELECT 1 FROM header_document)
"""


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingProfileContext(_ContractModel):
    key: Literal["mapping.standard"]
    version: Literal["1.0.0"]
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PhysicalAttributeContext(_ContractModel):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    data_type: str = Field(min_length=1, max_length=100)
    nullable: bool
    ordinal: int = Field(gt=0, le=_MAX_ATTRIBUTES)
    definition: str | None = Field(default=None, max_length=2_000)


class TargetObjectContext(_ContractModel):
    object_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_catalog: str = Field(min_length=1, max_length=255)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_description: str | None = Field(default=None, max_length=2_000)
    zone: Literal["silver", "gold"]
    is_locked: bool
    attributes: tuple[PhysicalAttributeContext, ...] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTES,
    )


class SourceObjectContext(_ContractModel):
    object_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_catalog: str = Field(min_length=1, max_length=255)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone: Zone
    batch_attribute_id: int | None = Field(default=None, gt=0)
    attributes: tuple[PhysicalAttributeContext, ...] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTES,
    )
    ingestion_mapping_ids: tuple[int, ...] = Field(max_length=128)
    prior_mapping_ids: tuple[int, ...] = Field(max_length=128)


class MappingSourceContext(_ContractModel):
    source_mapping_id: int = Field(gt=0)
    role: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=2_000)
    object: SourceObjectContext


class ModeledAttributeContext(_ContractModel):
    modeled_attribute_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    definition: str = Field(min_length=1, max_length=2_000)
    data_type: str = Field(min_length=1, max_length=100)
    nullable: bool
    ordinal: int = Field(gt=0, le=_MAX_ATTRIBUTES)


class ExistingMappingAttributeContext(_ContractModel):
    mapping_attribute_id: int = Field(gt=0)
    modeled_attribute_id: int = Field(gt=0)
    target_attribute_id: int = Field(gt=0)
    transformation: AttributeMappingTransformationDocumentV1 | None
    status: Literal["active", "needs_review", "inactive", "deprecated"]
    is_locked: bool


class ExistingMappingHeaderContext(_ContractModel):
    object_dependency_order: int = Field(ge=0)
    artifact_type: Literal["sql_file", "python_file", "python_notebook"] | None
    artifact_generation_instructions: str | None = Field(default=None, max_length=32_768)
    mapping_profile_key: str | None = Field(default=None, max_length=100)
    mapping_profile_version: str | None = Field(default=None, max_length=50)
    mapping_package_document: MappingPackageDocumentV1 | None
    object_mapping_transformation_document: ObjectMappingTransformationDocumentV1 | None
    status: Literal["active", "needs_review", "inactive", "deprecated"]
    is_locked: bool
    attributes: tuple[ExistingMappingAttributeContext, ...] = Field(
        max_length=_MAX_ATTRIBUTES,
    )


class MappingHeaderContext(_ContractModel):
    header_ref: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    mapping_object_id: int | None = Field(default=None, gt=0)
    modeled_entity_id: int = Field(gt=0)
    modeled_entity_name: str = Field(min_length=1, max_length=255)
    modeled_entity_definition: str = Field(min_length=1, max_length=2_000)
    modeled_entity_kind: str = Field(min_length=1, max_length=100)
    grain: str = Field(min_length=1, max_length=2_000)
    dependency_order: int = Field(ge=0)
    is_locked: bool
    attributes: tuple[ModeledAttributeContext, ...] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTES,
    )
    sources: tuple[MappingSourceContext, ...] = Field(
        min_length=1,
        max_length=_MAX_SOURCES,
    )
    existing: ExistingMappingHeaderContext | None


class SourceDependencyContext(_ContractModel):
    predecessor_source_system_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=2_000)


class TargetDependencyContext(_ContractModel):
    predecessor_target_object_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=2_000)


class SourceSystemContext(_ContractModel):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    dependency_order: int = Field(ge=0)


class MappingAuthoringContext(_ContractModel):
    target: TargetObjectContext
    source_system: SourceSystemContext
    headers: tuple[MappingHeaderContext, ...] = Field(
        min_length=1,
        max_length=_MAX_HEADERS,
    )
    source_dependencies: tuple[SourceDependencyContext, ...] = Field(max_length=256)
    target_dependencies: tuple[TargetDependencyContext, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> MappingAuthoringContext:
        if len({item.header_ref for item in self.headers}) != len(self.headers):
            raise ValueError("Mapping header references must be unique")
        if len({item.modeled_entity_id for item in self.headers}) != len(self.headers):
            raise ValueError("Mapping modeled Entity IDs must be unique")
        target_ids = [item.attribute_id for item in self.target.attributes]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Mapping target Attribute IDs must be unique")
        return self


class MappingAuthoringProof(_ContractModel):
    model_revision: int = Field(gt=0)
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    profile_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    header_count: int = Field(ge=1, le=_MAX_HEADERS)
    target_attribute_count: int = Field(ge=1, le=_MAX_ATTRIBUTES)


class GetModelMappingAuthoringContextResult(_ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=255)
    model_revision: int = Field(gt=0)
    modeled_entity_type: ModeledEntityType
    route: Route
    profile: MappingProfileContext
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proof: MappingAuthoringProof
    context: MappingAuthoringContext = Field(repr=False)


class MappingCandidateHeader(_ContractModel):
    header_ref: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    disposition: Literal["author", "update", "unchanged"]
    object_dependency_order: int = Field(ge=0)
    transformation: ObjectMappingTransformationDocumentV1
    status: Literal["active", "needs_review"]


class MappingCandidateAttribute(_ContractModel):
    header_ref: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=128)
    modeled_attribute_id: int = Field(gt=0)
    target_attribute_id: int = Field(gt=0)
    disposition: Literal["create", "update", "unchanged"]
    transformation: AttributeMappingTransformationDocumentV1
    status: Literal["active", "needs_review"]


class TargetAttributeDisposition(_ContractModel):
    target_attribute_id: int = Field(gt=0)
    disposition: Literal["mapped", "already_mapped", "intentionally_unmapped"]
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)

    @model_validator(mode="after")
    def validate_reason(self) -> TargetAttributeDisposition:
        if (self.reason is not None) != (self.disposition == "intentionally_unmapped"):
            raise ValueError("Only intentionally-unmapped targets require a reason")
        return self


class MappingCandidateCoverage(_ContractModel):
    expected_header_refs: list[str] = Field(min_length=1, max_length=_MAX_HEADERS)
    returned_header_refs: list[str] = Field(min_length=1, max_length=_MAX_HEADERS)
    expected_target_attribute_ids: list[int] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTES,
    )
    returned_target_attribute_ids: list[int] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTES,
    )

    @model_validator(mode="after")
    def validate_unique_coverage(self) -> MappingCandidateCoverage:
        collections = (
            self.expected_header_refs,
            self.returned_header_refs,
            self.expected_target_attribute_ids,
            self.returned_target_attribute_ids,
        )
        if any(len(values) != len(set(values)) for values in collections):
            raise ValueError("Mapping candidate coverage values must be unique")
        return self


class MappingCandidateV1(_ContractModel):
    schema_version: Literal["1.0"]
    package: MappingPackageDocumentV1
    headers: list[MappingCandidateHeader] = Field(
        min_length=1,
        max_length=_MAX_HEADERS,
    )
    attribute_mappings: list[MappingCandidateAttribute] = Field(
        max_length=_MAX_ATTRIBUTES,
    )
    target_attribute_dispositions: list[TargetAttributeDisposition] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTES,
    )
    coverage: MappingCandidateCoverage


class MaterializedMappingChange(_ContractModel):
    dataset: Literal["mapping_object", "mapping_attribute"]
    records: tuple[dict[str, object], ...] = Field(max_length=_MAX_ATTRIBUTES)


class MappingMaterializationProof(_ContractModel):
    contract: Literal["mapping-authoring@1.0"] = "mapping-authoring@1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    modeled_entity_type: ModeledEntityType
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    profile_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    change_count: int = Field(ge=0, le=2)
    record_count: int = Field(ge=0, le=_MAX_ATTRIBUTES * 2)


class MaterializeMappingCandidateResult(_ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    modeled_entity_type: ModeledEntityType
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proof: MappingMaterializationProof
    changes: tuple[MaterializedMappingChange, ...] = Field(max_length=2)


class MappingAuthoringToolError(Exception):
    """A bounded Mapping-authoring failure safe for MCP serialization."""


def register_mapping_authoring_tools(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Get one bounded, revision- and digest-bound Mapping authoring context "
            "for an exact target Object and source System pair."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_mapping_authoring_context(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        modeled_entity_type: ModeledEntityType,
        target_object_id: Annotated[int, Field(gt=0)],
        source_system_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelMappingAuthoringContextResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                result = await load_mapping_authoring_context(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    model_id=model_id,
                    modeled_entity_type=modeled_entity_type,
                    target_object_id=target_object_id,
                    source_system_id=source_system_id,
                )
            return result
        except AuthenticationError as error:
            raise MappingAuthoringToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MappingAuthoringToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MappingAuthoringToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_mapping_authoring_context",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={
            "model_id",
            "modeled_entity_type",
            "target_object_id",
            "source_system_id",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Strictly validate one digest-bound Mapping candidate and materialize "
            "complete natural-key Model Change Set records without staging or writing."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def validate_and_materialize_mapping_candidate(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_revision: Annotated[int, Field(gt=0)],
        modeled_entity_type: ModeledEntityType,
        target_object_id: Annotated[int, Field(gt=0)],
        source_system_id: Annotated[int, Field(gt=0)],
        context_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")],
        candidate: MappingCandidateV1,
        schema_version: Literal["1.0"] = "1.0",
    ) -> MaterializeMappingCandidateResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                prepared = await load_mapping_authoring_context(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    model_id=model_id,
                    modeled_entity_type=modeled_entity_type,
                    target_object_id=target_object_id,
                    source_system_id=source_system_id,
                )
                if (
                    prepared.model_revision != model_revision
                    or prepared.context_digest != context_digest
                ):
                    raise InvalidRequestError(
                        "The Mapping authoring context changed; prepare it again."
                    )
                changes = _materialize_candidate(prepared=prepared, candidate=candidate)
                candidate_digest = _candidate_digest(candidate, changes)
                proof = MappingMaterializationProof(
                    model_id=prepared.model_id,
                    model_revision=prepared.model_revision,
                    modeled_entity_type=prepared.modeled_entity_type,
                    target_object_id=target_object_id,
                    source_system_id=source_system_id,
                    profile_schema_digest=prepared.profile.schema_digest,
                    context_digest=prepared.context_digest,
                    candidate_digest=candidate_digest,
                    change_count=len(changes),
                    record_count=sum(len(item.records) for item in changes),
                )
            return MaterializeMappingCandidateResult(
                model_id=prepared.model_id,
                model_revision=prepared.model_revision,
                modeled_entity_type=prepared.modeled_entity_type,
                target_object_id=target_object_id,
                source_system_id=source_system_id,
                context_digest=prepared.context_digest,
                candidate_digest=candidate_digest,
                proof=proof,
                changes=changes,
            )
        except AuthenticationError as error:
            raise MappingAuthoringToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MappingAuthoringToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MappingAuthoringToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "validate_and_materialize_mapping_candidate",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={
            "model_id",
            "model_revision",
            "modeled_entity_type",
            "target_object_id",
            "source_system_id",
            "context_digest",
            "schema_version",
        },
    )


async def load_mapping_authoring_context(
    transaction: ReadTransaction,
    *,
    authorizer: AuthorizationService,
    principal: RequestPrincipal,
    model_id: int,
    modeled_entity_type: ModeledEntityType,
    target_object_id: int,
    source_system_id: int,
) -> GetModelMappingAuthoringContextResult:
    model = await authorize_model_read(
        transaction,
        authorizer=authorizer,
        principal=principal,
        model_id=model_id,
    )
    row = await transaction.fetch_one(
        _AUTHORING_CONTEXT_SQL,
        (
            model.model_id,
            model.tenant_id,
            model.model_revision,
            modeled_entity_type,
            target_object_id,
            source_system_id,
        ),
    )
    if row is None or row.get("context") is None:
        raise InvalidRequestError("The Mapping authoring context is unavailable.")
    try:
        context = MappingAuthoringContext.model_validate(row["context"], strict=False)
        reject_secret_shaped_values(context.model_dump(mode="json"))
    except TypeError, ValueError:
        raise InvalidRequestError("The Mapping authoring context is unavailable.") from None
    expected_zone = "silver" if modeled_entity_type == "logical_entity" else "gold"
    if (
        context.target.object_id != target_object_id
        or context.target.zone != expected_zone
        or context.source_system.system_id != source_system_id
    ):
        raise InvalidRequestError("The Mapping authoring context is unavailable.")
    profile = MappingProfileContext(
        key=MAPPING_STANDARD_PROFILE_KEY,
        version=MAPPING_STANDARD_PROFILE_VERSION,
        schema_digest=resolve_mapping_profile_schema_digest(
            MAPPING_STANDARD_PROFILE_KEY,
            MAPPING_STANDARD_PROFILE_VERSION,
        ),
    )
    digest = _context_digest(
        model_id=model.model_id,
        model_revision=model.model_revision,
        modeled_entity_type=modeled_entity_type,
        profile=profile,
        context=context,
    )
    proof = MappingAuthoringProof(
        model_revision=model.model_revision,
        target_object_id=target_object_id,
        source_system_id=source_system_id,
        profile_schema_digest=profile.schema_digest,
        context_digest=digest,
        header_count=len(context.headers),
        target_attribute_count=len(context.target.attributes),
    )
    return GetModelMappingAuthoringContextResult(
        model_id=model.model_id,
        model_name=model.model_name,
        model_revision=model.model_revision,
        modeled_entity_type=modeled_entity_type,
        route=(
            "logical_to_silver"
            if modeled_entity_type == "logical_entity"
            else "dimensional_to_gold"
        ),
        profile=profile,
        context_digest=digest,
        proof=proof,
        context=context,
    )


def _materialize_candidate(
    *,
    prepared: GetModelMappingAuthoringContextResult,
    candidate: MappingCandidateV1,
) -> tuple[MaterializedMappingChange, ...]:
    context = prepared.context
    package = candidate.package
    try:
        reject_secret_shaped_values(candidate.model_dump(mode="json"))
    except ValueError:
        raise InvalidRequestError(
            "Mapping candidates cannot contain secret-shaped values."
        ) from None
    if (
        package.target_object_id != context.target.object_id
        or package.source_system_id != context.source_system.system_id
        or package.route != prepared.route
        or package.pydantic_profile.key != prepared.profile.key
        or package.pydantic_profile.version != prepared.profile.version
        or package.pydantic_profile.schema_digest != prepared.profile.schema_digest
    ):
        raise InvalidRequestError("The Mapping candidate identity does not match its context.")

    headers = {item.header_ref: item for item in context.headers}
    target_attributes = {item.attribute_id: item for item in context.target.attributes}
    expected_header_refs = tuple(sorted(headers))
    returned_header_refs = tuple(sorted(item.header_ref for item in candidate.headers))
    expected_target_ids = tuple(sorted(target_attributes))
    returned_target_ids = tuple(
        sorted(item.target_attribute_id for item in candidate.target_attribute_dispositions)
    )
    coverage = candidate.coverage
    if (
        tuple(sorted(coverage.expected_header_refs)) != expected_header_refs
        or tuple(sorted(coverage.returned_header_refs)) != returned_header_refs
        or returned_header_refs != expected_header_refs
        or tuple(sorted(coverage.expected_target_attribute_ids)) != expected_target_ids
        or tuple(sorted(coverage.returned_target_attribute_ids)) != returned_target_ids
        or returned_target_ids != expected_target_ids
    ):
        raise InvalidRequestError("The Mapping candidate coverage is incomplete.")

    all_source_objects = {
        source.object.object_id: source.object
        for header in context.headers
        for source in header.sources
    }
    package_sources = {item.alias: item for item in package.executable_sources}
    if any(item.object_id not in all_source_objects for item in package_sources.values()):
        raise InvalidRequestError("A Mapping executable source is outside its context.")
    for executable_source in package_sources.values():
        source_object = all_source_objects[executable_source.object_id]
        batch_rule = executable_source.batch_rule
        if batch_rule is not None and batch_rule.attribute_id != source_object.batch_attribute_id:
            raise InvalidRequestError("A Mapping batch Attribute is outside its source.")
    for provenance in package.non_executable_provenance:
        source_object = all_source_objects.get(provenance.source_object_id)
        if (
            source_object is None
            or provenance.source_system_id != context.source_system.system_id
            or not set(provenance.executable_source_aliases) <= set(package_sources)
        ):
            raise InvalidRequestError("Mapping provenance is outside its context.")
        if provenance.lineage_kind == "original_ingestion":
            if not set(provenance.ingestion_object_mapping_ids) <= set(
                source_object.ingestion_mapping_ids
            ):
                raise InvalidRequestError("Mapping ingestion provenance is outside its context.")
        elif not set(provenance.prior_object_mapping_ids) <= set(source_object.prior_mapping_ids):
            raise InvalidRequestError("Mapping prior provenance is outside its context.")
    expected_source_dependencies = {
        (item.predecessor_source_system_id, item.reason) for item in context.source_dependencies
    }
    expected_target_dependencies = {
        (item.predecessor_target_object_id, item.reason) for item in context.target_dependencies
    }
    if (
        {
            (item.predecessor_source_system_id, item.reason)
            for item in package.source_system_dependencies
        }
        != expected_source_dependencies
        or {
            (item.predecessor_target_object_id, item.reason) for item in package.target_dependencies
        }
        != expected_target_dependencies
        or not set(package.load.merge_keys) <= set(target_attributes)
    ):
        raise InvalidRequestError("Mapping dependencies or load keys changed from context.")

    header_candidates = {item.header_ref: item for item in candidate.headers}
    if len(header_candidates) != len(candidate.headers):
        raise InvalidRequestError("Mapping candidate headers must be unique.")
    object_records: list[dict[str, object]] = []
    for header_ref in expected_header_refs:
        frozen = headers[header_ref]
        authored = header_candidates[header_ref]
        allowed_source_object_ids = {item.object.object_id for item in frozen.sources}
        allowed_aliases = {
            alias
            for alias, source in package_sources.items()
            if source.object_id in allowed_source_object_ids
        }
        if not set(authored.transformation.source_aliases) <= allowed_aliases:
            raise InvalidRequestError("A Mapping header alias is outside its Entity context.")
        if frozen.is_locked and authored.disposition != "unchanged":
            raise InvalidRequestError("A locked Mapping header cannot be changed.")
        if authored.disposition == "author" and frozen.existing is not None:
            raise InvalidRequestError("An existing Mapping header cannot be authored as new.")
        if authored.disposition in {"update", "unchanged"} and frozen.existing is None:
            raise InvalidRequestError("A new Mapping header must use author disposition.")
        if authored.disposition == "unchanged":
            _require_unchanged_header(frozen, authored, package)
            continue
        record = MappingObjectRecord(
            tenant_code=context.target.tenant_code,
            system_code=context.target.system_code,
            connection_code=context.target.connection_code,
            object_schema=context.target.object_schema,
            object_name=context.target.object_name,
            source_system_code=context.source_system.system_code,
            modeled_entity_type=prepared.modeled_entity_type,
            modeled_entity_name=frozen.modeled_entity_name,
            object_dependency_order=authored.object_dependency_order,
            artifact_type=package.artifact_type,
            artifact_generation_instructions=package.artifact_generation_instructions,
            mapping_profile_key=package.pydantic_profile.key,
            mapping_profile_version=package.pydantic_profile.version,
            mapping_package_document=cast(
                dict[str, object],
                package.model_dump(mode="json"),
            ),
            object_mapping_transformation_document=cast(
                dict[str, object],
                authored.transformation.model_dump(mode="json"),
            ),
            object_mapping_status=authored.status,
            object_mapping_is_locked=(
                False if frozen.existing is None else frozen.existing.is_locked
            ),
        )
        object_records.append(cast(dict[str, object], record.model_dump(mode="json")))

    dispositions = {
        item.target_attribute_id: item for item in candidate.target_attribute_dispositions
    }
    if len(dispositions) != len(candidate.target_attribute_dispositions):
        raise InvalidRequestError("Mapping target dispositions must be unique.")
    attribute_records: list[dict[str, object]] = []
    binding_keys: set[tuple[str, int, int]] = set()
    mapped_targets: set[int] = set()
    for authored in candidate.attribute_mappings:
        frozen = headers.get(authored.header_ref)
        if frozen is None:
            raise InvalidRequestError("A Mapping Attribute header is outside its context.")
        binding_key = (
            authored.header_ref,
            authored.modeled_attribute_id,
            authored.target_attribute_id,
        )
        if binding_key in binding_keys:
            raise InvalidRequestError("Mapping Attribute bindings must be unique.")
        binding_keys.add(binding_key)
        modeled_attribute = next(
            (
                item
                for item in frozen.attributes
                if item.modeled_attribute_id == authored.modeled_attribute_id
            ),
            None,
        )
        target_attribute = target_attributes.get(authored.target_attribute_id)
        existing = _existing_attribute(frozen, authored)
        if modeled_attribute is None or target_attribute is None:
            raise InvalidRequestError("A Mapping Attribute is outside its context.")
        if authored.disposition == "create" and existing is not None:
            raise InvalidRequestError("An existing Mapping Attribute cannot be created again.")
        if authored.disposition in {"update", "unchanged"} and existing is None:
            raise InvalidRequestError("A new Mapping Attribute must use create disposition.")
        if existing is not None and existing.is_locked and authored.disposition != "unchanged":
            raise InvalidRequestError("A locked Mapping Attribute cannot be changed.")
        alias_objects = {
            alias: source
            for alias, source in package_sources.items()
            if source.object_id in {item.object.object_id for item in frozen.sources}
        }
        for source_column in authored.transformation.source_columns:
            executable = alias_objects.get(source_column.source_alias)
            if executable is None:
                raise InvalidRequestError("A Mapping source alias is outside its context.")
            source_object = all_source_objects[executable.object_id]
            if source_column.source_attribute_id not in {
                item.attribute_id for item in source_object.attributes
            }:
                raise InvalidRequestError("A Mapping source Attribute is outside its context.")
        if (
            authored.transformation.step_output is not None
            and authored.transformation.step_output not in {item.output for item in package.steps}
        ):
            raise InvalidRequestError("A Mapping step output is outside its package.")
        mapped_targets.add(authored.target_attribute_id)
        if authored.disposition == "unchanged":
            assert existing is not None
            if existing.transformation != authored.transformation:
                raise InvalidRequestError("An unchanged Mapping Attribute was modified.")
            continue
        record = MappingAttributeRecord(
            tenant_code=context.target.tenant_code,
            system_code=context.target.system_code,
            connection_code=context.target.connection_code,
            object_schema=context.target.object_schema,
            object_name=context.target.object_name,
            attribute_name=target_attribute.attribute_name,
            source_system_code=context.source_system.system_code,
            modeled_entity_type=prepared.modeled_entity_type,
            modeled_entity_name=frozen.modeled_entity_name,
            modeled_attribute_name=modeled_attribute.name,
            attribute_mapping_transformation_document=cast(
                dict[str, object],
                authored.transformation.model_dump(mode="json"),
            ),
            attribute_mapping_status=authored.status,
            attribute_mapping_is_locked=(False if existing is None else existing.is_locked),
        )
        attribute_records.append(cast(dict[str, object], record.model_dump(mode="json")))

    existing_targets = {
        item.target_attribute_id
        for header in context.headers
        if header.existing is not None
        for item in header.existing.attributes
        if item.status == "active"
    }
    for target_id, disposition in dispositions.items():
        if disposition.disposition == "mapped" and target_id not in mapped_targets:
            raise InvalidRequestError("A mapped target Attribute has no Mapping.")
        if disposition.disposition == "already_mapped" and target_id not in existing_targets:
            raise InvalidRequestError("An already-mapped target Attribute has no active Mapping.")
        if disposition.disposition == "intentionally_unmapped" and target_id in mapped_targets:
            raise InvalidRequestError("An intentionally-unmapped Attribute has a Mapping.")

    changes: list[MaterializedMappingChange] = []
    if object_records:
        changes.append(
            MaterializedMappingChange(dataset="mapping_object", records=tuple(object_records))
        )
    if attribute_records:
        changes.append(
            MaterializedMappingChange(
                dataset="mapping_attribute",
                records=tuple(attribute_records),
            )
        )
    return tuple(changes)


def _existing_attribute(
    header: MappingHeaderContext,
    candidate: MappingCandidateAttribute,
) -> ExistingMappingAttributeContext | None:
    if header.existing is None:
        return None
    return next(
        (
            item
            for item in header.existing.attributes
            if item.modeled_attribute_id == candidate.modeled_attribute_id
            and item.target_attribute_id == candidate.target_attribute_id
        ),
        None,
    )


def _require_unchanged_header(
    header: MappingHeaderContext,
    candidate: MappingCandidateHeader,
    package: MappingPackageDocumentV1,
) -> None:
    existing = header.existing
    assert existing is not None
    if (
        existing.object_dependency_order != candidate.object_dependency_order
        or existing.mapping_package_document != package
        or existing.object_mapping_transformation_document != candidate.transformation
        or existing.status != candidate.status
    ):
        raise InvalidRequestError("An unchanged Mapping header was modified.")


def _candidate_digest(
    candidate: MappingCandidateV1,
    changes: tuple[MaterializedMappingChange, ...],
) -> str:
    document = {
        "candidate": candidate.model_dump(mode="json"),
        "changes": [item.model_dump(mode="json") for item in changes],
        "package_digest": mapping_package_digest(candidate.package.model_dump(mode="json")),
    }
    return hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _context_digest(
    *,
    model_id: int,
    model_revision: int,
    modeled_entity_type: ModeledEntityType,
    profile: MappingProfileContext,
    context: MappingAuthoringContext,
) -> str:
    document = {
        "schema_version": "1.0",
        "model_id": model_id,
        "model_revision": model_revision,
        "modeled_entity_type": modeled_entity_type,
        "profile": profile.model_dump(mode="json"),
        "context": context.model_dump(mode="json"),
    }
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    model_id = arguments.get("model_id")
    target_object_id = arguments.get("target_object_id")
    source_system_id = arguments.get("source_system_id")
    modeled_entity_type = arguments.get("modeled_entity_type")
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "modeled_entity_type": (
            cast(str, modeled_entity_type)
            if modeled_entity_type in {"logical_entity", "dimensional_entity"}
            else "invalid"
        ),
        "target_object_id": (
            target_object_id
            if type(target_object_id) is int and target_object_id > 0
            else "invalid"
        ),
        "source_system_id": (
            source_system_id
            if type(source_system_id) is int and source_system_id > 0
            else "invalid"
        ),
    }
