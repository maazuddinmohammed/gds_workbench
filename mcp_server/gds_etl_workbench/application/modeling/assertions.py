"""Applied Modeling Assertion queries for one governed Model."""

from __future__ import annotations

from typing import LiteralString

DOCUMENTS_SQL: LiteralString = """
SELECT document.modeling_assertion_document_id,
       document.modeling_assertion_document_name,
       tenant.tenant_code,
       system.system_code,
       document.modeling_assertion_file_pattern,
       document.modeling_assertion_document_type,
       document.modeling_assertion_document_description,
       document.modeling_assertion_document_metadata,
       document.is_active
  FROM model.modeling_assertion_document AS document
  LEFT JOIN core.tenant AS tenant
    ON tenant.tenant_id = document.tenant_id
  LEFT JOIN core.system AS system
    ON system.system_id = document.system_id
 WHERE document.model_id = %s
 ORDER BY lower(document.modeling_assertion_document_name),
          document.modeling_assertion_document_id
 LIMIT %s OFFSET %s
"""

RECORDS_SQL: LiteralString = """
SELECT record.modeling_assertion_record_id,
       record.modeling_assertion_document_id,
       record.modeling_assertion_record_key,
       document.modeling_assertion_document_name,
       record.modeling_assertion_record_type,
       record.modeling_assertion_text,
       record.modeling_assertion_details,
       record.modeling_assertion_source_location,
       record.modeling_assertion_applicable_layers,
       record.modeling_assertion_confidence,
       record.modeling_assertion_record_status,
       record.modeling_assertion_record_is_locked
  FROM model.modeling_assertion_record AS record
  JOIN model.modeling_assertion_document AS document
    ON document.modeling_assertion_document_id = record.modeling_assertion_document_id
   AND document.model_id = record.model_id
 WHERE record.model_id = %s
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR record.modeling_assertion_document_id = ANY(%s::BIGINT[])
   )
 ORDER BY lower(document.modeling_assertion_document_name),
          lower(record.modeling_assertion_record_key),
          record.modeling_assertion_record_id
 LIMIT %s OFFSET %s
"""
