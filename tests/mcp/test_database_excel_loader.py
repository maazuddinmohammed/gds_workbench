from __future__ import annotations

import re
import secrets
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, LiteralString, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

REPOSITORY_ROOT = Path(__file__).parents[2]
LOADER_ROOT = REPOSITORY_ROOT / "load_and_merge_scripts"
sys.path.insert(0, str(LOADER_ROOT))
import loader  # noqa: E402

if TYPE_CHECKING:
    from conftest import DisposablePostgres


CONFIG_PATH = REPOSITORY_ROOT / "load_and_merge_scripts" / "load_config.yaml"
TablePrivileges = Literal["SELECT", "INSERT, UPDATE", "UPDATE", "INSERT"]


def _returned_int(row: tuple[Any, ...] | None) -> int:
    assert row is not None
    value = row[0]
    assert isinstance(value, int)
    return value


def _configured_definitions() -> tuple[loader.LoadDefinition, ...]:
    """Read the generated config shape without adding PyYAML to the MCP runtime."""
    text = CONFIG_PATH.read_text(encoding="utf-8")
    blocks = re.findall(
        r"(?ms)^  - workbook: (?P<workbook>\S+)\n(?P<body>.*?)(?=^  - workbook: |\Z)",
        text,
    )
    definitions: list[loader.LoadDefinition] = []
    for workbook, body in blocks:
        sheet = _config_scalar(body, "sheet")
        schema = _config_scalar(body, "schema")
        table = _config_scalar(body, "table")
        order = int(_config_scalar(body, "dependency_order"))
        column_match = re.search(
            r"(?ms)^    columns:\n(?P<items>(?:      - [a-z][a-z0-9_]*\n)+)", body
        )
        assert column_match is not None
        columns = tuple(
            re.findall(r"(?m)^      - ([a-z][a-z0-9_]*)$", column_match.group("items"))
        )
        definition = loader.LoadDefinition(
            workbook=workbook,
            sheet=sheet,
            schema=schema,
            table=table,
            dependency_order=order,
            columns=columns,
            required_columns=(),
            source_key=(columns[0],),
            merge_statements=_config_statements(body, "merge_statements"),
            deferred_statements=_config_statements(body, "deferred_statements"),
        )
        loader.validate_definition(definition)
        definitions.append(definition)

    definitions.sort(key=lambda value: value.dependency_order)
    assert len(definitions) == 41
    assert len({definition.selection for definition in definitions}) == 41
    assert {definition.selection for definition in definitions} == set(
        loader.ALLOWED_LOAD_TARGETS
    )
    assert sum(len(definition.merge_statements) for definition in definitions) == 41
    assert sum(len(definition.deferred_statements) for definition in definitions) == 2
    return tuple(definitions)


def _config_scalar(body: str, name: str) -> str:
    match = re.search(rf"(?m)^    {name}: (.+)$", body)
    assert match is not None
    return match.group(1).strip()


def _config_statements(body: str, name: str) -> tuple[str, ...]:
    section_match = re.search(rf"(?m)^    {name}:\n", body)
    if section_match is None:
        return ()
    remainder = body[section_match.end() :]
    next_key = re.search(r"(?m)^(?:    [a-z_]+:| {0,3}\S)", remainder)
    section = remainder[: next_key.start()] if next_key is not None else remainder
    return tuple(
        textwrap.dedent(chunk).strip()
        for chunk in re.split(r"(?m)^      - \|\n", section)[1:]
    )


def _provision_loader_role(
    connection: psycopg.Connection[Any],
    postgres_database: DisposablePostgres,
    role_name: str,
    password: str,
    definitions: tuple[loader.LoadDefinition, ...],
) -> None:
    connection.execute(
        "SELECT set_config('gds.test_loader_password', %s, true)", (password,)
    )
    connection.execute(
        sql.SQL(
            "DO $create_loader$ BEGIN EXECUTE format("
            "'CREATE ROLE %I LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS PASSWORD %L', {}, "
            "current_setting('gds.test_loader_password')); END; $create_loader$"
        ).format(
            sql.Literal(role_name),
        )
    )
    connection.execute(
        sql.SQL("GRANT CONNECT, TEMPORARY ON DATABASE {} TO {}").format(
            sql.Identifier(postgres_database.database), sql.Identifier(role_name)
        )
    )

    targets = {(definition.schema, definition.table) for definition in definitions}
    read_tables = (
        targets
        | set(loader.BOOTSTRAP_ACTIVITY_TABLES)
        | {(schema, table) for schema, table, _ in loader.LOCK_TARGETS}
        | {
            ("core", "connection"),
            ("model", "model"),
            ("model", "model_revision_transaction"),
            ("security", "entra_principal_identity"),
            ("security", "principal"),
        }
    )
    schemas = sorted({schema for schema, _ in read_tables})
    connection.execute(
        sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
            sql.SQL(", ").join(sql.Identifier(schema) for schema in schemas),
            sql.Identifier(role_name),
        )
    )
    _grant_tables(connection, role_name, "SELECT", read_tables)
    _grant_tables(connection, role_name, "INSERT, UPDATE", targets)
    _grant_tables(
        connection,
        role_name,
        "UPDATE",
        {(schema, table) for schema, table, _ in loader.LOCK_TARGETS}
        | {("model", "model")},
    )
    _grant_tables(
        connection,
        role_name,
        "INSERT",
        {("model", "model_revision_transaction")},
    )
    _grant_target_sequences(connection, role_name, targets)
    connection.execute(
        sql.SQL("GRANT EXECUTE ON FUNCTION reference.is_nonblank(TEXT) TO {}").format(
            sql.Identifier(role_name)
        )
    )
    connection.execute(
        sql.SQL(
            "GRANT EXECUTE ON FUNCTION security.authorize_tenant_operation("
            "UUID, UUID, VARCHAR, BIGINT, VARCHAR) TO {}"
        ).format(sql.Identifier(role_name))
    )
    connection.execute(
        sql.SQL(
            "GRANT EXECUTE ON FUNCTION security.acquire_tenant_lock("
            "UUID, UUID, VARCHAR, BIGINT, INTEGER, VARCHAR) TO {}"
        ).format(sql.Identifier(role_name))
    )
    connection.execute(
        sql.SQL("GRANT SELECT ON public.gds_test_sentinel TO {}").format(
            sql.Identifier(role_name)
        )
    )


def _connect_as_loader(
    postgres_database: DisposablePostgres,
    role_name: str,
    definitions: tuple[loader.LoadDefinition, ...],
) -> psycopg.Connection[Any]:
    password = secrets.token_urlsafe(32)
    with postgres_database.connect_owner() as owner:
        _provision_loader_role(
            owner, postgres_database, role_name, password, definitions
        )

    connection: psycopg.Connection[Any] = psycopg.connect(
        host=postgres_database.host,
        port=postgres_database.port,
        dbname=postgres_database.database,
        user=role_name,
        password=password,
        connect_timeout=5,
    )
    identity = connection.execute(
        "SELECT current_database(), session_user, current_user, "
        "current_setting('server_version_num')::INTEGER / 10000, "
        "(SELECT marker FROM public.gds_test_sentinel)"
    ).fetchone()
    assert identity == (
        postgres_database.database,
        role_name,
        role_name,
        18,
        postgres_database.marker,
    )
    return connection


def _grant_tables(
    connection: psycopg.Connection[Any],
    role_name: str,
    privileges: TablePrivileges,
    tables: set[tuple[str, str]],
) -> None:
    connection.execute(
        sql.SQL("GRANT {} ON TABLE {} TO {}").format(
            sql.SQL(privileges),
            sql.SQL(", ").join(
                sql.Identifier(schema, table) for schema, table in sorted(tables)
            ),
            sql.Identifier(role_name),
        )
    )


def _grant_target_sequences(
    connection: psycopg.Connection[Any],
    role_name: str,
    targets: set[tuple[str, str]],
) -> None:
    target_values = sql.SQL(", ").join(
        sql.SQL("({}, {})").format(sql.Literal(schema), sql.Literal(table))
        for schema, table in sorted(targets)
    )
    sequences = connection.execute(
        sql.SQL(
            "WITH target(schema_name, table_name) AS (VALUES {}) "
            "SELECT sequence_namespace.nspname AS schema_name, "
            "sequence_relation.relname AS sequence_name "
            "FROM pg_depend AS dependency "
            "JOIN pg_class AS sequence_relation ON sequence_relation.oid = dependency.objid "
            "AND sequence_relation.relkind = 'S' "
            "JOIN pg_namespace AS sequence_namespace "
            "ON sequence_namespace.oid = sequence_relation.relnamespace "
            "JOIN pg_class AS table_relation ON table_relation.oid = dependency.refobjid "
            "JOIN pg_namespace AS table_namespace "
            "ON table_namespace.oid = table_relation.relnamespace "
            "JOIN target ON target.schema_name = table_namespace.nspname "
            "AND target.table_name = table_relation.relname "
            "WHERE dependency.deptype IN ('a', 'i')"
        ).format(target_values)
    ).fetchall()
    connection.execute(
        sql.SQL("GRANT USAGE, SELECT ON SEQUENCE {} TO {}").format(
            sql.SQL(", ").join(
                sql.Identifier(row["schema_name"], row["sequence_name"])
                for row in sequences
            ),
            sql.Identifier(role_name),
        )
    )


def test_all_configured_merges_parse_and_environment_is_idempotent(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    postgres_database = bootstrap_postgres_database
    definitions = _configured_definitions()
    role_name = f"gds_excel_loader_{secrets.token_hex(8)}"
    connection = _connect_as_loader(postgres_database, role_name, definitions)
    try:
        loader.execute_prepared_loads(
            connection,
            tuple(loader.PreparedLoad(definition, ()) for definition in definitions),
        )

        environment = next(
            definition
            for definition in definitions
            if definition.selection == ("reference.xlsx", "Environment")
        )
        row_by_column = {
            "environment_code": "INTEGRATION_TEST",
            "environment_name": "Integration Test",
            "environment_description": "Disposable PostgreSQL loader test",
            "is_active": "true",
        }
        row = tuple(row_by_column[column] for column in environment.columns)
        merge = environment.merge_statements[0].replace(
            "{staging_table}", f'pg_temp."{environment.staging_name}"'
        )
        with connection.cursor() as cursor:
            loader.insert_staging_rows(
                cursor, environment.staging_name, environment.columns, (row,)
            )
            cursor.execute(cast(LiteralString, merge))
            assert cursor.rowcount == 1
            cursor.execute(
                sql.SQL(
                    'UPDATE pg_temp.{} SET "environment_name" = %s '
                    'WHERE "environment_code" = %s'
                ).format(sql.Identifier(environment.staging_name)),
                ("Integration Test Updated", "INTEGRATION_TEST"),
            )
            cursor.execute(cast(LiteralString, merge))
            assert cursor.rowcount == 1

        stored = connection.execute(
            "SELECT count(*) AS row_count, min(environment_name) AS environment_name, "
            "min(created_by) AS created_by, min(updated_by) AS updated_by "
            "FROM reference.environment WHERE environment_code = 'INTEGRATION_TEST'"
        ).fetchone()
        assert stored == (1, "Integration Test Updated", role_name, role_name)
    finally:
        connection.rollback()
        connection.close()


def test_bootstrap_loader_refuses_after_a_queued_application_workflow_run(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    postgres_database = bootstrap_postgres_database
    suffix = secrets.token_hex(8)
    with postgres_database.connect_owner() as owner:
        project_id = owner.execute(
            "INSERT INTO core.project (project_code, project_name) "
            "VALUES (%s, %s) RETURNING project_id",
            (f"LOADER_RUN_{suffix}", f"Loader Run {suffix}"),
        ).fetchone()["project_id"]
        tenant_id = owner.execute(
            "INSERT INTO core.tenant "
            "(project_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING tenant_id",
            (
                project_id,
                f"LOADER_RUN_{suffix}",
                f"Loader Run {suffix}",
                f"loader_run_{suffix}",
                f"loader_admin_{suffix}",
            ),
        ).fetchone()["tenant_id"]
        principal_id = owner.execute(
            "INSERT INTO security.principal "
            "(principal_type, principal_display_name, principal_email) "
            "VALUES ('user', %s, %s) RETURNING principal_id",
            (f"Loader Run {suffix}", f"loader-run-{suffix}@example.test"),
        ).fetchone()["principal_id"]
        model_id = owner.execute(
            "INSERT INTO model.model (tenant_id, model_name) "
            "VALUES (%s, %s) RETURNING model_id",
            (tenant_id, f"Loader Run {suffix}"),
        ).fetchone()["model_id"]
        owner.execute(
            "INSERT INTO application.workflow_run "
            "(tenant_id, model_id, model_revision, model_workflow, "
            "actor_principal_id, selected_scope_digest, selected_scope_count, "
            "correlation_id) VALUES (%s, %s, 1, 'profiling', %s, %s, 1, %s)",
            (tenant_id, model_id, principal_id, "0" * 64, str(uuid4())),
        )

    definitions = _configured_definitions()
    environment = next(
        definition
        for definition in definitions
        if definition.selection == ("reference.xlsx", "Environment")
    )
    role_name = f"gds_excel_loader_{secrets.token_hex(8)}"
    connection = _connect_as_loader(postgres_database, role_name, definitions)
    try:
        with pytest.raises(
            loader.LoaderError, match="before governed runtime activity"
        ):
            loader.execute_prepared_loads(
                connection,
                (loader.PreparedLoad(environment, ()),),
            )
    finally:
        connection.rollback()
        connection.close()


def test_model_merge_keeps_naming_text_independent_from_json_templates(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    postgres_database = bootstrap_postgres_database
    definitions = _configured_definitions()
    model = next(
        definition
        for definition in definitions
        if definition.selection == ("model.xlsx", "Model")
    )
    role_name = f"gds_excel_loader_{secrets.token_hex(8)}"
    connection = _connect_as_loader(postgres_database, role_name, definitions)
    try:
        suffix = secrets.token_hex(6).upper()
        project_id = _returned_int(
            connection.execute(
                "INSERT INTO core.project (project_code, project_name) "
                "VALUES (%s, 'Excel Model Contract') RETURNING project_id",
                (f"EXCEL_{suffix}",),
            ).fetchone()
        )
        tenant_code = f"EXCEL_{suffix}"
        connection.execute(
            "INSERT INTO core.tenant "
            "(project_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog) "
            "VALUES (%s, %s, 'Excel Model Contract', %s, %s)",
            (
                project_id,
                tenant_code,
                f"excel_{suffix.lower()}",
                f"admin_{suffix.lower()}",
            ),
        )

        row_by_column = {
            "tenant_code": tenant_code,
            "model_name": "Canonical Contract",
            "model_description": "Initial values",
            "silver_model_naming_instructions": "Use lower snake_case names.",
            "silver_model_audit_columns_template": '{"columns":["loaded_at"]}',
            "gold_model_naming_instructions": "Use business-facing names.",
            "gold_model_technical_columns_template": '{"columns":["row_hash"]}',
            "gold_model_audit_columns_template": '{"columns":["created_at"]}',
            "is_active": "true",
        }
        row = tuple(row_by_column[column] for column in model.columns)
        merge = model.merge_statements[0].replace(
            "{staging_table}", f'pg_temp."{model.staging_name}"'
        )
        with connection.cursor() as cursor:
            loader.create_temp_table(cursor, model.staging_name, model.columns)
            loader.insert_staging_rows(
                cursor, model.staging_name, model.columns, (row,)
            )
            cursor.execute(cast(LiteralString, merge))
            assert cursor.rowcount == 1

            stored = connection.execute(
                "SELECT silver_model_naming_instructions, "
                "silver_model_audit_columns_template, gold_model_naming_instructions, "
                "gold_model_technical_columns_template, gold_model_audit_columns_template "
                "FROM model.model WHERE model_name = 'Canonical Contract'"
            ).fetchone()
            assert stored == (
                "Use lower snake_case names.",
                {"columns": ["loaded_at"]},
                "Use business-facing names.",
                {"columns": ["row_hash"]},
                {"columns": ["created_at"]},
            )

            cursor.execute(
                sql.SQL(
                    "UPDATE pg_temp.{} SET "
                    '"silver_model_naming_instructions" = %s, '
                    '"silver_model_audit_columns_template" = %s, '
                    '"gold_model_naming_instructions" = %s, '
                    '"gold_model_technical_columns_template" = %s, '
                    '"gold_model_audit_columns_template" = %s'
                ).format(sql.Identifier(model.staging_name)),
                (" ", '{"columns":["ingested_at"]}', "Use title case.", None, None),
            )
            cursor.execute(cast(LiteralString, merge))
            assert cursor.rowcount == 1

        updated = connection.execute(
            "SELECT silver_model_naming_instructions, "
            "silver_model_audit_columns_template, gold_model_naming_instructions, "
            "gold_model_technical_columns_template, gold_model_audit_columns_template "
            "FROM model.model WHERE model_name = 'Canonical Contract'"
        ).fetchone()
        assert updated == (
            None,
            {"columns": ["ingested_at"]},
            "Use title case.",
            None,
            None,
        )
    finally:
        connection.rollback()
        connection.close()


def test_lock_control_uses_database_role_owned_lock_and_revision_cas(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    postgres_database = bootstrap_postgres_database
    definitions = _configured_definitions()
    role_name = f"excel.lock.{secrets.token_hex(8)}@example.test"
    connection = _connect_as_loader(postgres_database, role_name, definitions)
    try:
        seeded = _seed_lock_target(connection, role_name)
        identity = connection.execute(
            "SELECT session_user AS session_user, current_user AS current_user"
        ).fetchone()
        assert identity == (role_name, role_name)

        loader.execute_prepared_loads(
            connection,
            (
                loader.PreparedLockLoad(
                    rows=(
                        (
                            "core",
                            "object",
                            "object_id",
                            seeded["object_id"],
                            True,
                            None,
                        ),
                        (
                            "model",
                            "model_scope",
                            "model_scope_id",
                            seeded["model_scope_id"],
                            True,
                            1,
                        ),
                    )
                ),
            ),
        )

        changed = connection.execute(
            "SELECT object.is_locked, scope.model_scope_is_locked, model.model_revision, "
            "revision.change_kind, revision.changed_by, object.updated_by AS object_updated_by, "
            "scope.updated_by AS scope_updated_by "
            "FROM core.object AS object "
            "JOIN model.model_scope AS scope ON scope.object_id = object.object_id "
            "JOIN model.model AS model ON model.model_id = scope.model_id "
            "JOIN model.model_revision_transaction AS revision "
            "ON revision.model_id = model.model_id "
            "WHERE object.object_id = %s AND scope.model_scope_id = %s",
            (seeded["object_id"], seeded["model_scope_id"]),
        ).fetchone()
        actor_label = f"principal:{seeded['principal_id']}"
        assert changed == (
            True,
            True,
            2,
            "excel_lock_control",
            actor_label,
            actor_label,
            actor_label,
        )
    finally:
        connection.rollback()
        connection.close()


def _seed_lock_target(
    connection: psycopg.Connection[Any], role_name: str
) -> dict[str, int]:
    system_type_id = _returned_int(
        connection.execute(
            "INSERT INTO reference.system_type (system_type_code, system_type_name) "
            "VALUES ('LOADER_TEST', 'Loader Test') RETURNING system_type_id"
        ).fetchone()
    )
    connection_type_id = _returned_int(
        connection.execute(
            "INSERT INTO reference.connection_type "
            "(connection_type_code, connection_type_name) "
            "VALUES ('LOADER_TEST', 'Loader Test') RETURNING connection_type_id"
        ).fetchone()
    )
    object_type_id = _returned_int(
        connection.execute(
            "INSERT INTO reference.object_type (object_type_code, object_type_name) "
            "VALUES ('LOADER_TEST', 'Loader Test') RETURNING object_type_id"
        ).fetchone()
    )
    zone_id = _returned_int(
        connection.execute(
            "INSERT INTO reference.zone (zone_code, zone_name) "
            "VALUES ('loader_test', 'Loader Test') RETURNING zone_id"
        ).fetchone()
    )
    project_id = _returned_int(
        connection.execute(
            "INSERT INTO core.project (project_code, project_name) "
            "VALUES ('LOADER_TEST', 'Loader Test') RETURNING project_id"
        ).fetchone()
    )
    tenant_id = _returned_int(
        connection.execute(
            "INSERT INTO core.tenant "
            "(project_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog) "
            "VALUES (%s, 'LOADER_TEST', 'Loader Test', 'loader_test', "
            "'loader_test_admin') RETURNING tenant_id",
            (project_id,),
        ).fetchone()
    )
    system_id = _returned_int(
        connection.execute(
            "INSERT INTO core.system (system_code, system_name, system_type_id) "
            "VALUES ('LOADER_TEST', 'Loader Test', %s) RETURNING system_id",
            (system_type_id,),
        ).fetchone()
    )
    connection_id = _returned_int(
        connection.execute(
            "INSERT INTO core.connection "
            "(tenant_id, system_id, connection_code, connection_name, "
            "connection_type_id) VALUES (%s, %s, 'LOADER_TEST', 'Loader Test', %s) "
            "RETURNING connection_id",
            (tenant_id, system_id, connection_type_id),
        ).fetchone()
    )
    object_id = _returned_int(
        connection.execute(
            "INSERT INTO core.object "
            "(connection_id, object_schema, object_name, object_type_id, zone_id) "
            "VALUES (%s, 'loader_test', 'loader_test', %s, %s) RETURNING object_id",
            (connection_id, object_type_id, zone_id),
        ).fetchone()
    )
    model_id = _returned_int(
        connection.execute(
            "INSERT INTO model.model (tenant_id, model_name) "
            "VALUES (%s, 'Loader Test') RETURNING model_id",
            (tenant_id,),
        ).fetchone()
    )
    model_scope_id = _returned_int(
        connection.execute(
            "INSERT INTO model.model_scope (model_id, object_id) "
            "VALUES (%s, %s) RETURNING model_scope_id",
            (model_id, object_id),
        ).fetchone()
    )
    principal_id = _returned_int(
        connection.execute(
            "INSERT INTO security.principal "
            "(principal_type, principal_display_name, principal_email) "
            "VALUES ('user', 'Excel Lock Loader', %s) RETURNING principal_id",
            (role_name,),
        ).fetchone()
    )
    connection.execute(
        "INSERT INTO security.entra_principal_identity "
        "(principal_id, principal_type, entra_tenant_id, entra_object_id) "
        "VALUES (%s, 'user', '81000000-0000-0000-0000-000000000001', "
        "'82000000-0000-0000-0000-000000000001')",
        (principal_id,),
    )
    connection.execute(
        "INSERT INTO security.tenant_principal_access "
        "(tenant_id, principal_id, tenant_role, granted_by_principal_id) "
        "VALUES (%s, %s, 'architect', %s)",
        (tenant_id, principal_id, principal_id),
    )
    acquired = connection.execute(
        "SELECT acquired FROM security.acquire_tenant_lock("
        "%s, %s, 'user', %s, 60, 'Excel LockControl integration test')",
        (
            "81000000-0000-0000-0000-000000000001",
            "82000000-0000-0000-0000-000000000001",
            tenant_id,
        ),
    ).fetchone()
    assert acquired == (True,)
    return {
        "object_id": object_id,
        "model_scope_id": model_scope_id,
        "principal_id": principal_id,
    }
