# Atlas design system

Use this document before changing `web_app/frontend`. It records the current
product language and interaction rules. Existing CSS remains the implementation
source of truth.

## Product character

Atlas is a governance-first data workspace. It should feel calm,
precise, dense, and trustworthy—not promotional.

- Prefer warm-neutral surfaces, dark readable type, and a restrained
  terracotta shell/navigation accent.
- Use the same terracotta for primary governed actions and warnings. Use green
  for confirmed success and red only for failure or destructive risk.
- Favor tables and ledgers for comparable records. Use cards only for summaries,
  choices, or a single bounded object.
- Keep authoritative state visible: Tenant, Model, revision, Tenant Lock, run
  state, and correlation reference.
- Do not hide operational evidence behind decorative UI.

## Source files

| Concern | Source |
| --- | --- |
| Tokens, focus, global defaults | `web_app/frontend/src/styles/foundation.css` |
| Shared buttons, typography, entry states | `web_app/frontend/src/styles/metadata.css` |
| App shell and Tenant workspace | `web_app/frontend/src/styles/tenant-workspace.css` |
| Model workspace, tables, badges | `web_app/frontend/src/styles/models-scope.css` |
| Model identity and horizontal navigation | `web_app/frontend/src/styles/model-workspace-overrides.css` |
| Workflow command bars, drawers, dialogs | `web_app/frontend/src/styles/profiling.css` |
| Workflow run monitor and events | `web_app/frontend/src/styles/workflow-runs.css` |
| Feature-specific exceptions | Other files imported by `web_app/frontend/src/styles.css` |

Do not add a new token or duplicate a shared component rule in a feature file
until the shared sources above have been checked.

## Foundations

### Color

Use semantic CSS variables. Never copy their hex values into new components.

| Token | Use |
| --- | --- |
| `--ink`, `--ink-2` | Primary text and strong dark surfaces |
| `--muted`, `--faint` | Supporting text and timestamps |
| `--paper`, `--surface`, `--soft` | Page, content, and quiet inset surfaces |
| `--line`, `--line-strong` | Dividers and control borders |
| `--blue`, `--blue-dark`, `--blue-soft` | Contextual links and data selection outside the application shell |
| `--orange`, `--orange-dark` | Primary governed command and warning emphasis |
| `--green`, `--green-soft` | Confirmed success or held lock |
| `--red` | Failure and destructive risk |

Within `.app-shell`, the existing blue selection tokens inherit the workspace
terracotta accent. This keeps legacy feature styles coherent without creating a
second competing navigation color.

The base palette is light-only. Do not infer a dark theme from browser settings.

### Typography

- Stack: system UI, beginning with `ui-sans-serif`, SF Pro Text, and Segoe UI.
- Body base: `16px`, line height `1.5`.
- Page headings: compact negative tracking; workflow labels remain sentence case.
- Eyebrows and field labels: small, bold, uppercase, tracked.
- Operational data: compact but never below the existing `0.52rem` metadata
  floor.
- Use `code` only for digests, failure codes, IDs, or machine values.

### Shape, depth, and motion

- Radius tokens: `--radius-small`, `--radius-medium`, `--radius-large`.
- Ordinary data surfaces use a border before a shadow.
- Use `--shadow-soft` for raised surfaces and `--shadow-float` for major floating
  context.
- Motion is short and functional. Use `--ease-fluid`; honor
  `prefers-reduced-motion`.
- Hover may clarify interactivity. It must not move primary layout.

### Spacing

No formal numeric spacing scale exists. Reuse nearby values and these patterns:

- Compact control gap: `0.5–0.65rem`.
- Surface padding: `0.75–1rem`.
- Page/workspace padding: `1.4–3rem`, responsive.
- Major section separation: `1.5–2.25rem`.

## Layout

### Application shell

- Desktop: `15rem` workspace navigation, `4.5rem` sticky top bar, flexible
  workspace. Its explicit control collapses the navigation to `4.75rem`.
- Workspace navigation contains Home, Metadata, Models and Prompts. Model-owned
  Mapping, Code generation and Validation appear in the Model navigation.
- Model pages use a persistent identity header and one horizontal navigation row:
  Overview, Settings, Input scope, Assertions, Enrichment, Profiling, Analysis,
  Conceptual, Logical, Dimensional, Mapping, Code generation and Validation.
- Keep the row scrollable, with explicit previous/next controls, visible active
  state and Arrow/Home/End keyboard navigation. Preserve the selected
  Logical/Dimensional layer when moving between Model sections or detail pages.
- Model tabs use a minimalist ribbon: a circle above each semibold label and a
  fine terracotta underline for the active section. Connect circles in three
  groups: Overview, Settings, Input scope and Assertions; Enrichment through
  Dimensional; Mapping through Validation. Leave a gap between groups.
  The first group is manual navigation: neutral gray circles with no run-status
  text, regardless of saved records or returned section states.
  The second and third groups show a short status below each label using explicit
  backend section states, without Object or record counts. Distinguish
  Completed from Results available: stored results may have been authored outside
  the web application, and a completed run alone does not imply current coverage.
  Latest Running, Queued or Failed states remain visible even with older results.
  Loading, unavailable data and revision conflicts must never imply Not run.
  All sections remain clickable. A soft gray inset highlight follows hover
  and keyboard focus without moving labels; disable its motion for reduced-motion
  preferences. Hide disabled overflow arrows and reveal the active tab after
  navigation or viewport resizing. Refresh section status is an explicit action
  beside the Model revision/lock context; do not poll for these statuses.
- Remember workspace navigation collapse across route changes. Collapsed links keep
  an accessible name and a native tooltip; the reveal control always remains
  reachable.
- At `42rem`, workspace navigation becomes a hideable bottom region. Model
  navigation remains a horizontally scrollable row.
- At `42rem`, page controls and high-density regions stack.

Use the shared dependency-free outline icons from `shared/ui.tsx` for shell
navigation. Keep them at `24×24`, `1.8px` stroke, rounded caps and joins. Do not
use emoji, Unicode symbols, or an unrelated icon family.

Workspace navigation uses warm-neutral surfaces, terracotta active markers and
a pale terracotta active fill. Model tabs use a quiet status ribbon and underline
without boxed backgrounds. Keep the workspace rail header to its
single left-aligned Hide/Show control. Tenant context stays in the top bar; the
Model header shows its name, description, revision and Tenant Lock state.

Every layout child in a flexible grid must use `min-width: 0`. Wide tables use a
scroll container and an intentional `min-width`; do not squeeze or silently
truncate governed values.

### Page hierarchy

Use this order when applicable:

1. Tenant and Model context in the shell.
2. Page or workflow command bar.
3. Lock/revision/status context.
4. Filters and explicit Refresh.
5. Primary table or ledger.
6. Inspector, drawer, or dialog for one selected record.
7. Empty, loading, and error state in the same content location.

Inside a Model, the active tab supplies the visible section title. Do not repeat
it in a large heading below the tabs; retain a visually hidden semantic heading
for assistive technology. Record-specific detail headings remain visible.
Use one compact toolbar: subsection/layer selection and context first, supporting
actions next and the primary action last. Follow with recent runs, filters and
the results ledger. Model identity and revision stay in the shared header.

Overview uses an unboxed summary: separate Logical and Dimensional schema lists,
with status and updated time aligned to the right on desktop. Schema labels wrap
without truncation; metadata moves below the lists on narrow screens. Keep the
workflow ledger close below this summary.

The Metadata catalog uses a full-width Excel Change Set above a left section
rail and the selected sheet. Keep the page heading to “Metadata catalog”;
Tenant identity stays in the shell. Use prominent Reference, Foundational, and
Operational buttons with sheet counts, without a separate navigation heading
or sheet filters. Keep Refresh and Export Excel in the page header. The Excel
panel uses “Tenant Lock is required” when unlocked, with draft details and
validation results shown only when relevant. Wide sheets scroll inside their
surface with sticky headers, first column, and row actions; Show details opens
the existing row drawer with Edit.

## Components

### Buttons and links

- `.button-primary`: one main write command per local decision area.
- `.button-secondary`: refresh, cancel, navigation, or supporting command.
- `.button-accent`: exceptional governed confirmation such as applying a
  validated draft.
- `.button-small`: compact command bars and table contexts.
- `.text-action`: row-level navigation or details.
- Disabled controls must explain the prerequisite through nearby text or a
  `title` when appropriate.

### Forms

- Visible label above every input. Placeholder text is never the label.
- Reuse `.workflow-filterbar` for list filters and the existing dialog field
  patterns for run configuration.
- Backend remains authoritative. Frontend checks exist for immediate feedback,
  then the backend revalidates.
- Put errors next to the affected action. Preserve user input after a recoverable
  failure.
- Use consistent select triggers. Multi-select menus float beneath their trigger
  without shifting the page; keep checkbox rows compact, searchable and keyboard
  accessible. Searching must preserve selected values and must not submit the form.
  Escape returns focus to the trigger; clicking an option label keeps the menu open.

### Tables and ledgers

- Use tables when records share fields or users compare values.
- Keep headers sticky inside long scroll regions.
- Keep the natural content visible with horizontal scrolling rather than card
  conversion or aggressive ellipsis.
- Right-align action columns; keep row action wording explicit, such as
  “Show details”.
- Active rows use `--blue-soft` plus the existing blue inset marker.

### Status

- Use `.status-badge`; never communicate state by color alone.
- Success: green. Failure: red. Warning: orange. Inactive/queued: neutral.
- Preserve exact backend state names while converting underscores to readable
  spaces.

### Drawers and dialogs

- Drawer: inspect one selected record without losing the ledger context.
- Dialog: make or confirm a bounded decision.
- Modal dialogs require a label, initial focus, focus trap, Escape handling, and
  focus restoration.
- Clear-layer previews lead with the total deletion count and collapsed workflow
  sections, then counts by record type and affected-record details. Show Record,
  Status and Lock, without repetitive Change/Reason columns. Keep blocked issues,
  permanent-delete confirmation, revision/digest protection and pagination intact.
- Use an opaque/light dialog body. Transparency belongs only in the surrounding
  scrim or restrained shell material.

### Loading, empty, and errors

- Loading: `.surface-state` with `aria-busy="true"`.
- Empty: `.empty-state`; explain what is absent, not merely “No data”.
- Error: `role="alert"`, a safe reason, and a concrete next action when one is
  known.
- Never display raw prompts, physical rows, tool output, credentials, secrets, or
  provider exception dumps.

## Workflow interaction contract

Workflow data is manually refreshed.

- Do not use `refetchInterval`, `setInterval`, hidden polling, or automatic page
  refresh for run lists, run details, events, or results.
- Fetch on initial navigation or explicit record selection.
- The visible Refresh button refetches the active view and its selected run.
- A successful user mutation may invalidate affected queries once so the result
  of that command is visible. It must not start a recurring refresh loop.
- An active run may remain visually stale until Refresh. This is intentional.

Run failures show only bounded server-approved diagnostics:

- failure code and safe message;
- last failed or blocked stage and attempt;
- execution mode and registered provider/model when available;
- event sequence, progress, and finding count;
- correlation reference for server-side investigation.

## Content style

- Use plain operational language: “Refresh runs”, “Apply validated draft”,
  “Tenant Lock required”.
- State what happened before suggesting what to do next.
- Use “Tenant”, “Model”, “Workflow Run”, and “Tenant Lock” consistently.
- Use one identity label for Tenant, System, and Connection references. Prefer
  codes in tables, pickers, and relationship details; do not stack the name,
  code, or internal ID as a subtitle. Keep roles, visibility, locks, and counts
  where relevant, and retain editable identity fields in the Metadata catalog.
- Avoid celebratory language, vague “Something went wrong” text, and internal
  implementation jargon.
- Use sentence case except for established identifiers and uppercase eyebrows.

## Accessibility

- Preserve semantic HTML: headings, labels, tables, lists, buttons, and links.
- All icon-only controls require an accessible name.
- Keep the global `:focus-visible` treatment.
- Ensure keyboard access, logical tab order, Escape-close behavior, and restored
  focus for overlays.
- Do not rely on hover, position, or color alone.
- Test narrow layouts at `58rem` and `42rem`; feature breakpoints may add tighter
  transitions.

## Change checklist

Before completing a frontend change:

- Read the shared source files listed above.
- Reuse semantic tokens and existing component classes.
- Confirm Tenant/Model scoping and backend authorization remain authoritative.
- Exercise loading, empty, success, stale/revision-conflict, and failure states.
- Test keyboard focus and a narrow viewport.
- Confirm no automatic workflow polling was added.
- Run `npm run check` from the repository root.

### Validation navigation

- Code Generation and Validation use prominent Logical/Dimensional links, with
  Silver/Gold context and the selected layer retained in navigation and runs.
- Code Generation filters show an Object multi-select followed by Status.
  Its ledger separates Schema and Entity name, in that order, and shows all
  contributing System codes.
  Generate SQL offers all unlocked or selected Objects, then all or selected
  contributing Systems, then combined or separate SQL files. Show the effective
  Object/System/file count. Preserve selection while searching and explain why
  an existing combined file requires all its Systems.
- Validation filters show Systems and currentness. Its run dialog selects
  Systems with applied Mapping in the current layer. Mark legacy Groups as
  shared across layers; keep them available for review.
- The Model's Validation page lists Groups in a table with an explicit Show
  details link. Group details list only that Group's Checks. Check details open
  a separate page showing its SQL and comparison contract.
- Use addressable Group/Check routes and Back to Groups / Back to Checks links.
  Focus the page heading on arrival. Keep Group selection/review at the Group
  ledger and Check selection/review inside its Group; reset selection on navigation.
- Preserve authoritative lock, active and currentness badges, safe load/revision
  errors and manual refresh. SQL panels stack at narrow widths; wide Check
  tables scroll inside their surface.

### Model metadata and target handoff

- Models offers Create Model only to Super Admins and Tenant Admins; the backend
  enforces the same restriction. Require a name and an owned Tenant Lock to save.
  Keep description, Silver/Gold policy settings, and registered agent defaults optional.
  Saved Logical and Dimensional schemas appear as muted read-only rows with a
  Saved label and explicit Edit action. Add schema creates an editable Unsaved row.
  Keep optional descriptions alongside each schema;
  each layer requires configured schemas before generation.
  Preserve form values on failure and open the new Model after creation.
- Model Settings has Definition and Prompts pages. Definition reuses the creation
  form for schema lists, naming rules, column policies and agent defaults.
  Silver settings includes Logical entity SCD type: Not specified, Type 1
  (overwrite changes), or Type 2 (preserve history). Preserve the saved choice
  when other settings are edited. It guides Logical and Mapping authoring;
  saving it does not change existing Entities or execute history processing.
  Use a compact form with thin dividers and short labels. Saved schemas use compact
  muted rows; show labels on editable rows. Prompt assignments show readable names
  and version/provenance, with machine identifiers and digests available in Details.
  Saving requires Architect or higher, an owned Tenant Lock and the loaded Model
  revision. Archived Models are read-only. Preserve unsaved fields on errors and
  stale revisions; require explicit discard before refreshing a dirty form.
  Preserve unchanged agent defaults without requiring a capabilities lookup.
  Offer an optional default Mapping System from the Tenant's existing Systems.
  Keep it in a collapsed Mapping settings section alongside Silver/Gold settings,
  with compact helper text.
  It applies only to assertion-only Entities without physical or Logical source
  support; backend eligibility remains authoritative.
- Enrichment opens on current physical metadata. Keep Workflow history separate
  and collapsed; show run state, date, and scope count, with consumption on demand.
- Scoped Object filters appear in this order: Source Tenant code, System code,
  Schema or Object name, then Zone. Visual and keyboard order must match.
  Tenant and System are dropdowns sourced from complete saved Model Input Scope,
  independent of the filtered page. Preserve revision/load errors and explicit
  refresh. Mapping System choices include eligible target Systems and retained
  Mapping results, including the configured fallback when eligible.
- Use Schema before Object in scoped metadata tables. Object details contain
  Attribute descriptions and inferred types. Row Actions contain only Edit;
  Show details opens the Object's Attributes. Put selection before Schema and
  bulk Lock/Unlock beside Refresh runs, using the physical locks from Metadata.
- The Object list offers Refresh, Run object enrichment and Run attribute
  enrichment. Object details explicitly offer Run attribute enrichment.
  Bulk Attribute runs offer all unlocked or selected Objects. Each Object starts
  with every active unlocked Attribute selected; users can open its Attribute
  list inside the same dialog and exclude individual Attributes. Preserve those
  choices when returning to the Object list or changing selection mode.
  Show per-Object selected/unselected counts, including zero, and distinguish
  locked Attributes. Parent Object locks protect their Attributes. Load complete
  details before starting; incomplete or failed loads must not create a partial
  run. Freeze every selected physical revision and omit Objects with no selected
  Attributes. Attribute runs also infer missing types and preserve existing
  inferred types. Description edits and runs use existing governed commands and
  receipts; concurrent changes protect the batch.
- Logical Attributes live inside Entity details, including review actions and
  their source mapping links. Logical and Dimensional provenance use the same
  Source/Rationale/Status table and structured detail renderer as Mapping.
  Both Entity ledgers show separate Schema and Entity name columns, in that order.
- Mapping opens a compact Entity mappings ledger at the Model level. Show details
  opens a separate Entity detail page with its Entity transformation displayed
  once in a focused panel above the Attribute transformations spreadsheet. Keep
  the System and Schema beside the Entity identity. Render authored logic first,
  sources below it, and repeated source records as compact tables. Attribute
  rows pivot transformation-document fields into separate columns, with target
  name/type first and compact status at the end. Show every active modeled
  Attribute, including missing mappings with blank transformation cells. A missing
  Mapping record has no selectable ID or Record info; real cleared records retain
  their governed review actions. Leave the Entity transformation blank when only
  Attribute mappings exist. Hide pairs with no Object or active Attribute output
  from the Entity ledger while preserving existing detail URLs and history. Retain custom fields and show
  nested source records as tables inside their cells. Keep nested table headings
  on one line and source identifiers intact; let their content size the source
  column and scroll within the spreadsheet on narrow screens. Omit a repeated
  document target name only when it exactly matches the target Attribute. Keep audit and
  template metadata in inline Record info; do not link out to a second Attribute
  transformation page. Existing Attribute detail URLs remain addressable.
  Show review actions only after selection; reveal Attribute
  filters on demand. Keep template metadata and the original Entity document in
  collapsed Mapping details. Keep transformations and Attributes off the Entity ledger.
  Humanize template field labels and structured values; preserve
  custom fields; never invent filler transformations for missing output. Long content
  expands inside its cell. Attribute filters, pagination, refresh, and review
  actions stay within that Entity.
- Mapping separates Logical and Dimensional with layer links in its
  command bar. Keep the layer in the URL, server-side ledger filters,
  separate System, Schema and Entity name columns in that order, and return navigation.
  Entity and Attribute Mapping results use dense spreadsheet-style tables with
  sticky headers and contained keyboard-accessible scrolling. Generate inherits that layer.
  Label retained Mapping Object order as Entity order. There is no System-order
  editor or Dependencies tab; legacy view query parameters open the Entity ledger.
  Show execution mode, Model and reasoning effort first, followed by the same
  All unlocked Entities / Selected Entities controls.
  Entity names open Attribute selection with Back to Entities, Select all unlocked
  Attributes and Clear Attribute selection. Preserve choices across navigation and
  scope-mode changes; search narrows the list without changing selected targets.
  Excluding an unauthored Attribute must not prevent partial Mapping generation.
  Incomplete pairs and true failed pairs use Partial results, including after
  Apply. Show counts for generated, incomplete, empty and failed outcomes; list
  only actual failed pairs in the System/Schema/Entity/Issue table. Apply review
  explains that omitted selected transformations become blank, while locked and
  unselected mappings and failed pairs stay unchanged. Never portray typed pair
  ordinals as completion progress. Code and Validation retain their complete
  Mapping eligibility gates.
- Conceptual detail pages use the workspace width, with status beside the title.
  Support evidence uses a Source/Rationale/Confidence/Status table; source codes,
  assertion text, and detailed reasoning remain available through Show details.
- Analysis shows inferred and observed cardinality separately. Unknown inference
  and unavailable measurements remain explicit. A difference is a nonblocking
  review warning, not proof that either the business rule or the measured data is wrong.
- Logical and Dimensional Export prepares a metadata workbook using each applied
  Entity's saved schema. Show selected Entity count, GDS placement readiness, revision
  conflicts, and download status. Keep registration as an optional Metadata handoff;
  Mapping and Code navigation do not require it. Dimensional generation selects
  applied Logical Entities with schema-qualified labels.
- Size tables for their actual columns. Keep selection controls compact and row
  actions visible at desktop widths; contain horizontal scrolling inside tables
  on narrow screens. Preserve keyboard focus after returning or saving.

### Manual Assertions

- Put Assertions after Input scope, in the manual navigation group. Show Documents, then the
  selected Document's Records, then Record details. Keep records filtered to their
  parent Document and provide Back to Documents / Back to the named Document links.
- Add Assertion explicitly offers New document or Existing document. Select an
  existing Document from a dropdown, then add a new assertion or choose an existing
  key to edit. Each key identifies one record and is unique within the Model.
- Document and Assertion types offer named suggestions plus Custom type; storage
  accepts free text. Reuse an existing Document's scope/type; do not alter other
  records by changing their shared Document in a record form.
- Require a stable record key, type and statement. Keep additional context and
  reference optional. Preserve legacy structured details; users need not write JSON.
- New document scope is Entire Model or a registered System within the Model Tenant.
- Remove the layer picker and layer filters. Explain once in the form that active
  assertions are available to downstream workflows and agents assess relevance.
- Manual records support editing and existing governed lock/unlock/status review.
  Require the Tenant Lock, protect locked records, preserve inputs on errors, and
  retry uncertain saves with the original request identity.
