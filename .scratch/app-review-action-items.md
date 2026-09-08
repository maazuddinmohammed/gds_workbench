# App review — 6 September 2026

Requested outcome: a complete, working app with compact tables, clear detail pages,
direct target export and a focused Binding workflow. Keep Home and Metadata as-is.

Visual thesis: calm, compact working surfaces; the selected record and its meaning
lead, with operational detail available below.
Content plan: title and action → primary record/result → related evidence →
collapsible technical detail. No repeated instruction banners.
Interaction thesis: preserve keyboard focus when dialogs open/close, reveal
secondary details on demand, and retain the table context while inspecting a row.

## Actions, implemented and verified one at a time

- [x] Fix global table widths: compact selection columns, useful data columns,
  bounded document previews and scroll only within the table.
- [x] Input Scope: Add Objects dialog with Tenant → System → Zone → schema/name
  search, governed Apply, pagination, and a separate Object schema column.
- [x] Preserve documented eligibility: Source/Bronze in Input Scope; bound Silver
  supplies Dimensional. No direct Silver scope change was assumed.
- [x] Enrichment: shorten title/copy and provide sample results in the local app.
- [x] Analysis columns: selection, From Object, From Attribute, To Object,
  To Attribute, Relationship, Cardinality, Confidence, Validation, Status, Lock.
- [x] Detail pages: one primary reading path for Analysis, Assertions, Conceptual,
  Logical, Dimensional, Mapping, Code and Validation; secondary details collapsed.
- [x] Remove the redundant “Select records to enable review actions” instruction.
- [x] Logical/Dimensional: Export on the model page; ask for schema only; produce
  import-ready Object/Attribute workbook with descriptions, types, keys and audit flags.
- [x] Binding: focus Targets screen on Logical→Silver / Dimensional→Gold; show the
  Tenant's GDS Connection, filter schema, suggest identical Object/Attribute names,
  allow review/change/deselection, validate and apply through governed backend.
- [x] Mapping: make the missing-Binding prerequisite and Binding action clear.
- [x] Prompts: preserve newlines, compact template names and reduce repeated copy.
- [x] Run relevant tests, types/build and package checks; verify populated screens
  at desktop/narrow widths and leave the complete local app running for review.

## Verification

- Final MCP/backend/SQL/plugin/packaging regression: 2,639 passed, 44 existing
  Windows PowerShell skips. Only disposable Docker fixture databases were used.
- Frontend: 335 tests, TypeScript and production build passed.
- Notebook Python 3.12: 159 tests plus all three extracted-artifact probes passed.
- Backend Pyright: zero errors/warnings. Changed Python lint/format and diff
  whitespace checks passed. App/notebook source archives rebuilt.
- Live browser: Add Objects cascade, already-added state, separate Schema,
  populated Enrichment, requested Analysis columns, focused Analysis/Conceptual/
  Logical/Mapping/Code details, Silver/Gold discovery and Attribute review,
  actual Silver and Gold XLSX downloads. Prompt text has real newlines and wraps;
  no raw prompt text logged. Narrow layouts contain horizontal table scrolling.
- Full local app remains at http://127.0.0.1:8080/tenants/1/models/1 using synthetic
  data, a fixture-owned disposable database, and simulated Agent/Databricks
  adapters. This does not verify live Foundry generation or customer data.

The new Input Scope database function belongs to the fresh-install SQL sequence;
no existing populated database was migrated or modified.
