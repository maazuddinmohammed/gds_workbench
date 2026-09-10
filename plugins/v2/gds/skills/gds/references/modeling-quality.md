# Review modeling evidence

`validate` separates structural `valid` from `quality`. Read `tasks/<task>.modeling-quality.json` and complete generated `tasks/<task>.modeling-decisions.json`; never edit computed results or invent keys/scores.

Checks cover affected active Concepts, Entities and relationships in the effective graph, including changed evidence. Unrelated Mapping/Profiling work requires no new modeling review.

## Minimal decisions, substantive evidence

The scaffold has two arrays, `entities` and `relationships`. Each entry contains its dataset, canonical key, a concise `decision`, and `evidence`. Logical Entities also declare `identity_mode` (`natural` or documented `append_only`) and `identity_attributes`: the complete tuple of actual natural-key Attributes. Keep generated field names; metrics are computed.

Entity evidence can cite a sanitized existing note:

```json
{"note":"working/01/object-analysis/orders.md"}
```

Or cite an existing active Analysis/Assertion by its canonical key:

```json
{"dataset":"modeling_assertion_record","key":{"modeling_assertion_record_key":"order.customer"}}
```

Retrieve actual keys; examples are fictional. Notes may reference earlier tasks. Include grain, determinants, full-key measurements, source qualification, uncertainty and aggregate evidence scope/method; never raw data or dumps.

Explain Attribute determinants and split/retain/consolidate decisions; use `examples/modeling-decisions.md` when needed.

Relationships require complete supported deterministic Analysis aligned to physical endpoints and cardinality, or an active Assertion whose document and applicable layer are active. Notes alone cannot activate relationships. Unresolved Analysis remains useful investigation but cannot pass as proof. An Assertion must come from supplied or confirmed business evidence; never create one to satisfy the check. Composite surrogate lookup needs full-tuple evidence; individual component checks are insufficient. If identity is truly append-only, document that business rule; a generated key alone is not deduplication evidence.

## Interpret the result

- `needs_evidence`: repair the affected decision/evidence, defer the unsupported proposed record, or report the specific blocker. Structural override does not bypass missing modeling evidence.
- `evidence_present`: required citations and consistency checks passed. The helper cannot judge prose truth, normalization quality or whether a business Assertion is correct. Review the actual model and measurements.
- `not_required`: no affected active Conceptual/Logical decision needs this check; this is not a model quality certificate.

Warnings expose disconnection, source-support shape, type/capacity issues and missing Logical counterparts. No Entity/edge quota or quality score applies; isolated reference Entities and normalized one-to-one structures can be valid. Explain material warnings.

Validate repaired decisions and present changes/limits before acknowledgement. `accept` separately binds report, cited note/decision bytes and Snapshot manifests. Changed evidence invalidates acceptance even with identical records; reassess and obtain renewed acknowledgement. Resume through `status`, without regenerating accepted artifacts.
