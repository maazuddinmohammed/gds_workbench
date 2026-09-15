# Workbench code map

Static, local-only browser app. Open `index.html` through the Atlas launcher; select an initialized working directory. Chrome/Edge directory access is required. No remote requests or hidden refresh polling. Review and edit locally; conversation acknowledgement and extension Stage remain outside this UI.

| File | Responsibility |
|---|---|
| `app.js` | Open/reload/save/validate/export flow and event wiring. |
| `ui/records.js` | Dataset filters, column selection, table and Snapshot/proposal comparison. |
| `ui/editor.js` | Schema-driven field controls and unsaved form tracking. |
| `ui/validation.js` | Findings, check coverage and record navigation. |
| `ui/text.js` | Escaping and readable scalar labels. |
| `workspace.js` | File permission handles, owner roots, Snapshot integrity, conflict checks and durable reports/exports. |
| `core.js` | Canonical identity, overlay and Python-compatible serialization; shared with helpers and extension. |
| `dbml.js` | Pure effective-Model rendering. Unknown cardinality is annotated without a false connector. |
| `validation/run.js` | Shared browser/CLI validation assembly and explicit check coverage. |
| `validation/common.js` | Published schema validation, canonical keys, duplicate keys, record protection and declared uniqueness. |
| `validation/metadata.js` | Metadata references, Tenant ownership and Object/Attribute locks. |
| `validation/model.js` | Applied scope, graph references, nested protection, bindings, mapping coverage, code/validation contracts. |
| `validation/model-policy.js` | New-table key/audit/name conventions; membership, lineage, type compatibility, Mapping documents and retarget guard. |
| `validation/sql.js` | Finite transformation statement/projection checks and governed validation-query shape. No SQL is executed. |
| `model-quality.js` | Bound decision evidence, honest inference/measurement distinction and coverage warnings. |

Pure validators return findings. They do not read files, execute SQL, change records or prove business meaning. The server remains authoritative. The same `validation/run.js` entry point serves the browser and helper.

Focused checks: `node --test tests/atlas/workbench-*.test.mjs` from the repository root. Fixtures contain synthetic records only. Browser URL policy currently blocks automated opening of local HTML; DOM tests do not establish screenshot, zoom or native directory-picker verification.
