# Confirmed first-apply dependency ordering defect

Read-only production review, 2026-09-05. Reproduction:
`.scratch/test_model_materializer_order_reproduction.py`: **2 passed** using only
fixture-created disposable PostgreSQL and synthetic canonical records. Assertions
describe the current bug; promote corrected expectations after the fix.

A minimal graph has one Source Object, one Logical Entity with two Attributes,
one Dimensional Entity with two Attributes, Silver and Gold Object/Attribute
bindings, and one upstream Logical Mapping with full Attribute coverage. It
contains no generated code, validation checks, profiling, Analysis or assertions.

Evidence:

1. `validate_future_graph` accepts the complete graph against the empty Model.
2. Current `ModelMaterializer.apply` fails on PostgreSQL constraint
   `fk_dimensional_entity_source_binding`. SQL09's immediate composite FK requires
   `(model_id, source_object_id)` to exist in `workflow.model_object_binding`.
3. Earlier Logical and Model Scope inserts roll back; snapshot equals baseline.
4. Real in-process MCP create -> stage -> validate returns `valid=true`, phase
   `complete`; Apply fails. Durable draft remains `validated`; Model revision
   remains 1, with no partial Logical rows or bindings.
5. In the same fixture, explicitly ordering the existing production per-layer
   methods succeeds without changing constraints or canonical data. Both binding
   layers, Dimensional Object/Attribute sources and upstream Mapping survive a
   snapshot round trip; full graph validation succeeds afterward.

Root cause: `model_apply.py:1093–1101` applies Logical, then Dimensional, then all
Object/Attribute bindings. The first Dimensional physical source is inserted
before its new Logical Silver binding. Existing bindings or assertion-only
Dimensional sources hide the defect, explaining the prior all-dataset fixture.

Smallest production correction, one cohesive subsequent checkpoint:

- In `ModelMaterializer.apply`, preserve all earlier and later phases.
- Apply Logical records, then the selected Logical Object bindings, then Logical
  Attribute bindings. Apply Dimensional records next, followed by its Object and
  Attribute bindings. Keep Mapping after both binding phases, then generated
  code and validation as today.
- Partition existing canonical binding tuples by `modeled_entity_type`, using
  the existing `_as`/typed record checks. No generic dependency scheduler, new
  persistence boundary, repeated full Apply, synthetic records or deferred FK.
- Do not simply move all bindings before Dimensional: newly staged Gold bindings
  reference Dimensional entities/attributes that do not exist until that phase.
- Count every staged binding exactly once and preserve same transaction/digests/
  ownership/revision locking. No SQL schema change is needed.

Regression gate after authorization:

- Promote minimal case into `tests/mcp/test_database_model_change_set_round_trip.py`
  or one dedicated materialization test module. Expect actual public Apply to
  succeed once, advance revision once, retain both binding layers, and produce
  the same validated complete snapshot.
- Preserve the fixture's newly introduced Gold bindings and physical Attribute
  sources: these catch moving the entire binding block too early.
- Run prior all-dataset MCP round trip, physical history tests, Model materializer
  mapping-policy/provenance tests, and web shared validated-draft Apply tests.
- Missing active Logical Mapping or missing source Attribute contribution must
  still fail canonical validation. No fake success or invariant relaxation.

Run (captured DB output hidden):

`PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m pytest -c web_app/backend/pyproject.toml -p tests.mcp.conftest .scratch/test_model_materializer_order_reproduction.py --tb=no --show-capture=no -q`

No production code, populated database, external provider, Databricks, or deployment
was changed. Separate safe diagnostic helper prints only exception type/source
line and canonical error codes; never raw rows, candidates, SQL errors or DSNs.
