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
| Project workspace and navigation | `styles/projects-scope.css`, `styles/project-workspace-overrides.css` |
| Workflow commands and run monitor | `styles/profiling.css`, `styles/workflow-runs.css` |
| Feature behavior | Matching `features/` package and its tests |

Use the selected **Navigator** web workspace: continuous KPMG-blue left navigation
and brand corner, white Meridian/ATLAS lockup, white header and working areas,
blue page headings and actions, and readable dense working text. The selected
navigation item is white with blue text; other items use white text on blue.
Tenant entry and local Workbench retain their existing Signature mastheads.
Tables/ledgers suit comparable records; cards suit summaries or choices.
Reuse semantic tokens instead of copying colors. Use shared outline icons, not emoji.
The current palette is light-only. Use short functional motion and reduced-motion
support. Every flexible layout child needs `min-width: 0`; wide tables scroll inside
an intentional container instead of truncating governed values.

## ATLAS Navigator / Meridian identity

Meridian identity selected on 2026-10-16; Navigator web shell approved on 2026-10-19
after prototype review. Keep the Atlas product name and an uppercase **ATLAS**
wordmark. Use KPMG-inspired colors without the official KPMG logo.

- `--brand: #00338D` fills the web sidebar and its aligned brand corner. The
  expanded sidebar is 14.5rem (12.5rem at tablet widths), collapsing to 4.75rem.
  Keep the 4.5rem header height and existing Project ribbon offsets. The header
  prioritizes Tenant/Project identity at narrow widths, hiding the supporting role
  badge and avatar. `--nav: #F5F6FA` remains a neutral token;
  records, fields, dialogs and the web header use `--surface: #FFFFFF`.
- Blue navigation uses `--on-brand: #FFFFFF` and `--on-brand-muted: #D9E5FB` text,
  `--on-brand-line: #8BA6D2` borders and `--brand-raised: #164795` hover surfaces.
  Active items remain white with blue text, including while hovered. Sidebar
  keyboard focus is white; header and content focus use `--accent`. Tenant/Project
  identity and role text use ink/muted tokens on the white header, with pale blue
  revision badges and avatar. Reduced-transparency mode preserves this placement.
- `--accent: #1E49E2`, `--accent-dark: #00338D`, `--accent-soft: #EDF2FF`
  for commands, links, focus and selection, including portaled dialogs.
- `--ink: #0C233C`, white working surfaces and `--paper: #F5F6FA` canvas.
  Amber warnings, green success and red failures remain distinct from brand colors.
- Bundle Open Sans Regular/SemiBold locally for UI, and Open Sans Condensed Bold
  for secondary blue section titles. Metadata, Projects, Prompts and Home use
  normal-width 24px Open Sans SemiBold headings in ink (22px on mobile).
  Record identities use normal-width Open Sans SemiBold
  in ink, with readable line height; do not repeat type/ID eyebrows above the name.
  Detail section headings use 16px Open Sans SemiBold in ink so they remain distinct
  from working text. Back links have clear space above and below them.
  Normal-weight working text, navigation, tables and dialogs
  remain centrally controlled. Tenant entry (26px), selected Project identity (22px)
  and Tenant Lock dialogs (20px) use normal-width Open Sans SemiBold in ink; entry and Project
  identity reduce to 24px and 20px on mobile.
- Shared lockup: 32px Meridian symbol, 11px gap, 23px Open Sans SemiBold **ATLAS**
  with 1.8px tracking. Use identical proportions on tenant entry, web and Workbench.
- Canonical vector: `web_app/frontend/public/assets/atlas.svg`; Workbench packages
  an identical `workbench/atlas.svg`. The web imports the canonical asset so Vite
  emits a content-hashed URL; fixed URLs can retain an older logo in browser caches.
  Both headers reference that asset rather than redrawing it.
  Scope `brightness(0) invert(1)` to blue brand areas for the white
  treatment; keep the canonical blue logo on light surfaces, including the mobile
  web header. The browser favicon uses
  `atlas-favicon.svg`, the same blue silhouette over a white circle, so its A stays
  white on dark browser tabs. Keep the
  32×32 viewBox and even-odd aperture. The extension icon is an antialiased
  512×512 PNG using the same silhouette on a pale tile.
- Fonts and OFL license ship in web `public/assets/fonts` and Workbench `fonts`.
  Workbench embeds font data in generated `fonts/fonts.css` for offline file launch;
  regenerate with `python3 atlas/build_workbench_fonts.py` after changing fonts.
  Keep plugin builder, Connector setup/updater and web upload allowlists in sync.
- Preserve desktop navigation collapse and mobile bottom navigation. The mobile web
  header stays white, with the blue wordmark above wrapping Tenant/Project rows; bottom
  navigation is blue with a white selected item. Workbench dataset navigation stays
  vertical on desktop and horizontal at 58rem and below.
  Tenant entry keeps clear space around the logo; sign-in details and long Tenant
  names wrap within their available width at small sizes.
  On mobile web, the Project ribbon stays in document flow so the taller masthead
  cannot cover its workflow links.

Rebuild the plugin ZIP, Connector ZIP and extension VSIX when their packaged sources
change. Brand assets do not change transport, authorization or workflow contracts.

## Navigation and hierarchy

Keep Tenant/Project, revision, lock and current run state visible. Workspace navigation
contains Home, Metadata, Projects and Prompts; workflow navigation belongs inside the
Project. Preserve Logical/Dimensional layer and addressable detail routes. The active
tab supplies the visible section heading; avoid another oversized heading below it.
Navigation labels use the same normal font weight as Prompts and Metadata, including
active items; color, surface and underline show selection.

Project navigation remains a keyboard-accessible, scrollable ribbon, including narrow
screens. Manual sections have neutral indicators. Workflow statuses come from explicit
backend section states, not record counts or guesses. Distinguish Completed from
Results available; loading/conflicts never imply Not run. Keep every section clickable.
Separate neutral setup sections from three navigation groups:
Profiling / Enrichment / Analysis; Subject Areas / Logical / Dimensional;
Mapping / Code generation / Validation. These groups organize navigation: Subject Areas
group Objects, Logical and Dimensional Build use those areas, and Dimensional consumes
Logical. Gaps between groups interrupt the connector line without interrupting keyboard
navigation.
Profiling stays before Enrichment.

Use one compact command bar, recent runs, filters, then the results ledger. Drawers
inspect without losing context; dialogs make bounded decisions. Keep one primary
command per decision area; Logical and Dimensional put Build and Optimize in one primary
Run menu (Run Logical, Run Dimensional), like the Analysis and Enrichment Run menus.
Refresh is the shared icon-only `RefreshButton` (the project header's arrows), named
Refresh for screen readers and tooltips. Preserve unsaved input after errors and request
explicit discard before refreshing dirty forms.
Record details keep identity and actions in one compact header. Edit stays visible;
lifecycle actions belong in More, with applicable state-specific choices when known.
Selection actions appear only after records are selected. Keep supporting facts aligned
in tables or definition grids instead of scattered labels and separate action rows.

Metadata uses Reference → Foundational → Objects → Operational tabs, full-width
tables, and normal-weight text. The selected sheet tab supplies its heading.
Catalogs are read-only; users edit through Excel export/import. Attributes live
inside Object details, while Excel retains all canonical sheets. Import opens the
governed Change Set drawer for workbook validation and apply.
Projects use normal-weight typography for values and controls. Main navigation page
titles use the normal-width heading treatment; secondary section titles retain the
condensed style. Project and record names use the
smaller, normal-width identity treatment. Stored descriptions, where needed, follow
the identity once; Profiling detail omits this repeated description. Enrichment puts
the Object name first, with schema below. Schema, System and other supporting
identity facts use a compact wrapping row on the white surface.
The Projects ledger shows Project, revision, lock status and updated time. Select one
Project with its radio control; Lock/Unlock sits beside Create Project. Project workspaces
show the lock status, with lock actions kept on the Projects ledger.
Object identity columns and catalog sorting follow Tenant code → System code →
Connection code → Zone → Schema → Object name. Object details and Attributes use
complete business-field grids; descriptions and key flags stay in their own columns,
without per-row detail disclosures. Catalog grids use the canonical Excel fields,
resolving relationships to natural codes/names and omitting raw IDs and audit columns.
Objects use View attributes to open the nested attribute grid; other rows need no
redundant details action. Column headings use PascalCase;
canonical workbook/import field names remain unchanged. Revisions stay internal.
Project export actions live under More: Export Metadata followed by Export DDL,
where supported. Mapping offers Export for either layer, selecting one System per
workbook; standard saved Mapping definitions and complete active Attributes form
the sheets. Export remains read-only and revision-fenced.
Mapping editing lives only inside Show details, with separate Edit Object Mapping
and Edit Attribute Mapping dialogs. Both reuse the shared dialog, focus, discard,
and retry behavior. Source pickers start collapsed, support search and selection,
and keep selected sources visible. Object edits save before Attribute edits; the
Attribute picker only offers columns from the saved Object sources. Logical source
choices cover the Project Input Scope for that System; Dimensional choices retain
Logical/Silver sources. Filter criteria and sample query belong to Object Mapping;
transformation logic and default record belong to Attribute Mapping.

Tenant Home uses a compact pale blue Tenant Lock panel, with a thin blue top rule,
neutral border and 6px corners. Keep owner/expiry/purpose together, a 40px owner
avatar and compact action controls. Acquire/Extend use deep brand blue; secondary
actions are neutral and confirmed destructive actions remain red. Open/locked
states retain green/amber badges, including the Project dialog. History opens on
demand and displays only the latest three events; no older-page control.

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
once. Window focus and network reconnect do not refresh cached screens or replace
open forms. Never introduce hidden polling, `setInterval` or recurring query refetch.
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

- Project schema/settings forms preserve saved values and unsaved changes. Display
  readable prompt names/version; internal identifiers/digests belong in Details.
- Selection survives search and nested Attribute selection. Complete selection data
  must load before a Run starts; failed loading must not create a partial selection.
  Multi-select run pickers provide select-all/clear controls. Header checkboxes show
  partial selection, affect eligible records only, and preserve nested Attribute choices.
- Profiling precedes Enrichment. Enrichment opens on current Project-owned results; keep
  history separate. Parent Project enrichment locks protect children. Object details allow
  description edits; Attribute details allow description/type and nullable key/PII flag edits.
  Unknown is distinct from No. Show saved Profiles in a technical table and export both
  dictionaries; retain unsaved edits on errors.
- Analysis separates inference from measured validation. Missing, zero and unavailable
  measurements have distinct labels; zero denominators are N/A. Cardinality differences
  are review warnings. Percentages use their actual measured denominators. The Run
  inference dialog's Analyze field picks One table per call (the default; Execution mode
  then offers One-shot only) or All tables in one call; run history names the first
  "One table per call · one shot".
- Logical/Dimensional ledgers separate schema and Entity name and show Active/Inactive.
  Provenance uses shared structured source/rationale/status views; sources have no order
  and may have no rationale. Export is an optional Metadata handoff.
  Both layers show Subject Areas, Entities and Relationships tabs; there are no Submodels.
  The Subject Areas tab lists active areas with their Objects, the layer's Entities and
  Last build; opening one lists its Entities, which open the usual Entity page. An eye
  icon in a narrow column before Show details opens a quick view in the side panel
  Activity uses (name, schema and type,
  then Show details, Expand/Reduce and Close): definition, Grain, Type, Subject Areas
  and Sources, then the active Attributes (Attribute, Data type, Nullable, Role). Escape
  or Close returns focus to the icon. Entity ledgers filter
  by Subject Area, and Entity details list their Subject Areas read-only (derived from
  Object sources) as clickable tags: pale blue pills, each opening its area. Attributes belong inside Entity details; retain addressable
  Attribute routes for references and back navigation. Relationships point child to
  parent: From (Entity + foreign-key Attribute) → To (parent Entity + key Attribute).
  Logical adds cardinality (Many to one or One to one) and a basis; Dimensional adds an
  optional role name and basis.
- Logical and Dimensional runs: Build lists active Subject Areas with Objects (name,
  Objects, shared Objects), most shared Objects first, then most Objects, then name,
  and builds the one area picked with a radio button; Start stays disabled until one
  is picked. One area per Build lets each draft be reviewed and applied before the next
  area builds on it; the backend still accepts several areas. Rows also show Last
  build. While the layer has a Build or Optimize draft waiting for
  Apply, Build names it and keeps Start disabled until it is applied or discarded.
  Optimize has no selection and reviews the whole model (cross-area fixes, merges
  by retiring duplicates). Both keep execution mode, model and reasoning settings, and
  run history names them Logical Build, Logical Optimize, Dimensional Build or
  Dimensional Optimize.
- Last build uses the Project ribbon's status circle: green check Applied, amber clock
  Draft waiting, dashed blue ring running, red mark failed, grey ring not built. In
  tables the circle stands alone, with its words and time on hover and for screen
  readers; the area page prints them. The backend decides the state.
- Mapping has Entity/System detail pages: Object logic once above a spreadsheet of
  all active modeled Attributes. Missing transformations stay blank. Preserve custom
  fields/nested values and whole source identifiers. Missing records have no selectable
  ID; persisted cleared records keep review actions and detail URLs.
- Mapping selection supports partial output. Explain selected omissions clear on Apply;
  locked/unselected records and true failed pairs stay unchanged. Show incomplete counts
  separately from failed-pair diagnostics. Pair ordinals are identities, not progress.
- Code uses Entities for generation selection and SQL files for saved-file review,
  including inactive versions. SQL detail puts the file first, with compact context
  and source mappings on demand. Keep stale guidance visible beside the file identity;
  supporting metadata belongs in SQL details. Reuse `workspace-sql` for read-only query panes.
- Code supports partial Mapping with warnings. Show exact Entity/System/file counts,
  preserve selection, and explain combined-file System coverage. Currentness is not
  execution readiness. Validation retains complete Mapping eligibility.
  More → Download all SQL exports all active saved files for the selected layer,
  including stale files, across pages and filters. The ZIP manifest records identity
  and currentness. Inactive versions retain their individual downloads.
- Validation uses addressable Group and Check pages with explicit back links; keep
  Group and Check review scopes separate. Group columns begin System, Group, Group
  description; Check and Description remain separate. Check details lead with purpose,
  pass/fail criteria and expected result shape, followed by SQL. Derive assertion
  wording from stored operators and operands; never infer execution results or intent
  from SQL. SQL panes stack at narrow widths. Group/Check grids keep readable column
  widths, scroll on both axes within a bounded height, and keep Actions visible.
  Supporting Group/Check definition context opens on demand; descriptions need no
  repeated explanatory heading or shared-layer annotation.
  More → Export all validations exports active groups/checks for the selected layer,
  including shared groups. ZIPs include SQL plus saved comparison criteria and
  currentness in a manifest; exports are read-only and revision-fenced.
- Context groups select a shared Context Type and list records in an editable table.
  Show selection, context text, source reference, status, lock, update time and Edit
  together. Edit opens the full stored content in a dialog without leaving the group;
  never save a bounded preview as the full record. Selected records use the governed
  review actions. Retain addressable detail routes for references and reading long
  values, but do not require a detail-page visit for ordinary editing. Generate
  record UUIDs once when creating drafts; never ask users to invent or edit them.
  Keep status and lock behavior visible. Relevance is assessed by each workflow.
  Use Context Group Name, Context Group Description and Context Record Text as the
  visible field labels. One group can contain many entries; show each as a separate
  table row. Source references remain plain text and bounded previews indicate truncation.
- Destructive Project operations retain bounded preview, dependency issues, permanent
  confirmation and revision/digest protection. Avoid duplicating implementation details.

For any change, exercise loading, empty, success, failure and revision-conflict states;
check focus/narrow layout; run the frontend checks in [AGENTS.md](../AGENTS.md).
