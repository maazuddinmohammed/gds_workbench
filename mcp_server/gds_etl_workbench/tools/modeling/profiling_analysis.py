"""Applied Profiling and Analysis queries for one governed Model."""

from __future__ import annotations

from typing import LiteralString

PROFILING_SQL: LiteralString = """
WITH requested_model AS (
    SELECT %s::BIGINT AS model_id
),
eligible_attributes AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_model
      CROSS JOIN LATERAL workflow.list_model_attribute_eligibility(
          requested_model.model_id
      ) AS eligibility
)
SELECT profile.object_id,
       tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object_record.object_schema,
       object_record.object_name,
       profile.attribute_id,
       attribute.attribute_name,
       profile.row_count,
       profile.non_null_count,
       profile.null_count,
       profile.blank_count,
       profile.distinct_count,
       profile.min_data_length,
       profile.max_data_length,
       profile.avg_data_length,
       profile.percent_populated,
       profile.percent_duplicates,
       profile.percent_null,
       profile.percent_blank,
       profile.percent_distinct
  FROM workflow.attribute_profile AS profile
  JOIN eligible_attributes AS eligible_attribute
    ON eligible_attribute.object_id = profile.object_id
   AND eligible_attribute.attribute_id = profile.attribute_id
   AND eligible_attribute.model_id = profile.model_id
   AND eligible_attribute.is_model_input_eligible
  JOIN core.object AS object_record
    ON object_record.object_id = profile.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object_record.connection_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.attribute AS attribute
    ON attribute.attribute_id = profile.attribute_id
   AND attribute.object_id = profile.object_id
 WHERE (
       cardinality(%s::BIGINT[]) = 0
       OR profile.object_id = ANY(%s::BIGINT[])
   )
 ORDER BY lower(object_record.object_schema),
          lower(object_record.object_name),
          attribute.attribute_ordinal_position,
          profile.attribute_id
 LIMIT %s OFFSET %s
"""

ANALYSIS_SQL: LiteralString = """
WITH requested_model AS (
    SELECT %s::BIGINT AS model_id
),
eligible_attributes AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_model
      CROSS JOIN LATERAL workflow.list_model_attribute_eligibility(
          requested_model.model_id
      ) AS eligibility
)
SELECT result.from_object_id,
       from_tenant.tenant_code AS from_tenant_code,
       from_system.system_code AS from_system_code,
       from_connection.connection_code AS from_connection_code,
       from_object.object_schema AS from_object_schema,
       from_object.object_name AS from_object_name,
       result.from_attribute_id,
       from_attribute.attribute_name AS from_attribute_name,
       result.to_object_id,
       to_tenant.tenant_code AS to_tenant_code,
       to_system.system_code AS to_system_code,
       to_connection.connection_code AS to_connection_code,
       to_object.object_schema AS to_object_schema,
       to_object.object_name AS to_object_name,
       result.to_attribute_id,
       to_attribute.attribute_name AS to_attribute_name,
       result.relationship_kind,
       result.relationship_confidence,
       result.relationship_basis,
       result.validation_policy_version,
       result.validation_result,
       result.validation_source_non_null_count,
       result.validation_source_distinct_count,
       result.validation_target_non_null_count,
       result.validation_target_distinct_count,
       result.validation_source_missing_target_count,
       result.validation_unused_target_count,
       result.validation_duplicate_target_key_count,
       result.analysis_result_status,
       result.analysis_result_is_locked
  FROM workflow.analysis_result AS result
  JOIN eligible_attributes AS eligible_from_attribute
    ON eligible_from_attribute.object_id = result.from_object_id
   AND eligible_from_attribute.attribute_id = result.from_attribute_id
   AND eligible_from_attribute.model_id = result.model_id
   AND eligible_from_attribute.is_model_input_eligible
  JOIN eligible_attributes AS eligible_to_attribute
    ON eligible_to_attribute.object_id = result.to_object_id
   AND eligible_to_attribute.attribute_id = result.to_attribute_id
   AND eligible_to_attribute.model_id = result.model_id
   AND eligible_to_attribute.is_model_input_eligible
  JOIN core.object AS from_object
    ON from_object.object_id = result.from_object_id
  JOIN core.connection AS from_connection
    ON from_connection.connection_id = from_object.connection_id
  JOIN core.tenant AS from_tenant
    ON from_tenant.tenant_id = from_connection.tenant_id
  JOIN core.system AS from_system
    ON from_system.system_id = from_connection.system_id
  JOIN core.attribute AS from_attribute
    ON from_attribute.attribute_id = result.from_attribute_id
   AND from_attribute.object_id = result.from_object_id
  JOIN core.object AS to_object
    ON to_object.object_id = result.to_object_id
  JOIN core.connection AS to_connection
    ON to_connection.connection_id = to_object.connection_id
  JOIN core.tenant AS to_tenant
    ON to_tenant.tenant_id = to_connection.tenant_id
  JOIN core.system AS to_system
    ON to_system.system_id = to_connection.system_id
  JOIN core.attribute AS to_attribute
    ON to_attribute.attribute_id = result.to_attribute_id
   AND to_attribute.object_id = result.to_object_id
 WHERE (
       cardinality(%s::BIGINT[]) = 0
       OR result.from_object_id = ANY(%s::BIGINT[])
       OR result.to_object_id = ANY(%s::BIGINT[])
   )
 ORDER BY result.from_object_id,
          result.from_attribute_id,
          result.to_object_id,
          result.to_attribute_id,
          lower(result.relationship_kind)
 LIMIT %s OFFSET %s
"""
