# Bounded question tree

Ask one question at a time. Default seven; hard maximum ten unless the user explicitly
changes it. Skip facts already answered or safely discoverable.

## Atomic branches

Choose the highest-priority unknown; never combine two branches in one question.

Candidate branches are:

- outcome: the one business decision or analytic use to support;
- stopping boundary: proposal, validated draft, or applied change;
- target layer: Conceptual, Logical, Dimensional, Mapping, or an ordered sequence;
- Model details/naming: preserve, adopt, or replace the current templates;
- Model Scope: the one unresolved physical Object boundary;
- profiling: the statistic or quality threshold required to support a decision;
- analysis: the relationship hypothesis or validation result required;
- Assertion: the sourced statement, document provenance, or applicable layer. Track
  any evidence owner only in the authorized decision/progress log, never as an
  Assertion JSON property;
- grain: what one concept instance, Entity row, or Fact row represents;
- structure: one unresolved identifier, relationship/cardinality, Fact, Dimension, or
  measure choice with the largest downstream effect;
- time/history: the one change that requires retained history;
- mapping: one unresolved physical source, modeled target, dependency, or
  transformation choice;
- naming/conformance: one unresolved shared-definition choice;
- ownership: who decides the most important open semantic/evidence issue; or
- completion: the one observable acceptance check.

Profiling, analysis, and Assertions are first-class Model Change Set evidence, not
preliminary trivia. Prefer their current governed records when safe reads answer the
branch. Ask the user only for the decision or provenance still missing, never for raw
physical rows.

Use any remaining turn for one blocking contradiction: Tenant boundary, mixed or
multivalued grain, unsafe aggregation, mapping transformation, or proposal versus
validated/applied stopping boundary. A clarification consumes another question turn.

## Stop test

Stop when the relevant eight-section coverage, type, scope, evidence, grain, history,
naming, mapping, ownership, and acceptance are answered or explicitly assigned as
open. Do not continue merely to collect nice-to-have detail.

On `stop`, `enough`, `pause`, or `summarize`, stop immediately and return the summary
without another question. Plain `skip` skips the current branch and consumes no extra
question; end only for `skip the interview` or `skip all remaining questions`.
