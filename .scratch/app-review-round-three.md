# App review: selection, enrichment, and target bindings

Visual thesis: quiet, rounded working tables with compact selection columns and
controls above the records, matching Profiling.

Content plan: primary command, current records, focused Object/Attribute detail,
then an explicit reviewed Apply. Activity stays separate and collapsed.

Interaction thesis: short hover feedback; focused dialogs with Escape and focus
restoration; reduced-motion support. Selection drives bulk actions.

## Implemented

- Enrichment Object and Attribute selection, select-all, bulk Lock/Unlock, Edit-only
  row actions, separate details navigation.
- All-unlocked or selected description runs at one level; selected Attributes also
  fill missing inferred types. Frozen revisions and physical locks protect edits.
- Binding inventory, schema/Object search, Attribute search, bulk locks, and
  reviewed schema generation using unique trimmed lowercase name matches.
- Existing bindings and inferred types remain protected. Ambiguous or incompatible
  target matches do not become automatic assignments.
- Shared target lookup SQL remains independent of workbook export for notebooks.

## Verification

- Backend, disposable PostgreSQL, SQL contracts, Python plugin helpers, and
  packaging: 2,666 passed; 44 skipped on this host.
- Frontend: 344 passed; TypeScript and production build passed.
- Notebooks: 159 passed; all 3 extracted-artifact probes passed on Python 3.12.
- Plugin JavaScript: 52 passed. Extension: 73 passed; types and bundle passed.
- Backend and notebook lint, format, and type checks passed. Formatting checked
  project source and the tests changed in this round; no unrelated test reformat.
- Rebuilt web/notebook archives; all 61 packaging tests passed afterward.
- Browser: separate Object and Attribute runs completed; locked Objects excluded
  from All unlocked; Object and Attribute Binding lock/unlock applied correctly;
  Generate reported locked bindings without changing them; target and Attribute
  search, detail navigation, focus restoration, and narrow layouts verified.
- Complete app restarted with final source and a fresh disposable sample database.
  Local AI and Databricks remain simulated; these checks do not claim live-provider
  output quality or Windows PowerShell execution.
