# GDS Workbench design system

Use this document before changing `web_app/frontend`. It records the current
product language and interaction rules. Existing CSS remains the implementation
source of truth.

## Product character

GDS Workbench is a governance-first data workspace. It should feel calm,
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
- Model pages add a `13.5rem` guided-journey rail inside the workspace. Its own
  control collapses the rail to `4.25rem` without changing workspace navigation.
- Remember both choices independently across route changes. Collapsed links keep
  an accessible name and a native tooltip; the reveal control always remains
  reachable.
- At `58rem`, the Model journey becomes a horizontal/top region. At `42rem`, the
  workspace navigation becomes a hideable bottom region.
- At `42rem`, page controls and high-density regions stack.

Use the shared dependency-free outline icons from `shared/ui.tsx` for shell
navigation. Keep them at `24×24`, `1.8px` stroke, rounded caps and joins. Do not
use emoji, Unicode symbols, or an unrelated icon family.

The workspace navigation and Model journey use warm-neutral rail surfaces,
terracotta active markers, and a pale terracotta active fill. Keep the rail
header to its single left-aligned Hide/Show control; Tenant and Model identity
remain in the top bar.

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
