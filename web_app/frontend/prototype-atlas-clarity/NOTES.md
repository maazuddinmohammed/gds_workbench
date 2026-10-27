# Atlas clarity options — temporary

Throwaway, isolated prototype. Synthetic data only. No production imports, API
calls, persistence, database access, or application/package changes.

## Question

How can Atlas show more information with less drilling down, and look cleaner,
without changing governed behavior?

## Run / discard

From the repository root:

```sh
python3 -m http.server 4330 --bind 127.0.0.1 --directory web_app/frontend
```

Open <http://127.0.0.1:4330/prototype-atlas-clarity/?option=rec&screen=overview>.
The dark bar at the bottom switches option and screen; **Notes** explains each option.
Keys: ← → switch options, ↑ ↓ move through records, Esc closes panels.
Delete this directory once a direction is chosen and built.

## Problems seen in the current app (local stack, 2026-10-26)

- ~270px of chrome (header, Project identity, 13-stage ribbon) before any content;
  the ribbon hides Mapping, Code generation and Validation at 1440px.
- Lists show identity only (schema, name, order, status, lock, updated). Definitions,
  attributes, keys, sources and coverage need **Show details** → full page → **Back**.
- Up to three levels: Logical list → Entity page → Attribute page. FK roles are not
  visible on the Entity page (Customer ID shows Role "—").
- Mapping detail nests tables inside table cells, with horizontal scrolling.
- Analysis is an 18-column table (`From Object schema (A)` … `B → A mismatch %`).
- Overview reports "2 results" / "Results available" with no counts, warnings or next step.
- All working text is 12px normal weight, so names, values and labels look alike.

## Options

| | Navigation | Details | Overview | Effort |
| --- | --- | --- | --- | --- |
| A · Inspector | Current ribbon, compacted | Side panel beside every list | Richer stage table | Low–medium |
| B · Cockpit | Stages in the side rail | Rows expand in place; Mapping matrix | Pipeline board + next step | Medium |
| C · Explorer | Subject Area → Entity tree | Entity page across all stages; model map | Entity × stage matrix | High |
| ★ Recommended | B | A, plus C's lineage strip | B | Medium |

Shared improvements in every option: counts and coverage bars in lists, readable
Analysis rows, key badges (NK / FK → parent / PII), audit columns collapsed by
default, semibold record names, 13–14px working text.

## Recommendation

**★ Recommended mix.** B's rail and Overview fix orientation and remove the ribbon.
A's side panel removes most page hops while keeping the list in view. C's lineage
strip shows one entity's progress through Mapping, SQL and Validation. Build it one
screen at a time: Overview first, then the Logical panel, then Mapping, then Analysis.

## Production impact (if chosen)

- Backend: one Project summary read (counts, warnings, last run per stage) and a few
  list counts (attributes, keys, relationships, mapping coverage, SQL state).
  Lineage strip needs a per-entity summary. States stay backend-owned.
- Design rules to update in `docs/design-system.md`: Project ribbon → rail
  navigation; detail pages optional; list typography (semibold names, 13px text).
- Unchanged: governed actions, locks, revisions, refresh-only data (no polling),
  addressable detail routes.

## Review performed

- Script syntax check; no browser console errors.
- All 4 options × 4 screens render at 1440×900; 1024px (panel overlays the list)
  and 391px (no document overflow; tables and filters scroll inside their areas).
- Row selection, ↑/↓, Esc, search highlight and attribute matches, filters,
  expand/collapse, audit toggle, lineage → Mapping jump, tree, model map.
- Fixed during review: visually hidden labels in the scrolling ribbon widened the
  page on phones; scroll containers now anchor them.
- Not covered: Home, Metadata, Prompts, Profiling, Enrichment, Code generation,
  Validation screens; mobile navigation; screen-reader walkthrough.

## Decision

Pending user review.
