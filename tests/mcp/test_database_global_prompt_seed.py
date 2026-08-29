from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import UUID

import psycopg
import pytest

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres, TestRow


SEED_ROOT = Path(__file__).parents[2] / "database" / "seed"
REFERENCE_SEED = SEED_ROOT / "04_application_reference.sql"
PROMPT_SEED_TEMPLATE = SEED_ROOT / "05_global_prompt_defaults.template.sql"
ENTRA_TENANT_ID = UUID("75000000-0000-0000-0000-000000000001")
ENTRA_OBJECT_ID = UUID("76000000-0000-0000-0000-000000000001")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,99})\s*\}\}")
type StageIdentity = tuple[str, str | None, str]

EXPECTED_AGENTIC_STAGES: frozenset[StageIdentity] = frozenset(
    {
        ("analysis", "one_shot", "relationship_inference"),
        ("analysis", "tool_assisted", "relationship_inference"),
        ("analysis", "detailed_coverage", "candidate_finder"),
        ("analysis", "detailed_coverage", "relationship_resolver"),
        ("analysis", "detailed_coverage", "whole_slice_reconciler"),
        ("analysis", "detailed_coverage", "analysis_reviewer"),
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
        ("logical", "detailed_coverage", "validator_worker"),
        ("logical", "detailed_coverage", "validator_lead"),
        ("dimensional", "one_shot", "candidate_authoring"),
        ("dimensional", "tool_assisted", "candidate_authoring"),
        ("dimensional", "detailed_coverage", "topology_builder"),
        ("dimensional", "detailed_coverage", "topology_reconciler"),
        ("dimensional", "detailed_coverage", "entity_detail_builder"),
        (
            "dimensional",
            "detailed_coverage",
            "whole_model_reconciliation",
        ),
        ("dimensional", "detailed_coverage", "validator_worker"),
        ("dimensional", "detailed_coverage", "validator_lead"),
        ("mapping", "one_shot", "mapping_authoring"),
        ("mapping", "tool_assisted", "mapping_authoring"),
        ("mapping", "detailed_coverage", "header_mapper"),
        ("mapping", "detailed_coverage", "attribute_mapper"),
        ("mapping", "detailed_coverage", "target_validator"),
        ("code_generation", None, "sql_generation"),
    }
)
TOOL_ASSISTED_STAGES: frozenset[StageIdentity] = frozenset(
    {
        ("analysis", "tool_assisted", "relationship_inference"),
        ("conceptual", "tool_assisted", "candidate_authoring"),
        ("logical", "tool_assisted", "candidate_authoring"),
        ("dimensional", "tool_assisted", "candidate_authoring"),
        ("mapping", "tool_assisted", "mapping_authoring"),
    }
)
VALIDATION_FAILURE_STAGES: frozenset[StageIdentity] = frozenset(
    {
        ("analysis", "detailed_coverage", "whole_slice_reconciler"),
        ("logical", "detailed_coverage", "whole_model_reconciliation"),
        ("dimensional", "detailed_coverage", "whole_model_reconciliation"),
    }
)
CODE_GENERATION_STAGE: StageIdentity = (
    "code_generation",
    None,
    "sql_generation",
)


def _prompt_parts(row: TestRow) -> tuple[str, ...]:
    return tuple(
        value
        for value in (
            row["system_prompt_template"],
            row["instruction_prompt_template"],
            row["tool_instruction_prompt_template"],
        )
        if value is not None
    )


def _assert_lean_nonduplicative_prompt(parts: tuple[str, ...]) -> None:
    assert all(part and part == part.strip() for part in parts)
    assert len(parts[0]) <= 1_400
    assert len(parts[1]) <= 1_900
    if len(parts) == 3:
        assert len(parts[2]) <= 1_600

    meaningful_units = [
        re.sub(
            r"\s+",
            " ",
            re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", unit),
        )
        .strip()
        .casefold()
        for part in parts
        for unit in re.split(r"(?<=[.!?])(?:\s+|$)|\n+", part)
        if len(unit.strip()) >= 40
    ]
    assert len(meaningful_units) == len(set(meaningful_units))


def _render_seed(template: str | None = None) -> str:
    rendered = (
        PROMPT_SEED_TEMPLATE.read_text(encoding="utf-8")
        if template is None
        else template
    )
    replacements = {
        "__REPLACE_WITH_ENTRA_TENANT_ID__": str(ENTRA_TENANT_ID),
        "__REPLACE_WITH_ENTRA_OBJECT_ID__": str(ENTRA_OBJECT_ID),
        "__REPLACE_WITH_PRINCIPAL_TYPE__": "user",
    }
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    assert all(placeholder not in rendered for placeholder in replacements)
    return rendered


def _apply_sql(postgres_database: DisposablePostgres, content: str) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(cast(LiteralString, content))


def _seed_super_admin(postgres_database: DisposablePostgres) -> int:
    with postgres_database.connect_owner() as connection:
        principal_id = require_row(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email,
                    is_super_admin
                ) VALUES (
                    'user',
                    'Global Prompt Seed Administrator',
                    'global.prompt.seed@example.test',
                    TRUE
                )
                RETURNING principal_id
                """
            ).fetchone()
        )["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
        )
    return principal_id


def _snapshot(postgres_database: DisposablePostgres) -> list[TestRow]:
    with postgres_database.connect_owner() as connection:
        return connection.execute(
            """
            SELECT stage.model_workflow,
                   stage.workflow_execution_mode,
                   stage.workflow_stage_code,
                   template.prompt_template_id,
                   template.prompt_template_code,
                   template.prompt_template_name,
                   template.prompt_template_description,
                   template.updated_time AS template_updated_time,
                   version.prompt_template_version_id,
                   version.prompt_template_version_number,
                   version.prompt_template_digest,
                   version.prompt_template_version_status,
                   version.system_prompt_template,
                   version.instruction_prompt_template,
                   version.tool_instruction_prompt_template,
                   version.updated_time AS version_updated_time,
                   assignment.prompt_assignment_id,
                   assignment.assigned_by_principal_id,
                   assignment.created_time AS assignment_created_time
              FROM application.workflow_stage AS stage
              JOIN application.prompt_template AS template
                ON template.workflow_stage_id = stage.workflow_stage_id
               AND template.prompt_template_ownership_scope = 'global'
               AND template.is_active
              JOIN application.prompt_assignment AS assignment
                ON assignment.workflow_stage_id = stage.workflow_stage_id
               AND assignment.prompt_assignment_scope = 'global_default'
               AND assignment.model_id IS NULL
               AND assignment.is_active
              JOIN application.prompt_template_version AS version
                ON version.prompt_template_version_id =
                   assignment.prompt_template_version_id
               AND version.workflow_stage_id = stage.workflow_stage_id
               AND version.prompt_template_id = template.prompt_template_id
             WHERE stage.workflow_stage_is_agentic
               AND stage.is_active
             ORDER BY stage.model_workflow,
                      stage.workflow_execution_mode NULLS FIRST,
                      stage.workflow_stage_order,
                      stage.workflow_stage_code
            """
        ).fetchall()


def test_global_prompt_seed_is_complete_governed_and_replay_safe(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    postgres_database = bootstrap_postgres_database
    template = PROMPT_SEED_TEMPLATE.read_text(encoding="utf-8")
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(psycopg.errors.RaiseException),
        connection.transaction(),
    ):
        connection.execute(cast(LiteralString, template))

    _apply_sql(postgres_database, REFERENCE_SEED.read_text(encoding="utf-8"))
    actor_id = _seed_super_admin(postgres_database)
    rendered = _render_seed(template)
    _apply_sql(postgres_database, rendered)

    first = _snapshot(postgres_database)
    stage_identities = [
        (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        )
        for row in first
    ]
    assert len(stage_identities) == len(set(stage_identities))
    assert set(stage_identities) == EXPECTED_AGENTIC_STAGES
    expected_count = len(EXPECTED_AGENTIC_STAGES)
    assert expected_count == 35
    assert len({row["prompt_template_id"] for row in first}) == expected_count
    assert len({row["prompt_template_version_id"] for row in first}) == expected_count
    assert len({row["prompt_assignment_id"] for row in first}) == expected_count
    assert {row["prompt_template_version_status"] for row in first} == {"published"}
    assert {row["assigned_by_principal_id"] for row in first} == {actor_id}

    tool_stages = {
        (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        )
        for row in first
        if row["tool_instruction_prompt_template"] is not None
    }
    assert tool_stages == TOOL_ASSISTED_STAGES

    with postgres_database.connect_owner() as connection:
        variables = connection.execute(
            """
            SELECT stage.model_workflow,
                   stage.workflow_execution_mode,
                   stage.workflow_stage_code,
                   array_agg(
                       variable.workflow_stage_variable_name
                       ORDER BY variable.workflow_stage_variable_order
                   ) AS names
              FROM application.workflow_stage AS stage
              JOIN application.workflow_stage_variable AS variable
                ON variable.workflow_stage_id = stage.workflow_stage_id
               AND variable.is_active
             WHERE stage.workflow_stage_is_agentic
               AND stage.is_active
             GROUP BY stage.workflow_stage_id
            """
        ).fetchall()
        counts = require_row(
            connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM application.prompt_template)
                        AS template_count,
                    (SELECT count(*) FROM application.prompt_template_version)
                        AS version_count,
                    (SELECT count(*) FROM application.prompt_assignment)
                        AS assignment_count,
                    (
                        SELECT count(*)
                          FROM application.prompt_template_version
                         WHERE prompt_template_version_status = 'draft'
                    ) AS draft_count
                """
            ).fetchone()
        )
    allowed = {
        (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        ): set(row["names"])
        for row in variables
    }
    assert set(allowed) == EXPECTED_AGENTIC_STAGES
    used_validation_failures: set[StageIdentity] = set()
    used_sql_generation_guide: set[StageIdentity] = set()
    for row in first:
        identity = (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        )
        parts = _prompt_parts(row)
        assert len(parts) == (3 if identity in TOOL_ASSISTED_STAGES else 2)
        _assert_lean_nonduplicative_prompt(parts)
        combined = "\n".join(parts)
        normalized = combined.casefold()
        for required_boundary in (
            "top-level instruction",
            "instruction-like",
            "business data",
            "tool results",
            "required_output_schema",
            "context.repair.validation_issues",
            "authoritative",
        ):
            assert required_boundary in normalized
        placeholder_names = PLACEHOLDER.findall(combined)
        placeholders = set(placeholder_names)
        assert len(placeholder_names) == len(placeholders)
        assert placeholders <= allowed[identity]
        assert "{{" not in PLACEHOLDER.sub("", combined)
        assert "}}" not in PLACEHOLDER.sub("", combined)
        assert "stage_context" not in placeholders
        assert row["prompt_template_code"] == (
            "global_default."
            f"{row['model_workflow']}."
            f"{row['workflow_execution_mode'] or 'common'}."
            f"{row['workflow_stage_code']}"
        )
        if "validation_failures" in placeholders:
            used_validation_failures.add(identity)
        if "sql_generation_guide" in placeholders:
            used_sql_generation_guide.add(identity)

        if identity in TOOL_ASSISTED_STAGES:
            tool_prompt = row["tool_instruction_prompt_template"].casefold()
            for tool_rule in (
                "manifest first",
                "smallest",
                "next_offset is null",
                "do not guess",
            ):
                assert tool_rule in tool_prompt

        if identity == CODE_GENERATION_STAGE:
            for output_term in ("artifacts", "target_ref", "generated_sql"):
                assert output_term in normalized
            assert "raw sql response" not in normalized

        if identity == (
            "conceptual",
            "detailed_coverage",
            "relationship_cardinality_refinement",
        ):
            assert "relationship basis" in normalized
            assert "cardinality basis" in normalized
            assert "optionality" not in normalized

        if identity == ("mapping", "detailed_coverage", "header_mapper"):
            for mapping_term in (
                "author",
                "extend",
                "preserve",
                "blocked",
                "expected_mapping_object_ids",
                "returned_mapping_object_ids",
            ):
                assert mapping_term in normalized

        if identity[2] == "validator_worker":
            for worker_term in (
                "reviewed_record_refs",
                "blocking invariant",
                "nonblocking",
                "error",
                "warning",
            ):
                assert worker_term in normalized

        if identity[2] == "validator_lead":
            for lead_term in (
                "reviewed_package_refs",
                "reviewed_finding_refs",
                "blocking_finding_refs",
                "repair_brief",
                "errors",
            ):
                assert lead_term in normalized
    assert used_validation_failures == VALIDATION_FAILURE_STAGES
    assert used_sql_generation_guide == {CODE_GENERATION_STAGE}
    assert counts == {
        "template_count": expected_count,
        "version_count": expected_count,
        "assignment_count": expected_count,
        "draft_count": 0,
    }

    _apply_sql(postgres_database, rendered)
    assert _snapshot(postgres_database) == first

    changed, replacement_count = re.subn(
        r"(\$objective\$[^$]+?)(\$objective\$)",
        r"\1 Apply conservative evidence thresholds.\2",
        rendered,
        count=1,
    )
    assert replacement_count == 1
    _apply_sql(postgres_database, changed)
    second = _snapshot(postgres_database)
    assert len(second) == expected_count

    identity = ("analysis", "one_shot", "relationship_inference")
    first_by_identity = {
        (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        ): row
        for row in first
    }
    second_by_identity = {
        (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        ): row
        for row in second
    }
    assert (
        second_by_identity[identity]["prompt_template_id"]
        == (first_by_identity[identity]["prompt_template_id"])
    )
    assert (
        second_by_identity[identity]["prompt_template_version_id"]
        != (first_by_identity[identity]["prompt_template_version_id"])
    )
    assert second_by_identity[identity]["prompt_template_version_number"] == 2
    assert (
        second_by_identity[identity]["prompt_assignment_id"]
        != (first_by_identity[identity]["prompt_assignment_id"])
    )
    for stage_identity, first_row in first_by_identity.items():
        if stage_identity != identity:
            assert second_by_identity[stage_identity] == first_row

    with postgres_database.connect_owner() as connection:
        changed_counts = require_row(
            connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM application.prompt_template)
                        AS template_count,
                    (SELECT count(*) FROM application.prompt_template_version)
                        AS version_count,
                    (SELECT count(*) FROM application.prompt_assignment)
                        AS assignment_count,
                    (
                        SELECT count(*)
                          FROM application.prompt_assignment
                         WHERE is_active
                    ) AS active_assignment_count
                """
            ).fetchone()
        )
    assert changed_counts == {
        "template_count": expected_count,
        "version_count": expected_count + 1,
        "assignment_count": expected_count + 1,
        "active_assignment_count": expected_count,
    }

    _apply_sql(postgres_database, changed)
    assert _snapshot(postgres_database) == second
