# First prompt-input slice: Metadata enrichment

Test-only preparation; production remains unchanged until the preceding gates
close. New tests remain in `.scratch/`, outside normal project collection.

## Agreed seam proposed to root

`features/workflows/authoring/prompt_inputs.py`:

```python
def project_prompt_input_values(
    *,
    plan: AgentRunPlan,
    stage: FrozenAgentStage,
    context: JsonValue,
    resolver_values: Mapping[str, object],
) -> dict[str, object]: ...

def get_prompt_input_contract(
    *,
    model_workflow: str,
    workflow_execution_mode: str | None,
    stage_code: str,
    resolver_key: str,
) -> PromptInputContract | None: ...
```

StageRunner and Logical/Dimensional/Mapping byte-fit probes already hold these
inputs. Only StageRunner needs the first Metadata implementation; the same seam
will be wired into those probes when their first named input is registered.
No database parameter, query or tool access belongs in the projection function.

The fixed descriptor carries name, resolver_key, data_type, description,
value_schema, example, source, availability, delivery, context_path. SQL still
owns stage registration, order and required flags. Add these **nullable fields
with None defaults** to the existing PromptStageVariable API:

- `value_schema: dict[str, JsonValue] | None`
- `source: str | None` — bounded 500-character provenance/purpose help.
- `availability: str | None` — bounded 500-character partition/empty-value help.
- `delivery: Literal['inline_value', 'structured_context', 'tool_dataset'] | None`
- `context_path: str | None` — bounded 200-character fixed documented path.

Unknown legacy definitions preserve stored help and None documentation fields.
Use the fixed descriptor in BOTH Prompt service list_stages and read_template;
the latter currently constructs variables through a separate code path.

## Two exact inputs

Both belong only to metadata_enrichment / one_shot / candidate_authoring:

| Name | Resolver suffix after workflow.metadata_enrichment.one_shot.candidate_authoring.inputs | Meaning |
| --- | --- | --- |
| assigned_description_refs | assigned_description_refs | Ordered, unique exact refs for this nonempty batch, 1–25; object:<positive ID> or attribute:<positive ID>. Inline coverage control. |
| description_requests | description_requests | Exact metadata-only Object/Attribute request union below, 1–25, already supplied at context.original_context.description_requests. |

Both new SQL registrations are optional, preserving existing frozen/custom
templates; old `stage_context` and `validation_failures` meanings remain exact.
Fresh reference-seed variable count becomes 84 (82 + 2), stages unchanged.
The new default references assigned_description_refs once as an inline control
and reads description_requests from structured context once. It must not inline
the entire request array or old stage_context as duplicate prose.

Projection selects new fields only when their exact resolver is registered on
the passed stage. It preserves all existing resolver values by identity and
leaves the input dictionary unchanged. Repeated projection is idempotent;
conflicting pre-existing normalized values fail with a safe InvalidRequestError.
Unknown stages/resolvers get no fabricated contract or data. Legacy-only stages
do not parse or reinterpret their context. Request records may not carry extra
fields, arbitrary IDs or samples; unexpected top-level private context fields
are never copied into either new value.

## Exact existing request union

Discriminator is `kind`; `extra='forbid'`; nullable fields remain required and
nullable. Do not impose the 2,000-character OUTPUT-description bound on existing
input metadata descriptions; provider byte limits already govern the total.

Object request:

```text
target_ref: object:<positive ID>
kind: object
name, schema, system: string
attributes: array[0..5000] of {
  name: string,
  storage_type: string,
  inferred_type: string|null,
  description: string|null
}
```

Attribute request:

```text
target_ref: attribute:<positive ID>
kind: attribute
name, object_name, system, storage_type: string
object_description, inferred_type: string|null
type_evidence_method: existing EvidenceMethod literal
source_attribute, source_description, source_object_description: string|null
```

Preserve valid multiline comments, null evidence and exact original values.
Ref prefix must match kind; duplicate refs fail instead of silently collapsing
in DescriptionValidator's target dictionary. Backend inference still owns all
types. Descriptions are the only provider output. These boundary models can
live beside the first fixed catalog; reuse EvidenceMethod from metadata contracts
and Pydantic TypeAdapter for list/union schemas and examples. No generic schema
authoring registry is needed.

## Tests prepared

`test_metadata_prompt_inputs.py`: 20 unit/real StageRunner cases covering both
descriptors, JSON schema/example conformance, union and cardinality rules,
nullable source/type evidence, forbidden fields, duplicate/mismatched refs,
missing evidence failure, non-mutating registered-only projection, legacy value
identity, private-context exclusion, conflicting normalized values, unknown
stage/mode, byte-identical old rendering, API legacy defaults, and a custom
template actually using both new variables through the real repair runner.
Both Prompt catalog and template-detail reads must expose the enriched fixed
help without replacing old unknown-resolver help or published template bytes.

`test_database_metadata_prompt_inputs.py`: fixture-only actual SQL04+05 install,
public governed create/start/exact claim, repository-loaded frozen plan, real
stage rendering and physical completion. It reuses the existing comprehensive
enrichment executor fixture/test, intercepting only the renderer to assert
registered optional definitions, projected values, schema conformance and no
unresolved placeholders. Default must use compact refs without duplicating
description_requests. No test-only prompt replaces the installed seed.

Existing seed publication/digest/replay and malformed-response repair tests
remain required alongside these first-slice regressions. Promote these scratch
tests into tests/web_backend and tests/mcp only when production implementation
starts; change the scratch cross-import accordingly.
