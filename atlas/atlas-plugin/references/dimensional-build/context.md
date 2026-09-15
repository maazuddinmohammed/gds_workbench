# Dimensional build context

Shared entry for Guided and Grill Me. Each skill owns its sequence; [dimensional design](design.md) owns modeling decisions and [Dimensional records](../model/dimensional.md) owns payloads and eligibility.

1. Follow the [working method](../working-method.md). Reuse Tenant, working directory, Model, SQL policy/environment and selected build skill. Resolve only missing inputs. Dimensional Build is optional; its presence does not force every Logical Entity into Gold.
2. Inspect the existing session, unfinished work and Snapshot identities. Reuse prior resume/freshness choices; otherwise resolve resume versus new work and fresh versus existing snapshots. Follow [Model](../snapshots/model.md) and [Metadata](../snapshots/metadata.md) reading/reconciliation rules. Never replace a baseline beneath pending edits.
3. Require applied Logical Mapping and eligible active Silver contributions for source-derived design. Resolve their Logical meanings, target Bindings, physical Objects/Attributes and source lineage. The Dimensional catalog has no blanket applied-section requirement; this workflow prerequisite is stricter than generic effective-graph acceptance. Do not treat arbitrary visible Silver tables or Source/Bronze Input Scope as eligible Dimensional sources.
4. Reuse existing descriptions, types, analysis and business rules. Investigate only material gaps; no mandatory new Profiling, Analysis or Conceptual phase. Silver definitions come from applied Logical context. Fix the actual upstream record through its owning workflow when needed; do not silently edit Logical/Metadata records here or invent a Silver profiling dataset. SQL evidence uses [query scope](../query-scope.md).
5. Inspect existing Dimensional records and resolve [existing work and update scope](../working-method.md#existing-work-and-update-scope). Identify affected business processes, shared dimensions and protected work. Follow [record state](../record-state.md), [naming](../model/naming.md) and [keys/audit](../model/keys-and-audit.md); reuse agreed defaults without asking again. Resolve missing template types/nullability before finalizing affected Attributes.
6. Resolve the analytical outcome from the user's request and evidence. Ask only if missing: "Which business process and questions should this model support?" Offer concrete possibilities from the eligible inputs. A department name or one report layout does not itself define a fact grain. For dimension-only work, resolve its intended use and member/version grain; do not require an invented fact or unrelated applied source.
7. Connect the resolved directory in the already open Workbench. Use the existing task for decisions, coverage and unresolved questions; no new bus-matrix dataset, interview transcript or handoff ledger is required.

## Switching build skills

Switching Guided/Grill Me preserves session context, evidence, snapshots and pending records. Load only the destination skill; reassess its next useful step from existing work. Switching does not discard a model, repeat profiling or trigger Stage/Apply.

## Downstream boundary

Accumulate the related Dimensional batch locally. After complete review and governed Apply, refresh context before requested Gold registration/Binding/Mapping. Discussing a history requirement does not establish runtime support; use [history and lookup rules](history.md) to keep missing consumer behavior explicit.
