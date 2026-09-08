from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, LiteralString, cast

from psycopg import sql

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres


SEED_FILE = Path(__file__).parents[2] / "database" / "seed" / "04_application_reference.sql"

EXPECTED_STAGES = {
    ("metadata_enrichment_object", "one_shot", "candidate_authoring", 10, True),
    ("metadata_enrichment_attribute", "one_shot", "candidate_authoring", 20, True),
    ("profiling", None, "profile_attributes", 10, False),
    ("analysis", None, "relationship_validation", 10, False),
    ("analysis", "one_shot", "relationship_inference", 10, True),
    ("analysis", "tool_assisted", "relationship_inference", 10, True),
    ("conceptual", None, "backend_validation", 100, False),
    ("conceptual", "one_shot", "candidate_authoring", 10, True),
    ("conceptual", "tool_assisted", "candidate_authoring", 10, True),
    ("logical", None, "policy_projection", 50, False),
    ("logical", None, "backend_validation", 100, False),
    ("logical", "one_shot", "candidate_authoring", 10, True),
    ("logical", "tool_assisted", "candidate_authoring", 10, True),
    ("dimensional", None, "gold_policy_projection", 50, False),
    ("dimensional", None, "foreign_key_projection", 80, False),
    ("dimensional", None, "backend_validation", 100, False),
    ("dimensional", "one_shot", "candidate_authoring", 10, True),
    ("dimensional", "tool_assisted", "candidate_authoring", 10, True),
    ("mapping", None, "dependency_validation", 80, False),
    ("mapping", None, "backend_validation", 100, False),
    ("mapping", "one_shot", "mapping_authoring", 10, True),
    ("mapping", "tool_assisted", "mapping_authoring", 10, True),
    ("code_generation", None, "sql_generation", 10, True),
    ("code_generation", None, "sql_validation", 20, False),
    ("validation", None, "validation_generation", 10, True),
    ("validation", None, "backend_validation", 20, False),
}

NON_REFERENCE_APPLICATION_TABLES = (
    "output_template",
    "output_template_field",
    "principal_preference",
    "prompt_assignment",
    "prompt_template",
    "prompt_template_version",
    "sql_generation_guide",
    "sql_generation_guide_version",
    "workflow_run",
    "workflow_run_mapping_target_selection",
    "workflow_run_object_selection",
    "workflow_run_prompt_snapshot",
    "workflow_run_system_selection",
)

StageIdentity = tuple[str, str | None, str]
VariableIdentity = tuple[
    str,
    str | None,
    str,
    str,
    str,
    str,
    bool,
    int,
    str,
]

FOUNDATIONAL_NAMES = {
    "source_context",
    "gds_context",
    "object_context",
    "object_attribute_context",
    "ingestion_mapping",
    "object_relationship_context",
    "modeling_assertions",
}
CONCEPTUAL_NAMES = {
    "conceptual_object_list",
    "conceptual_objects",
    "conceptual_relationship_list",
    "conceptual_relationships",
}
LOGICAL_NAMES = {
    "logical_submodel_list",
    "logical_submodels",
    "logical_entity_list",
    "logical_entities",
    "logical_attribute_list",
    "logical_attributes",
    "logical_relationship_list",
    "logical_relationships",
}
DIMENSIONAL_NAMES = {name.replace("logical", "dimensional") for name in LOGICAL_NAMES}
EXPECTED_NAMES = {
    "metadata_enrichment_object": FOUNDATIONAL_NAMES
    - {"object_relationship_context", "modeling_assertions"},
    "metadata_enrichment_attribute": FOUNDATIONAL_NAMES
    - {"object_relationship_context", "modeling_assertions"},
    "analysis": FOUNDATIONAL_NAMES,
    "conceptual": FOUNDATIONAL_NAMES | CONCEPTUAL_NAMES,
    "logical": FOUNDATIONAL_NAMES
    | CONCEPTUAL_NAMES
    | LOGICAL_NAMES
    | {"naming_instructions", "audit_columns"},
    "dimensional": LOGICAL_NAMES
    | DIMENSIONAL_NAMES
    | {
        "gds_context",
        "object_context",
        "object_attribute_context",
        "modeling_assertions",
        "logical_bindings",
        "naming_instructions",
        "audit_columns",
        "technical_columns",
    },
    "mapping": {
        "mapping_route",
        "operation",
        "target_metadata",
        "source_evidence",
        "existing_mapping",
        "authoring_policy",
        "readiness",
        "source_system",
        "object_output_template",
        "attribute_output_template",
    },
    "code_generation": {
        "target_metadata",
        "source_metadata",
        "source_systems",
        "object_transformations",
        "attribute_transformations",
        "target_ref",
        "sql_generation_guide",
    },
    "validation": {
        "system_ref",
        "system_scope",
        "mapping_evidence",
        "current_code",
        "applied_groups",
        "applied_checks",
    },
}


def _expected_variables() -> set[VariableIdentity]:
    from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
        list_prompt_input_contracts,
    )
    from jsonschema import Draft202012Validator

    variables: set[VariableIdentity] = set()
    for workflow, mode, stage, _, is_agentic in EXPECTED_STAGES:
        if not is_agentic:
            continue
        contracts = list_prompt_input_contracts(
            model_workflow=workflow,
            workflow_execution_mode=mode,
            stage_code=stage,
        )
        assert {contract.name for contract in contracts} == EXPECTED_NAMES[workflow]
        for index, contract in enumerate(contracts, 1):
            assert (
                contract.resolver_key
                == f"workflow.{workflow}.common.{stage}.inputs.{contract.name}"
            )
            Draft202012Validator.check_schema(contract.value_schema)
            assert cast(Any, Draft202012Validator(contract.value_schema)).is_valid(contract.example)
            # The catalog supplies the complete example; SQL reference rows retain
            # a bounded preview and use null when that preview exceeds the seed cap.
            encoded_example = json.dumps(
                contract.example, ensure_ascii=False, separators=(",", ":")
            )
            stored_example = (
                None if len(encoded_example.encode("utf-8")) > 3500 else contract.example
            )
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    contract.name,
                    contract.resolver_key,
                    contract.data_type,
                    False,
                    index * 10,
                    _example_identity(stored_example),
                )
            )
    return variables


def _example_identity(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _apply_seed(postgres_database: DisposablePostgres) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(cast(LiteralString, SEED_FILE.read_text(encoding="utf-8")))


def test_application_reference_seed_creates_exact_workflow_stage_inventory(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    _apply_seed(bootstrap_postgres_database)

    with bootstrap_postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT model_workflow,
                   workflow_execution_mode,
                   workflow_stage_code,
                   workflow_stage_order,
                   workflow_stage_is_agentic
              FROM application.workflow_stage
            """
        ).fetchall()

    assert {
        (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
            row["workflow_stage_order"],
            row["workflow_stage_is_agentic"],
        )
        for row in rows
    } == EXPECTED_STAGES


def test_application_reference_seed_allowlists_exact_prompt_variables(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    _apply_seed(bootstrap_postgres_database)

    with bootstrap_postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT stage.model_workflow,
                   stage.workflow_execution_mode,
                   stage.workflow_stage_code,
                   variable.workflow_stage_variable_name,
                   variable.workflow_stage_variable_resolver_key,
                   variable.workflow_stage_variable_data_type,
                   variable.workflow_stage_variable_is_required,
                   variable.workflow_stage_variable_order,
                   variable.workflow_stage_variable_example,
                   variable.workflow_stage_variable_description
              FROM application.workflow_stage_variable AS variable
              JOIN application.workflow_stage AS stage
                ON stage.workflow_stage_id = variable.workflow_stage_id
            """
        ).fetchall()

    assert all(row["workflow_stage_variable_description"].strip() for row in rows)
    assert sum(stage[4] for stage in EXPECTED_STAGES) == 14
    assert all(not row["workflow_stage_variable_is_required"] for row in rows)
    assert not {"stage_context", "read_only_dependencies", "available_tools"} & {
        row["workflow_stage_variable_name"] for row in rows
    }
    assert {
        (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
            row["workflow_stage_variable_name"],
            row["workflow_stage_variable_resolver_key"],
            row["workflow_stage_variable_data_type"],
            row["workflow_stage_variable_is_required"],
            row["workflow_stage_variable_order"],
            _example_identity(row["workflow_stage_variable_example"]),
        )
        for row in rows
    } == _expected_variables()


def test_application_reference_seed_replay_changes_nothing(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    _apply_seed(bootstrap_postgres_database)
    with bootstrap_postgres_database.connect_owner() as connection:
        before = connection.execute(
            """
            SELECT 'stage' AS record_type,
                   workflow_stage_id AS record_id,
                   created_time,
                   updated_time
              FROM application.workflow_stage
            UNION ALL
            SELECT 'variable',
                   workflow_stage_variable_id,
                   created_time,
                   updated_time
              FROM application.workflow_stage_variable
             ORDER BY record_type, record_id
            """
        ).fetchall()

    _apply_seed(bootstrap_postgres_database)
    with bootstrap_postgres_database.connect_owner() as connection:
        after = connection.execute(
            """
            SELECT 'stage' AS record_type,
                   workflow_stage_id AS record_id,
                   created_time,
                   updated_time
              FROM application.workflow_stage
            UNION ALL
            SELECT 'variable',
                   workflow_stage_variable_id,
                   created_time,
                   updated_time
              FROM application.workflow_stage_variable
             ORDER BY record_type, record_id
            """
        ).fetchall()

    assert after == before


def test_application_reference_seed_writes_no_mutable_or_prompt_content(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    _apply_seed(bootstrap_postgres_database)

    with bootstrap_postgres_database.connect_owner() as connection:
        populated_tables: list[str] = []
        for table_name in NON_REFERENCE_APPLICATION_TABLES:
            row = require_row(
                connection.execute(
                    sql.SQL("SELECT count(*) AS count FROM application.{}").format(
                        sql.Identifier(table_name)
                    )
                ).fetchone()
            )
            if row["count"]:
                populated_tables.append(table_name)

    assert populated_tables == []
