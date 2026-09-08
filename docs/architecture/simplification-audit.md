# Ponytail simplification audit — 2026-09-05

The audit removed **424 net lines of production source** while keeping the
existing deployment model and public behavior. No dependencies were added or
removed. The largest runtime improvement is faster local Stage chunk planning.

## Scope and method

Inventoried 839 repository text files, including existing uncommitted work.
Reviewed the architecture and ADRs, traced the main execution paths, scanned
Python and JavaScript/TypeScript syntax trees for duplicate functions and thin
wrappers, checked dependencies and callers, and ran the regression suites.
The function scans covered 313 Python files and 114 JavaScript/TypeScript files.

This was a whole-tree simplification review with focused manual examination of
the runtime boundaries and proposed changes. It was not a manual inspection of
every source line or a claim that tests prove every possible behavior.
Downloaded dependencies, virtual environments, Git internals, generated bundles,
and archives were excluded from handwritten-code cleanup. Generated packages
were rebuilt and verified against their sources.

All reduction figures compare against a snapshot taken before this audit,
including the user's pre-existing edits and new extension. They do not count
those earlier changes as audit work. Tests, docs, CI, and generated artifacts
are excluded from the production-source reduction.

## How the pieces fit

| Area | Execution path reviewed | Result |
| --- | --- | --- |
| MCP server | `runtime.py` → authentication/server registration → governed tools → application/domain rules → PostgreSQL | Shared tool annotations; removed unused Model selection code. All 37 tool contracts retained. |
| Agent plugin | Snapshot files → local helper/Workbench → validation and approval digest → Stage request | Reused Workbench normalization/serialization; faster chunk planning. |
| VS Code extension | `extension.ts` → trusted workspace/profile/authentication → `stage-runner.ts` → bounded MCP calls and receipt | Faster chunk planning; Unicode batching coverage; rebuilt bundle and VSIX. |
| Web backend | `main.py` → feature routers/services; workflow assembly → executor → validation/repair → governed persistence | Shared repeated parsing/diagnostics; removed unused reconciliation and schema helpers. |
| Notebooks | Notebook entry and preflight → Tenant Lock/Workflow Run control → shared in-process workflow assembly | Replaced manual thread result/exception handoff with `ThreadPoolExecutor`. |
| Frontend | Route/workspace → feature screens/dialogs → API client; temporary state remains in React | Reused identical fields, detail states, initials, and Model route-ID checks. |
| PostgreSQL | Preflight → install files `01`–`19` → verifier; authorization, locks, revisions, workflow and Change Set functions | Kept SQL integrity and privilege boundaries; exercised disposable-database tests. |
| Packaging/local launch | MCP ZIP builder, plugin ZIP builder, VSIX build, Databricks upload builder, local runner | Kept artifact isolation and allowlists; verified packaging contracts and extracted notebook imports. |
| CI/docs/tests | Both workflows, manifests, dependency files, architecture docs, test suites | Added omitted Workbench JavaScript tests to CI; installed Windows form-test dependencies; corrected stale docs and their count assertion. |

The web App and notebooks reuse Python source at build time and run workflows
in process. They do not call the deployed MCP server. This remains the design in
[ADR 005](../adr/005-independent-deployments-with-shared-source.md).

## Simplifications applied

Ranked by how much repeated or unused code each group removed:

1. **shrink:** Shared backend candidate parsing and Model validation diagnostics.
   Four authoring families now use the existing strict JSON parser and one
   diagnostic converter in `features/workflows/authoring/repair.py`. Dataset
   rules and user-facing failure behavior remain in their feature modules.
2. **shrink:** Shared frontend `DetailState`, `SelectField`, and `NumberField` in
   `shared/ui.tsx`; reused existing initials and Model route-ID helpers.
   Kept the same labels, markup, accessibility attributes, and input behavior.
   Similar-looking components with different behavior were left separate.
3. **delete:** Removed unused dimensional reconciliation partition merging and
   an unused Mapping schema compatibility helper. The active dimensional
   review-receipt validation and candidate materialization path remains intact.
4. **delete:** Removed unused `ModelObjectSelection`, its SQL count query, and
   its selection/audit helpers from MCP `application/model_read.py`. Checked
   imports, references, and actual read-tool paths first. Kept the live Model
   authorization query and input-scope validation.
5. **shrink:** Reused `workbench/core.js` normalization and stable serialization
   from the Node helper. Retained the existing Unicode implementation and
   digest format.
6. **stdlib:** Replaced notebook thread/result/error lists with
   `ThreadPoolExecutor.submit(...).result()`. Tests cover an existing event
   loop, a distinct worker thread, and original exceptions from both coroutine
   creation and execution, including cancellation.
7. **shrink:** Reused one closed-world MCP annotation function for Change Sets
   and Tenant Locks. Read-only, destructive, and idempotency hints remain the
   same.

| Production source | Net line change |
| --- | ---: |
| Backend | −205 |
| Frontend | −112 |
| MCP server | −71 |
| Node plugin helper | −19 |
| Notebook runtime | −18 |
| VS Code Stage runner | +1 |
| **Total** | **−424** |

## Stage chunk planning

Both the Node helper and extension previously copied the current chunk and
serialized the whole growing array for each record. They now serialize each
record once and count its UTF-8 bytes, commas, and array brackets. Record order,
chunk byte limits, record limits, and oversized-record rejection stay the same.

An old/new comparison covered **438 cases**, including Unicode, escaping,
exact byte boundaries, oversized records, empty input, and the record-count
boundary. Both implementations produced identical results. Extension batching
tests now run with ASCII, accented text, and emoji.

A local microbenchmark with 2,000 synthetic records and a 1 MiB chunk limit
fell from **597.35 ms to 1.11 ms**, using the median of three runs. This measures
only chunk planning, not network calls, server validation, or a complete Stage.

## Deliberately retained

- Explicit SQL constraints, authorization, locking, revision fencing,
  idempotency, and redaction. Their length represents enforced rules.
- Python/JavaScript/PowerShell validation where offline feedback and final
  server validation need separate implementations. Identical logic within one
  runtime was consolidated where a suitable shared helper already existed.
- PowerShell 5.1 fallback support. Removing it would remove Windows behavior.
- Distinct workflow executors and policies. Profiling, Analysis, Conceptual,
  Logical, Dimensional, Mapping, Code Generation, and Validation have different
  inputs and persistence rules; a generic base class would obscure those rules.
- Database/authentication/provider interfaces and resource-lifetime wrappers.
  A wrapper with one production implementation can still provide an important
  boundary for tests, transactions, or external I/O.
- Defensive copies of shared mutable schema/context data and Unicode tables.
- Existing provider SDKs and `aiohttp`, which is used by Azure's asynchronous
  transport even without a direct application import.

## Larger changes to review first

**Finish the existing MCP transport separation.** Change Set registration still
lives inside `application/change_sets/model.py` and `metadata.py`, with late MCP
imports. Their `tools/change_sets/` modules mostly re-export registration.
Move registration to those tool modules in a separate change, keeping the
application operations reusable. This follows ADR 005 and would make the shared
code easier to read. It was raised with the user and was not started here.

**Consider loading frontend routes on demand.** The production JavaScript entry
bundle is about 849 kB minified / 199 kB gzip and triggers Vite's size warning.
Route-level loading could reduce the first download, but needs deliberate
loading/error behavior and navigation checks. This was not included in the
duplicate-code cleanup.

No service merger, new shared deployment, ORM replacement, generic workflow
framework, or new dependency is recommended by this audit.

## Verification

| Check | Final result |
| --- | --- |
| MCP, backend, disposable PostgreSQL, plugin helpers, and packaging | **1,876 passed, 1 platform skip** in the final combined run |
| Notebook suite, Python 3.12 | **132 passed** |
| Frontend | **182 passed**; TypeScript checks and production build passed |
| VS Code extension | **45 passed**; TypeScript checks, bundle, and VSIX packaging passed |
| Workbench JavaScript | **44 passed** |
| Extracted notebook artifact probes, Python 3.12 | **3 passed** |
| MCP/backend/notebook Python lint, formatting, and types | Passed; no type errors |
| Updated CI workflow | YAML parsed; dependency/test step ordering checked |
| Final diff | No whitespace errors |

The full Python regression command and per-component commands are recorded in
[AGENTS.md](../../AGENTS.md). Python type checks used each project's interpreter;
notebook tests and extracted-artifact probes used Python 3.12.

The initial post-change regression run caught stale plugin ZIP and VSIX files.
Both were rebuilt from current source; packaging tests then passed. The updated
37-tool architecture description also required updating its old 35-tool test
assertion. No runtime test failure was hidden or skipped to accept these changes.

Windows PowerShell is unavailable on this machine; its execution test remains
a platform skip. Azure, Databricks, and a live VS Code extension host were not
executed. CI configuration was checked locally, not run on GitHub. Nothing was
pushed, published, deployed, or written to an external database.

**net: −424 production-source lines, 0 dependencies removed.**
