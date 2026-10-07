# Atlas design and interaction rules

Read before frontend work. Existing shared CSS/components define exact tokens,
spacing and implementations. This document records decisions worth preserving.

## Sources

| Concern | Source under `web_app/frontend/src/` |
| --- | --- |
| Tokens, focus, global defaults | `styles/foundation.css` |
| Shared workspace typography, density, tabs, filters and toolbars | `styles/workspace-design.css` |
| Toolbar layout and filter/menu behavior | `shared/ui.tsx` (`WorkspaceToolbar`), `features/workflows/WorkflowCommandCenter.tsx` |
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
Navigation labels use the same normal font weight as Prompts and Metadata, including
active items; color, surface and underline show selection.

Model navigation remains a keyboard-accessible, scrollable ribbon, including narrow
screens. Manual sections have neutral indicators. Workflow statuses come from explicit
backend section states, not record counts or guesses. Distinguish Completed from
Results available; loading/conflicts never imply Not run. Keep every section clickable.

Use one compact command bar, recent runs, filters, then the results ledger. Drawers
inspect without losing context; dialogs make bounded decisions. Keep one primary
command per decision area. Preserve unsaved input after errors and request explicit
discard before refreshing dirty forms.

Metadata uses Reference → Foundational → Objects → Operational tabs, full-width
tables, and normal-weight text. The selected sheet tab supplies its heading.
Catalogs are read-only; users edit through Excel export/import. Attributes live
inside Object details, while Excel retains all canonical sheets. Import opens the
governed Change Set drawer for workbook validation and apply.
Models use the same normal-weight typography for values, headings and controls.
The Models ledger shows Model, revision, lock status and updated time. Select one
Model with its radio control; Lock/Unlock sits beside Create Model. Model workspaces
show the lock status, with lock actions kept on the Models ledger.
Object identity columns and catalog sorting follow Tenant code → System code →
Connection code → Zone → Schema → Object name. Object details and Attributes use
complete business-field grids; descriptions and key flags stay in their own columns,
without per-row detail disclosures. Catalog grids use the canonical Excel fields,
resolving relationships to natural codes/names and omitting raw IDs and audit columns.
Objects use View attributes to open the nested attribute grid; other rows need no
redundant details action. Column headings use PascalCase;
canonical workbook/import field names remain unchanged. Revisions stay internal.
Model export actions live under More: Export Metadata followed by Export DDL,
where supported. Mapping offers Export for either layer, selecting one System per
workbook; standard saved Mapping definitions and complete active Attributes form
the sheets. Export remains read-only and revision-fenced.
Mapping editing lives only inside Show details, with separate Edit Object Mapping
and Edit Attribute Mapping dialogs. Both reuse the shared dialog, focus, discard,
and retry behavior. Source pickers start collapsed, support search and selection,
and keep selected sources visible. Object edits save before Attribute edits; the
Attribute picker only offers columns from the saved Object sources. Logical source
choices cover the Model Input Scope for that System; Dimensional choices retain
Logical/Silver sources. Filter criteria and sample query belong to Object Mapping;
transformation logic and default record belong to Attribute Mapping.

Tenant Home keeps the dark Tenant Lock panel central, with normal-weight text,
owner/expiry/purpose together and compact action controls. History opens on demand
and displays only the latest three events; no older-page control.

Prompts follows the same normal-weight, full-width ledger layout with collapsible
filters. Instructions are the primary workspace; System and Tool instructions switch
in place and expand for focused editing. Version history, variables, tools and
provenance open on demand. Keep draft edits across section switches and errors;
confirm discard before refreshing or leaving unsaved content.

## Central enforcement

`workspace-design.css` is loaded last and owns the `--workspace-*` tokens and shared
workspace rules. Change typography, control height, table padding and section spacing
there. Feature styles own column widths and domain layouts; do not add another
feature-wide font-weight override or a bespoke copy of filter/tab/toolbar styling.

Use `WorkspaceToolbar` for page context and actions. List filters must use
`WorkflowCommandCenter`, `WorkflowCommandTools` and `WorkflowFilters`: closed initially,
with entered/applied values preserved when hidden. Settings fields and required
search inputs in selection dialogs remain directly accessible. Use `workspace-tabs`
for secondary navigation and `ledger-grid` for comparable record tables.

`styles.test.mjs` checks shared typography (including a changed token value), consistent
selected tabs and the stylesheet cascade. Command-center and Input Scope integration
tests verify collapsed filters and state retention. Run
`npm --prefix web_app/frontend run check` before considering a UI change complete.

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
Run activity shows saved start/end timestamps and execution duration above its tabs.
Unstarted runs say Not started; missing end timestamps never imply completion.
Run history uses flat rows; token totals stay visible with breakdown and pricing
evidence available on demand.

Backend authorization, lock, revision, normalization and validation remain authoritative.
Explain disabled prerequisites. Retain original request identity after uncertain saves.
Show bounded failure code, safe message, stage/attempt, registered model/mode and
correlation reference; never expose raw provider diagnostics or model payloads.

## Important workflow semantics

- Model schema/settings forms preserve saved values and unsaved changes. Display
  readable prompt names/version; internal identifiers/digests belong in Details.
- Selection survives search and nested Attribute selection. Complete selection data
  must load before a Run starts; failed loading must not create a partial selection.
  Multi-select run pickers provide select-all/clear controls. Header checkboxes show
  partial selection, affect eligible records only, and preserve nested Attribute choices.
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
- Code uses Entities for generation selection and SQL files for saved-file review,
  including inactive versions. SQL detail puts the file first, with compact context
  and source mappings on demand. Reuse `workspace-sql` for read-only query panes.
- Code supports partial Mapping with warnings. Show exact Entity/System/file counts,
  preserve selection, and explain combined-file System coverage. Currentness is not
  execution readiness. Validation retains complete Mapping eligibility.
- Validation uses addressable Group and Check pages with explicit back links; keep
  Group and Check review scopes separate. Group columns begin System, Group, Group
  description; Check and Description remain separate. Check details lead with purpose,
  pass/fail criteria and expected result shape, followed by SQL. Derive assertion
  wording from stored operators and operands; never infer execution results or intent
  from SQL. SQL panes stack at narrow widths. Group/Check grids keep readable column
  widths, scroll on both axes within a bounded height, and keep Actions visible.
  Supporting Group/Check definition context opens on demand; descriptions need no
  repeated explanatory heading or shared-layer annotation.
- Assertions use Document → Record navigation. Stable key, type and statement are
  required; extra context is optional. Preserve legacy structured detail. Active
  Assertions are downstream context; relevance is assessed by each workflow.
- Destructive Model operations retain bounded preview, dependency issues, permanent
  confirmation and revision/digest protection. Avoid duplicating implementation details.

For any change, exercise loading, empty, success, failure and revision-conflict states;
check focus/narrow layout; run the frontend checks in [AGENTS.md](../AGENTS.md).
