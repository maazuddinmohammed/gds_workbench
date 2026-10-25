# What the AI sends back

The AI sends only judgment calls. The backend fills in everything it can work out,
then validates the whole model as today.

## Short ids instead of full keys

Today every source reference carries the full key: tenant, system, connection,
schema, table and, for columns, the column name. That alone is a large part of each
attribute.

Proposed instead:
- The prompt lists each input table once with a short id: `t1`, `t2`, ...
- The AI writes `t1` for a table and `t1.order_no` for a column.
- The backend expands each short id to the full key before saving.

## Subject areas run

```json
{
  "areas": [
    {"name": "Sales", "definition": "Orders, order lines and the products sold.",
     "tables": ["t1", "t2", "t3", "t4"]},
    {"name": "Support", "definition": "Tickets raised by users.",
     "tables": ["t4", "t5"]}
  ],
  "unassigned": ["t9"]
}
```

## Logical Build or Optimize run

```json
{
  "entities": [
    {
      "schema": "silver_sales",
      "name": "SalesOrder",
      "type": "transaction",
      "definition": "One row per order number per source system. A customer's order for products.",
      "sources": ["t1"],
      "attributes": [
        {"name": "SourceOrderNumber", "type": "STRING", "nullable": false,
         "natural_key": true, "from": "t1.order_no"},
        {"name": "OrderDate", "type": "DATE", "nullable": false, "from": "t1.order_dt"},
        {"name": "CustomerID", "type": "BIGINT", "nullable": false, "from": "t1.customer_id",
         "note": "Looked up from Customer by customer_id."}
      ]
    }
  ],
  "relationships": [
    {"from": "SalesOrder.CustomerID", "to": "User", "cardinality": "many_to_one",
     "basis": "Analysis: orders.customer_id → users.user_id, supported, 0 orphans."}
  ],
  "retire": ["SalesOrderArchive"]
}
```

- **Entity `type`:** one of the active rows in `reference.logical_entity_type`. The
  prompt lists them with their descriptions, so a newly added type needs no prompt edit.
- **Entity `definition`:** its first sentence says what one row is. The natural-key
  columns (`natural_key: true`) are the same grain in checkable form.
- **Attribute `definition`:** optional. When it's left out, the backend copies the
  source column's Project description; the AI must write one when there is no single
  source column.
- **Attribute `note`:** becomes `source_rationale`. It's only needed when the value
  isn't a straight copy.
- **Entity `sources`:** may include `{"table": "t2", "note": "..."}` when tables
  combine or rows are filtered.
- **Optimize:** uses the same shape. A merge is "retire one entity, move its sources
  and relationships to the other".
- **`retire`:** lists records to mark inactive. Nothing is deleted.

## Dimensional Build or Optimize run

Same shape, with Logical ids instead of table ids (`L1`, `L1.OrderDate`), plus:
- Entity `type`: `fact`, `dimension` or `bridge`.
- Facts: `fact_type` from `reference.dimensional_fact_type`, plus natural-key columns
  for the grain.
- Relationships: an optional `role` for role-playing dimensions; `basis` only when the
  relationship doesn't follow a Logical relationship.

## What the backend fills in

| Field | How |
|---|---|
| ids, project, run id, times | as today |
| full physical keys | expanded from short ids |
| surrogate key `<Entity>ID` | added to every new entity |
| audit columns | from the Project audit template |
| column order | surrogate first, then the AI's order, audit columns last |
| dependency order | from relationships: parents first |
| relationship parent key | the parent's surrogate key |
| attribute definition | the source column's description, when the AI left it out |
| lock flags | never sent; saved locks are kept |
| active flag | true, unless the record is listed in `retire` |
| Dimensional relationship kind and optionality | from entity types and column nullability |

## Rough size per attribute

| Shape | Bytes |
|---|---|
| Today | about 790 |
| This proposal, straight copy | about 90–120 |
| This proposal, with a definition or note | about 160–220 |

These are estimates from the examples above. A real run will vary.
