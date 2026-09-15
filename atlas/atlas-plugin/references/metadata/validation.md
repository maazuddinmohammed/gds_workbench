# Metadata validation

This reference explains Metadata checks. The shared Atlas validator implements local schema, key, reference, ownership and protection checks; the [validation index](../../docs/validation-index.md) maps rule IDs to code and tests. Live authorization and state remain server responsibilities.

Use the shared [local validation sequence](../local-validation.md) after authoring. This page owns Metadata-specific checks; [record state](../record-state.md) owns locked/unlocked/inactive behavior.

## Common checks

| Rule | Check / reason | Authority and local behavior |
|---|---|---|
| schema | Required fields, types, nulls, limits, constants; prevent malformed records. | Pydantic/current Snapshot schema; existing local schema interpreter. |
| eligibility | Dataset accepts Metadata Change Sets; prevent edits to foundational/reference context. | Shared registry and governed server operation; reject locally too. |
| key | Complete normalized natural key; prevent ambiguous matching. | Registry normalization; reuse the same local implementation. |
| uniqueness | Staged and effective records satisfy every unique constraint. | Database indexes plus backend/local checks; inactive rows still participate where indexes are unconditional. |
| references | Related complete keys exist in the effective result. | Database/backend authoritative; local checks use Snapshot plus pending records. |
| ownership | Records and referenced Objects belong to the Change Set Tenant. | Server rechecks; local scope checks provide early feedback. |
| protection | Follow [record state](../record-state.md), including Object protection of Attributes. | Snapshot check locally; current lock state rechecked at Apply. |
| current-state | Authorization, owned Tenant Lock, current draft revision/digest, dependencies. | Server-only guarantee; never report a local pass as equivalent. |

Each [table page](index.md) lists its own extra unique constraints, references, population rules, and table-specific checks explicitly. Reuse these common IDs instead of re-describing a whole validation engine for every table.

Apply framework-dependent semantic checks only where their consumer contract supports them. Use the [value-resolution procedure](editing.md#framework-dependent-values) when behavior is custom or unclear; a field name alone is not a validation rule.

## Interpreting table checklists

- **Existing:** enforcement found in the named layer; not a claim of tested cross-layer parity.
- **Review:** guidance/consumer behavior or cross-layer differences need a decision or verification.
- **Proposed:** useful check identified but not implemented by this work.
- **Server-only:** offline snapshots cannot establish the live condition.
- **Runtime-only:** orchestration behavior documented for context; not a metadata-authoring rejection rule or a local execution guarantee.
- **Deferred:** intentionally excluded by an agreed domain decision; not an outstanding validation failure. Field shape checks still apply.

Validation reports identify checks run or skipped and bounded findings with rule IDs and available record/field context. Review and server-only checks remain explicit; no raw source rows, credentials, or complete tool dumps belong in reports.

## Code reuse and source map

- Dataset eligibility, natural keys, uniqueness, references: `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py`.
- Field meanings/population guidance: `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py`.
- Exact field contracts: `mcp_server/gds_etl_workbench/domain/metadata_records.py`.
- Portable cross-field rules: `mcp_server/gds_etl_workbench/domain/portable_validation.py`.
- Published Snapshot schemas: `mcp_server/gds_etl_workbench/tools/snapshots/metadata/archive.py`.
- MCP dataset descriptions: `mcp_server/gds_etl_workbench/tools/snapshots/metadata/describe_metadata_dataset.py`.
- Backend effective-result validation: `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py`.
- Shared Atlas validation: [common.js](../../workbench/validation/common.js), [metadata.js](../../workbench/validation/metadata.js) and [run.js](../../workbench/validation/run.js).
- Database storage and Apply: `database/02_core.sql`, `database/16_mcp_metadata_apply.sql`.

These are development-source pointers, not runtime file dependencies. Current tool and Snapshot schemas govern field shape and reference contracts. User-confirmed framework behavior recorded on table pages supersedes older descriptive guidance about execution. Investigate schema mismatches; do not discard confirmed consumer rules merely because a legacy description differs.
