# Logical or Dimensional Mapping

Route `logical` maps source/Bronze evidence to registered Silver targets and accepts a target only with `is_logical_mapping_target_eligible=true`. Route `dimensional` maps Silver to registered Gold targets, requires applied active Logical Mapping, and accepts a target only with `is_dimensional_mapping_target_eligible=true`. Require fresh Snapshots and the route-specific derived flag; never substitute a Silver/Gold label. Otherwise emit the authorized-owner Resolution Prompt and wait.

Ask for Full or Selected scope. Full means every eligible registered active target in the authoritative Snapshot, never session history. The fixed work unit is target Object plus source System.

## Readiness sweep

Before writing a server draft, sweep every work unit. Require active target/Object/Attributes, executable applied model lineage, resolved target/source contribution, resolved write mode, and nonconflicting dependencies. Group all blockers into Resolution Prompts and set the task `waiting`. Do not create a server draft while blocked.

Automatic Mapping requires the committed mapper/materializer contract for `mapping.standard`; a generic `mapping_package_document` object is insufficient. For each exact target Object plus source System pair, call `get_model_mapping_authoring_context`. Author only from its bounded context and exact profile. Pass the unchanged `model_revision` and `context_digest` with the complete candidate to `validate_and_materialize_mapping_candidate`. This read-only tool validates the exact package, transformations, coverage, lineage, locks, dependencies, and load keys, then returns natural-key Change Set records plus a compact server proof. Block safely; never invent database IDs or a private package shape.

Bind only `result.proof` locally:

```text
mapping-proof --session <session> --target logical-mapping|dimensional-mapping --proof <result.proof-JSON>
```

After binding every selected unit, rerun readiness with the exact unit list:

```text
readiness --session <session> --target logical-mapping|dimensional-mapping --proof-units <[{target_object_id,source_system_id},...]-JSON>
```

Selected lists exactly its requested units; Full lists every eligible unit discovered from governed MCP reads. Never omit a unit to make readiness pass. Do not cache the context, candidate, records, or raw tool result as proof. A proof must match the current Model Snapshot ID/revision; replacing that Snapshot makes it unusable. If either MCP tool is missing from the deployed runtime, ask the platform owner to deploy the latest MCP server and stop safely.

## Build loop

For every ready unit:

1. Preserve compatible existing active mappings.
2. Map each required target Attribute or report it skipped/blocked.
3. Use only applied model lineage as executable sources.
4. Use Assertions for joins, filters, defaults, deduplication, source priority, aggregation, write mode, sequencing, and rationale; Assertions never substitute for executable lineage.
5. Preserve an existing/explicit append, overwrite, or merge mode. Keys/types may suggest a mode only as `needs_review`.
6. Order dependencies from explicit consumption and Assertions. Never infer order by names or types. Report cycles.
7. Shared target writes require proven disjointness, idempotence, or explicit serialization; otherwise `needs_review`.
8. Use the materializer's complete `changes` in one local `upsert-batch`; then run local review, validation, and acceptance.

Confidence is `active` for direct/deterministic/explicit supported rules, `needs_review` when lineage exists but transformation behavior is inferred, and blocked when lineage or conflict resolution is missing. Review by target then source System and accept the full digest. Show the complete affected list and obtain Stage approval before server Stage. Validate the latest server revision. Show its authoritative `action_review`, obtain fresh Apply approval, Apply once, mark Model stale, and stop. Applied `needs_review` does not unlock downstream work.
