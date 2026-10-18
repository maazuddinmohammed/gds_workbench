---
name: atlas-registration
description: Register applied Atlas Silver/Gold targets as physical Metadata, prepare optional creation DDL, or register generated files as runtime Process metadata. Use for operational handoff after modeling or code generation; never a Mapping or Code prerequisite.
---

# Register approved outputs

Goal: the selected registration, recorded as Metadata for the right physical owner, with anything unverified stated plainly.

## When to use

- Register modeled targets or prepare their creation DDL, or register generated files with runtime Process metadata. These are independent procedures, not a sequence.
- Not for: focused fixes to existing Process or Copy rows ([metadata](../atlas-metadata/SKILL.md)) or missing transformation logic ([mapping](../atlas-mapping/SKILL.md), [code generation](../atlas-code-generation/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules, plus current Metadata and Project Snapshots.
- Targets: applied Logical or Dimensional Entities and Attributes, and resolved owner and placement. DDL-only work needs no Metadata Change Set.
- Processes: applied Code, its source-System assignments and Mapping, separately registered compatible targets and confirmed runtime, group and type details.

## Steps

1. Pick the procedure: [target registration](../../references/methods/registration/targets.md), which leads to its target-definition guide, or [Process registration](../../references/methods/registration/processes.md). Load only that one.
2. Resolve the physical owner separately from the Project Tenant and GDS placement. Several owners use separate Metadata roots and Change Sets (`--owner <tenant-id>`).
3. Reuse verified choices and valid existing registrations. Scope changes from real dependencies; changed code text alone does not need a new Process identity.
4. Write complete Metadata records with `upsert-batch --session <dir> --area metadata --changes <JSON> --expected-digest <digest>`. Process order is a positive runtime stage, not an offset of Mapping order.
5. Run `validate --session <dir> --area metadata` and the procedure's semantic checks.
6. Submit with the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area metadata`, then confirm the saved registrations.

## Done when

- The selected registrations are validated, applied and confirmed, or DDL is generated as a local file.
- DDL is reported as generated, not executed. Runtime file existence, scheduling and deployment are reported unverified unless an authorized route proved them.

## Ask the user when

- Ownership, schema assignment or runtime location is unresolved.
- Runtime group, type or order details are missing.
- Approving Stage and, separately, Apply.

Creation DDL cannot run through `execute_databricks_sql`, and registration Apply never creates or alters tables. A local output folder is not a deployed runtime path. Registration never invents transformation logic or regroups artifacts.

## Next

Nothing downstream requires registration; stop at the requested outcome.
