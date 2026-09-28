"""Applied Validation must hash only the current Code used during authoring."""

# Existing builders and SQL readers operate only against disposable fixtures.
# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_workbench_api.features.validation.read_service import (
    _CURRENT_CONTEXT_SQL,
    _LEDGER_GROUPS_SQL,
    _assemble_ledger_groups,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    _replace_codes,
    _seed_model_foundation,
)


@pytest.mark.parametrize("code_state", ["current", "all_stale", "mixed_layers"])
async def test_newly_applied_validation_is_current_even_when_old_code_is_stale(
    web_postgres_database: DisposablePostgres,
    code_state: str,
) -> None:
    fixture = web_postgres_database
    prefix = "VALIDATION_CURRENT_" + uuid4().hex
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    graph = _replace_codes(complete_model_graph(), code_prefix=prefix)
    if code_state == "mixed_layers":
        dimensional_key = {
            "modeled_entity_type": "dimensional_entity",
            "modeled_entity_schema_name": "gold",
            "modeled_entity_name": "CustomerDimension",
        }
        graph["mapping_object"].append({**graph["mapping_object"][0], **dimensional_key})
        graph["mapping_attribute"].append(
            {
                **graph["mapping_attribute"][0],
                **dimensional_key,
                "modeled_attribute_name": "CustomerKey",
            }
        )
        for dataset in ("generated_code", "generated_code_source_system"):
            graph[dataset].append(
                {
                    **graph[dataset][0],
                    **dimensional_key,
                    "artifact_name": "CustomerDimension.sql",
                }
            )
    model = ModelReadContext(
        model_id=model_id,
        tenant_id=tenant_id,
        model_name="Validation currentness",
        model_revision=1,
    )
    runtime = fixture.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            snapshot = await build_model_snapshot(transaction, model)
            physical = await load_model_physical_scope(transaction, model)
            authored = validate_future_graph(
                snapshot=snapshot, staged_documents=graph, physical_scope=physical
            )
            assert authored.valid
            await ModelMaterializer(transaction, model_id, "a" * 64).apply(authored.records)
        if code_state != "current":
            with fixture.connect_owner() as connection:
                connection.execute(
                    "UPDATE workflow.generated_code SET code_input_digest=%s WHERE model_id=%s "
                    "AND modeled_entity_type='logical_entity'",
                    ("f" * 64, model_id),
                )
        async with runtime.write_transaction() as transaction:
            await ModelMaterializer(transaction, model_id, "b" * 64).apply(
                {"validation_group": authored.records["validation_group"]}
            )
        async with runtime.read_transaction() as transaction:
            groups = await transaction.fetch_all(_LEDGER_GROUPS_SQL, (tenant_id, model_id))
            contexts = await transaction.fetch_all(_CURRENT_CONTEXT_SQL, (tenant_id, model_id))
        assert len(groups) == 1
        assert len(contexts) == (2 if code_state == "mixed_layers" else 1)
        for target in contexts:
            stale = code_state != "current" and target["modeled_entity_type"] == "logical_entity"
            assert bool(target["generated_code"]) is not stale
        ledger = _assemble_ledger_groups(
            group_rows=groups, check_rows=[], context_rows=contexts
        )
        assert ledger[0].mapping_context_is_current
        assert ledger[0].code_context_is_current
        assert ledger[0].validation_group_is_current
        assert (groups[0]["code_context_digest"] is None) is (code_state == "all_stale")
    finally:
        await runtime.close()
