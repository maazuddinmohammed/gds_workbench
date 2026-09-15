---
name: atlas
description: Start or resume Atlas, resolve Tenant and working directory, and route a request to the appropriate data-modeling or metadata workflow. Use for Atlas initialization, missing workflow context or workflow selection; a clearly selected workflow can also be invoked directly.
---

# Start or resume atlas

Establish context and load the selected workflow. This entry skill does not own modeling methods, snapshot refresh policy or the submission lifecycle.

First, open or reuse the bundled Workbench using the [startup launcher](../../references/working-method.md#current-initialization-capabilities). Do this on every Atlas start/resume, including read-only requests or when no workflow, Tenant or Snapshot is selected yet. Do not wait for setup questions or data readiness; the app can open without a workspace. Reuse an already open Atlas Workbench rather than creating duplicate tabs.

## Establish only missing context

1. Follow the shared [working method](../../references/working-method.md#initialize-or-resume). Resolve Tenant and an absolute working directory, reusing valid saved context unless the user changes it. Only when neither supplied nor valid saved directory is available, announce the actual current directory and use it. An invalid supplied path requires correction. Do not begin workspace setup without a resolved directory.
2. Inspect existing `.atlas` context and unfinished work before creating or replacing anything. Show the relevant Tenant, Model/workflow and unfinished outcome. Reuse an explicit resume/new-work choice; ask "Resume this task or start new work?" only when existing unfinished work leaves intent unclear. Preserve old drafts and bindings when switching Tenant/Model or starting new work.
3. Resolve a supplied Tenant name/code against verified context or authorized MCP listings using [current initialization capabilities](../../references/working-method.md#current-initialization-capabilities). Ask for its name/code if absent. Show a Tenant choice list when requested or needed to resolve ambiguity; do not force a menu after a clear selection or invent an ID.
4. Resolve the requested workflow before asking for Model/SQL inputs. Use the table below; if unclear, ask "What would you like to do?" with the supported workflow choices, including Custom. Route a specific request directly rather than asking the user to restate it.
5. Read the selected workflow's entry requirements. Resolve a Model only when needed; reuse a valid supplied/saved Model, or ask for its name/ID and offer available Models when requested. Resolve SQL policy/environment only when relevant, following the working method. Group related missing questions; do not make a simple read complete every setup field.

## Select one workflow

Show these workflow choices when no workflow is selected. Guided and Grill Me are separate choices, not a hidden submenu.

| Workflow choice / request | Instructions to load |
|---|---|
| Metadata authoring — physical metadata, Copy or focused Process settings | [Metadata authoring](../atlas-metadata-authoring/SKILL.md). |
| Metadata enrichment — descriptions and inferred data types | [Metadata enrichment](../atlas-metadata-enrichment/SKILL.md); Model needed only for Model-scoped enrichment. |
| Logical build — Guided | [Logical Guided](../atlas-logical-build-guided/SKILL.md). |
| Logical build — Grill Me | [Logical Grill Me](../atlas-logical-build-grill-me/SKILL.md). |
| Dimensional / Gold build — Guided | [Dimensional Guided](../atlas-dimensional-build-guided/SKILL.md). |
| Dimensional / Gold build — Grill Me | [Dimensional Grill Me](../atlas-dimensional-build-grill-me/SKILL.md). |
| Target registration — Silver/Gold metadata and optional DDL | [Target registration](../atlas-target-registration/SKILL.md). |
| Entity binding — match Entities/Attributes to registered targets | [Entity Binding](../atlas-entity-binding/SKILL.md). |
| Mapping — transformation instructions | [Mapping](../atlas-mapping/SKILL.md). |
| Code generation — transformation code from Mapping | [Code Generation](../atlas-code-generation/SKILL.md); [first release](../../references/release-scope.md) generates SQL and preserves existing Python. |
| Validation — technical/functional checks | [Validation](../atlas-validation/SKILL.md). |
| Process metadata — register generated files and runtime details | [Process metadata](../atlas-process-metadata/SKILL.md). |
| Custom — investigation or other requests | [Custom](../atlas-custom/SKILL.md); derive required inputs from its outcome. |

If a request says only Logical or Gold build, resolve [Guided versus Grill Me](../../references/working-method.md#build-workflow-routing). A named mode already supplies the selection. Treat “drill me” as a conversational alias for Grill Me; keep the displayed name Grill Me and use the same dedicated skill. State the selected operation and mode together, such as “Logical build — Guided”, never only “Build” or “Guided”.

For registration, Binding, Mapping, Code or Validation, resolve Logical/Silver versus Dimensional/Gold from the request/context; ask only if ambiguous. Several requested workflows can form one journey, but run each under its own prerequisites and completion boundary. Naming a later workflow does not approve Apply or execution.

## Prepare and continue

1. Let the selected workflow decide which Metadata/Model Snapshots are required and when they must be fresh. Use the shared [snapshot rules](../../references/working-method.md#snapshot-use) and readers; do not fetch both blindly, refresh per task or install over pending work.
2. Establish/reuse saved context through the [Atlas runtime](../../docs/runtime-guide.md). Use `session-init`, `task-select`/`task-add`, `model-select` and `sql-policy` as needed; never point legacy GDS helpers at `.atlas`.
3. With Workbench already open, have the user select or reconnect the resolved working directory when `.atlas` is ready. Follow the shared initialization capability notes; do not invent a localhost server or port. Resume the selected folder rather than opening another workspace for every task.
4. State the resolved workflow/context and continue with its instructions in the current conversation. Use one task per meaningful authoring outcome; simple explanations need no task. Snapshot identities and handoff/progress follow the working method, without an extra handoff file.

Reading another `SKILL.md` is instruction routing, not a portable skill-call API or a new agent/session. Direct workflow entry uses the same context checks and must not loop through initialization again. Load only the selected skill and relevant references. See the [user guide](../../docs/user-guide.md) for exact prompts and choices.
