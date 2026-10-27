"""Code context carries Context routed to Code Generation or Validation, plus cited Context."""

# Shared disposable fixture seed helpers are intentionally imported.
# pyright: reportPrivateUsage=false

from typing import Any
from uuid import uuid4

from gds_etl_workbench.application.mapping_context import project_mapping_inputs
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope


def test_code_context_keeps_routed_and_cited_context_for_each_prompt(
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
        # The cited one is a Business Requirement scoped to another System.
        cited_id = str(uuid4())
        for name, type_name, system_id, record_id in (
            ("Code notes", "Code Context", None, str(uuid4())),
            ("Validation notes", "Validation Criterion", None, str(uuid4())),
            ("Business notes", "Business Requirement", None, str(uuid4())),
            ("Cited notes", "Business Requirement", scope.other_system_id, cited_id),
        ):
            group_id = require_row(
                connection.execute(
                    "INSERT INTO project.context_group "
                    "(project_id, name, context_type_id, source_system_id) "
                    "SELECT %s, %s, context_type_id, %s FROM reference.context_type "
                    "WHERE name = %s RETURNING context_group_id",
                    (project_id, name, system_id, type_name),
                ).fetchone()
            )["context_group_id"]
            connection.execute(
                "INSERT INTO project.context_record "
                "(project_id, context_group_id, context_record_id, context_text) "
                "VALUES (%s, %s, %s::UUID, %s)",
                (project_id, group_id, record_id, f"{name} guidance."),
            )
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping "
            "(project_id, logical_entity_id, context_record_id) VALUES (%s, %s, %s::UUID)",
            (project_id, scope.logical_entity_id, cited_id),
        )
        context = require_row(
            connection.execute(
                "SELECT source_context FROM workflow.list_code_generation_target_context(%s,%s) "
                "WHERE modeled_entity_id = %s",
                (project_id, "logical_entity", scope.logical_entity_id),
            ).fetchone()
        )["source_context"]

    both = ("code_generation", "validation")
    tagged = {
        ("Code notes", ("code_generation",)),
        ("Validation notes", ("validation",)),
        ("Cited notes", both),
    }
    stored = context["object_mappings"][0]["entity"]["context_records"]
    assert {
        (record["context_group_name"], tuple(record["context_type_workflows"]))
        for record in stored
    } == tagged

    def prompt_groups(workflow: str | None) -> list[dict[str, Any]]:
        values = project_mapping_inputs(context, workflow=workflow)
        return values["object_transformations"][0]["entity"]["context_records"]

    code_records = prompt_groups("code_generation")
    assert {record["context_group_name"] for record in code_records} == {
        "Code notes",
        "Cited notes",
    }
    assert all("context_type_workflows" not in record for record in code_records)
    assert {record["context_group_name"] for record in prompt_groups("validation")} == {
        "Validation notes",
        "Cited notes",
    }
    # The MCP view serves Atlas Code and Validation, so it keeps both, tagged.
    assert {
        (record["context_group_name"], tuple(record["context_type_workflows"]))
        for record in prompt_groups(None)
    } == tagged
