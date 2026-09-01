# Automatic journey

Load only for a multi-target Automatic request. Load `platform-lifecycle.md` once; safety gates stay
per target.

## Intake and queue

Ask one compact intake for missing decisions only: directory, Tenant Code, Model, Full/Selected
scope, Logical sections, destination Object Tenant/System/Connection/schema/type, Process metadata,
Dimensional branch, Code type, QA System codes, and SQL policy. Infer supplied answers.

After intake, queue the requested targets with plans. The first `task-add` returns `doing`; start it immediately
with readiness and its scope loop. Later tasks stay queued; never run their readiness early.
Do not create separate tasks for Profiling, Analysis, Conceptual, or external scope activation: the first
three are Logical phases, and external scope activation is a prerequisite on the Mapping task.
Normal route:

```text
Profiling evidence → Analysis → Conceptual → Logical
→ Silver Target Registration → external Model Scope activation
→ Logical Mapping → Code Generation and/or QA
```

Profiling checks existing coverage and may collect bounded evidence under the SQL policy; it never
creates authoritative Profile records. Analysis/Conceptual are optional; Logical is required.
Dimensional, Gold Registration/Mapping/Code, Code Generation, and QA are queued only when requested.

## Progress

Loop eligible scope units in compact batches. Persist the loop line defined by `session.md`.
Coverage checks are internal; ask no review question before the complete target digest. Pause only
for a blocker or the target boundary.

After fresh Apply approval and Apply, call `status`. For a returned waiting/queued task, state its prerequisite and ask one continue question;
on yes start it and reuse intake. When `status.resume` is null, report the journey complete;
do not ask to continue. Never ask the user to restate the journey.
