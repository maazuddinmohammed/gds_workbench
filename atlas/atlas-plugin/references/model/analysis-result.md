# Analysis Result record

Owns the exact `analysis_result` fields. The finding-relationships reference owns candidate discovery and judgment; [Model Change Set authoring](change-sets.md) owns local writes. Use [query scope](../query-scope.md) for measurements and [ownership and physical identity](../metadata/tables/object.md#ownership-and-physical-identity) for endpoint keys.

## Identity and fields

Natural key: all six `from_*` fields, all six `to_*` fields and `relationship_kind`. Preserve direction and exact registered names. Each endpoint identifies one real physical Attribute. Different Attributes on the same Object are allowed; identical normalized endpoints are not.

All non-validation fields below are required. The nine validation fields are nullable/default-null but form one complete group when measured evidence is supplied.

| Field | Accepted value / meaning |
|---|---|
| `from_tenant_code` | Physical Tenant of the from Attribute; nonblank string, 1–100 characters. |
| `from_system_code` | Physical System of the from Attribute; nonblank string, 1–100 characters. |
| `from_connection_code` | Physical Connection of the from Attribute; nonblank string, 1–100 characters. |
| `from_object_schema` | Registered from Object schema; nonblank string, 1–400 characters. |
| `from_object_name` | Registered from Object name; nonblank string, 1–400 characters. |
| `from_attribute_name` | Registered from Attribute name; nonblank string, 1–400 characters. |
| `to_tenant_code` | Physical Tenant of the to Attribute; nonblank string, 1–100 characters. |
| `to_system_code` | Physical System of the to Attribute; nonblank string, 1–100 characters. |
| `to_connection_code` | Physical Connection of the to Attribute; nonblank string, 1–100 characters. |
| `to_object_schema` | Registered to Object schema; nonblank string, 1–400 characters. |
| `to_object_name` | Registered to Object name; nonblank string, 1–400 characters. |
| `to_attribute_name` | Registered to Attribute name; nonblank string, 1–400 characters. |
| `relationship_kind` | Nonblank text, 1–100 characters, identifying the kind of finding; not an enum or a cardinality field. Reuse an applicable established term. Default ordinary foreign-key/category lookups to `reference`; explain categorical/string semantics in the basis. This vocabulary is guidance, not a new enum. |
| `relationship_confidence` | `low`, `medium` or `high`; judgment confidence, not an execution result. |
| `relationship_basis` | Nonblank explanation of business meaning, direction, evidence, material limits and conclusion. Distinguish declarations, agent inference and actual measurements. |
| `validation_policy_version` | Null or version string matching `digits.digits.digits`, at most 50 characters. Current deterministic lookup policy is `1.0.0`; do not invent a measured-policy claim. |
| `validation_result` | Null, `supported`, `inconclusive` or `unsupported`, derived from the complete group below. |
| `validation_source_non_null_count` | Null or nonnegative integer: from rows with a non-null key. Here “source” means from endpoint, not Source zone/source Tenant. |
| `validation_source_distinct_count` | Null or nonnegative integer: distinct non-null from keys. |
| `validation_target_non_null_count` | Null or nonnegative integer: to rows with a non-null key. |
| `validation_target_distinct_count` | Null or nonnegative integer: distinct non-null to keys. |
| `validation_source_missing_target_count` | Null or nonnegative integer: distinct from keys absent from to; not the number of orphan rows. |
| `validation_unused_target_count` | Null or nonnegative integer: distinct to keys absent from from. |
| `validation_duplicate_target_key_count` | Null or nonnegative integer: extra non-null to rows beyond the first per key. |
| `analysis_result_status` | `active`, `inactive` or `deprecated`; lifecycle, not supported/rejected/pending review. |
| `analysis_result_is_locked` | Boolean; preserve existing locks. New unlocked findings use false. |

## Evidence integrity

Leave **all nine `validation_*` fields null** for inference or declarations without a complete applicable deterministic result. Put the relationship, inferred cardinality and basis in `relationship_basis`; a clear metadata-based conclusion may be supported and high-confidence without SQL. Do not set **validation_result** to supported without executed evidence. Preserve valid existing evidence only if it still applies to the unchanged endpoints, interpretation and measurement scope. The record shape is identical for inferred and measured findings.

When adding executed evidence, supply all nine fields from one complete measurement under the recorded query scope. Let S/SD be source non-null/distinct counts; T/TD target non-null/distinct counts; M missing; U unused; D duplicate-target extras.

| Check | Required relationship |
|---|---|
| Count bounds | 0 ≤ SD ≤ S and 0 ≤ TD ≤ T; SD is zero exactly when S is zero, likewise TD/T. |
| Coverage | M ≤ SD; U ≤ TD; SD − M = TD − U. |
| Duplicates | D = T − TD. |
| Inconclusive | S = 0 or T = 0. |
| Supported | Both endpoints nonempty, M = 0 and D = 0. |
| Unsupported | Nonempty endpoints with M > 0 or D > 0. |

The result tests a directional lookup into unique target keys. `supported` does not prove business identity, future cardinality or mandatory participation. `unsupported` can describe an unsuitable lookup direction, incomplete temporal population or a genuine many-valued association; interpret the cause before rejecting the business relationship. Do not change counts or relax the policy to obtain support.

Null-key rows are excluded from these counts. The probe returns their separate counts; retain those in evidence when judging optionality. Do not add them as record fields. Evidence from incompatible batches/environments cannot be combined into one validation group.

## Scope and representational limits

- Backend validation checks new/changed endpoints against effective active Model Input Scope. Atlas relationship analysis additionally requires **active applied Input Scope** before evidence work; pending scope additions do not satisfy that workflow prerequisite. Retained historical records are not permission to create new out-of-scope findings.
- The record has no cardinality or optionality field. Record the supported interpretation in the basis/evidence; later Conceptual/Logical records own their explicit cardinality fields.
- The record has one Attribute per endpoint, with no composite arrays. Keep composite-key/dependency measurements together in task evidence; never claim their component pairs were independently proven.
- Grain, normalization and new reference-domain candidates without two real endpoints belong in analysis notes. Do not invent a reference Object or dummy Attribute to fit this dataset.
- No Model ID, source Tenant code/ID, database IDs, batch fields, query SQL/hashes, measured-at, validation digest or workflow-run fields are accepted. Server-owned digests/IDs are not authoring inputs.
- A different `relationship_kind` changes the natural key. Do not change kind, endpoint or casing to bypass an existing lock or duplicate check.

## Complete synthetic inferred example

Illustrates `model-change-set/analysis_result.json` without SQL. Replace the synthetic endpoints with eligible registered keys and the explanation with actual context. All 26 fields are present; measurement fields are null.

```json
[
  {
    "from_tenant_code": "demo_store",
    "from_system_code": "gds",
    "from_connection_code": "lakehouse",
    "from_object_schema": "bronze",
    "from_object_name": "orders",
    "from_attribute_name": "customer_id",
    "to_tenant_code": "demo_store",
    "to_system_code": "gds",
    "to_connection_code": "lakehouse",
    "to_object_schema": "bronze",
    "to_object_name": "customer",
    "to_attribute_name": "customer_id",
    "relationship_kind": "reference",
    "relationship_confidence": "high",
    "relationship_basis": "Synthetic metadata inference: Orders represents customer orders and its customer_id identifies the Customer in the same CRM domain. Infer Orders to Customer as many-to-one from these roles. SQL was not run; mandatory participation is unspecified.",
    "validation_policy_version": null,
    "validation_result": null,
    "validation_source_non_null_count": null,
    "validation_source_distinct_count": null,
    "validation_target_non_null_count": null,
    "validation_target_distinct_count": null,
    "validation_source_missing_target_count": null,
    "validation_unused_target_count": null,
    "validation_duplicate_target_key_count": null,
    "analysis_result_status": "active",
    "analysis_result_is_locked": false
  }
]
```

## Source pointers

Current contract: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`AnalysisResultRecord`, `AnalysisValidationEvidence`); key in `domain/snapshots/model.py`; scope checks in `application/change_sets/model_validation.py`; database rules in `database/05_workflow_analysis.sql`. Probe semantics: `plugins/v2/gds/skills/gds/scripts/analysis.js` and `references/analysis-probes.md`.

Atlas `analysis-plan` applies the shared resolved batch lists to each endpoint before measurements. Broad existing schema guidance about grain/dependency findings does not add fields or composite endpoints to this contract.
