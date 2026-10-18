"""Applied Validation must hash only the current Code used during authoring."""

# Existing builders and SQL readers operate only against disposable fixtures.
# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_workbench_api.features.validation.read_service import (
    _CURRENT_CONTEXT_SQL,
    _LEDGER_GROUPS_SQL,
    _assemble_ledger_groups,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.project_test_fixtures import complete_project_graph
from tests.mcp.test_database_project_change_set_round_trip import (
    _replace_codes,
    _seed_project_foundation,
)


@pytest.mark.parametrize("code_state", ["current", "all_stale", "mixed_layers"])
async def test_newly_applied_validation_is_current_even_when_old_code_is_stale(
    web_postgres_database: DisposablePostgres,
    code_state: str,
) -> None:
    fixture = web_postgres_database
    prefix = "VALIDATION_CURRENT_" + uuid4().hex
    project_id, tenant_id = _seed_project_foundation(fixture, code_prefix=prefix)
    graph = _replace_codes(complete_project_graph(), code_prefix=prefix)
    if code_state == "mixed_layers":
        dimensional_key = {
            "modeled_entity_type": "dimensional_entity",
            "modeled_entity_schema_name": "gold",
            "modeled_entity_name": "CustomerDimension",
        }
        graph["mapping_object"].append(
            {**graph["mapping_object"][0], **dimensional_key}
        )
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
    project = ProjectReadContext(
        project_id=project_id,
        tenant_id=tenant_id,
        project_name="Validation currentness",
        project_revision=1,
    )
    runtime = fixture.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            snapshot = await build_project_snapshot(transaction, project)
            physical = await load_project_physical_scope(transaction, project)
            authored = validate_future_graph(
                snapshot=snapshot, staged_documents=graph, physical_scope=physical
            )
            assert authored.valid
            await ProjectMaterializer(transaction, project_id, "a" * 64).apply(
                authored.records
            )
        if code_state != "current":
            with fixture.connect_owner() as connection:
                connection.execute(
                    "UPDATE workflow.generated_code SET code_input_digest=%s WHERE project_id=%s "
                    "AND modeled_entity_type='logical_entity'",
                    ("f" * 64, project_id),
                )
        async with runtime.write_transaction() as transaction:
            await ProjectMaterializer(transaction, project_id, "b" * 64).apply(
                {"validation_group": authored.records["validation_group"]}
            )
        async with runtime.read_transaction() as transaction:
            groups = await transaction.fetch_all(
                _LEDGER_GROUPS_SQL, (tenant_id, project_id)
            )
            contexts = await transaction.fetch_all(
                _CURRENT_CONTEXT_SQL, (tenant_id, project_id)
            )
        assert len(groups) == 1
        assert len(contexts) == (2 if code_state == "mixed_layers" else 1)
        for target in contexts:
            stale = (
                code_state != "current"
                and target["modeled_entity_type"] == "logical_entity"
            )
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
