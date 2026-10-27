"""Code context carries only Context routed to Code Generation or Validation."""

# Shared disposable fixture seed helpers are intentionally imported.
# pyright: reportPrivateUsage=false

from typing import Any
from uuid import uuid4

from gds_etl_workbench.application.mapping_context import project_mapping_inputs
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope


def test_code_context_keeps_each_prompts_routed_context_types(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False, create_run=False)
    project_id = scope.plan.project_id
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE workflow.mapping_object SET mapping_transformation_document = %s "
            "WHERE project_id = %s AND logical_entity_id = %s",
            (Jsonb({"steps": ["Read orders."]}), project_id, scope.logical_entity_id),
        )
        connection.execute(
            "UPDATE workflow.mapping_attribute SET attribute_mapping_transformation_document = %s "
            "WHERE project_id = %s AND logical_entity_id = %s",
            (Jsonb({"transformation": "customer_id"}), project_id, scope.logical_entity_id),
        )
        # One project-wide record per Type; Business Requirement goes to neither prompt.
        for type_name in ("Code Context", "Validation Criterion", "Business Requirement"):
            group_id = require_row(
                connection.execute(
                    "INSERT INTO project.context_group (project_id, name, context_type_id) "
                    "SELECT %s, %s, context_type_id FROM reference.context_type WHERE name = %s "
                    "RETURNING context_group_id",
                    (project_id, f"{type_name} notes", type_name),
                ).fetchone()
            )["context_group_id"]
            connection.execute(
                "INSERT INTO project.context_record "
                "(project_id, context_group_id, context_record_id, context_text) "
                "VALUES (%s, %s, %s::UUID, %s)",
                (project_id, group_id, str(uuid4()), f"{type_name} guidance."),
            )
        context = require_row(
            connection.execute(
                "SELECT source_context FROM workflow.list_code_generation_target_context(%s,%s) "
                "WHERE modeled_entity_id = %s",
                (project_id, "logical_entity", scope.logical_entity_id),
            ).fetchone()
        )["source_context"]

    stored = context["object_mappings"][0]["entity"]["context_records"]
    assert {
        (record["context_type_name"], tuple(record["context_type_workflows"]))
        for record in stored
    } == {("Code Context", ("code_generation",)), ("Validation Criterion", ("validation",))}

    def prompt_types(workflow: str) -> list[dict[str, Any]]:
        values = project_mapping_inputs(context, workflow=workflow)
        return values["object_transformations"][0]["entity"]["context_records"]

    code_records = prompt_types("code_generation")
    assert [record["context_type_name"] for record in code_records] == ["Code Context"]
    assert all("context_type_workflows" not in record for record in code_records)
    assert [record["context_type_name"] for record in prompt_types("validation")] == [
        "Validation Criterion"
    ]
