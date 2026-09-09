-- Fictional Mapping example; these business rules require confirmation.
-- OrderLine grain: (OrderID, LineNumber), with generated OrderLineID omitted.
-- Bronze identifiers are STRING. Posted headers have unique nonblank order_code.
-- silver.Order has unique (SourceSystemID, OrderCode) and every selected header
-- matches exactly one Order. Its generated OrderID supplies the foreign key.
-- SourceSystemID is the registered source System; every row has a valid value.
-- LineNumber is a significant STRING business identifier; preserve it unchanged.
-- Whole quantities and exact two-decimal prices fit DECIMAL(18,2) after multiplication.
-- Exclude unposted lines intentionally; no deduplication or rounding is needed.
-- Framework audit columns remain in DDL/Binding and have no SELECT expression.

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_posted_headers AS
SELECT h.order_code, h.source_system_id
FROM bronze.order_headers AS h
WHERE h.status = 'posted';

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_joined AS
SELECT o.OrderID, l.line_number, l.quantity, l.unit_price,
       CAST(h.source_system_id AS BIGINT) AS SourceSystemID
FROM bronze.order_lines AS l
INNER JOIN temp_order_line_erp_posted_headers AS h
  ON l.order_code = h.order_code AND l.source_system_id = h.source_system_id
INNER JOIN silver.Order AS o
  ON o.OrderCode = h.order_code
 AND o.SourceSystemID = CAST(h.source_system_id AS BIGINT);

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_projected AS
SELECT
  j.OrderID,
  j.line_number AS LineNumber,
  CAST(CAST(j.quantity AS BIGINT) * CAST(j.unit_price AS DECIMAL(18,2)) AS DECIMAL(18,2)) AS Amount,
  j.SourceSystemID
FROM temp_order_line_erp_joined AS j;

-- Each stage consumes previous results. Runtime owns target loading.
SELECT OrderID, LineNumber, Amount, SourceSystemID
FROM temp_order_line_erp_projected;
