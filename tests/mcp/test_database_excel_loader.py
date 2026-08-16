from __future__ import annotations

import re
import secrets
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

import psycopg
from psycopg import sql

REPOSITORY_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))
from load_and_merge_scripts import loader  # noqa: E402

if TYPE_CHECKING:
    from conftest import DisposablePostgres


CONFIG_PATH = REPOSITORY_ROOT / "load_and_merge_scripts" / "load_config.yaml"


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
        loader._validate_definition(definition)
        definitions.append(definition)

    definitions.sort(key=lambda value: value.dependency_order)
    assert len(definitions) == 41
    assert len({definition.selection for definition in definitions}) == 41
    assert {definition.selection for definition in definitions} == set(
        loader._ALLOWED_LOAD_TARGETS
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
    privileges: str,
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
    postgres_database: DisposablePostgres,
) -> None:
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
            loader._insert_staging_rows(
                cursor, environment.staging_name, environment.columns, (row,)
            )
            cursor.execute(merge)
            assert cursor.rowcount == 1
            cursor.execute(
                f'UPDATE pg_temp."{environment.staging_name}" '
                'SET "environment_name" = %s WHERE "environment_code" = %s',
                ("Integration Test Updated", "INTEGRATION_TEST"),
            )
            cursor.execute(merge)
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


def test_lock_control_uses_database_role_owned_lock_and_revision_cas(
    postgres_database: DisposablePostgres,
) -> None:
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
    system_type_id = connection.execute(
        "INSERT INTO reference.system_type (system_type_code, system_type_name) "
        "VALUES ('LOADER_TEST', 'Loader Test') RETURNING system_type_id"
    ).fetchone()[0]
    connection_type_id = connection.execute(
        "INSERT INTO reference.connection_type (connection_type_code, connection_type_name) "
        "VALUES ('LOADER_TEST', 'Loader Test') RETURNING connection_type_id"
    ).fetchone()[0]
    object_type_id = connection.execute(
        "INSERT INTO reference.object_type (object_type_code, object_type_name) "
        "VALUES ('LOADER_TEST', 'Loader Test') RETURNING object_type_id"
    ).fetchone()[0]
    zone_id = connection.execute(
        "INSERT INTO reference.zone (zone_code, zone_name) "
        "VALUES ('loader_test', 'Loader Test') RETURNING zone_id"
    ).fetchone()[0]
    project_id = connection.execute(
        "INSERT INTO core.project (project_code, project_name) "
        "VALUES ('LOADER_TEST', 'Loader Test') RETURNING project_id"
    ).fetchone()[0]
    tenant_id = connection.execute(
        "INSERT INTO core.tenant "
        "(project_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog) "
        "VALUES (%s, 'LOADER_TEST', 'Loader Test', 'loader_test', 'loader_test_admin') "
        "RETURNING tenant_id",
        (project_id,),
    ).fetchone()[0]
    system_id = connection.execute(
        "INSERT INTO core.system (system_code, system_name, system_type_id) "
        "VALUES ('LOADER_TEST', 'Loader Test', %s) RETURNING system_id",
        (system_type_id,),
    ).fetchone()[0]
    connection_id = connection.execute(
        "INSERT INTO core.connection "
        "(tenant_id, system_id, connection_code, connection_name, connection_type_id) "
        "VALUES (%s, %s, 'LOADER_TEST', 'Loader Test', %s) RETURNING connection_id",
        (tenant_id, system_id, connection_type_id),
    ).fetchone()[0]
    object_id = connection.execute(
        "INSERT INTO core.object "
        "(connection_id, object_schema, object_name, object_type_id, zone_id) "
        "VALUES (%s, 'loader_test', 'loader_test', %s, %s) RETURNING object_id",
        (connection_id, object_type_id, zone_id),
    ).fetchone()[0]
    model_id = connection.execute(
        "INSERT INTO model.model (tenant_id, model_name) "
        "VALUES (%s, 'Loader Test') RETURNING model_id",
        (tenant_id,),
    ).fetchone()[0]
    model_scope_id = connection.execute(
        "INSERT INTO model.model_scope (model_id, object_id) "
        "VALUES (%s, %s) RETURNING model_scope_id",
        (model_id, object_id),
    ).fetchone()[0]
    principal_id = connection.execute(
        "INSERT INTO security.principal "
        "(principal_type, principal_display_name, principal_email) "
        "VALUES ('user', 'Excel Lock Loader', %s) RETURNING principal_id",
        (role_name,),
    ).fetchone()[0]
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
