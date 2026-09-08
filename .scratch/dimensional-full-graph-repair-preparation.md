# Dimensional repair preparation

Read-only production investigation. No provider/database calls. Four passing
witnesses: `.scratch/test_dimensional_full_graph_preparation.py`.

The fixture starts with a complete valid canonical Model, keeps its actual active
Logical Bindings and Mapping, and derives the selected Silver Object/Attributes
through that graph. It tests new unbound Dimensional records and an applied,
fully bound Dimensional Entity. Dimensional authoring itself cannot create or
change Bindings; those remain server-only dependencies.

| Reachable first response | Local validation | Before Gold projection | After projection | Stage able to fix |
| --- | --- | --- | --- | --- |
| Inactive Entity, active business Attributes; new or bound | Pass | Active dependency failure | Failure | Entity detail |
| Bound descriptor changes overwrite → historize | Pass | Valid | Three Type-2 Attributes lack Bindings | Entity detail, when evidence supports overwrite |
| 253-character Dimension name with `{entity_name} key` policy | Pass, including native detail | Valid records | Surrogate name exceeds 255; projection raises safe InvalidRequestError | Topology reconciler, then detail and downstream stages |

Detailed reconciliation receipts only author Relationships. Repeating receipts
cannot change Entity status, business Attribute change behavior, or Entity names.
Entity detail can change status and business Attributes while preserving the
exact physical source and assertion coverage; it must keep the topology Entity
name and the proposal-derived Entity type/fact type/grain. The topology reconciler
can rename Entities, but type/fact type/grain originate in topology-builder
proposals. This makes a universal detail-only retry insufficient.

Smallest boundary proven sufficient for the four witnesses: restart topology
reconciliation through lead review while retaining physical contributions. The
tests show shortening the topology name makes the native detail and projected
full graph valid. A general retry that also repairs proposal-owned type/grain
must restart topology builder, using the same frozen physical/assertion/applied
context and stage schemas. Avoid adding a stage-routing abstraction merely to skip these bounded
upstream calls. Rebuild detail partitions, relationship ledger, draft manifest,
receipts and worker packages after each authoring pass; never reuse a receipt
against a changed manifest. Share one configured full-pass retry counter with
worker blockers, instead of nesting another independent full retry loop around
the existing receipt retries.

One-shot/tool-assisted: attach a final-validation callback to the existing stage
runner. The callback must normalize, apply both Gold/foreign-key projections,
then validate the exact complete future graph and change-set bounds. Projection
errors caused by candidate names/attributes need bounded candidate diagnostics;
they currently escape before repair. Do not retry authentication, revision,
claim or finalization failures.

Detailed feedback belongs in immutable-context copies and prompt resolvers, with
request bytes reserved before partitioning. Include required bound Entity and
Attribute names and policy ownership in bounded read-only dependency context;
the author cannot repair Binding coverage from a generic error alone. Preserve
the last complete projected rejected changes across later malformed output for
governed retention. An oversize projected document still cannot bypass storage
bounds. A frozen policy change incompatible with existing locked/required physical
Bindings may require metadata review; retries must not invent Binding changes or
claim guaranteed repair.
