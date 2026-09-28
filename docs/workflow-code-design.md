# Code Generation — Mapping evidence and SQL

Code Generation translates applied Mapping for one Logical or Dimensional Entity
at a time. All selected contributing Systems for that Entity are available together.
Artifacts belong to the Entity; physical target registration is not a prerequisite.
See [Entity ownership](adr/012-entity-owned-mapping-and-code.md).

Stage: `sql_generation`. The public workflow execution mode remains `null`; the
agent uses Tool-assisted delivery. Prompt authors choose workflow-local variables
and readers. The executor does not silently append Mapping documents to the prompt.

## Maintained prompt and examples

The [maintained default](workflow-prompts/code.tool_assisted.json) is the source for
the system/instruction prompts. The fresh-install
[seed](../database/seed/05_global_prompt_defaults.template.sql) carries identical
content, checked by tests. Existing published prompt versions are unchanged by
editing these files.

The default inlines only `target_ref` and the selected published
`sql_generation_guide`. Its examples demonstrate:

- One business Attribute plus explicitly mapped source provenance.
- Multiple source Objects, ordered temporary stages, a join, and several Attribute expressions.
- Combined System branches and the difference from separate files per System.

Examples are synthetic. Their names, joins, filters, constants and combination
policy are not evidence for a real Entity. Actual applied Mapping and the selected
Guide determine the SQL. Missing or conflicting business requirements must be
reported through the fixed output issue codes, not replaced with guessed SQL.

## Frozen context and readers

| Input | Reader | Evidence |
| --- | --- | --- |
| `target_metadata` | `get_code_target` | Owning Entity schema/name, Model placement, ordered modeled Attributes, data types and key roles. `population` identifies Mapping, database or framework ownership. |
| `source_metadata` | `get_code_sources` | Eligible source contributions, source System code, role/order and nested physical Object/Attribute metadata. |
| `source_systems` | `get_code_source_systems` | Selected System codes/names and explicit numeric `source_system_value` for provenance. Presentation order does not imply business precedence. |
| `object_transformations` | `get_object_transformations` | Full applied Object documents, source System code, dependency order and schema-qualified modeled Entity identity. |
| `attribute_transformations` | `get_attribute_transformations` | Full applied Attribute documents, source System code, schema-qualified modeled Entity identity, target Attribute name and ordinal. |

`target_ref` is an opaque output handle; copy it unchanged into artifacts. It is
neither a SQL relation nor a business key. `sql_generation_guide` is the exact
frozen content of the selected published Guide.

The default instructs the agent to read all five inputs and follow every
`next_cursor` with a cursor-only call. Optional selectors narrow the frozen
selection; an empty request returns all eligible records, paged. Whole records are
not silently truncated: an oversized indivisible record fails explicitly. The
backend preserves complete transformation documents, including custom nested
keys; it does not replace them with display summaries. Tool usage is instructed,
not enforced as a separate read-all completion gate.

Physical evidence retains Tenant/System/Connection/schema/Object/Attribute natural
keys and catalog placement. Generated Code uses actual `schema.Object` physical
references under the existing Code convention; temporary view names are
unqualified. Full catalog coordinates remain evidence and may be used by separate
Validation queries. Never infer identity from a display label or internal ID.

[Context schemas](workflow-prompts/code.context.json) ·
[Reader contracts](workflow-prompts/code.tools.json) ·
[Synthetic input/output](workflow-prompts/code.review.example.json)

## SQL delivery and validation

Object steps define source preparation, joins and filters. Attribute documents
define the corresponding expressions and source columns. Use ordered temporary
views when the Mapping requires stages, followed by one explicit final projection
in modeled Attribute order. A direct Mapping can be a single `SELECT`. Do not
invent unions, deduplication, joins, missing rules or provenance constants.

Only omit surrogate, audit or history columns when actual `population` metadata or
an explicit Guide rule assigns them to the database/framework. Runtime owns
loading and merge operations; generated transformation artifacts contain no
persistent DDL or DML. Every artifact is self-contained.

The backend checks frozen target coverage, exact System assignment, file layout,
artifact names, SQL syntax/shape, byte limits and the effective Model graph. It
preserves locks, revision fencing and idempotency. Combined layout assigns all
selected Systems once to one transformation file; per-System layout gives each
System its own transformation file. Support files assign no Systems.

Only complete active Mapping pairs are eligible for Code and Validation input.
Partial Mapping remains reviewable in the Mapping UI; blank transformations do not
become invented `NULL` expressions or defaults. Parsing and coverage checks do not
execute SQL or prove every business expression against live source data.
