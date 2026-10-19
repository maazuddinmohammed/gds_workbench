# Data operation — `reference.data_operation`

Registered framework operation/function selected by a Copy's target operation. The source operation remains a required reference but has no current runtime effect.

**Datasets:** `data_operation`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `data_operation_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset data_operation` for every field's type, limits, required and null rules, description and population guidance. This table lists only fields with rules that `describe` does not state.

| Field | Meaning and use |
|---|---|
| `data_operation_name` | Registered name selecting an implemented framework operation. |
| `data_operation_description` | Explains the function's actual target behavior, scope and custom rules. Use it to match the requested loading behavior. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [copy](../tables/copy.md).

## How authoring uses these values

Copy.source_data_operation_name and Copy.target_data_operation_name each require a reference to data_operation.data_operation_name.

- Source: no operation is performed from this field. Prefer a registered unused-source value when available; otherwise reuse a valid registered value consistent with existing Copies. Preserve existing valid values during unrelated edits. Do not invent a literal such as N/A or use null, because the reference remains required.
- Target: select the registered function matching the intended behavior. Read its description; creating metadata does not execute the function.
- Allowed names come from registered records, not a fixed enum.
- Read and Write are test seed examples; merge in generated guidance is illustrative, not proof of a registered option.
- User-confirmed framework behaviors: Copy Into always appends; Append explicitly appends; Override selects override/replacement behavior; custom operations call their registered logic. These behavior labels are not a fixed list of exact stored names.
- The registered description defines Override scope and custom behavior. Do not infer full-table deletion, merge keys, or overwrite behavior from a generic name such as Write.
- If a target description is insufficient, ask: "What data does this operation change, and which framework function implements it?" Record the confirmed scope. Source placeholders need no invented execution semantics.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Confirmed behavior

The source operation does not control extraction (see the runtime rules above). Both operation fields remain required registered references.

[All metadata tables](../index.md) · [Common validation](../validation.md)
