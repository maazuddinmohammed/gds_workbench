"""Physical metadata reaches Code and invalidates stale Validation code context."""

# Reuse exact Mapping route fixtures and the production Validation ledger query.
# pyright: reportPrivateUsage=false

from typing import Any, LiteralString, cast

import pytest
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.validation.read_service import _CURRENT_CONTEXT_SQL
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    downstream_input_contracts,
    project_downstream_inputs,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from jsonschema import Draft202012Validator

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_code_generation_context import _plan
from tests.web_backend.test_database_mapping_source_context import (
    _load,
    _seed_mapping_scope,
)
from tests.web_backend.test_database_model_change_sets import _required_id


@pytest.mark.parametrize("dimensional", [False, True], ids=["logical", "dimensional"])
async def test_code_and_validation_track_physical_metadata_without_model_revision(
    web_postgres_database: DisposablePostgres,
    dimensional: bool,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=dimensional)
    if dimensional:
        with web_postgres_database.connect_owner() as connection:
            mapping_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.mapping_object (
                        model_id, model_object_binding_id, source_system_id,
                        mapping_transformation_document
                    ) SELECT model_id, model_object_binding_id, %s, '{}'::JSONB
                        FROM workflow.model_object_binding
                       WHERE model_id = %s AND object_id = %s
                    RETURNING mapping_object_id
                    """,
                    (
                        scope.source_system_id,
                        scope.plan.model_id,
                        scope.plan.pair.target_object_id,
                    ),
                ).fetchone(),
                "mapping_object_id",
            )
            connection.execute(
                """
                INSERT INTO workflow.mapping_attribute (
                    mapping_object_id, model_attribute_binding_id,
                    attribute_mapping_transformation_document
                ) SELECT %s, attribute.model_attribute_binding_id, '{}'::JSONB
                    FROM workflow.model_attribute_binding AS attribute
                    JOIN workflow.model_object_binding AS object
                      ON object.model_object_binding_id = attribute.model_object_binding_id
                   WHERE object.model_id = %s AND object.object_id = %s
                """,
                (mapping_id, scope.plan.model_id, scope.plan.pair.target_object_id),
            )
    mapping_context = await _load(web_postgres_database, scope)
    runtime = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await runtime.open()
    try:

        async def current() -> dict[str, Any]:
            async with runtime.read_transaction() as transaction:
                row = await transaction.fetch_one(
                    """
                    SELECT * FROM workflow.list_code_generation_target_context(%s, %s, NULL)
                     WHERE object_id = %s
                    """,
                    (
                        scope.plan.model_id,
                        scope.plan.modeled_entity_type,
                        scope.plan.pair.target_object_id,
                    ),
                )
                assert row is not None
                return row

        initial = await current()
        assert await current() == initial
        source_context = initial["source_context"]
        input_plan = _plan(selected_object_ids=(scope.plan.pair.target_object_id,))
        prefix = "workflow.code_generation.common.sql_generation.inputs."
        input_contracts = {
            name: contract
            for name, contract in downstream_input_contracts("code_generation").items()
            if name != "sql_generation_guide"
        }
        input_stage = input_plan.stages[0].model_copy(
            update={
                "variables": tuple(
                    PromptVariableDefinition(
                        name=name,
                        resolver_key=prefix + name,
                        data_type="text"
                        if input_contracts[name][0].get("type") == "string"
                        else "json",
                        is_required=False,
                    )
                    for name in input_contracts
                )
            }
        )
        for mode in (None,):
            runtime_plan = input_plan.model_copy(update={"workflow_execution_mode": mode})
            values = project_prompt_input_values(
                plan=runtime_plan,
                stage=input_stage,
                context={"targets": [{"target_ref": "target_1", "context": source_context}]},
                resolver_values={},
            )
            projected = project_downstream_inputs(
                "code_generation",
                {"targets": [{"target_ref": "target_1", "context": source_context}]},
            )
            assert values[prefix + "source_metadata"] == projected["source_metadata"]
            assert values[prefix + "target_metadata"] == projected["target_metadata"]
            assert "object_id" not in projected["target_metadata"]
            assert [row["object"]["object_name"] for row in projected["source_metadata"]] == [
                row["object"]["object_name"] for row in source_context["physical_sources"]
            ]
            for name in input_contracts:
                contract = get_prompt_input_contract(
                    model_workflow="code_generation",
                    workflow_execution_mode=runtime_plan.workflow_execution_mode,
                    stage_code="sql_generation",
                    resolver_key=prefix + name,
                )
                assert contract is not None
                validator = cast(Any, Draft202012Validator(contract.value_schema))
                assert validator.is_valid(contract.example)
                assert validator.is_valid(values[prefix + name])
        assert [item["object"]["object_id"] for item in source_context["physical_sources"]] == [
            item.object.object_id for item in mapping_context.sources
        ]
        assert [item["object"]["zone_code"] for item in source_context["physical_sources"]] == (
            ["silver"] if dimensional else ["bronze", "source"]
        )
        target = source_context["target"]
        physical_source = source_context["physical_sources"][0]["object"]
        assert target["tenant_id"] == scope.placement_tenant_id != scope.tenant_id
        assert target["source_tenant_id"] == scope.tenant_id
        assert target["tenant_catalog"] == f"shared_{scope.plan.model_id}"
        assert physical_source["tenant_id"] == scope.placement_tenant_id
        assert physical_source["source_tenant_id"] == scope.tenant_id
        for object_record in (target, physical_source):
            assert object_record["attributes"][0]["attribute_data_type"] == "bigint"
            assert object_record["attributes"][0]["attribute_inferred_data_type"] is None

        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                """
                INSERT INTO workflow.generated_code (
                    model_object_binding_id, artifact_name, artifact_type,
                    generated_code_content, code_input_digest
                ) SELECT model_object_binding_id, 'orders.sql', 'sql_file', 'SELECT 1', %s
                    FROM workflow.model_object_binding
                   WHERE model_id = %s AND object_id = %s
                """,
                (
                    initial["code_input_digest"],
                    scope.plan.model_id,
                    target["object_id"],
                ),
            )
            connection.execute(
                """
                INSERT INTO workflow.validation_group (
                    model_id, tenant_id, system_id, validation_group_name, mapping_context_digest
                ) VALUES (%s, %s, %s, 'Metadata freshness fixture', %s)
                """,
                (
                    scope.plan.model_id,
                    scope.tenant_id,
                    scope.source_system_id,
                    "a" * 64,
                ),
            )
        async with runtime.read_transaction() as transaction:
            validation_before = await transaction.fetch_all(
                _CURRENT_CONTEXT_SQL, (scope.tenant_id, scope.plan.model_id)
            )
        assert (
            len(
                next(row for row in validation_before if row["object_id"] == target["object_id"])[
                    "generated_code"
                ]
            )
            == 1
        )

        changes: tuple[tuple[LiteralString, str], ...] = (
            (
                "UPDATE core.attribute SET attribute_data_type = 'string' WHERE object_id = %s",
                "attribute_data_type",
            ),
            (
                "UPDATE core.attribute SET attribute_inferred_data_type = 'decimal(18,2)' "
                "WHERE object_id = %s",
                "attribute_inferred_data_type",
            ),
            (
                "UPDATE core.attribute SET attribute_description = 'Customer business identifier.' "
                "WHERE object_id = %s",
                "attribute_description",
            ),
            (
                "UPDATE core.object SET object_description = 'One customer per record.' "
                "WHERE object_id = %s",
                "object_description",
            ),
        )
        prior = initial
        for object_id in (physical_source["object_id"], target["object_id"]):
            for query, changed_field in changes:
                with web_postgres_database.connect_owner() as connection:
                    connection.execute(query, (object_id,))
                    assert connection.execute(
                        "SELECT model_revision FROM model.model WHERE model_id = %s",
                        (scope.plan.model_id,),
                    ).fetchone() == {"model_revision": 1}
                changed = await current()
                assert changed["code_input_digest"] != prior["code_input_digest"], changed_field
                assert await current() == changed
                prior = changed
        for object_record in (
            prior["source_context"]["target"],
            prior["source_context"]["physical_sources"][0]["object"],
        ):
            assert object_record["object_description"] == "One customer per record."
            attribute = object_record["attributes"][0]
            assert attribute["attribute_data_type"] == "string"
            assert attribute["attribute_inferred_data_type"] == "decimal(18,2)"
            assert attribute["attribute_description"] == "Customer business identifier."
        async with runtime.read_transaction() as transaction:
            validation_after = await transaction.fetch_all(
                _CURRENT_CONTEXT_SQL, (scope.tenant_id, scope.plan.model_id)
            )
        stale = next(row for row in validation_after if row["object_id"] == target["object_id"])
        assert stale["code_input_digest"] == prior["code_input_digest"]
        assert stale["generated_code"] == []

        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.object SET source_tenant_id = %s WHERE object_id = %s",
                (scope.placement_tenant_id, physical_source["object_id"]),
            )
        foreign = await current()
        assert foreign["code_input_digest"] != prior["code_input_digest"]
        assert physical_source["object_id"] not in {
            item["object"]["object_id"] for item in foreign["source_context"]["physical_sources"]
        }
        assert await current() == foreign
    finally:
        await runtime.close()
