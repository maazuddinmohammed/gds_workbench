-- Fictional example; names and rules below are illustrative, never live defaults.
-- Applied Mapping defines CustomerSourceRecord at grain
-- (SourceSystemCode, CustomerCode), with three STRING data columns followed by BIGINT SourceSystemID.
-- All referenced source columns are STRING too.
-- Each source has unique, non-null, nonblank customer codes; copy codes unchanged.
-- SourceSystemCode literals ERP/CRM are confirmed lineage values. Their distinct
-- values make the composite target keys disjoint across branches.
-- Source source_system_id values are valid registered BIGINT identifiers.
-- The own surrogate and framework audit fields are omitted from SQL.
-- Names are optional: trim surrounding spaces and map empty names to null.
-- No filtering, joins, lookups, batching, deduplication or parameters apply here.
-- A unified business Customer requires an evidenced identity/reconciliation
-- Mapping before SQL generation; source-specific keys alone do not unify customers.

CREATE OR REPLACE TEMPORARY VIEW temp_erp_customer AS
SELECT
  'ERP' AS SourceSystemCode,
  c.customer_code AS CustomerCode,
  NULLIF(TRIM(c.customer_name), '') AS CustomerName,
  CAST(c.source_system_id AS BIGINT) AS SourceSystemID
FROM bronze.erp_customer AS c;

CREATE OR REPLACE TEMPORARY VIEW temp_crm_customer AS
SELECT
  'CRM' AS SourceSystemCode,
  c.customer_reference AS CustomerCode,
  NULLIF(TRIM(c.display_name), '') AS CustomerName,
  CAST(c.source_system_id AS BIGINT) AS SourceSystemID
FROM bronze.crm_customer AS c;

-- Final statement: exact runtime input shape. Runtime performs the natural-key merge.
SELECT SourceSystemCode, CustomerCode, CustomerName, SourceSystemID
FROM temp_erp_customer
UNION ALL
SELECT SourceSystemCode, CustomerCode, CustomerName, SourceSystemID
FROM temp_crm_customer;
