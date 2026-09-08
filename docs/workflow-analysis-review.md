# Analysis — approved design

Approved in the design discussion on 2026-09-07, including both prompt pairs,
the six reader contracts, paging, and concrete examples. Implementation remains
deferred. This package contains synthetic examples only; preparing and approving
it did not execute a model or change runtime code.

## Default prompts

| Workflow / stage | Mode | Default evidence | Complete prompt pair |
| --- | --- | --- | --- |
| Analysis / Relationship Inference | One-shot | All seven variables inline; no tools | [System + Instruction JSON](workflow-prompts/analysis.one_shot.json) |
| Analysis / Relationship Inference | Tool-assisted | `ingestion_mapping` inline; six selected readers | [System + Instruction JSON](workflow-prompts/analysis.tool_assisted.json) |

[Read both complete pairs as Markdown](workflow-analysis-design.md), or inspect
[fully rendered synthetic requests and expected output](workflow-prompts/analysis.rendered-review.example.json).
The rendered example includes the existing required output schema and illustrative
reads from all six tools. The model was not executed; this is not an accuracy test.

## Variables and tools

| Variable | Reader | Initial selection |
| --- | --- | --- |
| `source_context` | `get_source_context` | None |
| `gds_context` | `get_gds_context` | None |
| `object_context` | `get_objects` | Optional complete Source Connection key |
| `object_attribute_context` | `get_object_details` | Optional complete physical Object keys |
| `object_relationship_context` | `get_object_relationships` | Optional complete physical Object keys |
| `modeling_assertions` | `get_modeling_assertions` | Optional nominal assertion record keys |
| `ingestion_mapping` | No tool | Author-selected prompt variable only |

Omitted selection means all eligible records in the frozen run. A Source filter
finds related scoped physical Objects through registered ingestion mappings;
returned Bronze Objects keep their GDS keys. Detail and relationship reads use
those returned physical keys. Tenant-specific templates can change variable/tool
inclusion. No hidden full context is appended after rendering.

Relationship context is grouped by Object with incoming and outgoing lists.
Keep full endpoint keys, kind, confidence, basis, status, and lock on each record.
No validation fields. Directional copies are one saved relationship identity.
Objects without relationships retain explicit empty groups. Locked is immutable;
unlocked permits a supported change; unchanged output is a no-op. Discover new
candidates from the wider Object/Attribute evidence, including unconnected Objects.

## Paging contract

Every reader returns `items`, `next_cursor`, `is_complete`, and
`incomplete_object_key`. An initial call uses its selection arguments; later calls
use only the returned cursor, retaining the original run, tool, and filters.
Record identities continue to use natural keys; cursors are transport controls.

- `is_complete=true` means the selected result is exhausted and `next_cursor=null`.
- `incomplete_object_key` identifies an Object whose nested lists continue on the
  next page. Append its list slices by physical key; unfinished empty lists do
  not prove absence. Only the final Object on a page may be unfinished.
- Ordinary records stay whole. Existing response and cumulative budgets apply.
  An indivisible oversized record returns an explicit error, never silent
  truncation or raw-JSON fragments.

The [exact definitions and paging examples](workflow-prompts/analysis.context-and-tools.json)
include full schemas, defaults, filter/cursor rules, Source-to-Bronze discovery,
complete empty results, multi-Object pages, and continuation within one Object.

## Output and checks

Generate only supported high-confidence new or changed relationships, using the
existing flat `relationships` output schema. No schema or lock changes are
introduced by the context grouping. Scope/reference checks, duplicates, accepted
values, locks, and the bounded correction loop remain as agreed.

See the [short validation lists](workflow-validation-design.md) and
[field provenance](workflow-prompts/field-provenance.json). New variable bindings,
restricted Jinja rendering, reader registration, paging, and previously approved
missing metadata fields still require implementation. Existing uncommitted work
is preserved. Design approval covers the prompt wording and concrete contracts;
it does not authorize runtime implementation.
