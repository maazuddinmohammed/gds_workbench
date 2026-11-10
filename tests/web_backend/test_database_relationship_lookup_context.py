"""A modeled parent is eligible before its own Mapping is authored."""

# Shared seeds create only fixture-owned disposable databases.
# pyright: reportPrivateUsage=false

from typing import Any, cast

import pytest
from atlas_mcp.application.mapping_context import project_mapping_inputs
from atlas_platform.database import WebPostgresDatabase
from atlas_platform.features.mapping.preparation_contracts import MappingModeledEntity
from atlas_platform.features.workflows.authoring.downstream_contracts import CONTRACTS
from atlas_platform.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
)
from jsonschema import Draft202012Validator
from psycopg import sql

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_mapping_source_context import (
    _load,
    _seed_mapping_scope,
)
from tests.web_backend.test_database_project_change_sets import _required_id


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize("parent_mapping", ["none", "other_system"])
async def test_relationship_parent_is_available_without_same_system_mapping(
    web_postgres_database: DisposablePostgres, layer: str, parent_mapping: str
) -> None:
    scope = _seed_mapping_scope(
        web_postgres_database, dimensional=layer == "dimensional"
    )
    project_id = scope.plan.project_id
    target_id = scope.plan.pair.modeled_entity_id
    entity_type = f"{layer}_entity"
    schema = "silver" if layer == "logical" else "gold"
    parent_ids: dict[str, int] = {}
    with web_postgres_database.connect_owner() as connection:
        reference_system_id = _required_id(
            connection.execute(
                "INSERT INTO core.system (system_code,system_name,system_type_id) "
                "SELECT %s,'Reference directory',system_type_id FROM core.system "
                "WHERE system_id=%s RETURNING system_id",
                (f"REFERENCE_{project_id}", scope.source_system_id),
            ).fetchone(),
            "system_id",
        )
        for name in ("CustomerDirectory", "UnrelatedDirectory"):
            parent_ids[name] = _required_id(
                connection.execute(
                    sql.SQL(
                        "INSERT INTO workflow.{entity} (project_id,{schema},{name},"
                        "{definition},{kind},{grain}) VALUES (%s,%s,%s,'One customer per source "
                        "System and source customer number.',%s,'SourceSystemID and "
                        "SourceCustomerID.') RETURNING {id} AS id"
                    ).format(
                        entity=sql.Identifier(entity_type),
                        schema=sql.Identifier(f"{layer}_entity_schema_name"),
                        name=sql.Identifier(f"{layer}_entity_name"),
                        definition=sql.Identifier(f"{layer}_entity_definition"),
                        kind=sql.Identifier(f"{layer}_entity_type"),
                        grain=sql.Identifier(
                            "logical_entity_grain"
                            if layer == "logical"
                            else "dimensional_entity_grain_definition"
                        ),
                        id=sql.Identifier(f"{layer}_entity_id"),
                    ),
                    (
                        project_id,
                        schema,
                        name,
                        "core" if layer == "logical" else "dimension",
                    ),
                ).fetchone(),
                "id",
            )
        parent_id = parent_ids["CustomerDirectory"]
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.{source_mapping} (project_id,{entity_id},{source_id}) "
                "VALUES (%s,%s,%s)"
            ).format(
                source_mapping=sql.Identifier(f"{layer}_entity_source_mapping"),
                entity_id=sql.Identifier(f"{layer}_entity_id"),
                source_id=sql.Identifier(
                    "source_object_id"
                    if layer == "logical"
                    else "source_logical_entity_id"
                ),
            ),
            (
                project_id,
                parent_id,
                scope.source_object_id
                if layer == "logical"
                else scope.logical_entity_id,
            ),
        )
        attribute_ids: dict[str, int] = {}
        for entity_id, name, ordinal, natural, surrogate, audit in (
            (parent_id, "CustomerID", 1, False, True, False),
            (parent_id, "SourceCustomerID", 2, True, False, False),
            (parent_id, "SourceSystemID", 3, False, False, True),
            (target_id, "DirectoryCustomerID", 100, False, False, False),
        ):
            attribute_ids[name] = _required_id(
                connection.execute(
                    sql.SQL(
                        "INSERT INTO workflow.{attribute} (project_id,{entity_id},{name},"
                        "{definition},{dtype},{ordinal},{natural},{surrogate},{audit},{nullable}) "
                        "VALUES (%s,%s,%s,%s,'bigint',%s,%s,%s,%s,FALSE) RETURNING {id} AS id"
                    ).format(
                        attribute=sql.Identifier(f"{layer}_attribute"),
                        entity_id=sql.Identifier(f"{layer}_entity_id"),
                        name=sql.Identifier(f"{layer}_attribute_name"),
                        definition=sql.Identifier(f"{layer}_attribute_definition"),
                        dtype=sql.Identifier(f"{layer}_attribute_data_type"),
                        ordinal=sql.Identifier(f"{layer}_attribute_ordinal_position"),
                        natural=sql.Identifier(f"{layer}_attribute_is_natural_key"),
                        surrogate=sql.Identifier(f"{layer}_attribute_is_surrogate_key"),
                        audit=sql.Identifier(f"{layer}_attribute_is_audit_column"),
                        nullable=sql.Identifier(f"{layer}_attribute_is_nullable"),
                        id=sql.Identifier(f"{layer}_attribute_id"),
                    ),
                    (
                        project_id,
                        entity_id,
                        name,
                        name,
                        ordinal,
                        natural,
                        surrogate,
                        audit,
                    ),
                ).fetchone(),
                "id",
            )
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.{relationship} (project_id,{child},{child_attr},"
                "{parent},{parent_attr},{basis}) VALUES (%s,%s,%s,%s,%s,%s)"
            ).format(
                relationship=sql.Identifier(f"{layer}_relationship"),
                child=sql.Identifier(f"{layer}_relationship_from_entity_id"),
                child_attr=sql.Identifier(f"{layer}_relationship_from_attribute_id"),
                parent=sql.Identifier(f"{layer}_relationship_to_entity_id"),
                parent_attr=sql.Identifier(f"{layer}_relationship_to_attribute_id"),
                basis=sql.Identifier(f"{layer}_relationship_basis"),
            ),
            (
                project_id,
                target_id,
                attribute_ids["DirectoryCustomerID"],
                parent_id,
                attribute_ids["CustomerID"],
                "Resolve the customer number in its documented source System namespace.",
            ),
        )
        for entity_id, system_id in (
            (target_id, scope.source_system_id),
            *(
                ((parent_id, reference_system_id),)
                if parent_mapping == "other_system"
                else ()
            ),
        ):
            connection.execute(
                sql.SQL(
                    "INSERT INTO workflow.mapping_object (project_id,modeled_entity_type,"
                    "{entity_id},source_system_id,mapping_transformation_document) "
                    "VALUES (%s,%s,%s,%s,'{{}}'::JSONB) ON CONFLICT DO NOTHING"
                ).format(entity_id=sql.Identifier(f"{layer}_entity_id")),
                (project_id, entity_type, entity_id, system_id),
            )

    context = await _load(web_postgres_database, scope)
    peers = {
        source.object.entity_name: source.object
        for source in context.sources
        if source.role == "lookup" and isinstance(source.object, MappingModeledEntity)
    }
    assert set(peers) == {"CustomerDirectory"}
    attributes = {
        item.attribute_name: item for item in peers["CustomerDirectory"].attributes
    }
    assert attributes["CustomerID"].is_surrogate_key
    assert attributes["SourceCustomerID"].is_natural_key
    assert attributes["SourceSystemID"].is_audit_column

    runtime = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await runtime.open()
    try:
        async with runtime.read_transaction() as transaction:
            row = await transaction.fetch_one(
                "SELECT source_context,code_input_digest,source_system_count "
                "FROM workflow.list_code_generation_target_context("
                "%s,%s,NULL) WHERE modeled_entity_id=%s",
                (project_id, entity_type, target_id),
            )
        assert row is not None
        projected = project_mapping_inputs(
            row["source_context"], workflow="code_generation"
        )
        lookup_source: dict[str, Any] = next(
            source
            for source in projected["source_metadata"]
            if source["role"] == "lookup"
        )
        lookup = lookup_source["object"]
        assert lookup["object_name"] == "CustomerDirectory"
        columns = {item["attribute_name"]: item for item in lookup["attributes"]}
        assert columns["CustomerID"]["is_surrogate_key"]
        assert columns["SourceCustomerID"]["is_natural_key"]
        assert columns["SourceSystemID"]["is_meta_data"]
        bindings = lookup_source["source_system_bindings"]
        target_system = row["source_context"]["source_systems"][0]["system_code"]
        expected_codes = {target_system}
        if parent_mapping == "other_system":
            expected_codes.add(f"REFERENCE_{project_id}")
        assert {item["system_code"] for item in bindings} == expected_codes
        assert all("source_system_value" not in item for item in bindings)
        assert row["source_system_count"] == len(projected["source_systems"]) == 1
        assert projected["source_systems"][0]["system_code"] == target_system
        assert "source_system_value" not in projected["source_systems"][0]
        validator = cast(
            Any,
            Draft202012Validator(
                CONTRACTS["code_generation"]["source_metadata"]["value_schema"]
            ),
        )
        validator.validate(projected["source_metadata"])
        validation_inputs = project_mapping_inputs(
            row["source_context"], workflow="validation"
        )
        validation_schema = cast(
            Any,
            Draft202012Validator(
                CONTRACTS["validation"]["mapping_evidence"]["value_schema"]
            ),
        )
        validation_schema.validate(
            [
                {
                    "modeled_entity_type": entity_type,
                    "modeled_entity_schema_name": validation_inputs["target_metadata"][
                        "object_schema"
                    ],
                    "modeled_entity_name": validation_inputs["target_metadata"][
                        "object_name"
                    ],
                    "context": validation_inputs,
                }
            ]
        )
        reader = build_downstream_readers(
            "code_generation",
            projected,
            max_result_bytes=None,
            max_page_records=200,
            max_cumulative_result_bytes=None,
        )
        directory_parent = next(
            item
            for item in reader.invoke("get_code_sources", {"directory_only": True})[
                "items"
            ]
            if item["role"] == "lookup"
        )
        assert directory_parent["object"]["attributes"] == []
        assert directory_parent["source_system_bindings"] == bindings
        assert (
            reader.invoke("get_code_source_systems", {})["items"]
            == projected["source_systems"]
        )
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.system SET system_name='Renamed reference directory' "
                "WHERE system_id=%s",
                (reference_system_id,),
            )
        async with runtime.read_transaction() as transaction:
            changed = await transaction.fetch_one(
                "SELECT source_context,code_input_digest FROM "
                "workflow.list_code_generation_target_context(%s,%s,NULL) "
                "WHERE modeled_entity_id=%s",
                (project_id, entity_type, target_id),
            )
        assert changed is not None
        if parent_mapping == "other_system":
            assert changed["code_input_digest"] != row["code_input_digest"]
            updated_sources = project_mapping_inputs(
                changed["source_context"], workflow="validation"
            )
            changed_lookup = next(
                item
                for item in updated_sources["source_metadata"]
                if item["role"] == "lookup"
            )
            assert (
                next(
                    binding
                    for binding in changed_lookup["source_system_bindings"]
                    if binding["source_system_value"] == reference_system_id
                )["system_name"]
                == "Renamed reference directory"
            )
        else:
            # The registered but unrelated System is not context or digest input.
            assert changed["code_input_digest"] == row["code_input_digest"]
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.system SET is_active=FALSE WHERE system_id=%s",
                (reference_system_id,),
            )
        async with runtime.read_transaction() as transaction:
            retired = await transaction.fetch_one(
                "SELECT source_context,source_system_count FROM "
                "workflow.list_code_generation_target_context(%s,%s,NULL) "
                "WHERE modeled_entity_id=%s",
                (project_id, entity_type, target_id),
            )
        assert retired is not None and retired["source_system_count"] == 1
        retired_inputs = project_mapping_inputs(
            retired["source_context"], workflow="code_generation"
        )
        retired_parent = next(
            item
            for item in retired_inputs["source_metadata"]
            if item["role"] == "lookup"
        )
        assert {
            binding["system_code"]
            for binding in retired_parent["source_system_bindings"]
        } == {target_system}
    finally:
        await runtime.close()
