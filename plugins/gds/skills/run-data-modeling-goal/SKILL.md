---
name: run-data-modeling-goal
description: "Turn a Conceptual, Logical, Dimensional, or mapping brief into one durable Codex goal with a verifiable stopping condition, checkpoints, validation, exclusions, and pause rules. Use when a user asks for a /goal prompt, wants Codex to keep working toward a model, or explicitly asks to prepare or start a modeling goal."
---

# Run Data Modeling Goal

Prepare one bounded modeling objective. A skill cannot provide persistence by itself;
Codex's `/goal` feature owns the long-running loop.

Read [goal template](references/goal-template.md), then select the matching modeling
skill and read its workflow. Use [governed model workflow](../../references/governed-model-workflow.md)
for any server write.

## Distinguish prepare from start

- If the user asks for a prompt, instructions, draft, or template, return a paste-ready
  `/goal ...` prompt and do not create or start a goal.
- If the user explicitly asks to start, create, set, or run the goal, prepare the
  objective, inspect current goal state, and invoke the host goal mechanism when
  available. Pass objective text without a `/goal` prefix to a structured goal API.
- If another goal is unfinished, do not replace or clear it without explicit direction.
- If the host goal mechanism is unavailable, return the paste-ready prompt and state
  that it cannot be started in the current client. Do not invent configuration steps.

## Build one goal contract

Resolve the target layer, existing Tenant/Model, business scope, sources, owner,
naming posture, and intended stopping boundary. Ask one concise question only when a
missing choice materially changes the objective. Use `$grill-data-model` only when
the user explicitly asks for a grill or accepts an offered stress test.

Route Conceptual, Logical, Dimensional, and Model Mapping work to
`$build-conceptual-model`, `$build-logical-model`, `$build-dimensional-model`, and
`$build-data-mapping`, respectively.

Inspect affected datasets and direct dependencies only. Existing dependency records
do not become affected merely because they were read. Include supporting profiling,
analysis, Assertions, or mappings only when the objective authors them or cannot be
verified without them. Preserve current naming templates by default; include a naming
decision only when the user requests a naming/template change or a real conflict blocks
the work.

Write one cohesive objective, never a loose backlog. Include:

- one observable stopping condition;
- files, project instructions, current Model/tool schemas, and evidence to inspect
  first;
- the appropriate modeling skill and, only for a server boundary, the exact governed
  MCP workflow;
- small checkpoints with a compact progress log;
- validation artifacts or reads that prove each checkpoint;
- explicit scope exclusions and safety constraints;
- Apply as a separate pause requiring fresh user approval; and
- pause conditions for missing business decisions, source access, authorization,
  another Principal's lock, external writes, or unavailable evidence.

If this goal acquired a Tenant Lock, require release before a validated-draft
handoff and before any terminal pause or abandonment when release is safe. Report a
release failure as an unresolved blocker; never silently leave the lock held.

Choose one end state:

1. proposal: complete schema-checked ID-free records and decision/mapping review;
2. local draft: complete records are saved in `GDS/model-change-set`, locally checked,
   and no lock or server mutation occurs;
3. validated draft: authoritative server Validate succeeds, but nothing is Applied;
4. applied model: Apply occurs only after the user approves the validated action
   review, followed by fresh verification and lock release.

Do not make “keep working forever” the stopping condition. Do not mark an actual
model complete while required source, grain, history, naming, ownership, or acceptance
decisions are unknown. A precise blocker is a valid pause, not completion.

## Handoff

For prepare-only requests, output the finished prompt in one code block plus a short
list of placeholders the user must replace, if any. For an explicitly started goal,
report its objective and stopping condition, then let the goal loop own subsequent
checkpoints. Keep ordinary checkpoint reports to three bullets and 120 words unless a
blocker or authoritative approval review requires more. Never promise that the skill
itself will continue running.
