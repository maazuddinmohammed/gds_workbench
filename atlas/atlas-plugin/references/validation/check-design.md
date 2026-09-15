# Validation check design

Owns check selection, expected behavior and population. The [Validation skill](../../skills/atlas-validation/SKILL.md) owns workflow/questions; [Validation records](../model/validation.md) owns fields, operators and current storage/SQL constraints. Use the [complete Mapping view](../model/mapping-documents.md#complete-context-for-coding-and-validation), without reconstructing upstream modeling decisions.

## Establish what is being tested

1. Bind each selected target and originating System to its applied Mapping. Identify changes, preserved checks and missing coverage through the shared [update-scope rules](../working-method.md#existing-work-and-update-scope).
2. The agent selects the useful observation point for each failure: transformation output before persistence, or actual stored rows after the relevant framework operation. Use both only when they reveal distinct meaningful failures. This is a design decision, not a routine user selection; honor any explicit scope the user supplies.
3. Define the exact population: contributing System, key/grain, Mapping predicates, batch/time window and runtime point. Full current state, historical state and one load's changes are different populations. Group association and equal batch numbers do not make two queries comparable.
4. Read actual implementation only for the side being tested. Expected behavior comes from Mapping and attributable business rules. Comparing generated SQL with a copy of itself cannot expose a translation error. Do not invent filters, tolerances, nonempty-data guarantees or expected counts.
5. Resolve required target/source metadata, parameters and environment before finishing executable definitions. An absent physical table can leave execution pending; authoring does not create it. Current catalog qualification and external-consumer gaps remain explicit in the record guide.

## Select useful assertions

Choose checks from the Model's actual behavior and risks. There is no minimum count, fixed quota or mandatory check per field/target. Cover meaningful failures, then remove duplication; reducing the count must not hide a required invariant.

For each candidate, identify the failure it detects, why it matters here and what action a failure would prompt. Keep it only when it adds useful coverage beyond existing checks and verified enforcement. Skip tautologies, repetitive existence/type checks already established by structural validation, and checks that merely restate the same guarantee for every column or stage. A simple key or null check can still be valuable when it detects a plausible failure; "obvious" means no useful added assurance, not simply easy to write. Do not assume a declared database constraint is actually enforced.

| Concern | Useful assertion / qualification |
|---|---|
| Required values | Count missing required values equals zero; test blank text only when the contract treats it as missing. |
| Key uniqueness | Count duplicate groups on the complete key, including System namespace when part of identity. Null keys need a separate required-value rule. |
| References and lookups | Count non-null child keys without an eligible parent; respect complete join keys, optionality, filters and temporal validity. Check lookup multiplicity when it could multiply output. |
| Row reconciliation | Compare expected and actual populations after specified filtering, aggregation and deduplication. Raw source count equals target count only for an actual one-row-to-one-row contract. |
| Coverage and values | Detect missing/unexpected keys or wrong mapped values. Equal counts alone can hide one lost key and one extra key. Preserve duplicate multiplicity where relevant. |
| Control totals | Compare contract-defined amounts/counts at the correct grain and precision; no invented rounding or tolerance. |
| Domain/business rules | Test confirmed allowed values, relationships or conditional rules. Names and sampled values alone do not establish an exhaustive allowed set. |
| Types and output contract | Statically verify columns/types/order; use a justified SQL assertion for observable conversion/range failures. Successful execution alone does not prove valid values or full schema compatibility. |

Transformation-output checks use the actual supplied projection. The own surrogate and framework-generated fields, including applicable Type 2 validity/current-version fields, are absent there under the [population contract](../model/keys-and-audit.md#population-boundary-and-implementation-alignment); inspect them on loaded targets when relevant. Mapped natural/foreign keys, business fields and SourceSystemID remain output responsibilities. Historical versions intentionally repeat the member's natural key; a uniqueness check must use the appropriate current-member/version scope. Do not create identical checks at both points without a distinct failure they address.

For multi-System targets, explicitly filter System-specific assertions. Cross-System uniqueness/reconciliation needs the combined population defined by Mapping; a per-System filter would hide collisions. Resolve one appropriate owner Group and name the combined scope rather than duplicating a check under every System. Current records have one owning System and no structured multi-System assignment; freshness across contributing Systems needs explicit review.

## Group by technical purpose or functional feature

| Family | Group around | Example new Group / Check |
|---|---|---|
| Technical | A relevant mechanism or integrity concern, such as key integrity, lookup behavior or load reconciliation. | `SilverCustomerTechnicalIdentity` / `NoDuplicateCustomerKeys` |
| Functional | A business feature or outcome, such as order pricing, customer eligibility or balance calculation. | `SilverOrderFunctionalPricing` / `NetAmountMatchesPricingRule` |

These are naming examples, not required Groups. Reuse stable existing identities. For new names, use PascalCase and express technical purpose or functional feature; add target, layer or System only where useful to distinguish scope. Keep descriptions short. A Group may cover a relevant target or a System feature spanning targets; do not split every target/attribute into its own Group or force unrelated checks into a broad Technical/Functional bucket. Each Check still tests one recognizable assertion.

Reconciliation belongs to the applicable technical purpose or functional feature; it does not require a third family. New category codes can express this as `technical.uniqueness`, `technical.reconciliation` or `functional.pricing`. These are conventions within the flexible [record field](../model/validation.md#identity-and-field-shape), not new enums or payload fields; preserve valid existing categories. The family is conveyed through names/categories, without an extra Group-type field.

Severity identifies intended significance: confirmed required-contract violations normally `blocking`, uncertain diagnostics `warning` or `informational`. Severity alone does not prove a framework gating action exists.

## Build an independent scalar assertion

1. Query A measures actual behavior; Query B, when used, independently calculates the expected result. A literal is appropriate for a confirmed invariant such as zero duplicate groups. Required preparation may reproduce the actual code chain on A; do not mechanically copy that chain onto B as the expectation.
2. Each batch declares its own necessary temporary relations. Query B, another Check and another execution call cannot reuse A's temporary state. Include only required preparation, while retaining every dependency needed to test the real implementation.
3. End with exactly one row and one column of the declared type, except an explicit execution-only Check. Use an aggregate failure count or another deliberate scalar. A zero-row SELECT is a query-contract error; it is not the scalar value zero or null.
4. Choose the operator and typed operand from the record guide. Return enough precision to test the actual rule. For approved tolerance, calculate the deviation explicitly and compare with the confirmed bound; no assumed tolerance in `equal`.
5. Define empty-input and null behavior. `COUNT(*) = 0` can establish no observed violations in an empty population, but not that a transformation processed data. Add a nonempty assertion only when required. Aggregates such as SUM may yield null; do not turn that into an automatic pass with an unexplained default. Null operators test null deliberately; ordinary null-comparison behavior requires the consumer contract.

Synthetic reasoning example: if Mapping drops cancelled orders, comparing loaded count with all source orders is wrong. Compare the eligible population, then add key/value coverage where needed. If both sides contain ten rows but different OrderIDs, count equality alone misses the defect.

## Runtime scope and optional preflight

Saved definitions use confirmed runtime parameters/populations, not profiling batch IDs. Do not infer "latest", widen to all history, assume every target retains every source row, or add a filter solely from a field name. Loaded-state checks must account for the actual append/merge/history behavior being tested.

Optional evidence execution follows [query scope](../query-scope.md), including explicit batch selections for batched Objects, authorized access, masking and bounded independent calls. A runtime full-state definition and a batch-restricted probe can have different coverage; preserve the definition and label that limitation. Do not remove a required evidence filter to make a probe match, or claim partial execution validates the full runtime population.

Keep concrete substitutions and diagnostic variants separate from saved definitions. Respect SQL policy; Never permits authoring/static review only. The current tool can preflight supported SQL batches but does not establish an implemented external comparison runner. Record actual aggregate outcomes and scope when executed; never invent a passed assertion from a parser pass or persist raw physical rows/tool envelopes.

## Review the complete local batch

| Rule | Required review |
|---|---|
| `checks.coverage` | Selected targets/Systems and material Mapping rules are accounted for; preserved, excluded and unresolved items are visible. |
| `checks.independence` | Each expectation is supported independently of the implementation; no tautological comparison or invented business rule. |
| `checks.population` | A/B use comparable grain, Systems, filters, period and lifecycle point; cross-System and historical cases remain explicit. |
| `checks.meaning` | Each assertion detects a concrete error; empty/null handling and precision are deliberate. |
| `checks.value` | Each new check adds useful, actionable coverage; groups reflect model-specific technical purposes or functional features, without quotas or redundant checks at both stages. |
| `checks.contract` | Apply [record checks](../model/validation.md#validation-record-checks), complete references, SQL safety and independent batch rules. |
| `checks.preservation` | Selected updates preserve unrelated/locked work and pending edits; no partial input to complete-ledger retirement logic. |
| `checks.evidence` | Distinguish authored definitions, structural checks, SQL preflight, unexecuted checks and unknown external-runner behavior. |

Keep the concise coverage proposal and actual findings in the existing task and Workbench review. No second handoff ledger or invented result dataset is needed. Fix a bad test here; an ambiguous business rule returns to Mapping. Group freshness must reflect reviewed input changes, not just rewritten descriptions.

Source: existing GDS `references/workflows/validation.md`, the Mapping/Code consumer contracts and the source pointers in [Validation records](../model/validation.md). These are documentation rules; automation of additional semantic checks remains implementation work.
