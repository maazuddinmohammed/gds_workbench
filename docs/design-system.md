# Atlas design and interaction rules

Read before frontend work. Existing shared CSS/components define exact tokens,
spacing and implementations. This document records decisions worth preserving.

## Sources

| Concern | Source under `web_app/frontend/src/` |
| --- | --- |
| Tokens, focus, global defaults | `styles/foundation.css` |
| Shared controls and typography | `shared/ui.tsx`, `styles/metadata.css` |
| Formatting | `shared/presentation.ts` |
| Tenant shell/navigation | `styles/tenant-workspace.css` |
| Model workspace and navigation | `styles/models-scope.css`, `styles/model-workspace-overrides.css` |
| Workflow commands and run monitor | `styles/profiling.css`, `styles/workflow-runs.css` |
| Feature behavior | Matching `features/` package and its tests |

Use warm neutral surfaces, readable dense text and restrained terracotta primary
accents. Tables/ledgers suit comparable records; cards suit summaries or choices.
Reuse semantic tokens instead of copying colors. Use shared outline icons, not emoji.
The current palette is light-only. Use short functional motion and reduced-motion
support. Every flexible layout child needs `min-width: 0`; wide tables scroll inside
an intentional container instead of truncating governed values.

## Navigation and hierarchy

Keep Tenant/Model, revision, lock and current run state visible. Workspace navigation
contains Home, Metadata, Models and Prompts; workflow navigation belongs inside the
Model. Preserve Logical/Dimensional layer and addressable detail routes. The active
tab supplies the visible section heading; avoid another oversized heading below it.

Model navigation remains a keyboard-accessible, scrollable ribbon, including narrow
screens. Manual sections have neutral indicators. Workflow statuses come from explicit
backend section states, not record counts or guesses. Distinguish Completed from
Results available; loading/conflicts never imply Not run. Keep every section clickable.

Use one compact command bar, recent runs, filters, then the results ledger. Drawers
inspect without losing context; dialogs make bounded decisions. Keep one primary
command per decision area. Preserve unsaved input after errors and request explicit
discard before refreshing dirty forms.

## Controls and accessibility

- Visible labels; placeholders never replace labels. Icon-only buttons need names.
- Semantic headings, tables, buttons and links; retain `:focus-visible`.
- Modal label, initial focus, focus trap, Escape and focus restoration.
- Multi-select search preserves selection and never submits the form; Escape
  returns focus, and choosing a checkbox keeps the menu open.
- Status includes words, not color alone. Green success, red failure, orange warning.
- Keep natural keys visible. Prefer one code label over repeated name/code/ID rows.
- Loading uses `aria-busy`; safe errors use `role="alert"` and a concrete next action.
- Test keyboard access and narrow widths, including existing 58rem/42rem breakpoints.

## Refresh and governed actions

Workflow lists, details, events, results and section statuses refresh manually.
Fetch on navigation/selection or explicit Refresh. A successful mutation may invalidate
once. Never introduce hidden polling, `setInterval` or recurring query refetch.
An active Run can remain visually stale until Refresh by design.

Backend authorization, lock, revision, normalization and validation remain authoritative.
Explain disabled prerequisites. Retain original request identity after uncertain saves.
Show bounded failure code, safe message, stage/attempt, registered model/mode and
correlation reference; never expose raw provider diagnostics or model payloads.

## Important workflow semantics

- Model schema/settings forms preserve saved values and unsaved changes. Display
  readable prompt names/version; internal identifiers/digests belong in Details.
- Selection survives search and nested Attribute selection. Complete selection data
  must load before a Run starts; failed loading must not create a partial selection.
- Profiling precedes Enrichment. Enrichment opens on current Model-owned results; keep
  history separate. Parent Model enrichment locks protect children. Object details allow
  description edits; Attribute details allow description/type and nullable key/PII flag edits.
  Unknown is distinct from No. Show saved Profiles in a technical table and export both
  dictionaries; retain unsaved edits on errors.
- Analysis separates inference from measured validation. Missing, zero and unavailable
  measurements have distinct labels; zero denominators are N/A. Cardinality differences
  are review warnings. Percentages use their actual measured denominators.
- Logical/Dimensional ledgers separate schema and Entity name. Provenance uses shared
  structured source/rationale/status views. Export is an optional Metadata handoff.
- Mapping has Entity/System detail pages: Object logic once above a spreadsheet of
  all active modeled Attributes. Missing transformations stay blank. Preserve custom
  fields/nested values and whole source identifiers. Missing records have no selectable
  ID; persisted cleared records keep review actions and detail URLs.
- Mapping selection supports partial output. Explain selected omissions clear on Apply;
  locked/unselected records and true failed pairs stay unchanged. Show incomplete counts
  separately from failed-pair diagnostics. Pair ordinals are identities, not progress.
- Code supports partial Mapping with warnings. Show exact Entity/System/file counts,
  preserve selection, and explain combined-file System coverage. Currentness is not
  execution readiness. Validation retains complete Mapping eligibility.
- Validation uses addressable Group and Check pages with explicit back links; keep
  Group and Check review scopes separate. SQL panes stack at narrow widths.
- Assertions use Document → Record navigation. Stable key, type and statement are
  required; extra context is optional. Preserve legacy structured detail. Active
  Assertions are downstream context; relevance is assessed by each workflow.
- Destructive Model operations retain bounded preview, dependency issues, permanent
  confirmation and revision/digest protection. Avoid duplicating implementation details.

For any change, exercise loading, empty, success, failure and revision-conflict states;
check focus/narrow layout; run the frontend checks in [AGENTS.md](../AGENTS.md).
