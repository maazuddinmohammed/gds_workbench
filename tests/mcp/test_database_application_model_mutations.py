from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres

type TestRow = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelMutationContext:
    entra_tenant_id: UUID
    entra_object_id: UUID
    tenant_id: int
    principal_id: int


CREATE_MODEL_SQL: LiteralString = """
    SELECT *
      FROM application.create_model(
          %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
          %s::VARCHAR, %s::VARCHAR, %s::TEXT, %s::JSONB,
          %s::TEXT, %s::JSONB, %s::JSONB,
          %s::VARCHAR, %s::VARCHAR, %s::VARCHAR, %s::VARCHAR,
          %s::INTEGER, %s::INTEGER
      )
"""

UPDATE_MODEL_SQL: LiteralString = """
    SELECT *
      FROM application.update_model(
          %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT, %s::BIGINT,
          %s::VARCHAR, %s::VARCHAR, %s::TEXT, %s::JSONB,
          %s::TEXT, %s::JSONB, %s::JSONB,
          %s::VARCHAR, %s::VARCHAR, %s::VARCHAR, %s::VARCHAR,
          %s::INTEGER, %s::INTEGER
      )
"""

ARCHIVE_MODEL_SQL: LiteralString = """
    SELECT *
      FROM application.archive_model(
          %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT, %s::BIGINT
      )
"""


def _seed_context(postgres_database: DisposablePostgres) -> ModelMutationContext:
    suffix = uuid4().hex
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with postgres_database.connect_owner() as connection:
        project_id = require_row(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"model_project_{suffix}", f"Model Project {suffix}"),
            ).fetchone()
        )["project_id"]
        tenant_id = require_row(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id, tenant_code, tenant_name,
                    tenant_catalog, gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    f"model_tenant_{suffix}",
                    f"Model Tenant {suffix}",
                    f"model_catalog_{suffix}",
                    f"model_admin_{suffix}",
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
                (f"Model Architect {suffix}", f"model_{suffix}@example.test"),
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
                %s, %s, 'Model authoring', CURRENT_TIMESTAMP + INTERVAL '1 hour'
            )
            """,
            (tenant_id, principal_id),
        )
    return ModelMutationContext(
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


def _create_model(
    postgres_database: DisposablePostgres,
    context: ModelMutationContext,
) -> TestRow:
    with _connect_web(postgres_database) as connection:
        return require_row(
            connection.execute(
                CREATE_MODEL_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    context.tenant_id,
                    "Customer 360",
                    "Cross-system customer model",
                    "Use clear business names.",
                    '[{"name":"CreatedTime","type":"timestamp"}]',
                    "Use dimensional business names.",
                    '[{"name":"EffectiveDate","type":"date"}]',
                    '[{"name":"UpdatedTime","type":"timestamp"}]',
                    "openai_agents_sdk",
                    "microsoft_foundry",
                    "model-1",
                    "medium",
                    12,
                    2,
                ),
            ).fetchone()
        )


def _update_parameters(
    context: ModelMutationContext,
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
            created["model_id"],
            revision,
            created["model_name"],
            created["model_description"],
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
        )
    return (
        context.entra_tenant_id,
        context.entra_object_id,
        created["model_id"],
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
    )


def test_web_can_create_tenant_owned_model_with_agent_defaults(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_model(postgres_database, context)
    assert created["tenant_id"] == context.tenant_id
    assert created["model_name"] == "Customer 360"
    assert created["model_revision"] == 1
    assert created["default_agent_model_code"] == "model-1"
    assert created["default_validation_retry_count"] == 2
    assert created["is_active"] is True


def test_web_can_update_model_and_advance_revision_once(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_model(postgres_database, context)
    with _connect_web(postgres_database) as connection:
        updated = require_row(
            connection.execute(
                UPDATE_MODEL_SQL,
                _update_parameters(
                    context,
                    created,
                    revision=created["model_revision"],
                    name="Customer Domain",
                ),
            ).fetchone()
        )
    assert updated["model_name"] == "Customer Domain"
    assert updated["model_revision"] == 2
    assert updated["default_agent_sdk_code"] is None


def test_equivalent_model_update_is_revision_stable(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_model(postgres_database, context)
    with _connect_web(postgres_database) as connection:
        unchanged = require_row(
            connection.execute(
                UPDATE_MODEL_SQL,
                _update_parameters(
                    context,
                    created,
                    revision=created["model_revision"],
                    name="Customer 360",
                    preserve_values=True,
                ),
            ).fetchone()
        )
    assert unchanged["model_revision"] == 1
    assert unchanged["updated_time"] == created["updated_time"]


@pytest.mark.parametrize("revision", (None, 999))
def test_model_update_rejects_missing_or_stale_revision(
    postgres_database: DisposablePostgres,
    revision: int | None,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_model(postgres_database, context)
    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="stale_model_revision"),
    ):
        connection.execute(
            UPDATE_MODEL_SQL,
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
                "SELECT model_name, model_revision FROM model.model WHERE model_id = %s",
                (created["model_id"],),
            ).fetchone()
        )
    assert stored == {"model_name": "Customer 360", "model_revision": 1}


def test_web_can_archive_model_and_advance_revision_once(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    created = _create_model(postgres_database, context)
    with _connect_web(postgres_database) as connection:
        archived = require_row(
            connection.execute(
                ARCHIVE_MODEL_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                ),
            ).fetchone()
        )
    assert archived["is_active"] is False
    assert archived["model_revision"] == 2


def test_model_mutation_derives_owner_from_model(
    postgres_database: DisposablePostgres,
) -> None:
    owner = _seed_context(postgres_database)
    other = _seed_context(postgres_database)
    created = _create_model(postgres_database, owner)
    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="authorization_denied"),
    ):
        connection.execute(
            ARCHIVE_MODEL_SQL,
            (
                other.entra_tenant_id,
                other.entra_object_id,
                created["model_id"],
                created["model_revision"],
            ),
        )


def test_web_role_has_no_direct_model_mutation(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_context(postgres_database)
    _create_model(postgres_database, context)
    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute(
            "INSERT INTO model.model (tenant_id, model_name) VALUES (%s, 'Direct')",
            (context.tenant_id,),
        )
