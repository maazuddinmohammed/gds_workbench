"""Global Mapping templates use governed creation and freeze only new runs."""

from __future__ import annotations

# Shared disposable fixture builders intentionally reuse module-private helpers.
# pyright: reportPrivateUsage=false
import json
from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import uuid4

import pytest
from psycopg.errors import RaiseException

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres, TestRow

SEED = Path(__file__).parents[2] / "database/seed/07_global_mapping_output_templates.template.sql"
PROPOSAL = (
    Path(__file__).parents[2] / "docs/workflow-prompts/mapping.output-templates.proposal.json"
)


def seed_mapping_output_templates(database: DisposablePostgres) -> None:
    """Install the real seed under a fixture-created Super Admin identity."""
    with database.connect_owner() as connection:
        identity = connection.execute(
            """
            SELECT identity.entra_tenant_id, identity.entra_object_id
              FROM security.entra_principal_identity AS identity
              JOIN security.principal AS principal USING (principal_id, principal_type)
             WHERE principal.principal_display_name = 'Mapping template fixture administrator'
               AND principal.is_super_admin AND principal.is_active AND identity.is_active
             LIMIT 1
            """
        ).fetchone()
        if identity is None:
            tenant_id, object_id = uuid4(), uuid4()
            principal = require_row(
                connection.execute(
                    """
                    INSERT INTO security.principal (
                        principal_type, principal_display_name, principal_email, is_super_admin
                    ) VALUES ('user', 'Mapping template fixture administrator', %s, TRUE)
                    RETURNING principal_id
                    """,
                    (f"mapping_seed_{object_id.hex}@example.test",),
                ).fetchone()
            )
            connection.execute(
                """
                INSERT INTO security.entra_principal_identity (
                    principal_id, principal_type, entra_tenant_id, entra_object_id
                ) VALUES (%s, 'user', %s, %s)
                """,
                (principal["principal_id"], tenant_id, object_id),
            )
        else:
            tenant_id, object_id = identity["entra_tenant_id"], identity["entra_object_id"]
        seed = (
            SEED.read_text()
            .replace("__REPLACE_WITH_ENTRA_TENANT_ID__", str(tenant_id))
            .replace("__REPLACE_WITH_ENTRA_OBJECT_ID__", str(object_id))
            .replace("__REPLACE_WITH_PRINCIPAL_TYPE__", "user")
        )
        connection.execute(cast(LiteralString, seed))


def _snapshot(database: DisposablePostgres) -> list[TestRow]:
    with database.connect_owner() as connection:
        return connection.execute(
            """
            SELECT template.*, jsonb_agg(
                to_jsonb(field) - 'output_template_field_id' - 'output_template_id'
                ORDER BY field.output_template_field_order
            ) AS fields
              FROM application.output_template AS template
              JOIN application.output_template_field AS field USING (output_template_id)
             WHERE output_template_code IN ('mapping_object_default', 'mapping_attribute_default')
             GROUP BY template.output_template_id
             ORDER BY template.output_template_code
            """
        ).fetchall()


def test_seed_matches_confirmed_fields_and_exact_replay_changes_nothing(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    database = bootstrap_postgres_database
    seed_mapping_output_templates(database)
    before = _snapshot(database)
    seed_mapping_output_templates(database)
    assert _snapshot(database) == before
    expected = {
        item["output_template_code"]: item for item in json.loads(PROPOSAL.read_text())["templates"]
    }
    assert len(before) == 2
    for row in before:
        template = expected[row["output_template_code"]]
        assert row["output_template_target_type"] == template["output_template_target_type"]
        assert len(row["fields"]) == len(template["fields"])
        for actual, expected_field in zip(row["fields"], template["fields"], strict=True):
            assert {key: actual[key] for key in expected_field} == expected_field
        assert row["is_active"] is True
        assert len(row["output_template_schema_digest"]) == 64


def test_seed_requires_explicit_authorized_identity(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    with (
        bootstrap_postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="replace every"),
    ):
        connection.execute(cast(LiteralString, SEED.read_text()))
    rendered = (
        SEED.read_text()
        .replace("__REPLACE_WITH_ENTRA_TENANT_ID__", str(uuid4()))
        .replace("__REPLACE_WITH_ENTRA_OBJECT_ID__", str(uuid4()))
        .replace("__REPLACE_WITH_PRINCIPAL_TYPE__", "user")
    )
    with (
        bootstrap_postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="authorization denied"),
    ):
        connection.execute(cast(LiteralString, rendered))


def test_changed_seed_refuses_to_overwrite_existing_templates(
    bootstrap_postgres_database: DisposablePostgres,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = bootstrap_postgres_database
    seed_mapping_output_templates(database)
    before = _snapshot(database)
    changed_seed = tmp_path / "changed_mapping_seed.sql"
    changed_seed.write_text(
        SEED.read_text().replace("Default Object Mapping", "Changed Object Mapping")
    )
    monkeypatch.setattr(f"{__name__}.SEED", changed_seed)
    with pytest.raises(RaiseException, match="Output Template code conflict"):
        seed_mapping_output_templates(database)
    assert _snapshot(database) == before


@pytest.mark.parametrize("dimensional", (False, True), ids=("logical", "dimensional"))
@pytest.mark.parametrize("custom", ("none", "object", "attribute", "both"))
def test_new_mapping_runs_freeze_global_defaults_with_independent_custom_overrides(
    bootstrap_postgres_database: DisposablePostgres,
    dimensional: bool,
    custom: str,
) -> None:
    from tests.mcp.test_database_mapping_workflow_run import (
        CREATE_MAPPING_RUN_SQL,
        _parameters,
        _seed_mapping_context,
        _seed_output_template,
    )

    database = bootstrap_postgres_database
    context = _seed_mapping_context(database, dimensional=dimensional)
    defaults = {row["output_template_target_type"]: row for row in _snapshot(database)}
    with database.connect_owner() as connection:
        object_override = (
            _seed_output_template(connection, context, "mapping_object")
            if custom in {"object", "both"}
            else None
        )
        attribute_override = (
            _seed_output_template(connection, context, "mapping_attribute")
            if custom in {"attribute", "both"}
            else None
        )
        run = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                _parameters(
                    context,
                    correlation_id=uuid4(),
                    object_template_id=object_override[0] if object_override else None,
                    attribute_template_id=attribute_override[0] if attribute_override else None,
                ),
            ).fetchone()
        )
        frozen = require_row(
            connection.execute(
                "SELECT * FROM application.workflow_run WHERE workflow_run_id = %s",
                (run["workflow_run_id"],),
            ).fetchone()
        )
    assert frozen["mapping_route"] == (
        "dimensional_to_gold" if dimensional else "logical_to_silver"
    )
    for target_type, override in (
        ("mapping_object", object_override),
        ("mapping_attribute", attribute_override),
    ):
        assert frozen[f"{target_type}_output_template_id"] == (
            override[0] if override else defaults[target_type]["output_template_id"]
        )
        assert frozen[f"{target_type}_output_template_schema_digest"] == (
            override[1] if override else defaults[target_type]["output_template_schema_digest"]
        )


@pytest.mark.parametrize("target", ("Object", "Attribute"))
def test_replay_keeps_frozen_defaults_when_current_default_is_unavailable(
    bootstrap_postgres_database: DisposablePostgres,
    target: str,
) -> None:
    from tests.mcp.test_database_mapping_workflow_run import (
        CREATE_MAPPING_RUN_SQL,
        _parameters,
        _seed_mapping_context,
    )

    database = bootstrap_postgres_database
    context = _seed_mapping_context(database)
    parameters = _parameters(context, correlation_id=uuid4())
    with database.connect_owner() as connection:
        created = require_row(connection.execute(CREATE_MAPPING_RUN_SQL, parameters).fetchone())
        frozen = require_row(
            connection.execute(
                "SELECT * FROM application.workflow_run WHERE workflow_run_id = %s",
                (created["workflow_run_id"],),
            ).fetchone()
        )
    with database.connect_owner() as connection, connection.transaction(force_rollback=True):
        connection.execute(
            """
            UPDATE application.output_template SET is_active = FALSE
             WHERE output_template_code = %s
            """,
            (f"mapping_{target.lower()}_default",),
        )
        replay = require_row(connection.execute(CREATE_MAPPING_RUN_SQL, parameters).fetchone())
        assert replay["created"] is False
        assert replay["workflow_run_id"] == created["workflow_run_id"]
        assert (
            connection.execute(
                "SELECT * FROM application.workflow_run WHERE workflow_run_id = %s",
                (created["workflow_run_id"],),
            ).fetchone()
            == frozen
        )
        with (
            pytest.raises(RaiseException, match=f"Global default Mapping {target}"),
            connection.transaction(),
        ):
            connection.execute(CREATE_MAPPING_RUN_SQL, _parameters(context, correlation_id=uuid4()))
