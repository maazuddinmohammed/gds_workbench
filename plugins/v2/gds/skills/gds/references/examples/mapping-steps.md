# Steps that produce executable SQL

Teaching examples use fictional names and confirmed preconditions. Full physical identities belong in source_objects; these schema.table references are runtime SQL coordinates. Field expressions belong in Attribute transformations. Do not copy filters or precedence into unrelated models.

## Simple branch

Step: “Create temp_crm_customer from the scoped CRM input, one row per CustomerNumber. Apply the mapped business-field conversions and project CustomerNumber, CustomerName, SourceSystemID in that order. The target's CustomerID is database-generated.”

```sql
CREATE OR REPLACE TEMPORARY VIEW temp_crm_customer AS
SELECT customer_number AS CustomerNumber,
       NULLIF(TRIM(customer_name), '') AS CustomerName,
       CAST(source_system_id AS BIGINT) AS SourceSystemID
FROM bronze.crm_customer;
```

Preconditions: identifier formatting is retained, names may be null, source System IDs are valid BIGINT values, and identifiers are unique within that System. Add batch filtering only when Mapping and the runtime contract require it.

## Preparation, deduplication, and foreign keys

Steps: “Prepare the latest source version per (source_system_id, order_number), ordered by updated_at and a unique version_id tie-breaker. Resolve CustomerID by (SourceSystemID, CustomerNumber). Preserve order grain. Use the confirmed missing-customer policy; this example permits a null FK and defines a separate missing-reference validation.”

```sql
CREATE OR REPLACE TEMPORARY VIEW temp_erp_order_latest AS
SELECT source_system_id, order_number, customer_number, amount
FROM bronze.erp_order
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY source_system_id, order_number
  ORDER BY updated_at DESC, version_id DESC
) = 1;

CREATE OR REPLACE TEMPORARY VIEW temp_erp_order_projected AS
SELECT o.order_number AS OrderNumber,
       c.CustomerID,
       CAST(o.amount AS DECIMAL(18,2)) AS Amount,
       CAST(o.source_system_id AS BIGINT) AS SourceSystemID
FROM temp_erp_order_latest AS o
LEFT JOIN silver.Customer AS c
  ON c.SourceSystemID = CAST(o.source_system_id AS BIGINT)
 AND c.CustomerNumber = o.customer_number;

SELECT OrderNumber, CustomerID, Amount, SourceSystemID
FROM temp_erp_order_projected;
```

Preconditions: latest-version selection is a confirmed rule; ordering is deterministic; the lookup key is unique; numeric conversion is valid at the declared precision. The own OrderID is generated; the referenced CustomerID is supplied. A CTE within a temporary view can express the same preparation when clearer. Do not invent latest-wins or nullable FK policy.

## Multiple Systems and existing-value preservation

Each branch produces the same aliases/types/order and its declared grain. `multi-system-target.sql` shows explicit UNION ALL for disjoint source identities. For unified business identity, specify reconciliation before combining.

When an approved rule preserves an existing target value, name the target lookup, unique join key, and precedence explicitly; for example `COALESCE(existing.CustomerName, incoming.CustomerName)` only if “keep existing non-null name” is the actual rule. This is not a default fallback.

File layout is decided later by Code Generation. Every final artifact must contain all its own preparation and finish with the exact runtime input projection.
