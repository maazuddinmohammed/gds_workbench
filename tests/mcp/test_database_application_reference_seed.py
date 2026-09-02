from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast

from tests.mcp.database_test_support import require_row
from psycopg import sql

if TYPE_CHECKING:
    from conftest import DisposablePostgres


SEED_FILE = (
    Path(__file__).parents[2] / "database" / "seed" / "04_application_reference.sql"
)

EXPECTED_STAGES = {
    ("profiling", None, "profile_attributes", 10, False),
    ("analysis", None, "relationship_validation", 10, False),
    ("analysis", "one_shot", "relationship_inference", 10, True),
    ("analysis", "tool_assisted", "relationship_inference", 10, True),
    ("analysis", "detailed_coverage", "candidate_finder", 10, True),
    ("analysis", "detailed_coverage", "relationship_resolver", 20, True),
    ("analysis", "detailed_coverage", "whole_slice_reconciler", 30, True),
    ("analysis", "detailed_coverage", "analysis_reviewer", 40, True),
    ("conceptual", None, "backend_validation", 100, False),
    ("conceptual", "one_shot", "candidate_authoring", 10, True),
    ("conceptual", "tool_assisted", "candidate_authoring", 10, True),
    ("conceptual", "detailed_coverage", "object_contribution", 10, True),
    ("conceptual", "detailed_coverage", "entity_consolidation", 20, True),
    ("conceptual", "detailed_coverage", "entity_attribute_detail", 30, True),
    (
        "conceptual",
        "detailed_coverage",
        "relationship_candidate_derivation",
        40,
        False,
    ),
    (
        "conceptual",
        "detailed_coverage",
        "relationship_cardinality_refinement",
        50,
        True,
    ),
    (
        "conceptual",
        "detailed_coverage",
        "whole_model_reconciliation",
        60,
        True,
    ),
    ("logical", None, "policy_projection", 50, False),
    ("logical", None, "backend_validation", 100, False),
    ("logical", "one_shot", "candidate_authoring", 10, True),
    ("logical", "tool_assisted", "candidate_authoring", 10, True),
    ("logical", "detailed_coverage", "topology_builder", 10, True),
    ("logical", "detailed_coverage", "topology_reconciler", 20, True),
    ("logical", "detailed_coverage", "entity_detail_builder", 30, True),
    (
        "logical",
        "detailed_coverage",
        "whole_model_reconciliation",
        40,
        True,
    ),
    ("logical", "detailed_coverage", "validator_worker", 60, True),
    ("logical", "detailed_coverage", "validator_lead", 70, True),
    ("dimensional", None, "gold_policy_projection", 50, False),
    ("dimensional", None, "foreign_key_projection", 80, False),
    ("dimensional", None, "backend_validation", 100, False),
    ("dimensional", "one_shot", "candidate_authoring", 10, True),
    ("dimensional", "tool_assisted", "candidate_authoring", 10, True),
    ("dimensional", "detailed_coverage", "topology_builder", 10, True),
    (
        "dimensional",
        "detailed_coverage",
        "topology_reconciler",
        20,
        True,
    ),
    (
        "dimensional",
        "detailed_coverage",
        "entity_detail_builder",
        30,
        True,
    ),
    (
        "dimensional",
        "detailed_coverage",
        "whole_model_reconciliation",
        40,
        True,
    ),
    ("dimensional", "detailed_coverage", "validator_worker", 60, True),
    ("dimensional", "detailed_coverage", "validator_lead", 70, True),
    ("mapping", None, "dependency_validation", 80, False),
    ("mapping", None, "backend_validation", 100, False),
    ("mapping", "one_shot", "mapping_authoring", 10, True),
    ("mapping", "tool_assisted", "mapping_authoring", 10, True),
    ("mapping", "detailed_coverage", "header_mapper", 10, True),
    ("mapping", "detailed_coverage", "attribute_mapper", 20, True),
    ("mapping", "detailed_coverage", "target_validator", 30, True),
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

NAMING_STAGES: set[StageIdentity] = {
    ("conceptual", "one_shot", "candidate_authoring"),
    ("conceptual", "tool_assisted", "candidate_authoring"),
    ("conceptual", "detailed_coverage", "object_contribution"),
    ("conceptual", "detailed_coverage", "entity_consolidation"),
    ("conceptual", "detailed_coverage", "entity_attribute_detail"),
    (
        "conceptual",
        "detailed_coverage",
        "relationship_cardinality_refinement",
    ),
    ("conceptual", "detailed_coverage", "whole_model_reconciliation"),
    ("logical", "one_shot", "candidate_authoring"),
    ("logical", "tool_assisted", "candidate_authoring"),
    ("logical", "detailed_coverage", "topology_builder"),
    ("logical", "detailed_coverage", "topology_reconciler"),
    ("logical", "detailed_coverage", "entity_detail_builder"),
    ("logical", "detailed_coverage", "whole_model_reconciliation"),
    ("dimensional", "one_shot", "candidate_authoring"),
    ("dimensional", "tool_assisted", "candidate_authoring"),
    ("dimensional", "detailed_coverage", "topology_builder"),
    ("dimensional", "detailed_coverage", "topology_reconciler"),
    ("dimensional", "detailed_coverage", "entity_detail_builder"),
    ("dimensional", "detailed_coverage", "whole_model_reconciliation"),
}

REPAIR_STAGES: set[StageIdentity] = {
    ("analysis", "one_shot", "relationship_inference"),
    ("analysis", "tool_assisted", "relationship_inference"),
    ("analysis", "detailed_coverage", "whole_slice_reconciler"),
    ("conceptual", "one_shot", "candidate_authoring"),
    ("conceptual", "tool_assisted", "candidate_authoring"),
    ("conceptual", "detailed_coverage", "whole_model_reconciliation"),
    ("logical", "one_shot", "candidate_authoring"),
    ("logical", "tool_assisted", "candidate_authoring"),
    ("logical", "detailed_coverage", "whole_model_reconciliation"),
    ("dimensional", "one_shot", "candidate_authoring"),
    ("dimensional", "tool_assisted", "candidate_authoring"),
    ("dimensional", "detailed_coverage", "whole_model_reconciliation"),
    ("mapping", "one_shot", "mapping_authoring"),
    ("mapping", "tool_assisted", "mapping_authoring"),
    ("mapping", "detailed_coverage", "header_mapper"),
    ("mapping", "detailed_coverage", "attribute_mapper"),
    ("code_generation", None, "sql_generation"),
    ("validation", None, "validation_generation"),
}

MAPPING_OBJECT_TEMPLATE_STAGES: set[StageIdentity] = {
    ("mapping", "one_shot", "mapping_authoring"),
    ("mapping", "tool_assisted", "mapping_authoring"),
    ("mapping", "detailed_coverage", "header_mapper"),
}

MAPPING_ATTRIBUTE_TEMPLATE_STAGES: set[StageIdentity] = {
    ("mapping", "one_shot", "mapping_authoring"),
    ("mapping", "tool_assisted", "mapping_authoring"),
    ("mapping", "detailed_coverage", "attribute_mapper"),
}


def _expected_variables() -> set[VariableIdentity]:
    variables: set[VariableIdentity] = set()
    for workflow, mode, stage, _, is_agentic in EXPECTED_STAGES:
        if not is_agentic:
            continue
        stage_identity = (workflow, mode, stage)
        if stage_identity == ("validation", None, "validation_generation"):
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    "validation_context",
                    "workflow.validation.common.validation_context",
                    "json",
                    True,
                    10,
                    '{"system_ref":"system_1"}',
                )
            )
        else:
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    "stage_context",
                    f"workflow.{workflow}.{mode or 'common'}.{stage}.context",
                    "json",
                    True,
                    10,
                    '{"items":[],"schema_version":"1.0"}',
                )
            )
        if stage_identity in NAMING_STAGES:
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    "naming_instructions",
                    "model.naming_instructions",
                    "text",
                    False,
                    20,
                    '""',
                )
            )
        if stage_identity in REPAIR_STAGES:
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    "validation_failures",
                    "workflow.validation_failures",
                    "json",
                    False,
                    30,
                    "[]",
                )
            )
        if stage_identity in MAPPING_OBJECT_TEMPLATE_STAGES:
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    "mapping_object_output_template",
                    "workflow.mapping.object_output_template",
                    "json",
                    False,
                    40,
                    '{"fields":[]}',
                )
            )
        if stage_identity in MAPPING_ATTRIBUTE_TEMPLATE_STAGES:
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    "mapping_attribute_output_template",
                    "workflow.mapping.attribute_output_template",
                    "json",
                    False,
                    50,
                    '{"fields":[]}',
                )
            )
        if stage_identity == ("code_generation", None, "sql_generation"):
            variables.add(
                (
                    workflow,
                    mode,
                    stage,
                    "sql_generation_guide",
                    "workflow.code_generation.sql_generation_guide",
                    "text",
                    True,
                    40,
                    '""',
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
