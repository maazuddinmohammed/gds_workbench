"""Applied Mapping templates reach Code and Validation under both runtime roles."""

from __future__ import annotations

# Disposable fixture helpers are shared intentionally.
# pyright: reportPrivateUsage=false
from collections.abc import Iterator
from typing import Any, cast

import pytest
from gds_etl_workbench.application.mapping_context import project_mapping_inputs
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    downstream_input_contracts,
)
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_mapping_output_template_seed import seed_mapping_output_templates
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope


@pytest.fixture
def template_context_database() -> Iterator[DisposablePostgres]:
    yield from disposable_postgres()


@pytest.mark.parametrize("dimensional", [False, True], ids=["logical", "dimensional"])
@pytest.mark.parametrize("custom", [False, True], ids=["default", "custom"])
def test_applied_mapping_documents_keep_their_exact_template_semantics(
    template_context_database: DisposablePostgres, dimensional: bool, custom: bool
) -> None:
    database = template_context_database
    scope = _seed_mapping_scope(database, dimensional=dimensional, create_run=False)
    seed_mapping_output_templates(database)
    entity_type = scope.plan.modeled_entity_type
    layer = "dimensional" if dimensional else "logical"
    entity_id = scope.plan.pair.modeled_entity_id
    object_document: dict[str, Any] = {
        "source_tables": [],
        "filter_criteria": "Customer is eligible.",
        "sample_query": "SELECT customer_id FROM customer WHERE eligible = true",
    }
    attribute_document: dict[str, Any] = {
        "source_columns": [{"attribute_name": "customer_id"}],
        "transformation_logic": "Copy the source customer identifier.",
        "default_record": None,
    }
    templates: dict[str, dict[str, Any]] = {}
    with database.connect_owner() as connection:
        actor = require_row(
            connection.execute(
                "SELECT entra_tenant_id, entra_object_id FROM security.entra_principal_identity "
                "JOIN security.principal USING (principal_id, principal_type) "
                "WHERE principal_display_name='Mapping template fixture administrator'"
            ).fetchone()
        )
        for kind in ("object", "attribute"):
            if custom:
                field = {
                    "output_template_field_name": "rule_id",
                    "output_template_field_description": "Source rule identity and its semantics.",
                    "output_template_field_data_type": "object",
                    "output_template_field_array_item_type": None,
                    "output_template_field_example": {"business_id": {"source_id": 42}},
                    "output_template_field_is_required": True,
                    "output_template_field_order": 1,
                }
                template = require_row(
                    connection.execute(
                        "SELECT * FROM application.create_output_template("
                        "%s,%s,'user',%s,%s,%s,%s,%s,%s)",
                        (
                            actor["entra_tenant_id"],
                            actor["entra_object_id"],
                            f"custom.{layer}.{kind}",
                            f"Custom {kind} template",
                            "Synthetic custom document semantics.",
                            f"mapping_{kind}",
                            Jsonb([field]),
                            entity_type,
                        ),
                    ).fetchone()
                )
            else:
                template = require_row(
                    connection.execute(
                        "SELECT * FROM application.output_template WHERE output_template_code=%s",
                        (f"mapping_{layer}_{kind}_default",),
                    ).fetchone()
                )
            templates[kind] = template

        if custom:
            object_document = {"rule_id": {"business_id": 42, "filter": "eligible"}}
            attribute_document = {"rule_id": {"source_id": 7, "expression": "customer_id"}}
        if dimensional:
            mapping_id = require_row(
                connection.execute(
                    "INSERT INTO workflow.mapping_object (model_id, modeled_entity_type, "
                    "dimensional_entity_id, source_system_id) "
                    "VALUES (%s,'dimensional_entity',%s,%s) RETURNING mapping_object_id",
                    (scope.plan.model_id, entity_id, scope.source_system_id),
                ).fetchone()
            )["mapping_object_id"]
            connection.execute(
                "INSERT INTO workflow.mapping_attribute (mapping_object_id,model_id,"
                "modeled_entity_type,dimensional_entity_id,dimensional_attribute_id) "
                "SELECT %s,model_id,'dimensional_entity',dimensional_entity_id,"
                "dimensional_attribute_id FROM workflow.dimensional_attribute "
                "WHERE model_id=%s AND dimensional_entity_id=%s",
                (mapping_id, scope.plan.model_id, entity_id),
            )
        else:
            mapping_id = require_row(
                connection.execute(
                    "SELECT mapping_object_id FROM workflow.mapping_object WHERE model_id=%s "
                    "AND logical_entity_id=%s AND source_system_id=%s",
                    (scope.plan.model_id, entity_id, scope.source_system_id),
                ).fetchone()
            )["mapping_object_id"]
        connection.execute(
            "UPDATE workflow.mapping_object SET output_template_id=%s, "
            "mapping_transformation_document=%s WHERE mapping_object_id=%s",
            (templates["object"]["output_template_id"], Jsonb(object_document), mapping_id),
        )
        connection.execute(
            "UPDATE workflow.mapping_attribute SET output_template_id=%s, "
            "attribute_mapping_transformation_document=%s WHERE mapping_object_id=%s",
            (templates["attribute"]["output_template_id"], Jsonb(attribute_document), mapping_id),
        )

    query = (
        "SELECT * FROM workflow.list_code_generation_target_context(%s,%s,NULL) "
        "WHERE modeled_entity_id=%s"
    )
    parameters = (scope.plan.model_id, entity_type, entity_id)
    with database.connect_runtime() as connection:
        first = require_row(connection.execute(query, parameters).fetchone())
        privileges = require_row(
            connection.execute(
                "SELECT has_table_privilege(current_user,'application.output_template_field',"
                "'SELECT') AS can_read, has_table_privilege(current_user,"
                "'application.output_template_field','INSERT,UPDATE,DELETE,TRUNCATE') AS can_write"
            ).fetchone()
        )
    assert privileges == {"can_read": True, "can_write": False}
    source = first["source_context"]
    assert source["consumer_context_version"] == "entity-3"
    assert (
        source["object_mappings"][0]["output_template_code"]
        == templates["object"]["output_template_code"]
    )
    assert (
        source["attribute_mappings"][0]["output_template_code"]
        == templates["attribute"]["output_template_code"]
    )
    assert source["object_mappings"][0]["transformation"] == object_document
    assert source["attribute_mappings"][0]["transformation"] == attribute_document
    definitions = source["mapping_templates"]
    assert len(definitions) == len({item["code"] for item in definitions}) == 2
    assert [item["code"] for item in definitions] == sorted(item["code"] for item in definitions)
    assert all(item["modeled_entity_type"] == entity_type for item in definitions)
    if custom:
        assert definitions[0]["fields"][0]["example"] == {"business_id": {"source_id": 42}}
    else:
        assert {
            item["target_type"]: [field["name"] for field in item["fields"]] for item in definitions
        } == {
            "mapping_object": ["source_tables", "filter_criteria", "sample_query"],
            "mapping_attribute": ["transformation_logic", "default_record", "source_columns"],
        }
    projected = project_mapping_inputs(source)
    assert projected["mapping_templates"] == definitions
    assert projected["object_transformations"][0]["transformation"] == object_document
    assert projected["attribute_transformations"][0]["transformation"] == attribute_document
    for name, value in projected.items():
        cast(Any, Draft202012Validator(downstream_input_contracts("code_generation")[name][0])).validate(
            value
        )
    cast(
        Any, Draft202012Validator(downstream_input_contracts("validation")["mapping_evidence"][0])
    ).validate(
        [
            {
                "modeled_entity_type": entity_type,
                "modeled_entity_schema_name": first["modeled_entity_schema_name"],
                "modeled_entity_name": first["modeled_entity_name"],
                "context": projected,
            }
        ]
    )

    # Metadata used to interpret a document participates in currentness checks;
    # deactivating its template must not discard its saved field definitions.
    with database.connect_owner() as connection:
        template = templates["object"]
        connection.execute(
            "SELECT * FROM application.update_output_template(%s,%s,'user',%s,%s,%s,FALSE,%s)",
            (
                actor["entra_tenant_id"],
                actor["entra_object_id"],
                template["output_template_id"],
                template["output_template_name"],
                "Revised saved template meaning.",
                template["updated_time"],
            ),
        )
    with database.connect_runtime() as connection:
        updated = require_row(connection.execute(query, parameters).fetchone())
    assert updated["code_input_digest"] != first["code_input_digest"]
    updated_definitions = updated["source_context"]["mapping_templates"]
    inactive = next(item for item in updated_definitions if item["target_type"] == "mapping_object")
    original = next(item for item in definitions if item["target_type"] == "mapping_object")
    assert inactive["is_active"] is False
    assert inactive["fields"] == original["fields"]
    assert updated["source_context"]["object_mappings"] == source["object_mappings"]
