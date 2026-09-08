from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import UUID

import psycopg
import pytest

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres, TestRow


SEED_ROOT = Path(__file__).parents[2] / "database" / "seed"
REFERENCE_SEED = SEED_ROOT / "04_application_reference.sql"
PROMPT_SEED_TEMPLATE = SEED_ROOT / "05_global_prompt_defaults.template.sql"
ENTRA_TENANT_ID = UUID("75000000-0000-0000-0000-000000000001")
ENTRA_OBJECT_ID = UUID("76000000-0000-0000-0000-000000000001")
PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,99})\s*\}\}")
type StageIdentity = tuple[str, str | None, str]

EXPECTED_AGENTIC_STAGES: frozenset[StageIdentity] = frozenset(
    {
        ("metadata_enrichment_object", "one_shot", "candidate_authoring"),
        ("metadata_enrichment_attribute", "one_shot", "candidate_authoring"),
        ("analysis", "one_shot", "relationship_inference"),
        ("analysis", "tool_assisted", "relationship_inference"),
        ("conceptual", "one_shot", "candidate_authoring"),
        ("conceptual", "tool_assisted", "candidate_authoring"),
        ("logical", "one_shot", "candidate_authoring"),
        ("logical", "tool_assisted", "candidate_authoring"),
        ("dimensional", "one_shot", "candidate_authoring"),
        ("dimensional", "tool_assisted", "candidate_authoring"),
        ("mapping", "one_shot", "mapping_authoring"),
        ("mapping", "tool_assisted", "mapping_authoring"),
        ("code_generation", None, "sql_generation"),
        ("validation", None, "validation_generation"),
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
VALIDATION_FAILURE_STAGES: frozenset[StageIdentity] = frozenset({*()})
CODE_GENERATION_STAGE: StageIdentity = (
    "code_generation",
    None,
    "sql_generation",
)
VALIDATION_STAGE: StageIdentity = ("validation", None, "validation_generation")


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
                   version.agent_tool_names,
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
    assert all("\n" in str(row["system_prompt_template"]) for row in first)
    assert all("\\n" not in str(row["system_prompt_template"]) for row in first)
    assert all("\\n" not in str(row["instruction_prompt_template"]) for row in first)
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
    assert expected_count == 14
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
        if row["agent_tool_names"] is not None
    }
    assert tool_stages == TOOL_ASSISTED_STAGES | {
        CODE_GENERATION_STAGE,
        VALIDATION_STAGE,
    }

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
        variable_contract_rows = connection.execute(
            """
            SELECT stage.model_workflow,
                   stage.workflow_execution_mode,
                   stage.workflow_stage_code,
                   variable.workflow_stage_variable_name AS name,
                   variable.workflow_stage_variable_resolver_key AS resolver_key,
                   variable.workflow_stage_variable_data_type AS data_type,
                   variable.workflow_stage_variable_is_required AS is_required
              FROM application.workflow_stage AS stage
              JOIN application.workflow_stage_variable AS variable
                ON variable.workflow_stage_id = stage.workflow_stage_id
               AND variable.is_active
             WHERE stage.workflow_stage_is_agentic
               AND stage.is_active
             ORDER BY stage.model_workflow,
                      stage.workflow_execution_mode NULLS FIRST,
                      stage.workflow_stage_order,
                      variable.workflow_stage_variable_order
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
    for workflow in ("metadata_enrichment_object", "metadata_enrichment_attribute"):
        assert allowed[(workflow, "one_shot", "candidate_authoring")] == {
            "source_context",
            "gds_context",
            "object_context",
            "object_attribute_context",
            "ingestion_mapping",
        }
    for variable in variable_contract_rows:
        assert variable["resolver_key"] == (
            f"workflow.{variable['model_workflow']}.common."
            f"{variable['workflow_stage_code']}.inputs.{variable['name']}"
        )
        assert variable["is_required"] is False
    prompt_root = SEED_ROOT.parents[1] / "docs" / "workflow-prompts"
    for row in first:
        identity = (
            row["model_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        )
        file_workflow = "code" if identity[0] == "code_generation" else identity[0]
        file_mode = identity[1] or "tool_assisted"
        reviewed = json.loads(
            (prompt_root / f"{file_workflow}.{file_mode}.json").read_text()
        )
        assert row["system_prompt_template"] == reviewed["system_prompt"]
        assert row["instruction_prompt_template"] == reviewed["instruction_prompt"]
        assert row["tool_instruction_prompt_template"] is None
        assert row["agent_tool_names"] == (
            sorted(reviewed["tools"]) if file_mode == "tool_assisted" else None
        )
        assert set(reviewed["variables"]) <= allowed[identity]
        assert "stage_context" not in reviewed["variables"]
        assert row["prompt_template_code"] == (
            f"global_default.{identity[0]}.{identity[1] or 'common'}.{identity[2]}"
        )

    assert counts == {
        "template_count": expected_count,
        "version_count": expected_count,
        "assignment_count": expected_count,
        "draft_count": 0,
    }

    _apply_sql(postgres_database, rendered)
    assert _snapshot(postgres_database) == first

    match = re.search(
        r"\$workflow_defaults\$\n(.*?)\n\$workflow_defaults\$", rendered, re.DOTALL
    )
    assert match is not None
    payload = json.loads(match.group(1))
    target = next(
        row
        for row in payload
        if row["model_workflow"] == "analysis"
        and row["workflow_execution_mode"] == "one_shot"
    )
    target["system_prompt"] += "\nApply conservative evidence thresholds."
    changed = (
        rendered[: match.start(1)]
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + rendered[match.end(1) :]
    )
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
