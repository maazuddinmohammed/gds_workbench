# Mapping columns and Code provider diagnostics — 2026-09-28

## Changes
- Physical source tables use Tenant, System, Connection, Object schema, Object name, Attribute name; object tables place Alias last. Custom fields and original values remain intact.
- Wider transformation/source columns, bounded keyboard-scrollable attribute grid, explicit visible horizontal scrollbar. Chromium/WebKit styling avoids standard scrollbar-color overriding the custom track.
- Provider rejections map only known codes/allowlisted parameter shapes to fixed public guidance. Unknown rejections include only bounded HTTP status. Raw provider content remains private.

## Evidence
- Frontend check: 516 tests, types and production build pass. Rebuilt again after scrollbar-only CSS change.
- Backend targeted suite: 218 tests pass, including new real-SDK in-memory HTTP tests; final 31 diagnostic tests rerun after typing/format fixes.
- Full backend Pyright: zero errors. Changed Python Ruff lint/format pass. Git diff check passes.
- Web packaging: 55 tests pass. Source ZIP rebuilt after final frontend build.
- Browser: fresh random-credential/sentinel Docker fixture only; synthetic mapping documents include one and multiple source attributes. Verified canonical headings, 448px transformation column, bounded horizontal overflow, keyboard ArrowRight scrolling, visible scrollbar, and no whole-page overflow at the narrower browser size.
- Screenshots: atlas-mapping-layout.png and atlas-mapping-column-order.png in this chat visualization directory.

## Diagnosis boundary
The real SDK accepted all five Code context tools in the local synthetic conversation. A simulated later content-filter rejection propagates to the run with the fixed category and no draft. This proves request assembly and diagnostics locally; it does not establish the cause of the photographed deployed rejection. No live model/provider requests or external writes were made. Code still creates one atomic draft after all selected Entities succeed; earlier successes are not separately applicable if a later provider call fails.

## Next deployed check
Deploy the rebuilt app through the normal authorized release process, retry a single selected Entity, and inspect the new fixed failure reason. Do not infer a model configuration fault from the old generic rejection alone. Existing historical failures retain their old message.
