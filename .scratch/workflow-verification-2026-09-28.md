# Atlas workflow verification — 2026-09-28

## Scope and result

Verified Mapping, Code generation, Validation authoring, Atlas Workbench logic,
and the packaged VS Code Stage extension using synthetic fixtures and disposable
PostgreSQL. No existing database or external service was used.

| Area | Evidence |
| --- | --- |
| Mapping | 153 unit tests and 34 disposable-database tests passed. Covers independent Entity/System generation, Attribute coverage, and contribution eligibility. |
| Frontend | 493 tests passed; type checking and production build passed. |
| Web walkthrough | Mapping → Code → Validation completed for both Logical and Dimensional layers: 2 Entities / 6 Attributes, 2 SQL artifacts, and 2 Checks per layer. |
| Validation correction | Stale SQL is omitted consistently when applying Validation definitions. Three disposable-database regression cases passed. Fresh browser walkthrough confirms Definition, Mapping, and Code all show Current after applying new Logical checks while stale Dimensional Code remains. |
| Atlas Workbench | 133 JavaScript tests passed. Includes five-system coverage, missing Attribute mappings, missing/duplicate Code assignments, schema-qualified identity, locks, snapshots, DBML, and editing conflicts. |
| Atlas Python/package checks | 47 passed; 38 skipped because PowerShell is unavailable. Rebuilt plugin ZIP matches source; package references resolve. |
| Stage extension | 118 tests passed; types/build passed. Packaged VSIX passed isolated VS Code 1.139.1 host tests for activation, readiness, direct/chunked Stage, changed digests, lost-write recovery, and backend fingerprint protection. |
| Full repository suite | **3,063 passed; zero failures/skips** in 3m35s. All MCP, backend, web packaging, and Atlas packaging tests. Focused counts above overlap this suite. |

## Workbench corrections

- Logical SCD type remains visible but read-only in the local editor. Local
  validation now matches the server: change this setting through web Model settings.
  The PowerShell implementation carries the same rule for Windows parity checks.
- Mapping sheets display the System filter first. Attribute Mapping previously
  omitted it because it exceeded the three-filter display limit.
- Canonical plugin ZIP rebuilt after these changes. Extension source and shared
  serialization were unchanged; its existing packaged VSIX was tested directly.
- Canonical MCP and web source ZIPs rebuilt with the Validation fix; package/source
  parity passed. No deployment or publishing.

## Confirmed generation behavior

- Mapping runs independently for each selected eligible Entity/System pair in
  both layers and both authoring modes. Entity or Attribute source support cannot
  be skipped as inapplicable. Systems with no applicable support create no Mapping.
- Missing required Attribute mappings or a failed pair prevents a completed
  partial draft. Locked and deselected records remain preserved.
- Assertion-only Entities can use the governed fallback System. Its Mapping,
  exact Code assignments, and Validation path passed the persisted pipeline tests.
- Code covers each selected Entity and its contributing Systems. Tests reject
  missing or duplicate assignments and verify current input digests.

## Review fixture

The official Atlas local helpers initialized and validated a synthetic workspace
with zero issues: 4 Entity/System mappings, 6 Attribute mappings, 4 SQL artifacts,
4 source assignments, and 2 Validation groups/checks. It uses current Model JSON
schemas and default Mapping document structures.

The disposable workspace and one-off builder were removed during the subsequent
directory cleanup. Maintained regression tests remain under `tests/atlas/`.

## Limits

- Browser policy blocked opening the Workbench `file://` page. Native directory
  selection, manual UI save, and manual UI export were not verified; no workaround
  was attempted. Automated Workbench DOM/file-adapter tests passed.
- Browser workflow execution uses simulated AI and SQL responses, including
  `SELECT 1`. This verifies orchestration and persistence, not actual generated
  projection correctness or business meaning.
- No live LLM, Databricks execution, deployed pipeline, or loaded target data was
  tested. Validation authoring does not prove execution of its checks.
- The 38 PowerShell tests require their native runtime and remain unverified
  locally. Passing Node checks do not establish Windows PowerShell 5.1 parity.

## Local review

- Updated disposable app: http://127.0.0.1:8096/tenants/1/validation/models/1?layer=logical
- Current fixture: SCD Type 2 saved, two Logical SQL artifacts regenerated,
  two Logical checks applied; all new Validation currentness badges confirmed.
  The older seeded release-check group remains stale as expected.
- Browser evidence: `/Users/maazuddinmohammed/.codex/visualizations/2026/09/28/01a0e575-a0ec-72f0-8054-7277131f2dfc/atlas-validation-currentness.png`
- Final whitespace/diff check passed.
