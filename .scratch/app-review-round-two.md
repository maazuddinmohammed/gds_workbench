# App review round two

Visual thesis: a quiet working table, aligned like Profiling, with one record
and one decision in focus at a time.
Content plan: title/action → compact activity → Object table → record detail.
Interaction thesis: explicit row actions; a focused Binding detail with a back
action; brief focus/reveal transitions with existing reduced-motion support.

- [x] Enrichment: remove introductory copy; separate run status from current
  metadata. Object table: Schema, Object, Description, Zone, Attributes, Lock,
  actions. Attribute detail: Name, Inferred type, Description, Lock, actions.
- [x] Manual description edits and AI regeneration use governed metadata writes,
  current revisions, existing physical locks, and retry-safe run/command receipts.
- [x] Input Scope: Schema before Object; match Profiling table styling.
- [x] Analysis: explain missing cardinality from evidence, restore Show details.
- [x] Logical: Attributes live within Entity details. Logical/Dimensional source
  mapping documents reuse Mapping's readable tabular renderer.
- [x] Binding: Logical/Dimensional segmented buttons; searchable schema and target
  selection; focused Attribute Binding detail and explicit Apply.
- [x] Tests, package rebuilds, desktop/narrow browser review, running full app.

Locks remain the same Object/Attribute metadata locks seen in Metadata; no
separate description-only lock state is introduced.

## Verification

- Frontend: 339 tests, TypeScript and production build pass.
- Backend/shared full regression: 2,656 passed; 44 platform skips. Two plugin
  checks failed while the separate active “Refine plugin data modeling” task
  changed its guides: instruction footprint and checked-in ZIP freshness.
  The other task subsequently rebuilt its ZIP and updated the guidance checks;
  both affected test files now pass on recheck. No concurrent plugin edits were overwritten.
- Notebook source: 159 passed on Python 3.12; extracted artifact probes: 3 passed.
- Backend, MCP, notebook Pyright: zero errors. Backend Ruff passes.
- Updated web-app and notebook source archives rebuilt locally; all 61 web
  packaging checks pass.
- Desktop and narrow UI checked. Manual description save, shared lock/unlock,
  targeted Attribute regeneration, Entity/Attribute detail navigation, and
  schema/Object/Attribute binding review verified through the complete local app.
- Local app remains at http://127.0.0.1:8080 against its disposable PostgreSQL
  fixture. AI and Databricks adapters are simulated; no external runs performed.
