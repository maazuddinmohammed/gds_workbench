# Subject Area records

Owns the exact `subject_area` and `subject_area_table` fields and the grouping method. Use [Project Change Set authoring](change-sets.md) for local writes, [record state](../record-state.md) for locks and lifecycle, and [local validation](../local-validation.md) before completing work.

A Subject Area is a named business capability, such as Sales, Billing or Customer Support, over the Project's Bronze Input Scope. It is a focus window: a Logical or Dimensional Build works on one area's Objects at a time, while the Project keeps one Logical model. An Object may sit in several areas. An area is not a model and not evidence. Logical, Dimensional, Mapping, Code and SQL Validation work never cite it as a source, and its definition never justifies an Entity or a relationship.

## Identity and file shape

- `project-change-set/subject_area.json`: array of complete changed areas; key is `subject_area_name` within the owning Project.
- `project-change-set/subject_area_table.json`: array of complete changed memberships, one per member Object; key is `subject_area_name` plus the five-part physical key of the Object.
- Compare keys through the shared normalizer, which strips surrounding ASCII spaces and case-folds text. Preserve saved spelling. A new spelling is a new area, not a rename: write the new area, move its active memberships, and make the old area inactive.
- No section wrapper, internal numeric IDs, column lists, counts, SQL or task evidence fields belong in these payloads.

## Subject Area fields

All four fields are required; none is nullable.

| Field | Accepted value / meaning |
|---|---|
| `subject_area_name` | Nonblank string, 1–255 characters; short business name in Title Case, unique in the Project. |
| `subject_area_definition` | Nonblank text: one or two sentences on the capability the area covers and where it ends. |
| `subject_area_is_active` | Boolean; `false` retires the area. |
| `subject_area_is_locked` | Boolean; obey shared record-state rules. A locked area and its memberships do not change. |

## Subject Area Object fields

All eight fields are required; none is nullable.

| Field | Accepted value / meaning |
|---|---|
| `subject_area_name` | Exact existing or locally authored area name. |
| `tenant_code` | Nonblank string, 1–100 characters; physical placement Tenant. |
| `system_code` | Nonblank string, 1–100 characters; registered physical System. |
| `connection_code` | Nonblank string, 1–100 characters; registered physical Connection. |
| `object_schema` | Nonblank string, 1–400 characters; registered schema. |
| `object_name` | Nonblank string, 1–400 characters; registered Object. |
| `subject_area_table_is_active` | Boolean; `false` removes the Object from the area and keeps history. |
| `subject_area_table_is_locked` | Boolean; a locked membership stays whatever later grouping proposes. |

Copy physical keys from eligible Metadata; [Object ownership](../metadata/tables/object.md#ownership-and-physical-identity) explains why a Bronze Object keeps its GDS placement. One Object may belong to several areas, once per area.

## Contract checks

- The membership's area must exist in the effective Project, and an active membership needs an active area.
- The Object must be in active Project Input Scope. Group the Bronze Objects a Build models; Source-zone Objects do not belong in areas.
- Deactivating an area does not deactivate its memberships for you: make each active membership inactive in the same Change Set, or the active membership fails validation.
- Nothing is deleted through a Change Set. Unassigned Objects are not stored: an Object is unassigned when it has no active membership in an active area.
- `validate` reports each active area's `object_count`, `shared_object_count` (also in another active area) and `modeled_object_count` (already a source of an active Logical Entity) in `subject_area_summaries`, in the web Build dialog's default order: most shared Objects first.

## Grouping method

1. Read every Object first: what one row records and which business process or subject it serves. Use Project descriptions, Attribute names, profiles, Analysis links and Context records; do not stop at name prefixes.
2. Group by business capability: a process with its transactions, documents and events, plus the subjects it needs (Order Capture: order header, order line, order status). Never group by source System, schema or zone alone.
   Keep one subject from different Systems together: Objects that record the same thing for different originating Systems (CRM and ERP customer accounts, two regional order systems) belong in the same area, so one Logical Build designs one shared Entity for them. Never make one area per System. Their repeated columns add evidence, not design work, when sizing.
3. Keep together Objects one Build must join: header and detail, a subject and its history, an association and both ends. A supported Analysis link is strong evidence that two Objects belong together; a link alone does not define a capability.
4. Share reference and master Objects: put a customer, product, calendar or currency Object in every area that needs it. Shared Objects are modeled once, by the first area built, and reused by later areas.
5. Size each area for one Build: aim for about 5 to 12 Objects and a few hundred columns. Split an area above roughly 400 columns or 20 Objects along process boundaries (Order Capture, Fulfilment, Invoicing), keeping a header with its lines and a subject with its history; merge a one- or two-Object area into the capability that uses it unless it is a distinct capability. Sizes are guidance, not a limit.
6. Leave an Object unassigned only when no evidence places it: technical, staging, log, audit or control Objects, or Objects whose meaning stays unclear. Report each one with its reason.
7. Prefer stable, coherent areas: add new Objects to a saved area that fits before creating one. When the user asks to group only some Objects, change only those Objects' memberships, and do not retire an area that still holds other in-scope Objects.

## Complete synthetic records

Illustrates both files. All physical keys are fictitious and must be replaced with eligible registered keys.

```json
[
  {
    "subject_area_name": "Order Capture",
    "subject_area_definition": "Customer orders from submission to confirmation, with the customers and products they reference. Fulfilment and invoicing are separate areas.",
    "subject_area_is_active": true,
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
    "subject_area_table_is_active": true,
    "subject_area_table_is_locked": false
  },
  {
    "subject_area_name": "Order Capture",
    "tenant_code": "demo_store", "system_code": "gds", "connection_code": "lakehouse",
    "object_schema": "bronze", "object_name": "crm_customer",
    "subject_area_table_is_active": true,
    "subject_area_table_is_locked": false
  }
]
```
