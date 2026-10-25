# Subject Area records

Owns the exact `subject_area` and `subject_area_table` fields and the grouping method. Use [Project Change Set authoring](change-sets.md) for local writes, [record state](../record-state.md) for locks and lifecycle, and [local validation](../local-validation.md) before completing work.

A Subject Area is a named business capability, such as Sales, Billing or Customer Support, over the Project's Bronze Input Scope. It keeps each Logical Build small: the build models one area's tables at a time. An area is not a model and not evidence. Logical, Dimensional, Mapping, Code and SQL Validation work never cite it as a source, and its definition never justifies an Entity or a relationship.

## Identity and file shape

- `project-change-set/subject_area.json`: array of complete changed areas; key is `subject_area_name` within the owning Project.
- `project-change-set/subject_area_table.json`: array of complete changed memberships; key is `subject_area_name` plus the five-part physical key of the table.
- Compare keys through the shared normalizer, which strips surrounding ASCII spaces and case-folds text. Preserve saved spelling. A new spelling is a new area, not a rename: write the new area, move its active memberships, and make the old area inactive.
- No section wrapper, internal numeric IDs, column lists, counts, SQL or task evidence fields belong in these payloads.

## Subject Area fields

All four fields are required; none is nullable.

| Field | Accepted value / meaning |
|---|---|
| `subject_area_name` | Nonblank string, 1–255 characters; short business name in Title Case, unique in the Project. |
| `subject_area_definition` | Nonblank text: one or two sentences on the capability the area covers and where it ends. |
| `subject_area_status` | `active`, `inactive` or `deprecated`. |
| `subject_area_is_locked` | Boolean; obey shared record-state rules. A locked area and its memberships do not change. |

## Subject Area table fields

All eight fields are required; none is nullable.

| Field | Accepted value / meaning |
|---|---|
| `subject_area_name` | Exact existing or locally authored area name. |
| `tenant_code` | Nonblank string, 1–100 characters; physical placement Tenant. |
| `system_code` | Nonblank string, 1–100 characters; registered physical System. |
| `connection_code` | Nonblank string, 1–100 characters; registered physical Connection. |
| `object_schema` | Nonblank string, 1–400 characters; registered schema. |
| `object_name` | Nonblank string, 1–400 characters; registered Object. |
| `subject_area_table_status` | `active`, `inactive` or `deprecated`. Inactive removes the table from the area and keeps history. |
| `subject_area_table_is_locked` | Boolean; a locked membership stays whatever later grouping proposes. |

Copy physical keys from eligible Metadata; [Object ownership](../metadata/tables/object.md#ownership-and-physical-identity) explains why a Bronze table keeps its GDS placement. One table may belong to several areas, once per area.

## Contract checks

- The membership's area must exist in the effective Project, and an active membership needs an active area.
- The table must be in active Project Input Scope. Group the Bronze tables a Logical Build models; Source-zone tables do not belong in areas.
- Deactivating an area does not deactivate its memberships for you: make each active membership inactive in the same Change Set, or the active membership fails validation.
- Nothing is deleted through a Change Set. Unassigned tables are not stored: a table is unassigned when it has no active membership in an active area.

## Grouping method

1. Read every table first: what one row records and which business process or subject it serves. Use Project descriptions, column names, profiles, Analysis links and Context records; do not stop at name prefixes.
2. Group by business capability: a process with its transactions, documents and events, plus the subjects it needs (Order Capture: order header, order line, order status). Never group by source System, schema or zone alone.
3. Keep together tables one Logical Build must join: header and detail, a subject and its history, an association and both ends. A supported Analysis link is strong evidence that two tables belong together; a link alone does not define a capability.
4. Share reference and master tables: put a customer, product, calendar or currency table in every area that needs it.
5. Keep each area at or below the Project's column limit, 300 columns by default, counting every member table's columns. Split a large capability along process boundaries (Order Capture, Fulfilment, Invoicing), never arbitrarily.
6. Leave a table unassigned only when no evidence places it: technical, staging, log, audit or control tables, or tables whose meaning stays unclear. Report each one with its reason.
7. Prefer stable, coherent areas. Avoid one-table areas unless the table is a distinct capability.

## Complete synthetic records

Illustrates both files. All physical keys are fictitious and must be replaced with eligible registered keys.

```json
[
  {
    "subject_area_name": "Order Capture",
    "subject_area_definition": "Customer orders from submission to confirmation, with the customers and products they reference. Fulfilment and invoicing are separate areas.",
    "subject_area_status": "active",
    "subject_area_is_locked": false
  }
]
```

```json
[
  {
    "subject_area_name": "Order Capture",
    "tenant_code": "demo_store", "system_code": "gds", "connection_code": "lakehouse",
    "object_schema": "bronze", "object_name": "orders",
    "subject_area_table_status": "active",
    "subject_area_table_is_locked": false
  },
  {
    "subject_area_name": "Order Capture",
    "tenant_code": "demo_store", "system_code": "gds", "connection_code": "lakehouse",
    "object_schema": "bronze", "object_name": "crm_customer",
    "subject_area_table_status": "active",
    "subject_area_table_is_locked": false
  }
]
```
