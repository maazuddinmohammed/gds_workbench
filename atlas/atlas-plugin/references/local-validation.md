# Local validation

After each authored phase or coherent batch, validate the complete effective result: bound Snapshot plus all pending records overlaid by canonical key. Repeat affected checks after repairs. Phase completion requires structural checks and a review of meaning; it does not trigger Stage or Apply.

Workbench and `scripts/atlas-local.js` use the same [validation runner](../workbench/validation/run.js). The [validation index](../docs/validation-index.md) lists each rule family, code location, test and enforcement status. Reports say which checks ran, were skipped, need review or remain server-only.

## Structural checks

| Check | What is checked | Why |
|---|---|---|
| `local.schema` | Required fields, permitted nulls/values, nested shapes and published dataset constraints. | Plausible JSON can still be invalid. |
| `local.identity` | Complete unique canonical keys in Snapshot and pending files; exact registered physical references. | Similar names and aliases do not create real endpoints. |
| `local.state` | Applied locks, nested protection and activation dependencies under [record-state rules](record-state.md). | A valid field value does not permit changing protected content. |
| `local.scope` | Dataset-specific eligibility of new/changed references using physical Tenant/System/Connection/schema/Object/Attribute keys. | Visible historical records are not automatically eligible for new authoring. |
| `local.references` | Parent/child references, relationship endpoints, supports and assertions in the effective graph. | Prevent dangling, fabricated and inactive dependencies. |

For Model-derived Metadata spanning owners, validate each [owner root](workspace-contract.md#model-derived-metadata-owners) separately. Reports bind the owner, Snapshot and pending digest. Model validation combines all registered owners' **applied** Metadata baselines and rejects conflicting copies of the same physical record. Pending Metadata is not applied Model input. A missing registered owner Snapshot blocks substantive Model proposals; context-only validation reports the missing context as a warning.

Profiling, Analysis, Conceptual physical supports and Logical physical sources use active **applied Model Input Scope**. Dimensional sources, Bindings and Mapping use their own eligibility rules; Silver/Gold targets do not become Source/Bronze Input Scope Objects. Retain unchanged history and permitted lifecycle-only edits according to each dataset contract. Historical exceptions do not admit newly authored content.

Conceptual Relationships require real active endpoint Concepts. New active Assertion evidence must be active and applicable to its consuming layer. Intentionally independent/generated structures may have empty support/source arrays under the workflow rules; never invent support just to satisfy a checklist.

## Workflow-specific checks

| Area | Automated local checks | Still requires review |
|---|---|---|
| Logical / Dimensional | Matching parent Object lineage; active memberships; new-table first non-null BIGINT own surrogate; distinct ordinals; default PascalCase/ID/Key names; configured audit block; relationship endpoint type agreement. | Grain, normalization, natural identity, useful submodels and explicit naming overrides. See [Logical design](logical-build/logical-design.md), [Dimensional design](dimensional-build/design.md), [keys/audit](model/keys-and-audit.md). |
| Entity Binding | Actual eligible targets, unique assignments, active coverage, nested protection and unsupported-retarget rejection. | Ambiguous semantic matches and deployed-table existence. See [Binding](model/binding.md). |
| Mapping | Branch/Attribute coverage; default-template steps and transformation rules; real source identities, unique aliases and matching parent query inputs. | Conversion semantics, joins, filters, grain, natural keys, dependency order and complete standalone coding instructions. Custom templates need their own review. See [Mapping documents](model/mapping-documents.md#document-quality-checks). |
| Code | Record/branch references; finite SQL statement checks; declared temporary stages; two-part runtime physical inputs; explicit final projection without wildcard. | Exact Mapping fidelity, final names/types/order, generated-column exclusions and local-file/record equality. Static checks are not a complete SQL parser. See [SQL checks](code-generation/sql.md#local-content-checks). |
| Validation authoring | Record/operator/operand shapes; graph references; governed read-query form with three-part physical inputs; record protection. | Meaningful independent expectations, matched populations and restrained check selection. No local Change Set check executes SQL or establishes that business assertions passed. See [check design](validation/check-design.md#review-the-complete-local-batch). |

New-table policies preserve existing historical layouts. Explicit naming instructions produce a review finding instead of silently applying default casing. Missing audit template types/nullability produce a review finding; validators do not invent them. Exact SQL syntax, target framework behavior and business meaning remain outside finite local checks.

## Meaning and coverage

Confirm changes match the user's [update selection](working-method.md#existing-work-and-update-scope), including agreed dependents. Preserve unrelated/manual work and validate the full effective graph even for selected regeneration. Missing history does not prove an affected-item list is complete.

| Check | Review |
|---|---|
| `local.meaning` | Definitions, grain, cardinality and modeling reasons agree with available evidence; uncertainty stays explicit. |
| `local.evidence` | Inference differs from executed measurement; query/batch scope and retained note hashes remain bound. |
| `local.coverage` | Selected inputs and outputs are accounted for; exclusions, blocked work and unresolved candidates are visible. |

The shared quality module checks supplied decision/evidence references, consistency and coverage warnings. A separate decision file is optional: without one it reports `review_required`, and the agent reviews definitions, grain, relationship basis and task evidence. No extra Assertion or per-Entity sidecar is required merely to clear validation. Metadata-only relationship inference is allowed and labeled; measured claims need their actual counts/evidence. SQL is optional under policy, never an automatic prerequisite. Follow [query scope](query-scope.md) if SQL evidence is needed.

Deterministic record checks run without a decision file: Analysis measurements must be complete and their counts/result must reconcile; actual endpoints, applied scope, keys, locks and references still follow their structural contracts. Citation-specific checks need the chosen evidence basis: a cited Analysis must align with that relationship and support its declared cardinality, and cited notes/Assertions must exist and apply. Physical overlap alone does not establish that an Analysis describes the same business grain. With no explicit citation, review that choice; do not invent a link, require SQL, or create a decision file just to make validation pass.

## Implementation organization and review

| Code area | Responsibility |
|---|---|
| `validation/run.js` | Common browser/CLI assembly and explicit check coverage. |
| `validation/common.js` | Published schemas, canonical/unique keys, protection and overlay mechanics using `core.js`. |
| `validation/metadata.js` | Metadata references, ownership, table constraints and Object/Attribute locks. |
| `validation/model.js` | Model graph, scope, supports, relationships, Binding and dependent record contracts. |
| `validation/model-policy.js` | Key/audit/naming rules, parent lineage, membership, Binding retarget and default Mapping document structure. |
| `validation/sql.js` | Separate transformation and governed-validation SQL contracts; no execution. |
| `model-quality.js` | Bound decision/evidence checks and modeling-coverage warnings. |
| `workspace.js` / helper | Input files, hashes, evidence/report storage and concurrency checks. |
| `ui/validation.js` | Findings, coverage and navigation; no domain rules. |
| Backend/database | Authoritative authorization, validation and storage constraints. |

Keep cohesive rule families together. Pure validators return bounded structured findings; adapters own files and the UI displays results. Shared serialization remains compatible with the helper, extension and Python. Do not add one file per field or copy rule implementations into workflow/UI files.

Maintain the [code index](../docs/validation-index.md) as checks change: **rule ID, check/reason, code/function, layer, test, status**. Preserve coverage during refactors. Add meaningful valid/invalid cross-record tests, and distinguish automated checks from review guidance and server-only enforcement.

## Run and repair

1. From the installed plugin directory, run `node scripts/atlas-local.js validate --session <working-directory> --area metadata|model`. For another registered Metadata owner, add `--owner <verified-Tenant-id>`. The working directory contains `.atlas`; use `command-contract --command validate` for supported flags. Workbench's **Validate locally** uses the same runner.
2. Repair invalid records against real inputs. Never auto-unlock, reactivate, expand scope, rename an endpoint or fabricate evidence to clear an error. Preserve unaffected work.
3. Keep the report under `.atlas/tasks/<task>.evidence/`, with owner, Snapshot/draft hashes and retained evidence hashes. Content changes invalidate the result. Record concise remaining blockers in the task; failed required checks leave the phase incomplete.
4. Before submission, validate the complete batch again and follow the [Change Set lifecycle](change-set-lifecycle.md). The user reviews locally; server validation and separately approved Apply remain necessary.

DBML runs shared structural/policy checks over the complete effective Model but deliberately skips modeling-decision quality checks. Its report says so. A diagram export is neither full workflow completion nor approval.

## Optional decision evidence file

When detailed evidence binding is useful, use the validator's returned `quality.template` as the exact shape for `.atlas/tasks/<task>.evidence/modeling-decisions.json`. Fill only applicable decisions with concise reasoning and real evidence references; do not add pass flags or copy metric values into the template. Keep unchanged relevant decisions when updating it.

Evidence can name an existing Analysis/Assertion record by dataset and canonical key, or `{ "note": ".atlas/tasks/<task>.evidence/decision.md" }` for a retained business/metadata note. Referenced notes must exist, remain durable and contain no raw data or prompts. The helper binds their hashes. Assertions remain optional; a retained confirmed business note can explain append-only identity or a complete composite lookup. If a file is supplied, malformed/contradictory evidence is an error; deleting it is not a way to conceal a known unresolved modeling issue.
