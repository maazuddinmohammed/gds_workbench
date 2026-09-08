# Conceptual — approved design

Approved on 2026-09-07: both complete prompt pairs, default evidence delivery,
supported high/medium authoring, eleven workflow-local variables, ten optional
readers, and no-input all-record calls. Implementation remains deferred.

| Workflow / stage | Mode | Approved default delivery | Complete prompt pair |
| --- | --- | --- | --- |
| Conceptual / Candidate Authoring | One-shot | Nine full-evidence variables inline; no tools; compact duplicates omitted | [System + Instruction JSON](workflow-prompts/conceptual.one_shot.json) |
| Conceptual / Candidate Authoring | Tool-assisted | ingestion_mapping inline; ten optional readers; compact discovery then needed details | [System + Instruction JSON](workflow-prompts/conceptual.tool_assisted.json) |

[Read all four prompts](workflow-conceptual-design.md). Authors retain explicit
variable/projection and enabled-tool choices. No hidden evidence is appended.
Both modes retain the existing objects/relationships output and full records.

## Settled retrieval behavior

- list_conceptual_objects and list_conceptual_relationships return compact natural
  keys, optionally selected by direct supporting physical Object keys.
- get_conceptual_objects returns full records selected by concept names.
- get_conceptual_relationships returns full records selected by complete from/to
  concept names plus relationship name.
- Every reader accepts no selection inputs. Omitted/empty keys request all
  eligible records in the frozen authorized run, with paging.
- Readers are optional. Inline complete evidence can replace corresponding reads.
- A source-filtered directory may miss Assertion-only records. Use the global
  directory to preserve the overall model view; fetch full details before
  relying on a saved record's meaning, confidence, status, or lock.

The [exact variable schemas](workflow-prompts/conceptual.context.proposal.json)
and [tool schemas/examples](workflow-prompts/conceptual.tools.proposal.json)
retain record fields, supports, natural keys, and accepted physical-reader rules.
Detail records are whole under the approved paging limit; one oversized record
returns an explicit error, even if its compact key could be listed.

## Accepted decisions

1. Use the default delivery shown above for each mode.
2. Use supported high/medium confidence for authored Conceptual Objects,
   relationships, and supports; omit speculative low-confidence changes.
   Analysis retains its separately approved high-only policy.
3. Retain the approved complete prompt wording and explicit paging limits.

Business association and cardinality are assessed separately. A supported
high-confidence association may have unknown cardinality. Existing locks are
immutable; omitted records/supports remain; output lock fields stay false under
the existing backend contract.

The [short validation list](workflow-validation-design.md) records scope/support
references, duplicate identities, active endpoints, locks, and accepted values.
Existing checks and bounded correction are reused; there is no new framework.

Schema/example verification is not a model-quality evaluation. No model,
database, or tool runtime is executed by these design artifacts.
