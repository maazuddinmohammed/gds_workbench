# Code generation start and Mapping input verification — 2026-09-28

- Fixed dialog requests including Systems belonging only to unselected Entities. Stale explicit System selections block submission and preserve Entity reselection.
- Fixed Tool-assisted mode is visible; no public mode override added.
- Known missing Mapping/System/Guide/Prompt prerequisites return safe specific codes and actionable UI messages. Unknown database details stay redacted; retries retain run identity.
- Added a default SQL Guide through governed functions. Requires an active Super Admin. The subsequent user-requested update allows installation after Models exist; exact replay preserves Models, Mapping and frozen Run versions. Conflicting/custom Guide history is never overwritten. The update passed 16 focused disposable-database/packaging tests plus Ruff and Pyright; no existing database was used.
- Default Code prompt includes three synthetic SQL examples: direct projection/provenance, staged join with multiple Attributes, and combined System branches. Generated Code retains runtime schema.object references. Instructions explain complete paged Object/Attribute Mapping retrieval and interpretation.
- Full Mapping documents, custom nested content and schema-qualified identities survive paging (2 Systems, 10 Attributes). Prompt examples parse and pass the actual Code artifact validator. These checks do not prove live business SQL correctness.

| Check | Result |
| --- | --- |
| MCP + backend suite | 3,172 passed, no failures or skips. |
| New prompt examples/paging tests | 8 passed separately after the full suite was collected. |
| Frontend | 514 tests passed; types and production build passed. |
| Packaging + Atlas Python | 102 passed; 39 Windows-only PowerShell cases skipped. |
| Disposable DB pipelines | All 36 Mapping → Code → Validation cases passed using the real installed default Guide. Three additional seed/setup tests passed. |
| Browser | Actual dialog → create → generate → validate → Apply succeeded for both Logical Entities, then one selected Dimensional Entity. Selected output became Current; unselected output remained unchanged. |

Browser checks used random-credential, sentinel-verified disposable PostgreSQL and deterministic fake AI. No live AI/Databricks, existing-database changes, deployment or publishing. Review container/tab disposed. Web source ZIP rebuilt; latest frontend bundle: index-CrpDEgga.js. Existing published prompt versions remain unchanged; new examples are in maintained defaults/fresh-install seeds and require normal draft/publish on existing installations.

Screenshot: `/Users/maazuddinmohammed/.codex/visualizations/2026/09/28/01a0e575-a0ec-72f0-8054-7277131f2dfc/atlas-code-generation-verified.png`

---

# Partial Mapping behavior — final verification, 2026-09-28

This section supersedes the earlier complete-pair Mapping policy recorded below.

- Any valid Object or Attribute transformation retains its Entity/System pair.
- Every active modeled Attribute appears in web details; missing transformations are blank.
- Missing selected, unlocked saved transformations clear on regeneration. Locked and unselected records remain unchanged; protected Attribute logic also protects its Object context.
- New empty pairs create no records. Existing pairs cleared to empty retain history and detail URLs, and disappear from the Entity ledger.
- Evidence gaps are advisory; genuine invalid candidates/provider failures remain isolated failures. Ownership, lock, revision, digest and Apply checks remain authoritative.
- Code, Validation and executable modeled-source eligibility still require complete Mapping.
- Web generation normalizes content-free JSON to null. MCP/Atlas require explicit null for newly authored content-free documents, preserving historical bytes/digests and meaningful false/zero custom values.

| Check | Final result |
| --- | --- |
| MCP + backend | 3,163 passed; no failures or skips. Includes disposable PostgreSQL pipelines for both layers and authoring modes. |
| Frontend | 505 passed; types and production build passed. |
| Atlas JavaScript | 136 passed. |
| Stage extension | 118 passed; compilation passed; rebuilt VSIX contents identical to canonical artifact. |
| Packaging + Atlas Python | 107 passed. Windows PowerShell cases skipped because the runtime is unavailable. |
| Source quality | MCP/backend Ruff format, Ruff check and project-specific Pyright passed; changed backend tests linted. |
| Browser | Fresh disposable local fixture: Generate → Partial results → Apply → Entity details. All four modeled Attributes remained, two populated/two cleared. Database regressions separately verify ten rows/five blanks. |

MCP ZIP, web source ZIP and Atlas plugin ZIP rebuilt and checked against source.
No deployment, external writes, existing-database changes or live model calls.
Browser verification used deterministic fake model output. Its temporary Docker
container and browser tab were disposed after verification. Existing saved prompt
versions were not overwritten; maintained default prompt sources and fresh-install
seeds carry the new authoring guidance.

Screenshot: `/Users/maazuddinmohammed/.codex/visualizations/2026/09/28/01a0e575-a0ec-72f0-8054-7277131f2dfc/atlas-mapping-blank-attributes.png`

---

## Earlier verification history (Mapping completeness rules superseded above)

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

## Partial Mapping application — September 28 follow-up

- Reproduced missing transformation/join evidence in one Entity/System pair
  discarding valid sibling output. Replaced the all-or-nothing authoring policy
  with explicit partial results; complete valid pairs form a fully validated
  draft. Failed pairs remain unchanged. All-failed runs offer no successful Apply.
- Frozen selection ordinals identify failures even when dependency execution
  order differs. Typed outcome events support counts and System/Schema/Entity
  diagnostics; old events are not reinterpreted. Failed details are bounded to
  200 with an explicit truncation flag.
- Browser verification used a new disposable PostgreSQL fixture on port 8097
  and a synthetic missing-join response for Order. Customer generated, the exact
  successful draft applied, and Partial results plus Order's failure remained
  visible after Apply. The runner and its container were disposed afterward.
- Browser evidence:
  `/Users/maazuddinmohammed/.codex/visualizations/2026/09/28/01a0e575-a0ec-72f0-8054-7277131f2dfc/atlas-partial-mapping-applied.png`.
- Broad MCP/backend run: 3,052 passed; one collected test expected the old
  private-context error. Corrected fatal-context expectation and reran the
  affected suites: 105 passed. No unresolved failure remains from that run.
- Disposable Mapping → Apply → Code → Validation pipeline: 20 cases passed;
  four partial cases rechecked with reversed frozen selection order. Existing
  failed Object/Attribute rows remain identical, or remain absent.
- Frontend: 502 tests, types and production build passed. Web source ZIP rebuilt;
  65 packaging tests passed. Backend Ruff/Pyright and diff checks passed.
- Four additional disposable SQL scenarios verified sparse selection order,
  duplicate and superseded events, legacy runs, all-failed runs, failure-list
  bounds, tenant isolation and partial status in Model lists.
- No live provider, Databricks, populated-database test, schema migration or
  deployment was performed. Historical failed runs need a new generation run;
  their discarded successful candidates cannot be recovered retroactively.
