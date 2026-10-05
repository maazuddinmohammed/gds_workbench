# Member — `core.member`

A Member supplies one code and optional filter Attribute within a Member Group.
Configure it only when the user explicitly requests Member filtering for a Copy
Group. The group is associated through Copy Group Control in the same Tenant/System.

Dataset `member` is editable through Metadata Change Sets and the web catalog.
Database identity is `member_id`; FK is `member_group_id`. The database natural key
is `(member_group_id, member_code)`, using normalized code uniqueness. Snapshots
replace the FK with `tenant_code`, `system_code`, `member_group_name`; append
`member_code` to obtain the complete authoring key.

| Field | Meaning |
| --- | --- |
| `tenant_code`, `system_code`, `member_group_name` | Existing or pending parent Member Group; same Change Set Tenant. |
| `member_code` | Nonblank string, maximum 100 characters; unique within its Group. |
| `member_name` | Nonblank display name, maximum 200 characters. |
| `member_description` | Optional description, or null. |
| `member_attribute_name` | Optional filter Attribute name, maximum 400 characters; use the explicitly supplied source meaning. |
| `value` | Optional JSON details, default null; no implied behavior. |
| `is_active` | Boolean; new records default true. |

Created/updated time and actor fields are maintained by the backend. Do not include
IDs or audit fields in Change Sets. Preserve unrelated values and inactive history.
A Member code may repeat in another Group. Duplicate normalized codes in the same
Group and missing Group references fail validation. This metadata does not itself
execute pipelines or infer filter SQL.
