"""Model-owned enrichment selection with owner-qualified natural keys."""

from typing import LiteralString

OBJECT_ENRICHMENT_SQL: LiteralString = """
SELECT tenant.tenant_code, system.system_code, connection.connection_code,
       object.object_schema, object.object_name, enriched.object_description, enriched.is_locked,
       workflow.enrichment_review_revision(model.model_id, object.object_id) AS expected_revision
  FROM workflow.object_enrichment AS enriched
  JOIN model.model AS model ON model.model_id = enriched.model_id
  JOIN model.model_input_scope AS scope ON scope.model_id = model.model_id AND scope.object_id =
       enriched.object_id
  JOIN core.object AS object ON object.object_id = enriched.object_id
  JOIN core.connection AS connection USING (connection_id)
  JOIN core.tenant AS tenant ON tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
 WHERE enriched.model_id = %s
   AND (object.source_tenant_id = model.tenant_id OR object.source_tenant_id = ANY(%s::BIGINT[]))
   AND (NOT %s::BOOLEAN OR (scope.is_active AND object.is_active AND connection.is_active AND
       tenant.is_active AND system.is_active))
 ORDER BY lower(tenant.tenant_code), lower(system.system_code), lower(connection.connection_code),
          lower(object.object_schema), lower(object.object_name), object.object_id
 LIMIT %s OFFSET %s
"""

ATTRIBUTE_ENRICHMENT_SQL: LiteralString = """
SELECT tenant.tenant_code, system.system_code, connection.connection_code,
       object.object_schema, object.object_name, attribute.attribute_name,
       enriched.attribute_description, enriched.attribute_inferred_data_type,
       enriched.is_natural_key, enriched.is_primary_key, enriched.is_nullable, enriched.is_pii,
       enriched.is_locked,
       workflow.enrichment_review_revision(model.model_id, object.object_id, attribute.attribute_id)
           AS expected_revision
  FROM workflow.attribute_enrichment AS enriched
  JOIN model.model AS model ON model.model_id = enriched.model_id
  JOIN model.model_input_scope AS scope ON scope.model_id = model.model_id AND scope.object_id =
       enriched.object_id
  JOIN core.object AS object ON object.object_id = enriched.object_id
  JOIN core.connection AS connection USING (connection_id)
  JOIN core.tenant AS tenant ON tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
  JOIN core.attribute AS attribute ON attribute.object_id = object.object_id
   AND attribute.attribute_id = enriched.attribute_id
 WHERE enriched.model_id = %s
   AND (object.source_tenant_id = model.tenant_id OR object.source_tenant_id = ANY(%s::BIGINT[]))
   AND (NOT %s::BOOLEAN OR (scope.is_active AND object.is_active AND connection.is_active AND
       tenant.is_active AND system.is_active AND attribute.is_active))
 ORDER BY lower(tenant.tenant_code), lower(system.system_code), lower(connection.connection_code),
          lower(object.object_schema), lower(object.object_name), object.object_id,
       lower(attribute.attribute_name), attribute.attribute_id
 LIMIT %s OFFSET %s
"""
