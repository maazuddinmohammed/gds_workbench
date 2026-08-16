from __future__ import annotations

import os
import secrets
import socket
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from gds_etl_workbench.infrastructure.postgres import PostgresDatabase

POSTGRES_IMAGE = (
    "postgres:18.4-bookworm@"
    "sha256:882236b897e39051d2368c5ccc6cda944904723506b2dfc97f2a8f5bc9afa382"
)
DATABASE_ROOT = Path(__file__).parents[2] / "database"
DATABASE_FILES = tuple(
    path
    for path in sorted(DATABASE_ROOT.glob("[0-9][0-9]_*.sql"))
    if 1 <= int(path.name[:2]) <= 12
)
DATABASE_PREFLIGHT_FILE = DATABASE_ROOT / "00_preflight.sql"
DATABASE_VERIFY_FILE = DATABASE_ROOT / "13_verify_install.sql"
FORBIDDEN_CONNECTION_ENVIRONMENT = frozenset(
    {
        "APP_POSTGRES_DB",
        "APP_POSTGRES_HOST",
        "APP_POSTGRES_PASSWORD_KEY",
        "APP_POSTGRES_PORT",
        "APP_POSTGRES_USER",
        "DATABASE_URL",
        "GDS_DATABASE_DSN",
        "GDS_LOADER_DSN",
        "PGDATABASE",
        "PGHOST",
        "PGHOSTADDR",
        "PGPASSWORD",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGUSER",
    }
)


@dataclass(frozen=True, slots=True)
class DisposablePostgres:
    host: str
    port: int
    database: str
    owner_user: str
    runtime_user: str
    marker: UUID
    _owner_password: str = field(repr=False)
    _runtime_password: str = field(repr=False)

    def connect_owner(self) -> psycopg.Connection[Any]:
        connection: psycopg.Connection[Any] = psycopg.Connection.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.owner_user,
            password=self._owner_password,
            connect_timeout=5,
            row_factory=cast(Any, dict_row),
        )
        _assert_fixture_identity(connection, self)
        return connection

    def connect_runtime(self) -> psycopg.Connection[Any]:
        connection: psycopg.Connection[Any] = psycopg.Connection.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.runtime_user,
            password=self._runtime_password,
            connect_timeout=5,
            row_factory=cast(Any, dict_row),
        )
        _assert_fixture_identity(connection, self)
        connection.execute("SET ROLE gds_app_write")
        return connection

    def create_runtime_adapter(self) -> PostgresDatabase:
        return PostgresDatabase(
            dsn=make_conninfo(
                host=self.host,
                port=self.port,
                dbname=self.database,
                user=self.runtime_user,
                password=self._runtime_password,
            ),
            pool_min=1,
            pool_max=2,
            pool_timeout_seconds=5,
            require_runtime_role=True,
        )


@pytest.fixture(scope="session")
def postgres_database() -> Iterator[DisposablePostgres]:
    unexpected = sorted(
        key for key in FORBIDDEN_CONNECTION_ENVIRONMENT if os.environ.get(key)
    )
    if unexpected:
        pytest.fail(f"database tests reject connection environment: {unexpected[0]}")

    marker = uuid4()
    suffix = secrets.token_hex(8)
    container_name = f"gds-mcp-test-{suffix}"
    database = f"gds_{suffix}"
    owner_user = f"owner_{suffix}"
    runtime_user = f"runtime_{suffix}"
    owner_password = secrets.token_urlsafe(32)
    runtime_password = secrets.token_urlsafe(32)

    started = subprocess.run(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container_name,
            "--label",
            f"gds.test-run={marker}",
            "--env",
            f"POSTGRES_DB={database}",
            "--env",
            f"POSTGRES_USER={owner_user}",
            "--env",
            f"POSTGRES_PASSWORD={owner_password}",
            "--publish",
            "127.0.0.1::5432",
            POSTGRES_IMAGE,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        pytest.fail("failed to start the disposable PostgreSQL container")

    try:
        port = _published_port(container_name)
        fixture = DisposablePostgres(
            host="127.0.0.1",
            port=port,
            database=database,
            owner_user=owner_user,
            runtime_user=runtime_user,
            marker=marker,
            _owner_password=owner_password,
            _runtime_password=runtime_password,
        )
        _wait_for_postgres(fixture)
        with fixture.connect_owner() as connection, connection.transaction():
            connection.execute(
                "CREATE TABLE public.gds_test_sentinel (marker UUID PRIMARY KEY)"
            )
            connection.execute(
                "INSERT INTO public.gds_test_sentinel (marker) VALUES (%s)",
                (marker,),
            )
            connection.execute(
                cast(
                    LiteralString,
                    DATABASE_PREFLIGHT_FILE.read_text(encoding="utf-8"),
                )
            )
            for database_file in DATABASE_FILES:
                connection.execute(
                    cast(
                        LiteralString,
                        database_file.read_text(encoding="utf-8"),
                    )
                )
            connection.execute(
                cast(
                    LiteralString,
                    DATABASE_VERIFY_FILE.read_text(encoding="utf-8"),
                )
            )
            connection.execute(
                "SELECT set_config('gds.test_runtime_password', %s, true)",
                (runtime_password,),
            )
            connection.execute(
                sql.SQL(
                    """
                        DO $create_test_runtime$
                        BEGIN
                            EXECUTE format(
                                'CREATE ROLE %I LOGIN NOINHERIT NOSUPERUSER '
                                'NOCREATEDB NOCREATEROLE NOREPLICATION '
                                'NOBYPASSRLS PASSWORD %L',
                                {},
                                current_setting('gds.test_runtime_password')
                            );
                        END;
                        $create_test_runtime$
                        """
                ).format(sql.Literal(runtime_user))
            )
            connection.execute(
                sql.SQL("GRANT gds_app_write TO {}").format(
                    sql.Identifier(runtime_user)
                )
            )
            connection.execute(
                sql.SQL("GRANT SELECT ON public.gds_test_sentinel TO {}").format(
                    sql.Identifier(runtime_user)
                )
            )
        yield fixture
    finally:
        inspected = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                '{{index .Config.Labels "gds.test-run"}}',
                container_name,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if inspected.returncode != 0 or inspected.stdout.strip() != str(marker):
            pytest.fail("refusing to dispose an unverified PostgreSQL container")
        stopped = subprocess.run(
            ["docker", "stop", "--time", "10", container_name],
            check=False,
            capture_output=True,
            text=True,
        )
        if stopped.returncode != 0:
            pytest.fail("failed to dispose the verified PostgreSQL container")


def _published_port(container_name: str) -> int:
    result = subprocess.run(
        ["docker", "port", container_name, "5432/tcp"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail("failed to resolve the disposable PostgreSQL port")
    host, separator, raw_port = result.stdout.strip().rpartition(":")
    if separator != ":" or host not in {"127.0.0.1", "localhost"}:
        pytest.fail("disposable PostgreSQL was not bound to loopback")
    try:
        return int(raw_port)
    except ValueError:
        pytest.fail("disposable PostgreSQL returned an invalid port")


def _wait_for_postgres(fixture: DisposablePostgres) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(
                host=fixture.host,
                port=fixture.port,
                dbname=fixture.database,
                user=fixture.owner_user,
                password=fixture._owner_password,
                connect_timeout=2,
            ):
                return
        except psycopg.OperationalError:
            time.sleep(0.2)
    pytest.fail("disposable PostgreSQL did not become ready")


def _assert_fixture_identity(
    connection: psycopg.Connection[Any],
    fixture: DisposablePostgres,
) -> None:
    if fixture.host not in {"127.0.0.1", "localhost"}:
        raise AssertionError("database fixture host is not loopback")
    resolved = {item[4][0] for item in socket.getaddrinfo(fixture.host, fixture.port)}
    if not resolved or any(address not in {"127.0.0.1", "::1"} for address in resolved):
        raise AssertionError("database fixture host did not resolve only to loopback")
    row = connection.execute(
        """
        SELECT current_database() AS database_name,
               session_user AS session_user,
               current_setting('server_version_num')::INTEGER / 10000 AS major
        """
    ).fetchone()
    if row is None:
        raise AssertionError("database fixture identity query returned no row")
    if row["database_name"] != fixture.database or row["major"] != 18:
        raise AssertionError("database fixture identity mismatch")
    if row["session_user"] not in {fixture.owner_user, fixture.runtime_user}:
        raise AssertionError("database fixture user mismatch")
    sentinel_table = connection.execute(
        "SELECT to_regclass('public.gds_test_sentinel') AS relation"
    ).fetchone()
    if sentinel_table is not None and sentinel_table["relation"] is not None:
        sentinel = connection.execute(
            "SELECT marker FROM public.gds_test_sentinel"
        ).fetchone()
        if sentinel is None or sentinel["marker"] != fixture.marker:
            raise AssertionError("database fixture sentinel mismatch")
