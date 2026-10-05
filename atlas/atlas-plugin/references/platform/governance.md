# Authoring and submission boundaries

Agents use Model records, never DBML. Direct DBML export requests to the user's Generate DBML action in Atlas Local Workbench; that export is not validation or approval evidence.


Before authoring in any workflow, read [record state](../record-state.md): locked records stay unchanged, unlocked records still require eligibility, and inactive/deprecated history is preserved. Workflow entry does not reset those protections.

1. Accumulate all changes needed for the current outcome in the local Change Set, using the effective result for further authoring. After each authored phase's local batch, follow [local validation](../local-validation.md) and repair failures before dependent work. A new task or local edit does not trigger submission or refresh.
2. When the complete related batch is ready, follow the shared [Change Set lifecycle](../change-set-lifecycle.md): local validation, Atlas Local Workbench review, runner staging, server validation and separate Apply approval. Transport may use several bounded requests; they still represent one logical Change Set.
3. After verified Apply, mark affected snapshots stale and install fresh applied context before dependent work. Preserve receipts/evidence and retire only pending records confirmed as applied.
4. Each downstream workflow states whether it can work from the local effective result or requires applied inputs. Complete and Apply upstream changes before a stage that requires them; do not mistake pending records for applied state.

Metadata and Model changes retain their separate governed Change Sets and ownership/revision boundaries. Local batching does not combine them into a single transaction. Starting another workflow does not silently publish unfinished work.
