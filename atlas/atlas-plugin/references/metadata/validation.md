# Metadata validation

This reference explains Metadata checks. The shared Atlas validator implements local schema, key, reference, ownership and protection checks; [local validation](../local-validation.md) distinguishes automated checks from review and server enforcement. Live authorization and state remain server responsibilities.

Use the shared [local validation sequence](../local-validation.md) after authoring. This page owns Metadata-specific checks; [record state](../record-state.md) owns locked/unlocked/inactive behavior.

## Common checks

| Rule | Check / reason | Enforced by |
|---|---|---|
| schema | Required fields, types, nulls, limits, constants; prevent malformed records. | Local validator + server |
| eligibility | Dataset accepts Metadata Change Sets; prevent edits to foundational/reference context. | Local validator + server |
| key | Complete normalized natural key; prevent ambiguous matching. | Local validator + server |
| uniqueness | Staged and effective records satisfy every unique constraint; inactive rows still reserve keys where indexes are unconditional. | Local validator + server |
| references | Related complete keys exist in the effective result (Snapshot plus pending records). | Local validator + server |
| ownership | Records and referenced Objects belong to the Change Set Tenant. | Local validator + server |
| protection | Follow [record state](../record-state.md), including Object protection of Attributes; the current lock state is rechecked at Apply. | Local validator + server |
| current-state | Authorization, owned Tenant Lock, current draft revision/digest, dependencies. Never report a local pass as equivalent. | Server only, at Apply |

Each [table page](index.md) lists its own extra unique constraints, references, population rules, and table-specific checks explicitly. Reuse these common IDs instead of re-describing a whole validation engine for every table.

Apply framework-dependent semantic checks only where their consumer contract supports them. Use the [value-resolution procedure](editing.md#framework-dependent-values) when behavior is custom or unclear; a field name alone is not a validation rule.

## Interpreting table checklists

- **Local validator + server:** `validate` reports violations before Stage and the server rechecks them. Fix what the report shows.
- **Server only, at Apply:** live conditions an offline Snapshot cannot prove. Read the server validation and Apply results.
- **Your review:** no complete automated check exists. Verify the rule from evidence; a validator note names the known gap.
- **Your review (no automated check):** a confirmed consumer rule with no validator yet. Verify it the same way.
- **Not checked, by decision:** intentionally unenforced; field shape checks still apply.
- **Runtime framework (context only):** orchestration behavior described for context; never a reason to reject authoring.

Validation reports identify checks run or skipped and bounded findings with rule IDs and available record/field context. Review and server-only checks remain explicit; no raw source rows, credentials, or complete tool dumps belong in reports.

## Schemas and confirmed behavior

Current tool and Snapshot schemas govern field shape and reference contracts. Table pages record confirmed framework behavior for fields whose names do not explain their runtime use. Investigate a schema mismatch instead of discarding a confirmed consumer rule.
