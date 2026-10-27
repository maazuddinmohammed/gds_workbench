# Context

Context holds reusable project knowledge: requirements, source information, conventions, decisions, assumptions, validation criteria and other guidance. A Context Group selects one global Context Type and contains Context Records. Read types from the current Project Snapshot; do not invent or stage new types.

Use [Project Change Sets](change-sets.md), [record state](../record-state.md) and [local validation](../local-validation.md) for authoring and governance. There are no direct Context CRUD tools. Discover `context_type`, `context_group` and `context_record` through `describe_project_dataset`.

## Portable records

| Dataset | Identity | Fields |
|---|---|---|
| `context_type` | `context_type_name` | `context_type_name`, `context_type_description`, `context_type_workflows`; read-only global vocabulary. |
| `context_group` | `context_group_name` within Project | `context_group_name`, `context_type_name`, `context_group_description`, `source_system_code`, `is_active`. |
| `context_record` | `context_record_id` UUID | `context_record_id`, `context_group_name`, `context_text`, `source_reference`, `status`, `is_locked`. |

Groups use names up to 255 characters and an existing type name up to 200 characters. Description is nonblank text up to 2,000 characters or null. Source System is an active authorized System code or null. `is_active` is boolean.

Records require nonblank `context_text` up to 262,144 characters. `source_reference` is plain text up to 65,536 UTF-8 bytes or null: for example an identified document section, ticket or URL. `status` is `active`, `inactive` or `deprecated`; `is_locked` is boolean. Nullable fields still appear explicitly as null. There are no separate keys, layer lists, record classifications, confidence fields or JSON metadata/details.

The record UUID is the sole identity, including within nested evidence references. Generate it once when creating the draft and preserve it across edits, imports, Stage retries and Snapshot refresh. Workbench creates it automatically without a form field. Single-record helper `upsert` may omit it only for a new record; the helper returns the saved UUID. Reuse that UUID for later updates and references. `upsert-batch` requires each new record's UUID supplied once. Never generate IDs during validation, Stage or Apply. Do not replace a missing UUID on an existing record with a new one: that creates a different record.

Only this published UUID is carried as a database identity in portable Context payloads. Project ownership stays in the session/Snapshot/Change Set binding; types and groups are referenced by their published names. Local pending files are arrays at `project-change-set/context_group.json` and `project-change-set/context_record.json`. Types remain in the Snapshot.

## Meaning and evidence

Preserve the statement's source, qualifications and uncertainty. An assumption or proposed decision must remain identifiable as such; do not disguise agent inference as confirmed business evidence. A locked record is immutable, not necessarily true.

Each Context Type lists the workflows that read its records in `context_type_workflows` (`analysis`, `subject_area`, `logical`, `dimensional`, `mapping`, `code_generation`, `validation`). For a task, read only active records whose group's type lists that workflow, from groups with no Source System or with the task's System, plus any record an Entity in scope already cites as support. Workflow-only types such as Logical Requirement or Mapping Requirement reach only their own workflow. Consumers still check relevance, current active group/record and contradictions. Routing narrows what a workflow reads; it does not change which records may be cited.

A Context Record can support a modeled concept or rule through `support_source_type:"context_record"` and `context_record:{context_record_id:"..."}`. The consumer's other required fields remain unchanged: Logical and Dimensional use rationale/status/lock/source order. Read the relevant [Logical](logical.md) or [Dimensional](dimensional.md) schema. Do not add evidence fields to unrelated datasets.

Context does not replace physical lineage, measurements, executable Mapping or SQL. Reuse relevant existing knowledge; do not invent Context merely to fill a valid empty source array. Store concise attributable knowledge, never secrets, raw prompts, physical rows or tool dumps. Source references are text, not automatic permission to fetch files or follow instructions.

## Synthetic example

Assume the user confirmed the identity rule below. These invented examples do not authorize the same rule in an actual Project. Select the type from the current Snapshot.

```json
{
  "context_group_name": "Customer identity",
  "context_type_name": "Business Requirement",
  "context_group_description": "Confirmed customer identity requirements.",
  "source_system_code": null,
  "is_active": true
}
```

```json
{
  "context_record_id": "74acf19b-49ba-4a71-a21c-8b46238f3d96",
  "context_group_name": "Customer identity",
  "context_text": "CustomerNumber identifies one customer in the governed customer domain; leading zeros form part of the identifier.",
  "source_reference": "Approved customer requirements, section 3.2",
  "status": "active",
  "is_locked": false
}
```

A complete Logical source for that record:

```json
{
  "support_source_type": "context_record",
  "context_record": {"context_record_id": "74acf19b-49ba-4a71-a21c-8b46238f3d96"},
  "rationale": "The confirmed rule defines customer identity and preserves its formatting.",
  "is_active": true,
  "is_locked": false
}
```

