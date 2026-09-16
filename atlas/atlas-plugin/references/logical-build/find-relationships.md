# Finding relationships

Atlas Analysis uses metadata first. Clear Object purpose, Attribute roles and consistent business context can support a relationship and intended cardinality without SQL. Use SQL selectively under the saved policy to resolve useful questions, not to test every relationship. The batch-aware Analysis generator prepares only requested measurements; the workflow decides reuse or redo.

## Read the right context

Use the [Model Snapshot](../snapshots/model.md), [Model record authoring](../model/change-sets.md), [Analysis record](../model/analysis-result.md) and [query-scope](../query-scope.md) guides as needed. They own file/record/tool and batch rules; do not redefine them here.

1. **Inventory the requested scope.** Resolve requested Objects/Attributes within active applied Model Input Scope. Read Object meaning/grain, Attribute descriptions and physical/inferred types, System context, applicable glossary terms, known keys, profiles, assertions, provenance and existing analysis. Reuse relevant prior findings. Track reviewed Objects so unfamiliar, isolated or unprofiled inputs are not silently omitted. Redo may focus on affected neighborhoods; both endpoints must remain in Model scope.
2. **Find identity and role references.** Compare names, aliases, role prefixes and documented abbreviations: customer_id, bill_to_customer_id and Customer.ID may identify different roles. Normalize names only for discovery, not stored identity or data values. Clear names and consistent Object meaning can support an inferred reference immediately. Also inspect differently named identifiers, hierarchy links and cross-System candidates. Generic id names or incompatible business domains need more context.
3. **Make a separate domain-reference pass.** Inspect every Object's type, category, status, classification, country, currency, code and name Attributes against the scoped reference/lookup Objects. Use descriptions, glossary terms and existing profiles when available. String keys are valid: Product.product_type may reference ProductType.type_name even though neither is numeric or ends in ID. Look for semantic equivalents with different names. A matching business domain supports inference; low distinct counts or shared values alone do not. A category without a reference Object in scope stays a domain/concept suggestion; do not invent an endpoint or require normalization.
4. **State the candidate precisely.** Identify the two exact endpoint keys, business role, direction and complete proposed key tuple. Describe why the meanings should match and what would disprove it. Include Tenant/System/company qualifiers only when they belong to the actual identifier domain. Distinguish a reference, shared category and same business identity; they require different evidence. Preserve billing/shipping roles and self-reference through different Attributes.

Complete both discovery passes across the requested scope. The Grill Me workflow may investigate the current part and its relevant in-scope neighbors, retaining coverage across parts rather than rescanning the whole Model each time. Considering a neighbor does not authorize unrelated changes; a request for the complete Model is finished only after overall coverage review. Include hierarchy links and differently named references. Track meaningful unresolved candidates; no Object must have an edge merely to look connected.

## Resolve uncertainty when needed

5. **Decide whether more evidence is useful.** If names, Object grain, descriptions and known rules give a coherent relationship, retain it as inferred and continue without SQL. Missing profiles do not block that conclusion. Ask a focused question or use a permitted query when uncertainty could change the endpoint, direction, key, cardinality or meaning. Proactive policy may support additional useful investigation; it does not require querying every candidate. SQL Never keeps all reasoning within existing metadata, documents and user context.
6. **Identify the complete key.** Understand whether CustomerNumber is sufficient or Company + CustomerNumber is required. This is a modeling decision from available context, not an instruction to run a SQL test. Preserve all needed columns and their pairing; do not turn a composite relationship into independently claimed component matches. [PostgreSQL key definitions](https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-FK)

### If SQL is needed

Choose only the checks that answer the unresolved question below. First follow shared query-scope rules for each endpoint's batch column, explicit IDs and time/population alignment. Reuse applicable profiling choices. The batch filter applies before counts and joins; a metadata-only inference does not need a fresh batch-selection conversation.

| Unresolved question | Optional measurement |
|---|---|
| Is the proposed parent key usable? | Complete-key rows, distinct complete tuples, duplicate extras, and null-key rows. Explain duplicates from history/repeated loads before changing the model. |
| Does the child reference the parent? | Distinct missing child keys and unmatched child-row counts, separately; check the selected parent population is appropriate. |
| What does each relationship occurrence mean? | Distinct child identities per parent at the established child grain, and possible parent matches per child. Do not use inflated join-result row counts as multiplicity. |
| Is participation optional? | All-null/partially-null child key counts, schema constraints and confirmed business rules. Non-null orphan rows are a different issue. |
| Is a dependency or category meaningful? | Whether the complete determinant identifies one dependent tuple, plus business meaning and lifecycle; repeated values alone are insufficient. |

For tuples, count partial and all-null keys separately. Databricks multi-column COUNT/DISTINCT excludes tuples containing nulls; a matching percentage alone can hide them. [Databricks COUNT semantics](https://docs.databricks.com/aws/en/sql/language-manual/functions/count)

Atlas `analysis-plan` prepares `key`, `dependency` and `join` probes, including composite tuples, with each endpoint's resolved IN batch filter applied before measurement. Unbatched endpoints alone use all stored rows. See the exact input shapes below; do not use the legacy GDS all-row planner on batched data.

When querying, prepare bounded self-contained aggregate queries and expected-output mappings, then follow the shared execution procedure. Preserve exact typed tuples; do not concatenate keys or silently transform values to force matches. A custom query does not automatically qualify for deterministic validation fields. Keep unsupported measurement shapes, including composite results, in evidence.

## Determine cardinality and meaning

7. **Infer the business cardinality; distinguish measurements when present.** Describe cardinality from the referencing Object to the referenced Object. Names, grain and business roles can establish a useful intended relationship without counting data. Label it inferred. If measurements are used, describe observed multiplicity separately and count business occurrences rather than repeated load rows.

| Evidence | Permitted conclusion |
|---|---|
| Orders has one customer_id reference per order; Customer represents customers in the same business context | Infer Orders → Customer as many-to-one and the reverse as one-to-many. No SQL required. |
| Product has one product_type classification; ProductType defines those type names | Infer a many-to-one string-based reference when the meanings agree. No numeric key or SQL proof is required. |
| Documented roles/grain specify one detail record per parent | Infer intended one-to-one from that context; do not require observed counts. |
| Unique parent key; several distinct child occurrences reference a parent | Observed many-to-one. Its reverse is one-to-many. |
| Unique parent key and unique child reference within the inspected population | Observed at-most-one in both directions. A sparse batch alone does not establish a permanent one-to-one business rule. |
| Associative records identify multiple distinct partners on both sides, with meaningful endpoint keys | Evidence for a many-to-many business association. Represent actual bridge references in physical Analysis; conceptual/logical structure is decided later. |
| Duplicate proposed parent keys | Ambiguous lookup, history, incomplete key or repeated data to investigate; not automatic many-to-many. |
| Measurements are absent/empty, but metadata explains the relationship | Keep the supported inference; do not call it measured. |
| Neither metadata nor available evidence explains the relationship adequately | Keep the uncertain aspect unresolved. |

Infer mandatory participation only from applicable constraints or confirmed rules with consistent evidence. Zero non-null orphans does not prove optionality is false: null checks and reference checks are separate. [dbt relationship and null checks](https://docs.getdbt.com/reference/resource-properties/data-tests#relationships)

Declared Databricks PK/FK/unique constraints can support intended relationships as metadata. They do not certify stored-data compliance; that distinction does not require querying them before inference. Resolve known contradictions when present. [Databricks constraints](https://docs.databricks.com/aws/en/tables/constraints)

8. **Decide and review.** Record the supported inference, rejected candidate or unresolved question with its basis. A relationship need not remain unresolved merely because SQL was not run; confidence may be high when context is clear. Consider competing parents, identifier namespaces, code meanings and role distinctions. Equal IDs across independent Systems or equal categories with different meanings do not establish shared identity. Resolve material contradictions instead of hiding them behind confidence.

## Save findings and review coverage

9. **Keep the same output shape.** Use the shared Analysis record guide's existing 26 fields. For unmeasured inference, put the relationship, inferred cardinality and reasoning in relationship_basis, choose appropriate confidence and leave all nine validation_* fields null. No new inference/cardinality fields are added. Record physical Attribute pairs only; keep composite tuples, domain suggestions and other unrepresentable findings in task evidence. Lifecycle status remains separate from the conclusion.
10. **Review coverage and hand off.** Confirm both discovery passes covered scoped Objects, including string classifications, differently named references, role links and hierarchies. Keep meaningful unresolved candidates visible; explain isolated Objects without inventing links. Validate record structure locally through the Model authoring guide; this does not require SQL relationship tests. Preserve locks/unrelated edits and follow the shared Change Set lifecycle when ready.

SQL's directional validation verdict and the overall business conclusion remain distinct. A failed lookup on an incomplete parent batch does not by itself disprove the business relationship. A successful lookup does not establish meaning, required participation or future cardinality. Unsupported measurements must affect the conclusion or its limitations rather than being attached and ignored.

## Compact examples

- **Order → Customer:** clear Object roles and Order.customer_id support an inferred many-to-one relationship without SQL. Record the metadata basis and leave validation fields null. Whether every order must have a customer is a separate optionality question.
- **Product.product_type → ProductType.type_name:** compatible string classifications in the same documented business domain can form an inferred reference. Different names and nonnumeric types do not exclude it.
- **Company + CustomerNumber:** known company-specific numbering requires both columns. Retain the tuple from context; query only when needed to resolve uncertainty. The current Analysis payload cannot express a composite edge.
- **OrderStatus without a status Object:** record a business-domain suggestion, not a fabricated relationship or a mandatory normalization decision.
- **Customer IDs in two CRMs:** equal names and overlapping numbers are candidates only. Require a shared namespace, authoritative crosswalk or other applicable business evidence before identity consolidation.

## Quality checks

| Check | Purpose |
|---|---|
| analysis.scope | Both real endpoints belong to active Model input scope; complete physical keys and ownership distinctions are correct. |
| analysis.evidence | State metadata inference or actual measurement accurately. SQL is optional; generated descriptions are not independent confirmation of themselves. |
| analysis.cardinality | Grain, multiplicity and optionality are distinguished; batch duplication is not promoted to a relationship rule. |
| analysis.payload | Exact schema, lifecycle values, complete validation group, correct metric units and locked-record protection. |
| analysis.coverage | Both identity/role and category/reference passes cover all Objects, including strings and nonmatching names; unresolved candidates remain visible. |

These checks and the procedure are a design synthesis from the cited definitions and the agreed Atlas requirements. The shared local validator checks structure, scope and evidence; business meaning still needs review.

## Analysis to modeled relationships

Analysis has no dedicated cardinality field: put direction and inferred cardinality in `relationship_basis`, leaving unmeasured validation fields null. Later Conceptual/Logical records use their own explicit cardinality field. A category label can be a valid reference key; use `relationship_kind="reference"` for ordinary lookups and describe its category/domain semantics. Matching low-cardinality strings alone do not establish shared meaning or uniqueness.

Analysis findings do not create Logical FKs. During Logical design, map relevant supported associations to the actual modeled grains and keys, then author explicit relationships under the [relationship and graph review](logical-design.md#relationship-and-graph-review). Do not mechanically copy every physical edge or infer a join from matching names alone. Review isolated Entities and disconnected components with the user before completing model work; intentional separation remains valid.

## Analysis planner input

Use `analysis-plan --session <directory> --plan-file <input.json>`. The wrapper is `{ "selections": { "batches": <profiling-selections>, "probes": [...] }, "execution_connections": [...] }`; execution Connection entries follow the [runtime guide](../../docs/runtime-guide.md#profiling-and-analysis-files). Supply one to 50 probes.

| Kind | Exact probe fields |
|---|---|
| `key` | `id`, `kind:"key"`, `object`, `columns:["CustomerCode"]`. |
| `dependency` | `id`, `kind:"dependency"`, `object`, `determinants:["CategoryCode"]`, `dependents:["CategoryName"]`. Determinants/dependents cannot overlap. |
| `join` | `id`, `kind:"join"`, `from:{object,columns:["CustomerCode"]}`, `to:{object,columns:["CustomerCode"]}`. Equal-length ordered lists with matching registered types. |

An `object` is exactly `{tenant_code,system_code,connection_code,object_schema,object_name}` with registered string values. Each column list contains one to eight distinct registered Attribute names. `id` starts with an ASCII letter, followed by at most 63 letters/digits/underscores/hyphens, and is unique in the plan. These are planning inputs, not Analysis Change Set records. The returned manifest lists each query's `result_columns` and interpretation; all queries return one aggregate row.
