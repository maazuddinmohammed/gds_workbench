"""SQL Guide setup with existing Models; disposable fixtures, no external execution."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from collections.abc import Iterator
from pathlib import Path
from typing import LiteralString, cast
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.capabilities import (
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
)
from psycopg.errors import RaiseException

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_global_prompt_seed import (
    ENTRA_OBJECT_ID,
    ENTRA_TENANT_ID,
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
)
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope

SEED = Path(__file__).parents[2] / "database/seed/06_global_sql_generation_guide.template.sql"


@pytest.fixture
def guide_database() -> Iterator[DisposablePostgres]:
    yield from disposable_postgres()


def _guide_seed() -> str:
    return (
        SEED.read_text()
        .replace("__REPLACE_WITH_ENTRA_TENANT_ID__", str(ENTRA_TENANT_ID))
        .replace("__REPLACE_WITH_ENTRA_OBJECT_ID__", str(ENTRA_OBJECT_ID))
        .replace("__REPLACE_WITH_PRINCIPAL_TYPE__", "user")
    )


def test_fresh_sql_guide_seed_is_authorized_and_exact_replay_preserves_history(
    guide_database: DisposablePostgres,
) -> None:
    with (
        guide_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="replace every"),
    ):
        connection.execute(cast(LiteralString, SEED.read_text()))
    with pytest.raises(RaiseException, match="requires Super Admin"):
        _apply_sql(guide_database, _guide_seed())
    _seed_super_admin(guide_database)
    _apply_sql(guide_database, _guide_seed())
    with guide_database.connect_owner() as connection:
        before = connection.execute(
            "SELECT guide.*, version.* FROM application.sql_generation_guide guide "
            "JOIN application.sql_generation_guide_version version "
            "USING(sql_generation_guide_id)"
        ).fetchall()
    assert len(before) == 1
    assert before[0]["is_default"] and before[0]["is_active"]
    assert before[0]["sql_generation_guide_version_status"] == "published"
    _apply_sql(guide_database, _guide_seed())
    with guide_database.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT guide.*, version.* FROM application.sql_generation_guide guide "
                "JOIN application.sql_generation_guide_version version "
                "USING(sql_generation_guide_id)"
            ).fetchall()
            == before
        )
    with pytest.raises(RaiseException, match="conflicts with existing guide history"):
        _apply_sql(
            guide_database,
            _guide_seed().replace(
                "Default Databricks query conventions",
                "Changed Databricks query conventions",
            ),
        )


def test_sql_guide_seed_preserves_custom_default_with_or_without_models(
    guide_database: DisposablePostgres,
) -> None:
    _seed_super_admin(guide_database)
    with guide_database.connect_owner() as connection:
        guide = require_row(
            connection.execute(
                "SELECT * FROM application.save_sql_generation_guide(%s,%s,'user',NULL,"
                "'custom.fixture','Custom fixture',NULL,TRUE,TRUE,NULL)",
                (ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
            ).fetchone()
        )
        version = require_row(
            connection.execute(
                "SELECT * FROM application.save_sql_generation_guide_draft("
                "%s,%s,'user',%s,NULL,%s,NULL)",
                (
                    ENTRA_TENANT_ID,
                    ENTRA_OBJECT_ID,
                    guide["sql_generation_guide_id"],
                    "Synthetic custom SQL guidance.",
                ),
            ).fetchone()
        )
        connection.execute(
            "SELECT * FROM application.transition_sql_generation_guide_version(%s,%s,'user',%s,"
            "'draft','published')",
            (
                ENTRA_TENANT_ID,
                ENTRA_OBJECT_ID,
                version["sql_generation_guide_version_id"],
            ),
        )
    with pytest.raises(RaiseException, match="will not replace an existing default"):
        _apply_sql(guide_database, _guide_seed())
    _seed_mapping_scope(guide_database, dimensional=False, create_run=False)
    with pytest.raises(RaiseException, match="will not replace an existing default"):
        _apply_sql(guide_database, _guide_seed())
    with guide_database.connect_owner() as connection:
        preserved = require_row(
            connection.execute(
                "SELECT guide.sql_generation_guide_code, version.sql_generation_guide_digest "
                "FROM application.sql_generation_guide guide "
                "JOIN application.sql_generation_guide_version version "
                "USING(sql_generation_guide_id)"
            ).fetchone()
        )
    assert preserved["sql_generation_guide_code"] == "custom.fixture"
    assert preserved["sql_generation_guide_digest"] == version["sql_generation_guide_digest"]


async def test_seed_with_existing_model_preserves_mapping_and_supports_code_run(
    guide_database: DisposablePostgres,
) -> None:
    _seed_super_admin(guide_database)
    _apply_sql(guide_database, REFERENCE_SEED.read_text())
    _apply_sql(guide_database, _render_seed())
    scope = _seed_mapping_scope(guide_database, dimensional=False, create_run=False)
    # Installing guidance must not rewrite the Model or its applied Mapping.
    snapshot_query = """
        SELECT to_jsonb(model) AS model,
               (SELECT jsonb_agg(to_jsonb(mapping) ORDER BY mapping_object_id)
                  FROM workflow.mapping_object mapping
                 WHERE mapping.model_id = model.model_id) AS objects,
               (SELECT jsonb_agg(to_jsonb(attribute) ORDER BY mapping_attribute_id)
                  FROM workflow.mapping_attribute attribute
                 WHERE attribute.model_id = model.model_id) AS attributes
          FROM model.model model WHERE model.model_id = %s
    """
    with guide_database.connect_owner() as connection:
        before = require_row(connection.execute(snapshot_query, (scope.plan.model_id,)).fetchone())
    _apply_sql(guide_database, _guide_seed())
    with guide_database.connect_owner() as connection:
        assert connection.execute(snapshot_query, (scope.plan.model_id,)).fetchone() == before
    with guide_database.connect_owner() as connection:
        actor = require_row(
            connection.execute(
                "SELECT entra_tenant_id, entra_object_id FROM security.entra_principal_identity "
                "WHERE principal_id=%s",
                (scope.plan.actor_principal_id,),
            ).fetchone()
        )
        acquired = require_row(
            connection.execute(
                "SELECT acquired FROM security.acquire_tenant_lock(%s,%s,'user',%s,60,"
                "'Synthetic Code selection verification')",
                (actor["entra_tenant_id"], actor["entra_object_id"], scope.tenant_id),
            ).fetchone()
        )
        systems = connection.execute(
            "SELECT system_id, system_code FROM core.system WHERE system_id=ANY(%s)",
            ([scope.source_system_id, scope.other_system_id],),
        ).fetchall()
        guide = require_row(
            connection.execute(
                "SELECT version.sql_generation_guide_version_id, "
                "version.sql_generation_guide_digest "
                "FROM application.sql_generation_guide guide "
                "JOIN application.sql_generation_guide_version version "
                "USING(sql_generation_guide_id) "
                "WHERE guide.is_default AND version.sql_generation_guide_version_status='published'"
            ).fetchone()
        )
    assert acquired["acquired"]
    codes = {row["system_id"]: str(row["system_code"]) for row in systems}
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=cast(UUID, actor["entra_tenant_id"]),
        entra_object_id=cast(UUID, actor["entra_object_id"]),
    )
    database = WebPostgresDatabase(
        dsn=guide_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    commands = DatabaseWorkflowCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    base = CreateWorkflowRunRequest(
        expected_model_revision=1,
        model_workflow="code_generation",
        selected_entity_ids=[scope.logical_entity_id],
        modeled_entity_type="logical_entity",
        code_generation_coverage_mode="selected_targets",
        selected_system_codes=[codes[scope.source_system_id]],
        agent=AgentRunSelection(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="foundry-primary",
            reasoning_effort_code="none",
            max_turns=8,
            validation_retry_count=1,
        ),
    )
    await database.open()
    try:
        with pytest.raises(WorkbenchError) as failure:
            await commands.create_run(
                principal,
                tenant_id=scope.tenant_id,
                model_id=scope.plan.model_id,
                correlation_id=uuid4(),
                command=base.model_copy(
                    update={
                        "selected_system_codes": [
                            codes[scope.source_system_id],
                            codes[scope.other_system_id],
                        ]
                    }
                ),
            )
        assert failure.value.code == "code_system_unavailable"
        created = await commands.create_run(
            principal,
            tenant_id=scope.tenant_id,
            model_id=scope.plan.model_id,
            correlation_id=uuid4(),
            command=base,
        )
        assert created.created
        with guide_database.connect_owner() as connection:
            frozen = require_row(
                connection.execute(
                    "SELECT sql_generation_guide_version_id, sql_generation_guide_digest "
                    "FROM application.workflow_run WHERE workflow_run_id=%s",
                    (created.workflow_run_id,),
                ).fetchone()
            )
        assert frozen == guide
        # Replay after Model/Run creation must preserve the run's exact Guide version.
        _apply_sql(guide_database, _guide_seed())
        with guide_database.connect_owner() as connection:
            assert connection.execute(snapshot_query, (scope.plan.model_id,)).fetchone() == before
            assert (
                require_row(
                    connection.execute(
                        "SELECT sql_generation_guide_version_id, sql_generation_guide_digest "
                        "FROM application.workflow_run WHERE workflow_run_id=%s",
                        (created.workflow_run_id,),
                    ).fetchone()
                )
                == frozen
            )
            assert (
                require_row(
                    connection.execute(
                        "SELECT count(*) AS count FROM application.sql_generation_guide_version"
                    ).fetchone()
                )["count"]
                == 1
            )
    finally:
        await database.close()
