from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import CheckViolation, InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres

type TestRow = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ProjectMutationContext:
    entra_tenant_id: UUID
    entra_object_id: UUID
    tenant_id: int
    principal_id: int


CREATE_PROJECT_SQL: LiteralString = """
    SELECT *
      FROM application.create_project(
          %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
          %s::VARCHAR, %s::VARCHAR, '[]'::JSONB, '[]'::JSONB, %s::TEXT, %s::JSONB,
          %s::TEXT, %s::JSONB, %s::JSONB,
          %s::VARCHAR, %s::VARCHAR, %s::VARCHAR, %s::VARCHAR,
          %s::INTEGER, %s::INTEGER, %s::VARCHAR, %s::VARCHAR
      )
"""

UPDATE_PROJECT_SQL: LiteralString = """
    SELECT *
      FROM application.update_project(
          %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT, %s::BIGINT,
          %s::VARCHAR, %s::VARCHAR, '[]'::JSONB, '[]'::JSONB, %s::TEXT, %s::JSONB,
          %s::TEXT, %s::JSONB, %s::JSONB,
          %s::VARCHAR, %s::VARCHAR, %s::VARCHAR, %s::VARCHAR,
          %s::INTEGER, %s::INTEGER, %s::VARCHAR, %s::VARCHAR
      )
"""

ARCHIVE_PROJECT_SQL: LiteralString = """
    SELECT *
      FROM application.archive_project(
          %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT, %s::BIGINT
      )
"""


def _seed_context(postgres_database: DisposablePostgres) -> ProjectMutationContext:
    suffix = uuid4().hex
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with postgres_database.connect_owner() as connection:
        lane_id = require_row(
            connection.execute(
                """
                INSERT INTO core.lane (lane_code, lane_name)
                VALUES (%s, %s)
                RETURNING lane_id
                """,
                (f"project_project_{suffix}", f"Project Project {suffix}"),
            ).fetchone()
        )["lane_id"]
        tenant_id = require_row(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    lane_id, tenant_code, tenant_name,
                    tenant_catalog, gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    lane_id,
                    f"project_tenant_{suffix}",
                    f"Project Tenant {suffix}",
                    f"project_catalog_{suffix}",
                    f"project_admin_{suffix}",
                ),
            ).fetchone()
        )["tenant_id"]
        principal_id = require_row(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type, principal_display_name, principal_email
                ) VALUES ('user', %s, %s)
                RETURNING principal_id
                """,
                (f"Project Architect {suffix}", f"project_{suffix}@example.test"),
            ).fetchone()
        )["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id, principal_type, entra_tenant_id, entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id, principal_id, tenant_role, granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id, locked_by_principal_id,
                tenant_lock_purpose, tenant_lock_expires_time
            ) VALUES (
                %s, %s, 'Project authoring', CURRENT_TIMESTAMP + INTERVAL '1 hour'
            )
            """,
            (tenant_id, principal_id),
        )
    return ProjectMutationContext(
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        tenant_id=tenant_id,
        principal_id=principal_id,
    )


def _connect_web(
    postgres_database: DisposablePostgres,
) -> psycopg.Connection[TestRow]:
    connection = psycopg.Connection[TestRow].connect(
        postgres_database.web_runtime_dsn(), row_factory=dict_row
    )
    connection.execute("SET ROLE gds_web_write")
    return connection


def _create_project(
    postgres_database: DisposablePostgres,
    context: ProjectMutationContext,
    logical_entity_scd_type: str | None = None,
    dimensional_entity_scd_type: str | None = None,
) -> TestRow:
    with _connect_web(postgres_database) as connection:
        return require_row(
            connection.execute(
                CREATE_PROJECT_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    context.tenant_id,
                    "Customer 360",
                    "Cross-system customer project",
                    "Use clear business names.",
                    '[{"name":"CreatedTime","type":"timestamp"}]',
                    "Use dimensional business names.",
                    '[{"name":"EffectiveDate","type":"date"}]',
                    '[{"name":"UpdatedTime","type":"timestamp"}]',
                    "openai_agents_sdk",
                    "microsoft_foundry",
                    "project-1",
                    "medium",
                    12,
                    2,
                    logical_entity_scd_type,
                    dimensional_entity_scd_type,
                ),
            ).fetchone()
        )


def _update_parameters(
    context: ProjectMutationContext,
    created: TestRow,
    *,
    revision: int | None,
    name: str,
    preserve_values: bool = False,
) -> tuple[object, ...]:
    if preserve_values:
        return (
            context.entra_tenant_id,
            context.entra_object_id,
            created["project_id"],
            revision,
            created["project_name"],
            created["project_description"],
            created["silver_model_naming_instructions"],
            '[{"name":"CreatedTime","type":"timestamp"}]',
            created["gold_model_naming_instructions"],
            '[{"name":"EffectiveDate","type":"date"}]',
            '[{"name":"UpdatedTime","type":"timestamp"}]',
            created["default_agent_sdk_code"],
            created["default_agent_provider_code"],
            created["default_agent_model_code"],
            created["default_reasoning_effort_code"],
            created["default_max_turns"],
            created["default_validation_retry_count"],
            created["logical_entity_scd_type"],
            created["dimensional_entity_scd_type"],
        )
    return (
        context.entra_tenant_id,
        context.entra_object_id,
        created["project_id"],
        revision,
        name,
        "Curated customer domain",
        "Prefer complete business terms.",
        '[{"name":"CreatedTime","type":"timestamp"}]',
        "Prefer dimensional business terms.",
        '[{"name":"EffectiveDate","type":"date"}]',
        '[{"name":"UpdatedTime","type":"timestamp"}]',
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_web_can_create_tenant_owned_project_with_agent_defaults(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_project(postgres_database, context)
    assert created["tenant_id"] == context.tenant_id
    assert created["project_name"] == "Customer 360"
    assert created["project_revision"] == 1
    assert created["default_agent_model_code"] == "project-1"
    assert created["default_validation_retry_count"] == 2
    assert created["is_active"] is True


def test_web_can_update_project_and_advance_revision_once(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_project(postgres_database, context)
    with _connect_web(postgres_database) as connection:
        updated = require_row(
            connection.execute(
                UPDATE_PROJECT_SQL,
                _update_parameters(
                    context,
                    created,
                    revision=created["project_revision"],
                    name="Customer Domain",
                ),
            ).fetchone()
        )
    assert updated["project_name"] == "Customer Domain"
    assert updated["project_revision"] == 2
    assert updated["default_agent_sdk_code"] is None


def test_equivalent_project_update_is_revision_stable(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_project(postgres_database, context)
    with _connect_web(postgres_database) as connection:
        unchanged = require_row(
            connection.execute(
                UPDATE_PROJECT_SQL,
                _update_parameters(
                    context,
                    created,
                    revision=created["project_revision"],
                    name="Customer 360",
                    preserve_values=True,
                ),
            ).fetchone()
        )
    assert unchanged["project_revision"] == 1
    assert unchanged["updated_time"] == created["updated_time"]


@pytest.mark.parametrize("revision", (None, 999))
def test_project_update_rejects_missing_or_stale_revision(
    postgres_database: DisposablePostgres,
    revision: int | None,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_project(postgres_database, context)
    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="stale_project_revision"),
    ):
        connection.execute(
            UPDATE_PROJECT_SQL,
            _update_parameters(
                context,
                created,
                revision=revision,
                name="Stale Change",
            ),
        )
    with postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                "SELECT project_name, project_revision FROM project.project WHERE project_id = %s",
                (created["project_id"],),
            ).fetchone()
        )
    assert stored == {"project_name": "Customer 360", "project_revision": 1}


def test_web_can_archive_project_and_advance_revision_once(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_project(postgres_database, context)
    with _connect_web(postgres_database) as connection:
        archived = require_row(
            connection.execute(
                ARCHIVE_PROJECT_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["project_id"],
                    created["project_revision"],
                ),
            ).fetchone()
        )
    assert archived["is_active"] is False
    assert archived["project_revision"] == 2


def test_project_mutation_derives_owner_from_project(
    postgres_database: DisposablePostgres,
) -> None:
    owner = _seed_context(postgres_database)
    other = _seed_context(postgres_database)
    created = _create_project(postgres_database, owner)
    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="authorization_denied"),
    ):
        connection.execute(
            ARCHIVE_PROJECT_SQL,
            (
                other.entra_tenant_id,
                other.entra_object_id,
                created["project_id"],
                created["project_revision"],
            ),
        )


def test_web_role_has_no_direct_project_mutation(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    _create_project(postgres_database, context)
    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute(
            "INSERT INTO project.project (tenant_id, project_name) VALUES (%s, 'Direct')",
            (context.tenant_id,),
        )


def test_logical_scd_choice_persists_and_is_revision_fenced(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    stored = _create_project(
        postgres_database, context, logical_entity_scd_type="type_2"
    )
    assert stored["logical_entity_scd_type"] == "type_2"
    for choice in ("type_1", None):
        parameters = _update_parameters(
            context,
            stored,
            revision=stored["project_revision"],
            name=stored["project_name"],
            preserve_values=True,
        )
        with _connect_web(postgres_database) as connection:
            updated = require_row(
                connection.execute(
                    UPDATE_PROJECT_SQL, parameters[:-2] + (choice, parameters[-1])
                ).fetchone()
            )
        assert updated["logical_entity_scd_type"] == choice
        assert updated["project_revision"] == stored["project_revision"] + 1
        with (
            _connect_web(postgres_database) as connection,
            pytest.raises(RaiseException, match="stale_project_revision"),
        ):
            connection.execute(UPDATE_PROJECT_SQL, parameters)
        with _connect_web(postgres_database) as connection:
            unchanged = require_row(
                connection.execute(
                    UPDATE_PROJECT_SQL,
                    _update_parameters(
                        context,
                        updated,
                        revision=updated["project_revision"],
                        name=updated["project_name"],
                        preserve_values=True,
                    ),
                ).fetchone()
            )
        assert unchanged["project_revision"] == updated["project_revision"]
        stored = updated


def test_database_rejects_unknown_logical_scd_choice(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    with pytest.raises(CheckViolation, match="ck_project_logical_entity_scd_type"):
        _create_project(postgres_database, context, logical_entity_scd_type="type_3")


def test_dimensional_scd_choice_persists_and_is_revision_fenced(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    stored = _create_project(
        postgres_database,
        context,
        dimensional_entity_scd_type="type_2",
        logical_entity_scd_type="type_1",
    )
    assert stored["dimensional_entity_scd_type"] == "type_2"
    for choice in ("type_1", None):
        parameters = _update_parameters(
            context,
            stored,
            revision=stored["project_revision"],
            name=stored["project_name"],
            preserve_values=True,
        )
        with _connect_web(postgres_database) as connection:
            updated = require_row(
                connection.execute(
                    UPDATE_PROJECT_SQL, parameters[:-1] + (choice,)
                ).fetchone()
            )
        assert updated["dimensional_entity_scd_type"] == choice
        assert updated["logical_entity_scd_type"] == "type_1"
        assert updated["project_revision"] == stored["project_revision"] + 1
        with (
            _connect_web(postgres_database) as connection,
            pytest.raises(RaiseException, match="stale_project_revision"),
        ):
            connection.execute(UPDATE_PROJECT_SQL, parameters)
        with _connect_web(postgres_database) as connection:
            unchanged = require_row(
                connection.execute(
                    UPDATE_PROJECT_SQL,
                    _update_parameters(
                        context,
                        updated,
                        revision=updated["project_revision"],
                        name=updated["project_name"],
                        preserve_values=True,
                    ),
                ).fetchone()
            )
        assert unchanged["project_revision"] == updated["project_revision"]
        stored = updated


def test_database_rejects_unknown_dimensional_scd_choice(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    with pytest.raises(CheckViolation, match="ck_project_dimensional_entity_scd_type"):
        _create_project(
            postgres_database, context, dimensional_entity_scd_type="type_3"
        )
