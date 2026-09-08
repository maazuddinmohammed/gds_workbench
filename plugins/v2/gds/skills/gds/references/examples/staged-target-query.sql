-- Fictional structure example, not a business rule or the user's original SQL.
-- Applied Object Mapping uses example.bronze.order_lines AS l and
-- example.bronze.order_headers AS h. Ordered natural-language steps:
-- 1. Keep headers with status = 'posted'; order_id is unique and non-null.
-- 2. Inner join lines to those headers on l.order_id = h.order_id. This
--    intentionally excludes unposted/unmatched lines and preserves line grain.
-- 3. Project the bound Attributes using their separate Mapping rules.
-- Confirmed output grain: (OrderID, LineID); line keys are unique/non-null.
-- Attribute Mapping rules (all inputs non-null):
-- OrderID <- l.order_id unchanged (BIGINT).
-- LineID <- l.line_id unchanged (BIGINT).
-- ClientID <- h.client_id unchanged (BIGINT).
-- Amount <- l.quantity * l.unit_price, cast to DECIMAL(18,2).
-- Evidence establishes whole quantities and exact two-decimal prices, with
-- products inside DECIMAL(18,2); no rounding, overflow or default policy needed.
-- No aggregation, deduplication, other sources or targets are in this Mapping.

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_posted_headers AS
SELECT h.order_id, h.client_id
FROM example.bronze.order_headers AS h
WHERE h.status = 'posted';

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_joined AS
SELECT l.order_id, l.line_id, h.client_id, l.quantity, l.unit_price
FROM example.bronze.order_lines AS l
INNER JOIN temp_order_line_erp_posted_headers AS h
  ON l.order_id = h.order_id;

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_projected AS
SELECT
  j.order_id AS OrderID,
  j.line_id AS LineID,
  j.client_id AS ClientID,
  CAST(j.quantity * j.unit_price AS DECIMAL(18,2)) AS Amount
FROM temp_order_line_erp_joined AS j;

-- Each stage consumes the previous result. Runtime owns target loading.
SELECT OrderID, LineID, ClientID, Amount
FROM temp_order_line_erp_projected;
