# Dimensional design

Shared method for Guided and Grill Me. [Context](context.md) defines eligible inputs; [Dimensional records](../model/dimensional.md) defines fields/sources. Use [naming](../model/naming.md) and [keys/audit](../model/keys-and-audit.md) rather than copying their policies here.

## Process and grain first

Apply the fact-specific decisions below when facts are in scope. A dimension-only request instead defines its member/version or calendar grain and intended use, then follows the relevant dimension/history/source rules. It does not require inventing a fact, measures or a physical source.

1. Start from the analytical outcome and an operational business process, such as taking orders, recording payments or measuring daily stock. Propose plausible processes from the eligible context; do not turn every Silver table or report into a fact.
2. State one row's business meaning before choosing measures or dimension keys: for example, one posted order line, one account at each day-end, or one claim moving through milestones. Include identity, time boundary and whether repeats/corrections create a new occurrence. A list of foreign keys or a generated surrogate alone is not a grain definition.
3. Check that the source actually supports that detail and requested history. Prefer useful atomic detail; create deliberate aggregate structures only for a justified analytical need with their own grain. Do not invent missing historical states.
4. Resolve inconsistent header/line, event/current-state or time-period meanings before proceeding. A header charge cannot be repeated on every line and then summed; retain its own grain or use an explicit supported allocation rule.

This sequence follows [Kimball's four design decisions](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/four-4-step-design-process/): process, grain, dimensions and facts.

## Dimensions and conformance

- Identify descriptive context true to the fact grain. Favor useful flattened business hierarchies; do not mechanically reproduce Logical normalization as a chain of dimension tables. A separate dimension/bridge needs a real semantic or analytical reason. See [flattened dimensions](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/denormalized-flattened-dimension/).
- Reuse a shared dimension only when meaning, business identity, values and relevant history agree. Matching names, column layouts or IDs across Systems do not prove conformance. Keep distinct identities until the reconciliation rule is known. See [conformed dimensions](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/conformed-dimension/).
- Reuse one dimension for genuine roles, with distinct FK Attributes, relationship roles and query aliases—for example OrderDate and ShipDate. Do not copy the dimension's rows/definition for each role. See [role-playing dimensions](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/role-playing-dimension/).
- A transaction identifier with no independent descriptive context may remain a degenerate dimension Attribute on the fact. A repeated label or low-cardinality field alone does not justify another table. Retain useful business descriptors and identifiers without forcing arbitrary dimension-count targets.
- Compare processes with a compact process-to-dimension view when it helps reveal reuse or incompatible meanings. Keep it in existing task/review context, not a new required Model dataset. Reuse Entities through Submodel memberships rather than creating process-specific copies.

## Facts and measures

| Pattern | Row meaning and decisions |
|---|---|
| Transaction | One business event at the declared detail; preserve event identity and timestamp meaning. |
| Periodic snapshot | One reporting entity at a defined period boundary; define cadence, as-of meaning and required population, including no-activity cases. |
| Accumulating snapshot | One process occurrence updated across known milestones; define milestone roles, repeated events and completion/reopening behavior. |
| Factless | An event, coverage or eligibility relationship without numeric measures; define exactly what a row counts. Do not invent a measure merely to fill the model. |

Choose the pattern from behavior, not its table name. The first three have different time/row semantics; see [Kimball fact-table patterns](https://www.kimballgroup.com/2008/11/fact-tables/). Factless is an additional supported Atlas fact-type value; it does not by itself specify whether rows mean events or coverage.

For each measure, record its meaning, units/currency, supported type/precision, additivity and default aggregation. Name valid axes for a semi-additive measure: an account balance may sum across accounts but not across dates. Ratios need a valid calculation basis, often summed numerator/denominator rather than averaging row ratios. Do not sum identifiers, mix currencies/units or manufacture a default aggregation. See [additivity guidance](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/additive-semi-additive-non-additive-fact/).

The schema requires aggregation fields for measures and a basis for semi/non-additive measures. Preserve that exact shape. Non-measure Attributes cannot carry measure-policy fields. Bridge weights have their own role; keep their allocation meaning in supported definitions/basis rather than incompatible measure fields.

## Relationships, history and bridges

1. Use actual modeled Attribute endpoints with compatible types and supported cardinality; identify optionality explicitly. FKs normally reference the dimension's surrogate. Their values require the complete business-key lookup, not copying a Silver identifier into an unrelated generated key.
2. Apply [history and lookup rules](history.md) to current versus event-time membership, late arrivals and corrections. Resolve essential business decisions before dependent Mapping; keep unverified execution support explicit.
3. Introduce a bridge only for meaningful multiple membership at the stated grain. Declare one bridge row, membership identity, applicable time and how filtering/aggregation avoids double counting. Allocation weights are used only when the business defines allocation; never invent equal weights. See [multivalued dimensions and bridges](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/multivalued-dimension-bridge-table/).
4. Review joins for row multiplication and loss. Avoid joining unrelated atomic facts just on shared dimension keys; compare their separately aggregated results at a compatible grain. See [fact-to-fact join guidance](https://www.kimballgroup.com/data-warehouse-business-intelligence-resources/kimball-techniques/dimensional-modeling-techniques/multipass-sql/).
5. Set model dependency order from known lookups and relationships; retain cycles/repeated-pass needs explicitly. It is not a Process schedule or permission to execute code. SQL evidence is optional under [query scope](../query-scope.md), including explicit batch choices and qualified coordinates.

## Lineage, standalone structures and Submodels

- Trace derived Entity/Attribute sources to eligible physical Silver Objects/Attributes under the record contract. Logical entity names and Mapping IDs are not supported source-type substitutes. Every Attribute's physical source needs its corresponding Object source on the Entity; source ordering is not executable transformation logic.
- Use multiple real contributors where needed, with concise contribution roles/rationale. Do not duplicate the same source key merely to label a second role. Keep reconciliation or generation decisions available for later Mapping.
- Calendar, constant/reference sets and other justified generated structures can have empty sources. Define calendar grain/range/fiscal rules or the constant values/meanings and change ownership. Use an applicable [Assertion](../model/assertions.md) when useful, never just to satisfy an imagined support requirement. Do not fabricate an Object or System.
- A source-less design still needs a supported population/provenance path before executable Mapping/Code. Current Mapping requires a real source-System context; do not hide this gap with a fake `SourceSystemID` or promise unsupported execution.
- Group Submodels around useful business processes. One small cohesive model may need no split; avoid one group per table/System or speculative empty groups. Share each dimension through memberships, preserving cross-process relationships and active/locked state.
- Account for selected Silver contributions as represented, context-only, excluded with reason or unresolved. Completeness means the requested analytical outcome and useful lineage, not copying every source field into Gold.

## Quality checks

| Rule | Required review |
|---|---|
| `dimensional.grain` | One supported row meaning per Entity; fact/bridge grain explicit, no mixed detail or hidden duplicate business identity. |
| `dimensional.dimensions` | Context fits grain; conformance and role reuse preserve meaning, identity and history. |
| `dimensional.measures` | Facts fit grain; aggregation, units, precision and valid axes prevent wrong totals. |
| `dimensional.joins` | Real endpoints, compatible keys, supported cardinality/optionality; bridges and time lookups avoid fan-out/loss. |
| `dimensional.history` | Attribute changes and fact lookup time agree; required technical fields and their population are explicit. |
| `dimensional.lineage` | Valid Silver sources, matching parent sources and useful coverage; justified standalone structures have no fabricated lineage. |
| `dimensional.population` | Confirmed first generated surrogate on every table, complete shared audit block and explicit extra technical-column responsibility. |
| `dimensional.grouping` | Submodels aid understanding, preserve one shared definition and do not conceal cross-process effects. |

Run [local validation](../local-validation.md) over the complete effective graph and review actual analytical examples. A parser pass, a small table count or a plausible star diagram does not establish correct totals. Preserve locks and unrelated work; keep material uncertainty explicit rather than creating unsupported records.
