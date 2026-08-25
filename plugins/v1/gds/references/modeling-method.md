# Modeling method

Use this as design guidance, not as a substitute for the live GDS record schemas or
the user's business decisions. The dimensional guidance paraphrases relevant methods
from *The Data Warehouse Toolkit*, third edition; no book text is bundled.

## Shared discovery

Before choosing records, establish:

- business outcome and in/out scope;
- model layer(s) and intended consumers;
- source systems, physical scope, profiling evidence, and known quality limits;
- business vocabulary, owners/stewards, security boundaries, and refresh needs;
- Preserve current naming templates and established names by default; ask only when
  the user requests a naming/template change or a real conflict prevents progress;
- decisions already made, open questions, and measurable acceptance checks.

Use existing Model records as the baseline. Preserve traceability with physical source
keys or Modeling Assertion support records. Mark uncertain claims with honest
confidence and `needs_review`; do not turn assumptions into facts.

## Model Change Set evidence

Treat all eight Sections as one evidence chain when they are relevant:

```text
Model Scope → Profiling / Analysis / Assertions → Conceptual → Logical
            → Dimensional → Mapping
```

Profiling records contain observed counts, lengths, and percentages; Analysis records
contain evaluated relationship results and validation counts; Assertions capture
sourced statements not established by physical evidence alone. They may be staged in
the same governed Model Change Set as layer and mapping records, but only with real
provenance. A grill may establish which evidence is required, its owner, and its
acceptance threshold. It must not manufacture observations or claim an analysis ran.

## Conceptual model

Describe the business, not storage implementation.

1. Define the domain boundary and a short shared vocabulary.
2. Identify stable business concepts with singular, business-readable names.
3. Give every concept a definition, type, and grain: what one instance represents.
4. Add aliases only when they clarify real terminology differences.
5. Define relationships in business language. Record direction, cardinality, basis,
   and confidence; use unknown when evidence is genuinely insufficient.
6. Attach source Object or Assertion support and explain why it supports the claim.
7. Review for duplicate concepts, overloaded terms, hidden implementation detail,
   unsupported cardinality, and out-of-scope concepts.

Acceptance: a business stakeholder can explain the scope, every concept, and every
relationship without reading physical table names.

## Logical model

Describe normalized business structure independently of a target platform.

1. Start from approved Conceptual vocabulary and source evidence.
2. Define each Entity's purpose, type, grain, dependency order, and submodel.
3. Add complete Attributes with definitions, logical data types, ordinal,
   nullability, and source traceability.
4. Identify durable business/natural identifiers. Introduce a logical surrogate key
   only when its role is explicit; a key Attribute cannot be nullable and cannot be
   both natural and surrogate.
5. Resolve repeating groups and mixed-grain Attributes. Normalize to a level that
   prevents update anomalies while keeping explicit business rules.
6. Define relationship endpoints and one/many cardinality. The live relationship enum
   does not encode zero/minimum participation; record optionality in its basis and an
   authorized decision/Assertion, clearly labeled as descriptive rather than enforced.
7. Check that every Attribute depends on the Entity's declared grain, every
   relationship endpoint exists, and names follow the selected template.

Acceptance: identifiers, optionality, cardinality, normalization choices, business
rules, and source lineage are explicit and reviewable.

## Dimensional model

Use the four-step discipline for each measurable business process:

1. Select one business process that produces measurable events.
2. Declare the fact grain in one precise sentence before choosing dimensions or
   measures. Prefer atomic grain and use separate facts for separate grains.
3. Identify Dimensions that are single-valued at that grain: who, what, where, when,
   why, and how.
4. Identify Facts true at exactly that grain. Classify each measure as additive,
   semi-additive, or non-additive and record its valid aggregation basis.

Then decide and document:

- transaction, periodic-snapshot, accumulating-snapshot, or factless fact type;
- conformed dimensions and measures across processes; incompatible measures get
  distinct names;
- warehouse surrogate keys while retaining business/natural identifiers;
- role-playing dates, degenerate transaction identifiers, junk flags, and audit
  provenance where justified;
- SCD behavior per descriptive Attribute: fixed, overwrite, or historize, based on a
  steward decision that distinguishes source correction from true change;
- explicit unknown/not-applicable members instead of null fact foreign keys;
- bridges for legitimate multivalued Dimensions, including effective periods and
  allocation weights when needed;
- late facts resolved to the historical Dimension version effective at event time;
  and placeholder Dimension records for valid context that arrives later.

Grill each Dimension: can there be more than one value for one fact row? If yes,
change the grain, omit it, or use an explicit multivalued pattern. Grill each Fact:
is it true at the exact declared grain, and is its aggregation safe?

Acceptance: business process, atomic grain, dimensions, facts, additivity,
conformance, history, late-arrival behavior, default members, and source feasibility
have named decisions and validation evidence.

## Data mapping

Prefer derivation from existing `mapping_*` records and modeled source metadata.
When absent, elicit the missing mapping at two grains:

- Object: source physical Object, source system, target modeled type/name,
  dependency order, artifact choice, package instructions, and direct/derived
  transformation document.
- Attribute: exact parent Object mapping, source physical Attribute, target modeled
  Attribute, direct/expression transformation, data type handling, null/default
  behavior, filters, joins, keys, and data-quality rules.

Profile source columns before finalizing transformations. Record dependencies and
audit provenance. A transformation description is not executable proof; validate
the mapping against source availability, target grain, keys, and representative edge
cases. Never place raw physical row samples into records or logs.

## Iteration and review

Move between requirements and source evidence. Review vocabulary and meaning with
business owners, and feasibility, keys, transforms, and quality with technical
owners. Keep an issues/decision log. A model is ready only when it meets stated
requirements, its sources can populate it, open issues are visible, and the GDS
server validates its future graph.

Source page references for the paraphrased dimensional practices: PDF pages 74–103
(printed 38–67), 466 and 472–477 (printed 430 and 436–441), 513–515 (printed
477–479), and 536–538 (printed 500–502).
