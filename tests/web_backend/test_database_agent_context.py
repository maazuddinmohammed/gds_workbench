from collections.abc import Mapping
from pathlib import Path
from typing import Any, LiteralString, Protocol, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from psycopg import Connection
from tests.mcp.conftest import (
    bootstrap_postgres_database as bootstrap_postgres_database,
)
from tests.web_backend.test_database_seeded_defaults import SeedStages
from tests.web_backend.test_database_seeded_defaults import (
    installed_stages as installed_stages,
)

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    PostgresAgentContextRepository,
    focus_subject_area,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
    PlannedSubjectArea,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    project_prompt_input_values,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates, render_prompt

_DATABASE_ROOT = Path(__file__).resolve().parents[2] / "database"


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...

    def web_runtime_dsn(self) -> str: ...


def _required_int(row: Mapping[str, object] | None, field: str) -> int:
    if row is None:
        raise AssertionError(f"missing database field {field}")
    value = row.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"invalid database field {field}")
    return value


def _plan(*, project_id: int, project_revision: int, object_id: int) -> AgentRunPlan:
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "project_id": project_id,
            "correlation_id": uuid4(),
            "project_revision": project_revision,
            "project_workflow": "subject_area",
            "workflow_execution_mode": "one_shot",
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (object_id,),
            "selection": AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=2,
            ),
            "stages": (
                FrozenAgentStage(
                    workflow_stage_id=31,
                    stage_code="candidate_authoring",
                    stage_order=10,
                    prompt_template_version_id=81,
                    prompt_template_digest="b" * 64,
                    templates=PromptComponentTemplates(
                        system="private system prompt",
                        instruction="private instruction prompt",
                        tool_instruction=None,
                    ),
                    variables=(),
                ),
            ),
        },
        strict=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", ["analysis", "subject_area", "logical"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_database_context_uses_object_source_tenant_under_web_role(
    web_postgres_database: DisposablePostgresFixture,
    installed_stages: SeedStages,
    workflow: str,
    mode: str,
) -> None:
    with web_postgres_database.connect_owner() as connection:
        seeded = connection.execute(
            "SELECT 1 FROM core.lane WHERE lane_code = 'DEMO_LANE'"
        ).fetchone()
        if seeded is None:
            connection.execute(
                cast(
                    LiteralString,
                    (_DATABASE_ROOT / "seed/01_metadata_snapshot_demo.sql").read_text(
                        encoding="utf-8"
                    ),
                )
            )
        foundation = connection.execute(
            """
            SELECT tenant.tenant_id,
                   object_record.object_id
              FROM core.tenant AS tenant
              JOIN core.object AS object_record
                ON object_record.source_tenant_id = tenant.tenant_id
             WHERE tenant.tenant_code = 'DEMO_TENANT'
               AND object_record.object_schema = 'bronze_demo'
               AND object_record.object_name = 'customer'
            """
        ).fetchone()
        tenant_id = _required_int(foundation, "tenant_id")
        object_id = _required_int(foundation, "object_id")
        project = connection.execute(
            """
            INSERT INTO project.project (
                tenant_id, project_name, logical_schemas, dimensional_schemas
            )
            VALUES (%s, %s,
                    '[{"schema_name":"silver","description":null}]',
                    '[{"schema_name":"gold","description":null}]')
            RETURNING project_id, project_revision
            """,
            (tenant_id, f"Agent Context {uuid4().hex}"),
        ).fetchone()
        project_id = _required_int(project, "project_id")
        project_revision = _required_int(project, "project_revision")
        connection.execute(
            "INSERT INTO project.project_input_scope (project_id, object_id) VALUES (%s, %s)",
            (project_id, object_id),
        )
        attributes = connection.execute(
            "SELECT attribute_id FROM core.attribute WHERE object_id=%s "
            "ORDER BY attribute_ordinal_position",
            (object_id,),
        ).fetchall()
        connection.execute(
            """INSERT INTO workflow.analysis_result (
                project_id,from_object_id,from_attribute_id,to_object_id,to_attribute_id,
                relationship_kind,relationship_basis,analysis_result_is_locked
            ) VALUES (%s,%s,%s,%s,%s,'reference','Synthetic stored relationship.',TRUE)""",
            (
                project_id,
                object_id,
                attributes[0]["attribute_id"],
                object_id,
                attributes[1]["attribute_id"],
            ),
        )
        connection.execute(
            """INSERT INTO workflow.attribute_profile (
                project_id,object_id,attribute_id,source_context_digest,
                row_count,non_null_count,null_count,avg_data_length,percent_populated
            ) VALUES (%s,%s,%s,%s,2,2,0,3.500000,100.0000)""",
            (project_id, object_id, attributes[0]["attribute_id"], "a" * 64),
        )

        connection.execute(
            "INSERT INTO workflow.object_enrichment(project_id,object_id,object_description) "
            "VALUES(%s,%s,'Project object description')",
            (project_id, object_id),
        )
        connection.execute(
            "INSERT INTO workflow.attribute_enrichment(project_id,object_id,attribute_id,"
            "attribute_description,attribute_inferred_data_type,is_natural_key,is_primary_key,"
            "is_nullable,is_pii) VALUES(%s,%s,%s,'Project attribute description','BIGINT',"
            "TRUE,TRUE,FALSE,NULL)",
            (project_id, object_id, attributes[0]["attribute_id"]),
        )
        # A Logical Build reads its Subject Area's member Objects.
        area_id = _required_int(
            connection.execute(
                "INSERT INTO workflow.subject_area (project_id, subject_area_name, "
                "subject_area_definition) VALUES (%s, 'Customers', 'Customer accounts.') "
                "RETURNING subject_area_id",
                (project_id,),
            ).fetchone(),
            "subject_area_id",
        )
        connection.execute(
            "INSERT INTO workflow.subject_area_table (project_id, subject_area_id, object_id) "
            "VALUES (%s, %s, %s)",
            (project_id, area_id, object_id),
        )
    area = PlannedSubjectArea(
        subject_area_id=area_id,
        subject_area_name="Customers",
        subject_area_definition="Customer accounts.",
    )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    stages = installed_stages[(workflow, mode)]
    # A Logical run freezes one stage: Build packages each area's call, Optimize the model.
    runs = [
        (stage.stage_code.removesuffix("_authoring") if workflow == "logical" else None, stage)
        for stage in stages
    ]
    await database.open()
    try:
        loaded: list[tuple[AgentRunPlan, FrozenAgentStage, AgentContextBundle]] = []
        for operation, stage in runs:
            plan = _plan(
                project_id=project_id, project_revision=project_revision, object_id=object_id
            ).model_copy(
                update={
                    "project_workflow": workflow,
                    "workflow_execution_mode": mode,
                    "workflow_operation": operation,
                    "subject_areas": (area,) if operation == "build" else (),
                    "stages": stages if operation is None else (stage,),
                },
            )
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                result = await PostgresAgentContextRepository().load(
                    transaction,
                    tenant_id=tenant_id,
                    plan=plan,
                )
            if operation == "build":
                assert result.snapshot is not None
                focused = focus_subject_area(
                    result, plan=plan, subject_area=area, logical=result.snapshot.logical
                )
                assert focused is not None
                result = focused
            loaded.append((plan, stage, result))
    finally:
        await database.close()

    for plan, stage, result in loaded:
        selected = result.context.selected_objects[0]
        assert selected.object.tenant_code == "DEMO_GDS_TENANT"
        assert selected.object.source_tenant_code == "DEMO_TENANT"
        assert selected.object.connection_code == "DEMO_GDS"
        assert [attribute.attribute_name for attribute in selected.attributes] == [
            "customer_id",
            "customer_name",
        ]
        assert isinstance(result.embedded_context, dict)
        assert "workflow_run_id" not in result.embedded_context
        assert "project_id" not in result.embedded_context
        catalog = result.tool_catalog
        values = project_prompt_input_values(
            plan=plan,
            stage=stage,
            context=result.embedded_context,
            resolver_values={},
            tool_definitions=catalog.definitions if catalog else (),
            precomputed_values=catalog.prompt_values if catalog else None,
        )
        prefix = f"workflow.{workflow}.common.{stage.stage_code}.inputs."
        rendered = render_prompt(
            templates=stage.templates, variables=stage.variables, resolver_values=values
        )
        assert rendered.system and rendered.instruction
        assert not rendered.warning_codes and not rendered.unknown_placeholders
        assert values[prefix + "source_context"] and values[prefix + "gds_context"]
        if workflow == "subject_area":
            # Compact table evidence only; a self-reference is not a link between tables.
            assert values[prefix + "scope_tables"] == [
                {
                    "table": "t1",
                    "description": "Project object description",
                    "zone_code": "bronze",
                    "row_count": 2,
                    "column_count": 2,
                    "column_names": ["customer_id", "customer_name"],
                }
            ]
            assert values[prefix + "table_links"] == []
            continue
        groups = cast(list[dict[str, Any]], values[prefix + "object_relationship_context"])
        for direction in ("incoming_relationships", "outgoing_relationships"):
            assert len(groups[0][direction]) == 1
            assert groups[0][direction][0]["analysis_result_is_locked"] is True
            relationship = groups[0][direction][0]
            assert {
                name: value
                for name, value in relationship.items()
                if name.startswith("validation_")
            } == {
                "validation_policy_version": None,
                "validation_result": None,
                "validation_source_non_null_count": None,
                "validation_source_distinct_count": None,
                "validation_target_non_null_count": None,
                "validation_target_distinct_count": None,
                "validation_source_missing_target_count": None,
                "validation_unused_target_count": None,
                "validation_duplicate_target_key_count": None,
            }
        attribute_groups = cast(list[dict[str, Any]], values[prefix + "object_attribute_context"])
        assert attribute_groups[0]["attributes"][0]["profile"]["avg_data_length"] == 3.5
        enriched = attribute_groups[0]["attributes"][0]
        assert enriched["attribute_description"] == "Project attribute description"
        assert enriched["attribute_inferred_data_type"] == "BIGINT"
        assert [
            enriched[flag] for flag in ("is_natural_key", "is_primary_key", "is_nullable", "is_pii")
        ] == [True, True, False, None]
        assert values[prefix + "ingestion_mapping"]
