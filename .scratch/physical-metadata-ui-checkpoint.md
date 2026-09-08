# Physical metadata review UI checkpoint — 2026-09-05

Completed `/tenants/$tenantId/metadata/objects`, linked from Metadata and the
successful Model Input Scope Object inspector. Native catalog and one Object
inspector support all four actions on real Object/Attribute IDs and current
opaque revision tokens. Active/inactive/all catalog discovery, server cursor
pages, bounded local Attribute pages, parent lock guidance and storage/inferred
type distinction are visible. Canonical workbook rows stay unchanged.

Commands retain exact payload and UUID after network/408/5xx uncertainty; UI
freezes competing edits until retry resolves. Definitive errors require Refresh.
Source ownership/record identity/revision response checks hide stale or invalid
data. Success displays reviewed/changed counts including zero and invalidates
affected Tenant catalog/scope caches once. No polling or Model revision invention.

Verification:

- 26 new actual-router/HTTP screen tests: all eight lifecycle paths, inactive deep
  links/Attributes, paging, all/filtered selection, current tokens, parent/role/
  expired-lock restrictions, ambiguity replay, stale conflict, unavailable cached
  detail and catalog, no-op feedback, manual Refresh and keyboard close/focus.
- Reader agent added eight transport tests (ten Metadata adapter tests total),
  including exact filters/cursor/POST headers and safe error propagation.
- Full frontend `npm run check`: **287 tests across 38 files**, types and production
  build pass. Final CSS refinement rebuilt successfully; scoped diff-check clean.
  Existing Vite warning for a >500 kB bundle remains unchanged in kind.
- Actual app/router preview with synthetic HTTP at desktop and 390px: compact
  filter row, original-case names, scrollable wide tables, wrapped command bars,
  native description disclosure via Enter/Space, successful Attribute lock with
  refreshed state, Escape closes inspector and returns focus to Object trigger.
- Preview tab closed; local Vite session stopped. No external systems used.

Production files: metadata API + screen, shared ObjectAttribute type re-export,
Metadata/Model Input Scope links, app route, narrow CSS, focused tests. No backend
or other result-detail changes in this UI slice.

Existing backend limit remains explicit: Object detail supports at most 2,000
Attributes. It rejects wider Objects; the UI reports this safely instead of
showing a partial detail as complete. Governed SQL authorization/atomicity tests
are root/writer/reader's separate same-feature backend gate.
