from collections.abc import Mapping
from pathlib import Path
from typing import LiteralString, Protocol, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from psycopg import Connection

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.authoring.context import (
    PostgresAgentContextRepository,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates

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


def _plan(*, model_id: int, model_revision: int, object_id: int) -> AgentRunPlan:
    return AgentRunPlan.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": model_id,
            "correlation_id": uuid4(),
            "model_revision": model_revision,
            "model_workflow": "conceptual",
            "workflow_execution_mode": "one_shot",
            "modeled_entity_type": None,
            "selected_scope_digest": "a" * 64,
            "selected_object_ids": (object_id,),
            "selection": AgentRunSelection(
                sdk_code="langchain_create_agent",
                provider_code="databricks",
                model_code="databricks-primary",
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
async def test_database_context_uses_discovery_assigned_tenant_under_web_role(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    with web_postgres_database.connect_owner() as connection:
        seeded = connection.execute(
            "SELECT 1 FROM core.project WHERE project_code = 'DEMO_PROJECT'"
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
              JOIN core.tenant_metadata_discovery_scope AS discovery_scope
                ON discovery_scope.tenant_id = tenant.tenant_id
               AND discovery_scope.is_active
              JOIN core.object AS object_record
                ON object_record.connection_id = discovery_scope.gds_connection_id
               AND object_record.zone_id = discovery_scope.zone_id
               AND lower(btrim(object_record.object_schema)) =
                   lower(btrim(discovery_scope.object_schema))
             WHERE tenant.tenant_code = 'DEMO_TENANT'
               AND object_record.object_schema = 'bronze_demo'
               AND object_record.object_name = 'customer'
            """
        ).fetchone()
        tenant_id = _required_int(foundation, "tenant_id")
        object_id = _required_int(foundation, "object_id")
        model = connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id, model_revision
            """,
            (tenant_id, f"Agent Context {uuid4().hex}"),
        ).fetchone()
        model_id = _required_int(model, "model_id")
        model_revision = _required_int(model, "model_revision")
        connection.execute(
            "INSERT INTO model.model_scope (model_id, object_id) VALUES (%s, %s)",
            (model_id, object_id),
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        async with database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            result = await PostgresAgentContextRepository().load(
                transaction,
                tenant_id=tenant_id,
                plan=_plan(
                    model_id=model_id,
                    model_revision=model_revision,
                    object_id=object_id,
                ),
            )
    finally:
        await database.close()

    selected = result.context.selected_objects[0]
    assert selected.object.tenant_code == "DEMO_TENANT"
    assert selected.object.tenant_code != "DEMO_GDS_TENANT"
    assert selected.object.connection_code == "DEMO_GDS"
    assert [attribute.attribute_name for attribute in selected.attributes] == [
        "customer_id",
        "customer_name",
    ]
    assert isinstance(result.embedded_context, dict)
    assert "workflow_run_id" not in result.embedded_context
    assert "model_id" not in result.embedded_context
