# Modeling Assertions

Owns Assertion Document/Record contracts and how other records cite them. An Assertion records an attributable business statement supplied by the user or an identified document. Agent inference remains analysis/design reasoning until confirmed; creating an Assertion must not disguise inference as a fact or bypass a quality check. Ordinary technical choices do not each need an Assertion.

Use [Model Change Set authoring](change-sets.md) for local reading/writing and MCP contract discovery, [record state](../record-state.md) for lifecycle/locks, and [local validation](../local-validation.md) before completion. For `describe_model_dataset`, select `modeling_assertion_document` or `modeling_assertion_record` using the shared call contract; do not invent separate Assertion CRUD tools.

## Identity and structure

- `model-change-set/modeling_assertion_document.json`: array of complete Document records; natural key `modeling_assertion_document_name` within the Model.
- `model-change-set/modeling_assertion_record.json`: array of complete atomic statements; natural key `modeling_assertion_record_key` within the Model, **not** Document name + key.
- A Record references its Document by name. Documents describe evidence provenance; they do not contain a nested Record array or the original document content.
- No Model/database IDs, raw files, raw prompts, physical rows or tool dumps belong here. JSON detail objects contain compact normalized evidence, not unrestricted storage.

## Assertion Document fields

All eight fields are required. Nullable fields still appear explicitly as null.

| Field | Accepted value / meaning |
|---|---|
| `modeling_assertion_document_name` | Nonblank string, 1–255 characters; Document identity. |
| `tenant_code` | Nonblank string ≤100 or null; if supplied, must identify the owning Model Tenant, not physical placement/source ownership. |
| `system_code` | Nonblank string ≤100 or null; if supplied, must identify an active authorized System. |
| `modeling_assertion_file_pattern` | Nonblank string ≤500 or null; applicable source-document pattern, not a file upload or executable instruction. |
| `modeling_assertion_document_type` | Nonblank string ≤100 or null; open description of evidence-document kind. |
| `modeling_assertion_document_description` | Nonblank string ≤2,000 or null; concise purpose and provenance. |
| `modeling_assertion_document_metadata` | JSON object; `{}` valid. Normalized provenance metadata, at most 65,536 encoded bytes. |
| `is_active` | Boolean; Document availability as current evidence. There is no Document lock/status field. |

## Assertion Record fields

All ten fields are required. Confidence and source location may be null.

| Field | Accepted value / meaning |
|---|---|
| `modeling_assertion_record_key` | 1–100 characters matching `[A-Za-z][A-Za-z0-9_.-]{0,99}`; stable identity within the Model. |
| `modeling_assertion_document_name` | Nonblank string, 1–255 characters; existing or locally authored parent Document. |
| `modeling_assertion_record_type` | Nonblank string ≤100; open category of business statement, not a fixed enum. |
| `modeling_assertion_text` | Nonblank atomic statement, at most 262,144 characters; preserve what the source actually establishes. |
| `modeling_assertion_details` | JSON object, at most 262,144 encoded bytes; `{}` valid. Compact meaning/conditions/evidence. |
| `modeling_assertion_source_location` | JSON object, at most 65,536 encoded bytes, or null; attributable location such as an identified document section. |
| `modeling_assertion_applicable_layers` | Unique array drawn from `analysis`, `conceptual`, `logical`, `dimensional`, `mapping`. Select the layers where the statement applies. |
| `modeling_assertion_confidence` | `low`, `medium`, `high` or null; recorded confidence is not automatic proof. |
| `modeling_assertion_record_status` | `active`, `inactive` or `deprecated`. |
| `modeling_assertion_record_is_locked` | Boolean; shared lock rules apply. |

The schema accepts an empty layer array; useful authored evidence needs at least one applicable layer. There are no `code_generation` or `validation` layer values; downstream work may consume applicable upstream evidence without inventing new enum values.

JSON metadata/details/location use source-specific keys, not a fixed nested schema. Current validator limits each object to 4,096 traversed nodes, depth ≤12, and individual string values ≤32,768 characters, as well as the byte limits above. It rejects prohibited raw-content/credential keys, including normalized forms of `content`, `payload`, `rows`, `prompt`, `raw_tool_output`, secret/credential/connection-string keys and file/workbook content. Use compact sanitized summaries and locations. Passing this validator does not make sensitive values safe to retain.

## Evidence use and references

1. Reuse applicable saved evidence; verify actual statement, provenance, active Document/Record, applicable layer and any contradictions. A locked statement is immutable, not necessarily true.
2. Add a statement only when attributable to supplied/confirmed business evidence. Preserve qualifications and uncertainty; ask only when a necessary business rule cannot be established.
3. Reference the **Record key** inside the consumer's allowed source shape. Do not cite a Document alone as typed support or add Assertion fields to an unrelated dataset.
4. Validate Document/Record references and consuming-layer applicability locally. Existing backend reference checks verify existence/layer; workflow checks additionally ensure current active evidence and substantive relevance.

Conceptual uses `supports` with `support_reason`, `support_confidence`, `support_status` and `support_is_locked`: see [Conceptual records](conceptual.md). Logical Entity/Attribute uses `sources` with `rationale`, `status`, `is_locked` and nullable `source_order`: see [Logical records](logical.md). Dimensional Entity sources additionally require `source_role`. These are different schema shapes; do not interchange them.

Assertions may explain an approved calendar, constant set or generated business rule without a physical Object source. Do not create a fictitious physical Object/Attribute or an Assertion merely to fill an otherwise valid empty source array. Assertions express evidence; they are not executable Mapping or SQL.

## Complete synthetic Document and Record

Assume the user explicitly confirmed that CustomerNumber identifies a customer within the business's governed customer domain, and that the leading zeros matter. These examples are invented; they do not themselves authorize that rule for an actual Model.

`model-change-set/modeling_assertion_document.json`:

```json
[
  {
    "modeling_assertion_document_name": "CustomerIdentityRules",
    "tenant_code": null,
    "system_code": null,
    "modeling_assertion_file_pattern": null,
    "modeling_assertion_document_type": "confirmed_business_rules",
    "modeling_assertion_document_description": "Synthetic user-confirmed customer identity rules.",
    "modeling_assertion_document_metadata": {},
    "is_active": true
  }
]
```

`model-change-set/modeling_assertion_record.json`:

```json
[
  {
    "modeling_assertion_record_key": "customer-number-identity",
    "modeling_assertion_document_name": "CustomerIdentityRules",
    "modeling_assertion_record_type": "business_identity",
    "modeling_assertion_text": "CustomerNumber identifies one customer in the governed customer domain; leading zeros form part of the identifier.",
    "modeling_assertion_details": {},
    "modeling_assertion_source_location": null,
    "modeling_assertion_applicable_layers": ["analysis", "logical", "mapping"],
    "modeling_assertion_confidence": "high",
    "modeling_assertion_record_status": "active",
    "modeling_assertion_record_is_locked": false
  }
]
```

Complete nested source for a Logical Entity or Attribute; include it in that parent's `sources` only when applicable:

```json
{
  "support_source_type": "assertion",
  "assertion_record": {"modeling_assertion_record_key": "customer-number-identity"},
  "source_order": null,
  "rationale": "The confirmed synthetic rule defines CustomerNumber as business identity and preserves its formatting.",
  "status": "active",
  "is_locked": false
}
```

## Source pointers

Fields: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`ModelingAssertionDocumentRecord`, `ModelingAssertionRecordRecord`, `AssertionRecordKey`). JSON bounds: `domain/assertion_safety.py`. Keys: `domain/snapshots/model.py`. Owning Tenant/System and layer/reference checks: `application/change_sets/model_validation.py`.
