# Dimensional build context

Shared inputs for either interaction mode. The dimensional skill owns its sequence; [dimensional design](design.md) owns modeling decisions and [Dimensional records](../project/dimensional.md) owns payloads and eligibility.

1. Follow the [working method](../working-method.md). Reuse Tenant, working directory, Project, SQL policy/environment and selected build skill. Resolve only missing inputs. Dimensional Build is optional; its presence does not force every Logical Entity into Gold.
2. Inspect the existing session, unfinished work and Snapshot identities. Follow clear intent; ask about resuming only when it is ambiguous. Reuse valid bound inputs, fetch missing inputs and reconcile required refreshes before dependent work. Follow [Project](../snapshots/project.md) and [Metadata](../snapshots/metadata.md) reading/reconciliation rules. Never replace a baseline beneath pending edits.
3. Require active applied Logical Entities and Attributes. Resolve schema-qualified Logical identities and supporting lineage; Dimensional design does not require physical Silver registration or applied Logical Mapping. Mapping readiness is checked separately before Mapping and Code generation. When the user names a Subject Area, [build that area](design.md#build-one-subject-area-at-a-time): the active Logical Entities with an active Object source among its member Objects, the Dimensional Entities already built from them and their neighbours.
4. Reuse existing descriptions, types, analysis and business rules, including Context records whose type is routed to `dimensional` (see [Context](../project/context.md)). Investigate only material gaps; no mandatory new Profiling or Analysis. Subject Areas only choose which Logical Entities to read; they are never evidence. Silver definitions come from applied Logical context. Fix the actual upstream record through its owning workflow when needed; do not silently edit Logical/Metadata records here or invent a Silver profiling dataset. SQL evidence uses [query scope](../query-scope.md).
5. Inspect existing Dimensional records and resolve [existing work and update scope](../methods/change-impact.md). Identify affected business processes, shared dimensions and protected work. Follow [record state](../record-state.md), [naming](../project/naming.md) and [keys/audit](../project/keys-and-audit.md); reuse agreed defaults without asking again. Resolve missing template types/nullability before finalizing affected Attributes.
6. Resolve the analytical outcome from the user's request and evidence. Ask only if missing: "Which business process and questions should this project support?" Offer concrete possibilities from the eligible inputs. A department name or one report layout does not itself define a fact grain. For dimension-only work, resolve its intended use and member/version grain; do not require an invented fact or unrelated applied source.
7. Open/reuse Atlas Local Workbench when authoring or review needs it and connect the resolved directory. Use the existing task for decisions, coverage and unresolved questions; no new bus-matrix dataset, interview transcript or handoff ledger is required.

Entity schemas must come from the Project's configured `dimensional_schemas`. Resolve an empty or conflicting configuration before generation. Use [Entity ownership](../project/entity-ownership.md) for schema-qualified identities.

## Switching build skills

Switching Guided/Grill Me preserves session context, evidence, snapshots and pending records. Keep the same skill and task; load interview guidance only when needed and assess the next useful step from existing work. Switching does not discard a project, repeat profiling or trigger Stage/Apply.

## Downstream boundary

Accumulate the related Dimensional batch locally. After complete review and governed Apply, refresh context before requested Mapping and optional later Gold registration. Discussing a history requirement does not establish runtime support; use [history and lookup rules](history.md) to keep missing consumer behavior explicit.
