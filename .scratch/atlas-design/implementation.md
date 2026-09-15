# Atlas implementation

User authorized the complete agreed first release and local validation. Work incrementally; no deployment, external writes or populated-database changes. Preserve existing GDS behavior. New Python generation and Member table support remain deferred.

## Completion ledger

- [x] Portable scaffold, 14 skills, shared references, approved Workbench preview.
- [x] Workspace/session/tasks/owner roots and durable operation evidence.
- [x] Snapshot installation/read/edit/reconcile helpers and shared validation.
- [x] Profiling batch-list SQL planning/results; analysis scope parity.
- [x] Target DDL instructions and mapping/code/validation local contracts. DDL remains agent-authored, as in the existing plugin; no dedicated legacy generator existed.
- [x] Readable Workbench/editor/validation/DBML with modular code.
- [x] Modular Atlas Stage Runner with exact helper/manifest contract and recovery.
- [x] Backend/database compatibility, governed consumer context and validations.
- [x] Validation index, executable helper contracts and user guide.
- [x] Plugin/extension packaging and artifacts.
- [x] Native validation parity: missing Metadata owners, task Snapshot bindings, cross-owner key contracts and generated SQL checks. Optional modeling evidence remains optional; deterministic record checks run independently.
- [x] Relevant complete regression suites, types/lint, synthetic lifecycle and package checks. Final Atlas suite: 53 passed, including 22 native PowerShell cases; combined GDS/Atlas JavaScript: 197 passed; legacy plugin Python: 352 passed. No skipped cases. Plugin ZIP rebuilt and source parity verified after the follow-up.

## Ownership

Root: scripts/contracts, workspace/session/evidence, integration, docs, packaging.
Workbench agent: Atlas workbench sources and its new tests; shared module contract changes coordinated.
Extension agent: atlas-vs-code sources/tests, Stage request contract coordinated with root.
Backend agent: authoritative Python/SQL changes/tests and compatibility/operator guidance.

Current state: Atlas implementation and local verification complete. Atlas runtime is independent of the legacy GDS workspace contract. Existing GDS plugin/extension sources remain unchanged; shared backend/SQL changes are documented and tested. See `atlas/validation-report.md` for results and honest platform limits. Exact Windows PowerShell 5.1, native browser visual checks and live deployment checks remain environment-specific verification, not claimed local passes. Deployment remains separate.
