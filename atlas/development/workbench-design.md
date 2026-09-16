# atlas Workbench design

Implemented local Workbench using the approved table and comparison-panel layout. Covers workspace opening, local draft ownership, table interaction, DBML inputs and code boundaries. Automated DOM/file-contract checks pass; native browser visual and directory-picker verification remains outstanding.

## Responsibilities

Workbench lets users inspect Snapshots and review/edit the same local Change Sets used by the agent. The [working method](../atlas-plugin/references/working-method.md#workspace-records) owns workspace layout and identity. The [Change Set lifecycle](../atlas-plugin/references/change-set-lifecycle.md) owns approval, Stage and Apply; this document defines the local interface behavior.

Atlas opens bundled HTML in Chrome/Edge using explicit directory access; it has no local web server. It reads files, edits pending records, validates locally and generates DBML. Acceptance/manifest preparation belong to local helpers, Stage to the extension, and server validation/Apply to governed MCP tools. Workbench shows retained operation status without adding submission controls.

## Open or resume a workspace

1. Atlas opens or reuses Workbench immediately at startup, before resolving context or preparing inputs. The empty app needs no workflow or Snapshot; opening it does not select a workflow or fetch Snapshots.
2. Once the working directory and `.atlas` context are ready, choose **Open working directory** and select that folder, not `.atlas` itself. The browser may require a fresh directory-access gesture; do not promise automatic reconnection.
3. Read `.atlas/session.json`, then the available Snapshot manifests/catalogs and local draft inventory. Verify Tenant/Model identity and Snapshot integrity using shared rules. Folder names are not identity evidence.
4. Show the working path, Tenant, Model when selected, current workflow/task when present, and applicable SQL policy/environment. These values describe saved context; they do not prove current server authorization, freshness or lock ownership.
5. Resume the existing local view and drafts. Follow the shared resume/new-work decision when intent is unclear; opening the app does not create a new task or session.

One primary Tenant and at most one active Model belong to each working directory. Other Models use separate directories. Model-derived Metadata work can use [additional owner roots](../atlas-plugin/references/workspace-contract.md#model-derived-metadata-owners) in this same directory. Show a separate **Metadata owner** selector when several are available; keep the primary Tenant/Model context visible and unchanged. Missing optional folders are valid; create only what the work needs.

| State | Workbench behavior |
|---|---|
| No directory selected / access unavailable | Offer **Open working directory** or **Reconnect directory**. Do not claim access before permission succeeds. |
| Missing session file | Explain that Atlas must initialize this directory, or let the user open another. Do not infer Tenant/Model from folder names. |
| Invalid session or conflicting identities | Show the specific conflict and stop affected edits/submission. Preserve files for correction; no automatic rebinding. |
| Required Snapshot missing or invalid | Explain which input is needed. Keep valid independent areas available; the workflow owns fetching/installing the required Snapshot. |
| Existing draft or unfinished task | Show and preserve it. Starting new work does not clear pending changes. |
| Known stale Snapshot | Show why it needs refresh; preserve the draft for reconciliation. A reload cannot clear this condition. |
| Remote freshness unknown | Say so. A valid local manifest or recent file timestamp does not establish server freshness. |

The implementation retains GDS's Chrome/Edge File System Access approach. Other browsers, embedded webviews and persistent directory permissions are not established by the automated checks.

## Shared local drafts

- Read the effective result: immutable Snapshot records plus complete proposed records keyed by their canonical identities. Use the shared [Metadata](../atlas-plugin/references/snapshots/metadata.md) and [Model](../atlas-plugin/references/snapshots/model.md) guides for format and access.
- **Save local changes** writes the proposal to the same Change Set files the agent uses. It does not update a Snapshot, Stage a server draft or Apply changes.
- **Remove local change** removes that proposal: an existing record returns to its Snapshot value; a newly proposed record disappears from the draft. It does not delete an applied record.
- Apply [record protection](../atlas-plugin/references/record-state.md) before enabling edits and show the reason when a record is read-only. Existing natural-key renames follow the manual correction policy. Backend validation remains authoritative.
- Before saving, compare the loaded file/context versions with disk. If the agent or another window changed them, preserve the unsaved input and show a conflict; never overwrite silently. Save failures must not be presented as success.
- Before closing an edited record, changing directories or reloading, resolve unsaved input with **Save**, **Discard**, or **Cancel**. Save may still require conflict resolution.
- Content changes invalidate affected validation/review evidence according to its bindings. A saved edit does not remain approved merely because the task still says “reviewed.”

## Reload and status

**Reload local files** rereads the selected directory after agent/helper changes. It does not download a Snapshot or verify remote freshness. Use explicit reload, with no hidden interval polling. Fresh Snapshot acquisition follows the workflow and preserves/reconciles pending work before installation.

Present observed local and server states separately: saved locally, locally validated, reviewed, staged, server validated and applied. Each state needs its actual content/version binding or receipt. Editing task progress cannot establish a successful operation. Historical evidence may remain visible without being valid for the current draft.

Tasks remain short outcome/progress/evidence records, not a required sequence of UI stages. Keep durable validation reports, approvals and submission receipts outside disposable `.atlas/temp/`; tasks link to that evidence under the [workspace contract](../atlas-plugin/references/workspace-contract.md). Metadata reports/status bind the selected owner; switching owners cannot reuse another owner's approval or hide an uncertain operation.

## First-release acknowledgement

The user reviews/edits local records and actual findings in Workbench, then acknowledges the exact batch in the agent conversation. Helpers record its content binding. The agent invokes Stage Runner, presents the complete server validation/action review and asks separately to Apply. Workbench has no acknowledgement, Stage or Apply buttons in this release. Its observed status comes from durable helper/extension evidence, never inferred from conversation prose or task checkboxes.

## Validation boundary

Workbench uses shared schemas, normalization, serialization and local validation rules. It must report which checks ran and whether the evidence still matches the current files. See [local validation](../atlas-plugin/references/local-validation.md); do not duplicate domain rules here.

“Local Change Set validation” checks proposed records and their effective graph. It is distinct from running the business Validation Checks authored by the Validation workflow. Browser and CLI call `validation/run.js`; both report skipped checks and remaining human/server responsibilities. Model validation aggregates every registered owner's applied Metadata baseline, rejects conflicting physical records, and keeps owner-specific pending Metadata out of Model context. Substantive Model authoring requires the registered owner Snapshots; context-only reads can report a missing owner as a warning.

## Table readability and visual direction

Keep the overall layout, glassy shell, **Validate locally** action and validation-report flow. The user approved this table and comparison-panel layout for implementation.

The implementation replaces the earlier 10px data/9px headers with readable relative sizing, a near-solid table, explicit value labels and a closable side comparison panel. Column selection/resizing, keyboard controls, owner selection and DBML text preview are implemented. DOM tests verify interaction and content; browser URL policy prevented runtime visual, zoom and native directory-picker verification. Those checks remain explicit release-verification limits.

| Concern | Agreed behavior |
|---|---|
| Readable type | Start with 14px-equivalent data text, 12–13px headers, approximately 40px minimum rows and comfortable padding. Use relative units; verify with zoom and long real-world names. |
| Glass material | Retain translucent toolbar/frame surfaces. Use a near-solid table and editor background for stable contrast; honor reduced transparency/contrast preferences. |
| Column hierarchy | Put record name and distinguishing context first, then useful comparison fields. Default columns are dataset-specific; **Columns** exposes other fields. Do not hide identity needed to distinguish same-named records. |
| Orientation | Keep headers and the principal record-name column sticky. Allow horizontal scrolling and adjustable widths; do not squeeze every field into the viewport. |
| Long values | Descriptions wrap. SQL, Mapping documents and nested collections get meaningful summaries plus **Show details**. Full values are selectable/copyable in a side panel; hover is not the only way to read them. |
| Comparison | Keep **Snapshot** and **Change Set** views. Show local change labels such as Added, Changed or Deactivated; highlight changed values and provide Snapshot/proposed values in details. Local drafts must not be labeled Staged. |
| Value clarity | Distinguish `null`, empty string and a missing value. Keep Active/Inactive, lock state and local change state separate. Use readable labels as well as color. |
| Interaction | Retain filters, paging and explicit row actions. A detail panel preserves table context; editing follows the shared Save/Discard/Cancel and conflict rules. Keyboard focus and actions remain visible. |

Example default columns for Logical Attributes, with synthetic local proposals:

| Attribute | Entity | Data type | Key role | Nullable | Local change | Description |
|---|---|---|---|---|---|---|
| CustomerName | Customer | STRING | None | Yes | Changed | Name used to identify the customer in correspondence. |
| Email | Customer | STRING | None | Yes | Added | Customer's primary email address. |

This is a reading layout, not a new record schema. Exact payload fields, ordering and validation rules remain unchanged. Show the full technical field name in details when useful. Preserve access to all fields without requiring every field to dominate the default table.

Validation keeps its existing sequence: **Validate locally → findings → Open record → correct draft → validate again**. Apply the same readable typography to findings without redesigning that workflow.

## Generate DBML from the effective Model

The input is **Model Snapshot plus all saved Model Change Set records**, merged by canonical key using the existing shared overlay. Pending records replace matching baseline records; additions appear; untouched baseline records remain. Table paging, filters and the currently selected Snapshot/Change Set tab do not restrict generation.

1. Resolve any unsaved editor changes before generation. Use one consistent set of saved input files, with their Snapshot identity and pending digest.
2. Build the effective Model. Stop on malformed records, duplicate keys or overlay failure; never silently substitute Snapshot-only output.
3. Use the shared structural checks for valid references, key/status rules and record protection. Link blocking findings to the existing validation view. DBML generation does not establish full server validity or approval.
4. Render active concepts/entities/attributes/relationships and their submodels. Active locked records remain visible. Keep existing complete-model and submodel exports; full diagrams retain cross-submodel relationships.
5. Preserve attribute order, types, nullability and key roles. Do not depict unknown cardinality as confirmed one-to-one; annotate uncertainty and omit an unsupported connector when DBML cannot express it honestly.
6. Verify the saved inputs still match before publishing the export. If they changed during generation, discard the candidate output and report that regeneration is needed. Bind the manifest to the exact inputs used.
7. Show the generated file list and readable DBML text, with **Copy** and **Download** actions. Label it **Snapshot + local changes**. Preserve the existing export manifest/file management; changed inputs make an older export out of date.

Atlas retains the shared overlay/renderer and exports to `model-dbml/` only through the user's Workbench action. The browser validates the full effective graph, binds inputs before rendering, and rechecks them before publishing. There is no Atlas CLI or MCP export command; agents do not generate or consume DBML. An overlay failure cannot silently become Snapshot-only output. Unknown Conceptual cardinality produces an annotation without a misleading connector.

The browser keeps managed-file backups under `.atlas/temp/` and restores prior output if publication fails; CLI prepares a candidate directory and restores its previous directory on failure. Neither path declares a successful export after detecting changed inputs. Browser multi-file writes cannot be an atomic filesystem transaction; the manifest and rollback checks make this limitation explicit.

Synthetic tests cover effective overrides/additions, untouched records, duplicates, locked edits, unknown cardinality, concurrent input changes and prior-export restoration. UI tests ensure table filters do not restrict DBML and verify the preview. The tests use no external services.

## Code boundaries

Refactor by responsibility while preserving the existing shared logic and static-browser packaging. Keep one clear controller; extract substantial UI concerns from `app.js`. File size alone is not a reason to split code.

| Module | Owns |
|---|---|
| `app.js` | Current view state, event wiring and readable operation flows: open, reload, save, validate, generate DBML. |
| `ui/records.js` | Dataset display configuration, table/filter rendering and record details/comparison. One shared renderer, not one file per dataset. |
| `ui/editor.js` | Record form, unsaved input, field feedback and save/cancel interaction. Delegates persistence and domain checks. |
| `ui/validation.js` | Existing report summary, finding filters and navigation to affected records. |
| `workspace.js` | File access, Snapshot verification, draft persistence/conflict checks and report/export storage. No screen rendering. |
| `core.js` | Existing canonical keys, normalization, serialization, overlay and change classification shared with other consumers. |
| `metadata.js`, `model.js`, `validation/`, `model-quality.js` | Area adapters and reusable validation/quality rules. Follow the shared [validation organization and review index](validation-index.md#implementation-organization); no copied rules inside UI modules. |
| `dbml.js` | Pure effective-Model-to-DBML conversion; no DOM, filesystem access or separate merge logic. |
| `ui-state.js`, `styles.css` | Existing UI eligibility helpers and presentation styles. Split further only when a concrete concern needs an independent home. |

This separation does not require a new UI framework, table library, local server or per-field component system. Frontend checks support feedback; backend authorization and validation remain authoritative. Shared serialization must remain compatible with CLI, extension and Python consumers.

See the [Workbench code map](workbench-code-map.md) and [validation index](validation-index.md) for exact modules and rule tests. The static browser packaging and canonical serialization remain shared with the helper and extension.

## Reuse and required adaptations

| Preserve from GDS | Adapt for Atlas |
|---|---|
| Static browser launcher and explicit directory access | Select working root; read `.atlas/session.json`; tolerate absent optional areas. |
| Snapshot inventory/hash checks and complete-record overlays | Check Metadata Tenant and Model identities consistently against explicit context. |
| File digest conflict checks and evidence bindings | Preserve unsaved input; separate flexible task narrative from machine operation state. |
| Existing normalization, serialization and validators | Align browser/helper coverage; expose unsupported checks and locked-record reasons. |

Development verification: `node --test tests/atlas/workbench-*.test.mjs`; CLI integration checks in `tests/atlas/test_workspace.py`. Atlas uses its own launcher, helper and `.atlas` contract; GDS helpers must not be run against Atlas files. Final packaging is verified separately from these source tests.
