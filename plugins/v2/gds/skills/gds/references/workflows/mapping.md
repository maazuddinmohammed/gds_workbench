# Logical or Dimensional Mapping

Route `logical` maps source/Bronze to Silver only with `is_logical_mapping_target_eligible=true`.
Route `dimensional` requires applied Logical Mapping and maps Silver to Gold only with
`is_dimensional_mapping_target_eligible=true`. Require fresh Snapshots and the flag, never a zone
label; otherwise emit the authorized-owner Resolution Prompt.

Ask for Full or Selected scope. Full means every eligible registered active target in the authoritative Snapshot, never session history. The fixed work unit is target Object plus source System.
`source_system_code` is not the target physical Object's `system_code`; preserve both exact values
from governed context.

Load each compact Mapping dataset contract only immediately before its first batch.

## Readiness sweep

Before any server draft, sweep every unit for active targets/Attributes, executable applied lineage,
target/source contribution, write mode, and dependency conflicts. Group real Resolution Prompts,
set `waiting`, and create no draft while blocked. Missing materializer proof during this first sweep
is an expected preflight action, not a terminal blocker: collect every proof below and run final
readiness. Only a failure returned by authoring/materialization or final readiness blocks.

Automatic Mapping requires the committed mapper/materializer contract for `mapping.standard`; a
generic `mapping_package_document` object is insufficient. For each exact target/source pair, call
`get_model_mapping_authoring_context`, author only from its bounded context/profile, then pass its
unchanged revision/digest and the complete candidate to `validate_and_materialize_mapping_candidate`.
Use the returned natural-key changes and proof, and never invent database IDs or a private package.

Bind only `result.proof` locally:

```text
mapping-proof --session <session> --target logical-mapping|dimensional-mapping --proof <result.proof-JSON>
```

After binding every selected unit, run final readiness with the exact unit list:

```text
readiness --session <session> --target logical-mapping|dimensional-mapping --proof-units <[{target_object_id,source_system_id},...]-JSON>
```

Selected lists requested units; Full lists all eligible units from governed reads. Never omit one to
pass. Cache only `result.proof`; it must match the current Snapshot ID/revision. If either MCP tool
is missing, ask the platform owner to deploy the latest MCP server and stop.

## Build loop

For every ready unit:

1. Preserve compatible active mappings; map every required Attribute or report it skipped/blocked.
2. Use only applied model lineage as executable sources.
3. Use Assertions for transformations, source priority, write mode, sequencing, and rationale, never
   as executable lineage.
4. Preserve explicit append/overwrite/merge; inferred modes are `needs_review`.
5. Order dependencies only from consumption/Assertions; report cycles. Shared-target writes need
   proven disjointness/idempotence or serialization.
6. Put complete materializer `changes` into one `upsert-batch`, then review, validate, and accept.

Use `active` for supported deterministic rules, `needs_review` for inferred behavior, and block
missing lineage/conflict resolution. Review by target/source System. Follow common governed gates,
Apply once, mark Model stale, and stop; applied `needs_review` unlocks nothing.
