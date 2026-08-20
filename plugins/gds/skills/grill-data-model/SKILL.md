---
name: grill-data-model
description: "Run a bounded, one-question-at-a-time interview to stress-test a Conceptual, Logical, Dimensional, or mapping brief and record decisions. Use only when a user explicitly says grill me, requests a modeling interview or stress test, or accepts an offered grill; do not trigger merely because a brief is ambiguous."
---

# Grill Data Model

Resolve the smallest set of decisions needed for a high-quality model. Ask exactly one
question per turn and wait for its answer.

Read [question tree](references/question-tree.md) for branch order and stopping rules.
Read [decision record](../../references/decision-record.md) before writing decisions.
Use [modeling method](../../references/modeling-method.md) to challenge the design.
Read [model datasets](../../references/model-datasets.md) when the brief may affect
profiling, analysis, Assertions, mappings, Model details, or Model Scope in the same
19-dataset Model Change Set.

For best results, start with the target Tenant/Model, intended layer or business
process, stopping boundary, and any accessible requirements or decisions. Route source
material through `$capture-modeling-assertions` first when durable facts and locations
will answer several branches. Do not re-ask facts already present in current Model
records or retrieved Assertions.

## Set the bound

At the start, state the default budget: up to seven questions. Stop early when shared
understanding is sufficient. The hard maximum is ten unless the user explicitly asks
for a different limit. The budget counts total question turns, including
clarifications and requests for documentation authorization. State the budget and ask
the first atomic question in the same turn.

If the user says stop, enough, pause, or summarize, ask nothing else and return the
bounded summary immediately. If the user says skip, mark only the current branch open
or not needed and continue within the remaining budget. End on skip only when the user
says to skip the interview or all remaining questions.

If the user already supplied answers, acknowledge them and skip those branches. Use
safe MCP reads to verify discoverable current Model facts, including profiling,
analysis, Assertion, and mapping records; do not ask the user to repeat them. Do not
acquire a Tenant Lock, create/Stage/Apply a Change Set, or run external SQL during the
interview unless the user separately requests that action.

## Ask one decision at a time

For each turn:

1. summarize the relevant accepted fact in one sentence;
2. ask one material question with one decision focus;
3. explain why that decision changes the model in one short sentence; and
4. wait.

Do not bundle subquestions, ask for a data dump, or present an exhaustive
questionnaire. Challenge contradictions directly: mixed grains, missing owners,
unsupported identifiers/cardinality, unsafe aggregation, unowned history policy,
unmapped sources, or naming that conflicts with current templates.

Maintain a compact readiness ledger across all Model Change Set sections:
`model_scope`, `profiling`, `analysis`, `assertion`, `conceptual`, `logical`,
`dimensional`, and `mapping`. Mark each current, proposed, not needed, or blocked with
an owner. Ask about only the highest-impact unresolved item; do not turn the ledger
into eight questions.

Update the existing ADR/decision log after each resolved branch when the user has
authorized local documentation. If no format exists, ask before creating the suggested
`.scratch` record. Separate user decisions, source evidence, recommendations, and
assumptions. Do not turn interview answers into Modeling Assertion records unless the
user explicitly requests that separate authoring boundary.

## Stop deliberately

Stop early once these are known for the requested scope: Model Change Set sections,
model type, business scope, sources/evidence, required profiling/analysis, Assertion
provenance, grain, history behavior where relevant, mapping coverage, naming posture,
ownership, and observable acceptance criteria. A branch can be marked open when the
responsible owner and next decision are explicit; do not invent an answer.

At the bound, do not ask another question. Return:

- accepted decisions;
- assumptions and confidence;
- unresolved issues with owners;
- current naming/source/grain/history posture;
- eight-section/19-dataset readiness, including profiling, analysis, Assertions, and
  mappings;
- recommended model skill and stopping boundary; and
- the next one to three safe actions.

The interview improves a brief; it does not itself validate or apply a model.
