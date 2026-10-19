"""Lease clocks must be checked after database lock waits, using disposable runs."""

# Shared fixture lifecycle helpers are confined to disposable database tests.
# pyright: reportPrivateUsage=false

from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from typing import TYPE_CHECKING

import psycopg
import pytest
from psycopg.errors import RaiseException
from psycopg.rows import dict_row

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context
from tests.web_backend.test_database_workflow_run_claims import _complete_run, _create_run

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres


@pytest.mark.parametrize(
    ("operation", "blocked_row"),
    [
        ("renew", "run"),
        ("renew", "project"),
        ("release", "run"),
        ("release", "project"),
        ("assert", "run"),
    ],
)
def test_claim_operation_rejects_expiry_during_a_lock_wait(
    web_postgres_database: DisposablePostgres,
    operation: str,
    blocked_row: str,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)

    with (
        psycopg.Connection[dict[str, object]].connect(
            web_postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
            autocommit=True,
        ) as worker,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        worker.execute("SET ROLE gds_web_write")
        worker.execute("SET statement_timeout = '10s'")
        claim = require_row(
            worker.execute("SELECT * FROM application.claim_next_workflow_run(2)").fetchone()
        )
        assert claim["workflow_run_id"] == run_id
        worker_pid = worker.info.backend_pid

        def renew() -> None:
            with pytest.raises(RaiseException, match="claim is unavailable"):
                if operation == "renew":
                    worker.execute(
                        "SELECT * FROM application.renew_workflow_run_claim(%s, %s, 2)",
                        (run_id, claim["workflow_run_claim_token"]),
                    ).fetchone()
                elif operation == "release":
                    worker.execute(
                        "SELECT application.release_workflow_run_claim(%s, %s)",
                        (run_id, claim["workflow_run_claim_token"]),
                    ).fetchone()
                else:
                    worker.execute(
                        "SELECT application.assert_workflow_run_claim(%s, %s)",
                        (run_id, claim["workflow_run_claim_token"]),
                    ).fetchone()

        with web_postgres_database.connect_owner() as blocker:
            if blocked_row == "run":
                blocker.execute(
                    "SELECT 1 FROM application.workflow_run WHERE workflow_run_id = %s FOR UPDATE",
                    (run_id,),
                )
            else:
                blocker.execute(
                    "SELECT 1 FROM project.project WHERE project_id = %s FOR UPDATE",
                    (context.project_id,),
                )
            renewal = executor.submit(renew)
            deadline = monotonic() + 3
            while monotonic() < deadline:
                blocker.execute("SELECT pg_stat_clear_snapshot()")
                waiting = require_row(
                    blocker.execute(
                        "SELECT wait_event_type = 'Lock' AS waiting "
                        "FROM pg_stat_activity WHERE pid = %s",
                        (worker_pid,),
                    ).fetchone()
                )
                if waiting["waiting"]:
                    break
                sleep(0.01)
            else:
                pytest.fail("Renewal did not reach the expected database lock wait")
            # The renewal already entered SQL; now make its original lease expire.
            sleep(2.1)
        try:
            renewal.result(timeout=5)
        finally:
            with web_postgres_database.connect_owner() as connection:
                _complete_run(connection, context, run_id)


@pytest.mark.parametrize("blocked_row", ["tenant_lock", "project"])
def test_new_claim_lease_starts_after_startup_lock_waits(
    web_postgres_database: DisposablePostgres,
    blocked_row: str,
) -> None:
    context = seed_workflow_context(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)

    try:
        with (
            psycopg.Connection[dict[str, object]].connect(
                web_postgres_database.web_runtime_dsn(),
                row_factory=dict_row,
                autocommit=True,
            ) as worker,
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            worker.execute("SET ROLE gds_web_write")
            worker.execute("SET statement_timeout = '10s'")
            worker_pid = worker.info.backend_pid

            def acquire() -> dict[str, object]:
                return require_row(
                    worker.execute(
                        "SELECT * FROM application.claim_next_workflow_run(2)"
                    ).fetchone()
                )

            with web_postgres_database.connect_owner() as blocker:
                if blocked_row == "tenant_lock":
                    blocker.execute(
                        "SELECT 1 FROM security.tenant_lock WHERE tenant_id = %s FOR UPDATE",
                        (context.tenant_id,),
                    )
                else:
                    blocker.execute(
                        "SELECT 1 FROM project.project WHERE project_id = %s FOR UPDATE",
                        (context.project_id,),
                    )
                acquisition = executor.submit(acquire)
                deadline = monotonic() + 3
                while monotonic() < deadline:
                    blocker.execute("SELECT pg_stat_clear_snapshot()")
                    waiting = require_row(
                        blocker.execute(
                            "SELECT wait_event_type = 'Lock' AS waiting "
                            "FROM pg_stat_activity WHERE pid = %s",
                            (worker_pid,),
                        ).fetchone()
                    )
                    if waiting["waiting"]:
                        break
                    sleep(0.01)
                else:
                    pytest.fail("Claim acquisition did not reach the expected database lock wait")
                # A new lease starts after startup guards/fences finish waiting.
                sleep(2.1)

            claim = acquisition.result(timeout=5)
            assert claim["workflow_run_id"] == run_id
            lease = require_row(
                worker.execute(
                    "SELECT workflow_run_claim_expires_time > clock_timestamp() AS live "
                    "FROM application.workflow_run WHERE workflow_run_id = %s",
                    (run_id,),
                ).fetchone()
            )
            assert lease["live"] is True
    finally:
        with web_postgres_database.connect_owner() as connection:
            _complete_run(connection, context, run_id)
