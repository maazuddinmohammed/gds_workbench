---
name: atlas-subject-areas
description: Group a Project's Bronze Input Scope tables into Subject Areas, business capabilities such as Sales or Billing, so each Logical Build works on one manageable set of tables. Use for subject-area, capability or table-grouping requests; areas are never modeling evidence.
---

# Group tables into Subject Areas

Goal: every Bronze Input Scope table sits in a clearly named Subject Area or is knowingly unassigned, and each area is small enough for one Logical Build.

## When to use

- Create, rename, regroup or retire Subject Areas, or place unassigned tables.
- Subject areas decide which tables a Logical Build works on; they are not modeling evidence. Logical, Dimensional, Mapping and Code work never cite an area as a source.

## What you need

- [Working context](../../references/working-method.md) and its golden rules. A discussion-only answer needs no workspace or records.
- For saved areas: the Project, applied Input Scope, installed Snapshots and effective `subject_area` and `subject_area_table` records.
- Table meaning from Project enrichment, profiles, Analysis and attributable Context records. Material gaps go to [source analysis](../atlas-source-analysis/SKILL.md).

## Steps

1. Read existing areas and memberships with `select --session <dir> --area project --dataset <name> --view effective` for `subject_area` and `subject_area_table`, following `next_cursor` until it is null.
2. Read every Bronze Input Scope table: description, columns and Analysis links. Decide what one row records and which business process it serves.
3. With [Subject Areas](../../references/project/subject-areas.md), group by business capability, keep together tables one Logical Build must join, share reference tables across areas, and keep each area within the column limit.
4. Keep saved names and boundaries that still fit. Change a saved area only to correct or extend it, and retire it only when its capability no longer applies. Locked areas and locked memberships stay unchanged.
5. Write complete records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>`. Remove a table from an area by making its membership inactive.
6. Run `validate --session <dir> --area project` and review the result: every table in an active area or knowingly unassigned, no empty or oversized area.
7. To save, follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`.

## Done when

- Every Bronze Input Scope table is in an active area or reported as unassigned with its reason.
- Area names and definitions are clear; each area's table and column counts are reported, with changed areas listed.
- No Logical or later work was created from these changes.

## Ask the user when

- A table could serve different capabilities and the evidence does not decide.
- A saved area should be renamed, split, merged or retired.
- Approving Stage and, separately, Apply.

Use the interview method from working context for consequential ambiguity and reuse confirmed answers. Unknown facts stay unknown; never create a Context record only to place a table.

## Next

Stop here unless the user asks for more. Modeling one area's tables uses [logical modeling](../atlas-logical-model/SKILL.md).
