# Foundry-only Run dialogs: bounded diff plan

Implemented after the authorized history checkpoint, 2026-09-05; frontend slice frozen.

Verification: `npm --prefix web_app/frontend run check` passed (232 tests, types, production build); scoped `git diff --check` passed. Browser QA used synthetic-only previews of the shared and Validation dialogs at desktop and 390px. Model changes updated compatible effort; Shift-Tab wrapped within each dialog; Escape restored trigger focus; narrow controls and scrolled footer remained reachable. Preview server stopped and tab closed. No backend/provider/SQL calls were made for browser QA.

## Contract assumption

Keep the current capability response and full `CreateWorkflowRunCommand.agent` payload shape in this UI slice unless root changes that backend contract first. The submitted SDK/provider are fixed `openai_agents_sdk` / `microsoft_foundry`; only Model and reasoning effort belong in agent form state. Turns/retries are resolved from a valid Model default, otherwise the capability default, and revalidated by the backend. Do not clamp stale out-of-range defaults to an arbitrary endpoint. Root should confirm this hidden-limit policy before implementation.

Existing stored Model defaults are preferences for new Runs. A removed SDK/provider or unsupported model/profile must not prevent choosing a compatible Foundry model. Frozen historical Run details are not changed.

## Exact files / changes

### `web_app/frontend/src/features/workflows/api.ts`

- Restrict shared selection helpers to the fixed SDK/provider pair. Require both pair registration and matching per-model execution profiles; a mixed old capability response must not reintroduce Databricks or LangChain.
- Simplify `listCompatibleExecutionModes` to take capabilities alone and return its currently supported mode order. Keep fixed workflow mode restrictions at the caller boundary.
- Simplify `findAgentExecutionProfile` to take model + mode and check the fixed SDK/provider internally.
- Simplify `resolveAgentProfileSelection` inputs to preferred mode, model code and effort. Keep the current deterministic fallback ordering: preferred supported mode first, then existing tool-assisted preference, then registry mode order. Within that mode, preferred eligible model first, then registry order; preferred supported effort first, then its profile order intersected with registered efforts.
- Reuse this profile resolution for fixed-mode `resolveDefaultAgent` with an explicit allowed-mode list containing only the effective mode. Fixed-mode resolution must return null rather than fall back to another mode. Do not keep duplicate SDK/provider traversal loops.
- `resolveDefaultAgent` still constructs the full command agent object and resolves hidden limits. Remove obsolete SDK/provider arguments from its default input. Backend remains authoritative.
- Preserve `default` versus `none` reasoning semantics. Visible copy may become “Model default” and “None”; never turn a valid explicit `none` into a missing setting.
- Keep Run read fields (`agent_sdk_code`, `agent_provider_code`, limits) for historical data. This is removal of choices, not removal of provenance.

### `features/workflows/WorkflowRunDialog.tsx`

- Covers Analysis inference, Conceptual, Logical, Dimensional and metadata enrichment. Remove `sdkCode`, `providerCode`, `maxTurns`, `validationRetryCount` form defaults, subscriptions, validation branches and synchronization effects.
- Remove the four widgets; retain Model and reasoning effort selects. Use the shared resolver for a non-null compatible submission agent; reject submit when current displayed model/effort no longer match an eligible profile.
- Preserve the existing normal execution mode selector. Enrichment stays exactly one-shot, without a mode selector. A capability list containing only tool-assisted models must leave enrichment unavailable, not switch its mode.
- Preserve all scope pagination/revision/max-200 enrichment checks, Batch rules, deterministic Analysis validation (`agent:null`) and create/start request shapes.
- Preserve `createAttempt` fingerprint/key reuse and the pending start’s exact Run ID/mode. Disable configuration controls once retrying an already-created Run so the form cannot suggest a changed model will affect that Run.

### `features/mapping/MappingRunDialog.tsx`

- Same removal of SDK/provider/turn/retry form state, validation and controls. Remove `NumberField` import after checking no remaining use.
- Keep Mapping execution mode, logical/dimensional target type, target, source System, build/extend, and optional Object/Attribute template fields unchanged.
- Resolve model/effort for the currently selected mode and submit the fixed provider/SDK with backend-approved limits.
- Preserve exact pending Run/mode for retry and all target/dependency revision checks.

### `features/code_generation/CodeGenerationRunDialog.tsx`

- Same form-state and widget deletion; remove unused `NumberField` import.
- Keep effective agent mode fixed Detailed coverage. Creation still sends `workflow_execution_mode:null`; do not change public Code Generation semantics or introduce a mode dropdown.
- Preserve selected/all-eligible target coverage, modeled layer, SQL guide choice, exact revision and queued Run retry.

### `features/validation/ValidationRunDialog.tsx`

- Replace `useMemo` of immutable Model defaults with model/effort selection state initialized from Model preferences and reconciled against the fixed Detailed coverage profile.
- Replace six “Internal agent profile” facts (including SDK/provider/limits) with two native selects using shared `SelectField` and clear loading/unavailable feedback. Remove the local `Fact` helper if no remaining references.
- Preserve fixed Detailed coverage and `workflow_execution_mode:null`, exact selected System codes, empty Object selection and existing system coverage validation.
- Keep portal/inert/focus/Escape handling and exact queued start retry. Disable the two selects while a request is pending or a created Run awaits retry.

### Styling

- Reuse `agent-run-grid`; it currently has three desktop columns, two at tablet, one at narrow widths. Add one reusable modifier for the two agent fields if the desktop gap is visually awkward; do not alter Mapping’s separate multi-field configuration grid.
- Remove `.validation-agent-profile .detail-fact-grid` rules only after the facts are gone and no matching consumers remain. No new palette, components, or animation required.

## Retry gap already present, separate decision

Mapping, Code Generation and Validation currently call `crypto.randomUUID()` on every create attempt. Unlike the shared dialog, they can duplicate a Run after an ambiguous create response. Their exact queued-Run start retry already works. Either add the same small fingerprint/ref mechanism while those submission functions are touched, with one regression per dialog, or schedule it as the immediate next small fix; do not regress the shared dialog’s existing guarantee.

## Test changes / acceptance

- `features/workflows/api.test.ts`: fixed-pair filtering against mixed legacy capabilities; removed defaults -> valid Foundry fallback; model change -> valid effort fallback; explicit none retained; mode preference stable; fixed-mode missing profile -> null; invalid hidden defaults -> capability defaults; no compatible deployment -> null.
- `AnalysisScreen.test.tsx`: mode/model/effort interaction, no four removed controls, two distinct Foundry models, obsolete Model defaults, exact submitted selection; deterministic Analysis validation still sends no agent.
- Existing Conceptual/Logical/Dimensional/Mapping/Code/Validation/enrichment test fixtures: selectable profiles use real `openai_agents_sdk` / `microsoft_foundry` codes. Preserve at least one legacy Model-default fixture and historical Run provider fixture intentionally; do not globally replace historical provenance strings.
- Mapping and Code tests: only model/effort AI controls, correct hidden fields, fixed/variable modes, selection changed before submit reflected exactly; queued start retry does not create another Run.
- Validation tests: model/effort now editable, unavailable mode disables create, selected Systems unchanged, no SDK/provider/turn/retry facts, portal keyboard focus remains contained/restored.
- Enrichment tests: one-shot only, removed-profile defaults fallback, scope bounds unchanged, stable create idempotency and exact start endpoint preserved.
- Run all frontend tests/types/build. Browser QA at desktop and 390px: two readable selects, no empty option after stale defaults, no horizontal modal overflow, keyboard ordering/Escape/return focus; verify one shared dialog and Validation’s separate portal implementation.

Implemented scope includes stable create fingerprint/ref retries for Mapping, Code Generation and Validation, with network/server regressions for each. No consumption UI added.
