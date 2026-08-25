# Logical or Dimensional Mapping

Route `logical` maps source/Bronze evidence to registered Silver targets and accepts a target only with `is_logical_mapping_target_eligible=true`. Route `dimensional` maps Silver to registered Gold targets, requires applied active Logical Mapping, and accepts a target only with `is_dimensional_mapping_target_eligible=true`. Require fresh Snapshots and the route-specific derived flag; never substitute a Silver/Gold label. Otherwise emit the authorized-owner Resolution Prompt and wait.

Ask for Full or Selected scope. Full means every eligible registered active target in the authoritative Snapshot, never session history. The fixed work unit is target Object plus source System.

## Readiness sweep

Before writing a server draft, sweep every work unit. Require active target/Object/Attributes, executable applied model lineage, resolved target/source contribution, resolved write mode, and nonconflicting dependencies. Group all blockers into Resolution Prompts and set the task `waiting`. Do not create a server draft while blocked.

Automatic Mapping also requires the committed mapper/materializer contract for the selected `mapping.standard` profile. The generic `mapping_package_document` object accepted by the Change Set schema is not that contract. If only an ID-free Snapshot and the generic object are available, block and say: “Ask the platform owner to expose the committed mapper/materializer contract for this Mapping profile, download a fresh Model Snapshot, then resume.” Block safely; never invent database IDs or a private package shape.

## Build loop

For every ready unit:

1. Preserve compatible existing active mappings.
2. Map each required target Attribute or report it skipped/blocked.
3. Use only applied model lineage as executable sources.
4. Use Assertions for joins, filters, defaults, deduplication, source priority, aggregation, write mode, sequencing, and rationale; Assertions never substitute for executable lineage.
5. Preserve an existing/explicit append, overwrite, or merge mode. Keys/types may suggest a mode only as `needs_review`.
6. Order dependencies from explicit consumption and Assertions. Never infer order by names or types. Report cycles.
7. Shared target writes require proven disjointness, idempotence, or explicit serialization; otherwise `needs_review`.

Confidence is `active` for direct/deterministic/explicit supported rules, `needs_review` when lineage exists but transformation behavior is inferred, and blocked when lineage or conflict resolution is missing. Review by target then source System, accept the full digest, Apply once, mark Model stale, and stop. Applied `needs_review` does not unlock downstream work.
