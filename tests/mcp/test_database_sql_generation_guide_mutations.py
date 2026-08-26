from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from psycopg.errors import RaiseException
from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres, TestRow


@dataclass(frozen=True, slots=True)
class GuideActor:
    entra_tenant_id: UUID
    entra_object_id: UUID
    principal_id: int


SAVE_GUIDE_SQL = """
    SELECT *
      FROM application.save_sql_generation_guide(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::BOOLEAN,
          %s::BOOLEAN,
          %s::TIMESTAMPTZ
      )
"""

SAVE_GUIDE_DRAFT_SQL = """
    SELECT *
      FROM application.save_sql_generation_guide_draft(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::TEXT,
          %s::TIMESTAMPTZ
      )
"""

TRANSITION_GUIDE_VERSION_SQL = """
    SELECT *
      FROM application.transition_sql_generation_guide_version(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR
      )
"""


def _seed_guide_actor(
    postgres_database: DisposablePostgres,
    *,
    is_super_admin: bool,
) -> GuideActor:
    suffix = uuid4().hex
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()

    with postgres_database.connect_owner() as connection:
        principal_id = require_row(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES ('user', %s, %s, %s)
            RETURNING principal_id
            """,
                (
                    f"SQL Guide Actor {suffix}",
                    f"sql_guide_actor_{suffix}@example.test",
                    is_super_admin,
                ),
            ).fetchone()
        )["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )

    return GuideActor(
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        principal_id=principal_id,
    )


def _save_guide(
    postgres_database: DisposablePostgres,
    actor: GuideActor,
    *,
    code: str,
    name: str,
    is_default: bool = False,
) -> TestRow:
    with postgres_database.connect_owner() as connection:
        return require_row(
            connection.execute(
                SAVE_GUIDE_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    None,
                    code,
                    name,
                    None,
                    is_default,
                    True,
                    None,
                ),
            ).fetchone()
        )


def test_sql_generation_guide_header_is_super_admin_governed_idempotent_and_fenced(
    postgres_database: DisposablePostgres,
) -> None:
    denied_actor = _seed_guide_actor(
        postgres_database,
        is_super_admin=False,
    )
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    code = f"governed_guide_{suffix}"
    name = f"Governed Guide {suffix}"

    with pytest.raises(RaiseException, match="Super Admin"):
        _save_guide(
            postgres_database,
            denied_actor,
            code=f"denied_guide_{suffix}",
            name="Denied Guide",
        )

    created = _save_guide(
        postgres_database,
        actor,
        code=code,
        name=name,
        is_default=True,
    )
    replayed = _save_guide(
        postgres_database,
        actor,
        code=code,
        name=name,
        is_default=True,
    )

    assert replayed == created
    assert created["created_by_principal_id"] == actor.principal_id
    assert created["updated_by_principal_id"] == actor.principal_id

    with postgres_database.connect_owner() as connection:
        guide_count = require_row(
            connection.execute(
                """
            SELECT count(*) AS guide_count
              FROM application.sql_generation_guide
             WHERE lower(sql_generation_guide_code) = lower(%s)
            """,
                (code,),
            ).fetchone()
        )["guide_count"]
    assert guide_count == 1

    with (
        pytest.raises(RaiseException, match="identity.*immutable"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            SAVE_GUIDE_SQL,
            (
                actor.entra_tenant_id,
                actor.entra_object_id,
                created["sql_generation_guide_id"],
                f"changed_{code}",
                name,
                None,
                True,
                True,
                created["updated_time"],
            ),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        updated = require_row(
            connection.execute(
                SAVE_GUIDE_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    created["sql_generation_guide_id"],
                    code,
                    f"{name} Updated",
                    "Updated through the governed function.",
                    True,
                    True,
                    created["updated_time"],
                ),
            ).fetchone()
        )

    assert updated["sql_generation_guide_id"] == created["sql_generation_guide_id"]
    assert updated["updated_by_principal_id"] == actor.principal_id
    assert updated["updated_time"] > created["updated_time"]

    with (
        pytest.raises(RaiseException, match="stale_sql_generation_guide"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            SAVE_GUIDE_SQL,
            (
                actor.entra_tenant_id,
                actor.entra_object_id,
                created["sql_generation_guide_id"],
                code,
                f"{name} Stale Update",
                "This update must lose the optimistic race.",
                True,
                True,
                created["updated_time"],
            ),
        ).fetchone()


def test_sql_generation_guide_version_mutations_authorize_before_resource_lookup(
    postgres_database: DisposablePostgres,
) -> None:
    denied_actor = _seed_guide_actor(
        postgres_database,
        is_super_admin=False,
    )
    missing_id = 9_223_372_036_854_775_807

    with (
        pytest.raises(RaiseException, match="Super Admin"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            SAVE_GUIDE_DRAFT_SQL,
            (
                denied_actor.entra_tenant_id,
                denied_actor.entra_object_id,
                missing_id,
                None,
                "Authorization must run before guide lookup.",
                None,
            ),
        ).fetchone()

    with (
        pytest.raises(RaiseException, match="Super Admin"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            TRANSITION_GUIDE_VERSION_SQL,
            (
                denied_actor.entra_tenant_id,
                denied_actor.entra_object_id,
                missing_id,
                "draft",
                "published",
            ),
        ).fetchone()


def test_sql_generation_guide_default_transfer_is_atomic(
    postgres_database: DisposablePostgres,
) -> None:
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    first = _save_guide(
        postgres_database,
        actor,
        code=f"first_default_{suffix}",
        name="First Default",
        is_default=True,
    )
    second = _save_guide(
        postgres_database,
        actor,
        code=f"second_default_{suffix}",
        name="Second Default",
    )

    with postgres_database.connect_owner() as connection:
        transferred = require_row(
            connection.execute(
                SAVE_GUIDE_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    second["sql_generation_guide_id"],
                    second["sql_generation_guide_code"],
                    second["sql_generation_guide_name"],
                    second["sql_generation_guide_description"],
                    True,
                    True,
                    second["updated_time"],
                ),
            ).fetchone()
        )
        states = connection.execute(
            """
            SELECT sql_generation_guide_id, is_default
              FROM application.sql_generation_guide
             WHERE sql_generation_guide_id = ANY(%s::BIGINT[])
             ORDER BY sql_generation_guide_id
            """,
            (
                [
                    first["sql_generation_guide_id"],
                    second["sql_generation_guide_id"],
                ],
            ),
        ).fetchall()
        active_default_count = require_row(
            connection.execute(
                """
            SELECT count(*) AS active_default_count
              FROM application.sql_generation_guide
             WHERE is_active AND is_default
            """
            ).fetchone()
        )["active_default_count"]

    assert transferred["is_default"] is True
    assert states == [
        {
            "sql_generation_guide_id": first["sql_generation_guide_id"],
            "is_default": False,
        },
        {
            "sql_generation_guide_id": second["sql_generation_guide_id"],
            "is_default": True,
        },
    ]
    assert active_default_count == 1


def test_concurrent_sql_generation_guide_default_transfers_serialize(
    postgres_database: DisposablePostgres,
) -> None:
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    _save_guide(
        postgres_database,
        actor,
        code=f"concurrent_first_default_{suffix}",
        name="Concurrent First Default",
        is_default=True,
    )
    candidates = [
        _save_guide(
            postgres_database,
            actor,
            code=f"concurrent_candidate_{index}_{suffix}",
            name=f"Concurrent Candidate {index}",
        )
        for index in (1, 2)
    ]

    def promote(candidate: TestRow) -> TestRow:
        with postgres_database.connect_owner() as connection:
            connection.execute("SET LOCAL statement_timeout = '5s'")
            return require_row(
                connection.execute(
                    SAVE_GUIDE_SQL,
                    (
                        actor.entra_tenant_id,
                        actor.entra_object_id,
                        candidate["sql_generation_guide_id"],
                        candidate["sql_generation_guide_code"],
                        candidate["sql_generation_guide_name"],
                        candidate["sql_generation_guide_description"],
                        True,
                        True,
                        candidate["updated_time"],
                    ),
                ).fetchone()
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(promote, candidate) for candidate in candidates]
        promoted = [future.result(timeout=10) for future in futures]

    candidate_ids = {candidate["sql_generation_guide_id"] for candidate in candidates}
    assert {result["sql_generation_guide_id"] for result in promoted} == candidate_ids
    assert all(result["is_default"] for result in promoted)

    with postgres_database.connect_owner() as connection:
        active_defaults = connection.execute(
            """
            SELECT sql_generation_guide_id
              FROM application.sql_generation_guide
             WHERE is_active AND is_default
            """
        ).fetchall()
    assert len(active_defaults) == 1
    assert active_defaults[0]["sql_generation_guide_id"] in candidate_ids


def test_sql_generation_guide_draft_is_server_owned_single_and_retry_safe(
    postgres_database: DisposablePostgres,
) -> None:
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    guide = _save_guide(
        postgres_database,
        actor,
        code=f"draft_guide_{suffix}",
        name="Draft Guide",
    )
    content = "Generate SQL with exact UTF-8 guidance: café, 数据."
    expected_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    draft_arguments = (
        actor.entra_tenant_id,
        actor.entra_object_id,
        guide["sql_generation_guide_id"],
        None,
        content,
        None,
    )

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                draft_arguments,
            ).fetchone()
        )
    with postgres_database.connect_owner() as connection:
        replayed = require_row(
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                draft_arguments,
            ).fetchone()
        )

    assert replayed == created
    assert created["sql_generation_guide_version_number"] == 1
    assert created["sql_generation_guide_digest"] == expected_digest
    assert created["created_by_principal_id"] == actor.principal_id
    assert created["updated_by_principal_id"] == actor.principal_id

    with (
        pytest.raises(RaiseException, match="draft.*exists"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            SAVE_GUIDE_DRAFT_SQL,
            (
                actor.entra_tenant_id,
                actor.entra_object_id,
                guide["sql_generation_guide_id"],
                None,
                "A different implicit draft must not be created.",
                None,
            ),
        ).fetchone()

    revised_content = "Generate ANSI SQL with exact UTF-8 guidance: café, 数据."
    with postgres_database.connect_owner() as connection:
        revised = require_row(
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    guide["sql_generation_guide_id"],
                    created["sql_generation_guide_version_id"],
                    revised_content,
                    created["updated_time"],
                ),
            ).fetchone()
        )
        draft_count = require_row(
            connection.execute(
                """
            SELECT count(*) AS draft_count
              FROM application.sql_generation_guide_version
             WHERE sql_generation_guide_id = %s
               AND sql_generation_guide_version_status = 'draft'
            """,
                (guide["sql_generation_guide_id"],),
            ).fetchone()
        )["draft_count"]

    assert (
        revised["sql_generation_guide_version_id"]
        == created["sql_generation_guide_version_id"]
    )
    assert revised["sql_generation_guide_version_number"] == 1
    assert (
        revised["sql_generation_guide_digest"]
        == hashlib.sha256(revised_content.encode("utf-8")).hexdigest()
    )
    assert revised["updated_time"] > created["updated_time"]
    assert draft_count == 1

    with postgres_database.connect_owner() as connection:
        replayed_revision = require_row(
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    guide["sql_generation_guide_id"],
                    created["sql_generation_guide_version_id"],
                    revised_content,
                    created["updated_time"],
                ),
            ).fetchone()
        )
    assert replayed_revision == revised

    with (
        pytest.raises(RaiseException, match="stale_sql_generation_guide_draft"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            SAVE_GUIDE_DRAFT_SQL,
            (
                actor.entra_tenant_id,
                actor.entra_object_id,
                guide["sql_generation_guide_id"],
                created["sql_generation_guide_version_id"],
                "This update uses the stale draft fence.",
                created["updated_time"],
            ),
        ).fetchone()


def test_sql_generation_guide_version_rejects_a_direct_digest_content_mismatch(
    postgres_database: DisposablePostgres,
) -> None:
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    guide = _save_guide(
        postgres_database,
        actor,
        code=f"digest_guard_guide_{suffix}",
        name="Digest Guard Guide",
    )
    content = "SQL generation guidance with an exact digest."
    mismatched_digest = hashlib.sha256(b"different content").hexdigest()

    with (
        pytest.raises(RaiseException, match="digest.*content"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            """
            INSERT INTO application.sql_generation_guide_version (
                sql_generation_guide_id,
                sql_generation_guide_version_number,
                sql_generation_guide_content,
                sql_generation_guide_digest,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, 1, %s, %s, %s, %s)
            """,
            (
                guide["sql_generation_guide_id"],
                content,
                mismatched_digest,
                actor.principal_id,
                actor.principal_id,
            ),
        )


def test_sql_generation_guide_invalid_content_error_is_sanitized(
    postgres_database: DisposablePostgres,
) -> None:
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    guide = _save_guide(
        postgres_database,
        actor,
        code=f"sanitized_guide_{suffix}",
        name="Sanitized Guide",
    )
    sensitive_marker = "SENSITIVE_GUIDE_CONTENT_MARKER"
    oversized_content = sensitive_marker + ("x" * 262_144)

    with pytest.raises(RaiseException, match="content is invalid") as exception_info:
        with postgres_database.connect_owner() as connection:
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    guide["sql_generation_guide_id"],
                    None,
                    oversized_content,
                    None,
                ),
            ).fetchone()

    diagnostics = exception_info.value.diag
    exposed_error = " ".join(
        value
        for value in (
            str(exception_info.value),
            diagnostics.message_primary,
            diagnostics.message_detail,
            diagnostics.message_hint,
            diagnostics.context,
        )
        if value
    )
    assert sensitive_marker not in exposed_error

    with postgres_database.connect_owner() as connection:
        version_count = require_row(
            connection.execute(
                """
            SELECT count(*) AS version_count
              FROM application.sql_generation_guide_version
             WHERE sql_generation_guide_id = %s
            """,
                (guide["sql_generation_guide_id"],),
            ).fetchone()
        )["version_count"]
    assert version_count == 0


def test_sql_generation_guide_version_lifecycle_is_governed_and_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    guide = _save_guide(
        postgres_database,
        actor,
        code=f"lifecycle_guide_{suffix}",
        name="Lifecycle Guide",
    )

    with postgres_database.connect_owner() as connection:
        first_draft = require_row(
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    guide["sql_generation_guide_id"],
                    None,
                    "Published SQL guidance version one.",
                    None,
                ),
            ).fetchone()
        )
        published = require_row(
            connection.execute(
                TRANSITION_GUIDE_VERSION_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    first_draft["sql_generation_guide_version_id"],
                    "draft",
                    "published",
                ),
            ).fetchone()
        )

    assert published["sql_generation_guide_version_status"] == "published"
    assert published["published_time"] is not None
    assert published["published_by_principal_id"] == actor.principal_id
    assert published["updated_by_principal_id"] == actor.principal_id

    with postgres_database.connect_owner() as connection:
        replayed_publish = require_row(
            connection.execute(
                TRANSITION_GUIDE_VERSION_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    first_draft["sql_generation_guide_version_id"],
                    "draft",
                    "published",
                ),
            ).fetchone()
        )
    assert replayed_publish == published

    with (
        pytest.raises(RaiseException, match="published.*immutable"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            """
            UPDATE application.sql_generation_guide_version
               SET sql_generation_guide_content = 'Forbidden change.'
             WHERE sql_generation_guide_version_id = %s
            """,
            (first_draft["sql_generation_guide_version_id"],),
        )

    with postgres_database.connect_owner() as connection:
        second_draft = require_row(
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    guide["sql_generation_guide_id"],
                    None,
                    "Published SQL guidance version two.",
                    None,
                ),
            ).fetchone()
        )
        retired = require_row(
            connection.execute(
                TRANSITION_GUIDE_VERSION_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    first_draft["sql_generation_guide_version_id"],
                    "published",
                    "retired",
                ),
            ).fetchone()
        )

    assert second_draft["sql_generation_guide_version_number"] == 2
    assert retired["sql_generation_guide_version_status"] == "retired"
    assert retired["retired_time"] is not None
    assert retired["retired_by_principal_id"] == actor.principal_id

    with (
        pytest.raises(RaiseException, match="stale.*status"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            TRANSITION_GUIDE_VERSION_SQL,
            (
                actor.entra_tenant_id,
                actor.entra_object_id,
                second_draft["sql_generation_guide_version_id"],
                "published",
                "retired",
            ),
        ).fetchone()

    with (
        pytest.raises(RaiseException, match="transition"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            TRANSITION_GUIDE_VERSION_SQL,
            (
                actor.entra_tenant_id,
                actor.entra_object_id,
                first_draft["sql_generation_guide_version_id"],
                "retired",
                "published",
            ),
        ).fetchone()

    with (
        pytest.raises(RaiseException, match="cannot be deleted"),
        postgres_database.connect_owner() as connection,
    ):
        connection.execute(
            """
            DELETE FROM application.sql_generation_guide_version
             WHERE sql_generation_guide_version_id = %s
            """,
            (first_draft["sql_generation_guide_version_id"],),
        )


@pytest.mark.parametrize(
    ("expected_status", "target_status"),
    ((None, "published"), ("draft", None)),
)
def test_sql_generation_guide_transition_rejects_null_statuses(
    postgres_database: DisposablePostgres,
    expected_status: str | None,
    target_status: str | None,
) -> None:
    actor = _seed_guide_actor(postgres_database, is_super_admin=True)
    suffix = uuid4().hex
    guide = _save_guide(
        postgres_database,
        actor,
        code=f"null_transition_source_{suffix}",
        name="NULL transition source guide",
    )
    with postgres_database.connect_owner() as connection:
        draft = require_row(
            connection.execute(
                SAVE_GUIDE_DRAFT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    guide["sql_generation_guide_id"],
                    None,
                    "NULL transition source guidance.",
                    None,
                ),
            ).fetchone()
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="transition"),
    ):
        connection.execute(
            TRANSITION_GUIDE_VERSION_SQL,
            (
                actor.entra_tenant_id,
                actor.entra_object_id,
                draft["sql_generation_guide_version_id"],
                expected_status,
                target_status,
            ),
        )


def test_sql_generation_guide_mutations_are_web_only_security_definer_functions(
    postgres_database: DisposablePostgres,
) -> None:
    expected_functions = {
        "save_sql_generation_guide",
        "save_sql_generation_guide_draft",
        "transition_sql_generation_guide_version",
    }

    with postgres_database.connect_owner() as connection:
        functions = connection.execute(
            """
            SELECT procedure.proname AS function_name,
                   procedure.prosecdef AS is_security_definer,
                   procedure.proconfig AS settings,
                   has_function_privilege(
                       'gds_web_write', procedure.oid, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', procedure.oid, 'EXECUTE'
                   ) AS mcp_can_execute,
                   has_function_privilege(
                       'public', procedure.oid, 'EXECUTE'
                   ) AS public_can_execute
              FROM pg_catalog.pg_proc AS procedure
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'application'
               AND procedure.proname = ANY(%s)
             ORDER BY procedure.proname
            """,
            (list(expected_functions),),
        ).fetchall()
        table_access = connection.execute(
            """
            SELECT table_name,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'SELECT'
                   ) AS web_can_select,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate,
                   has_table_privilege(
                       'gds_app_write',
                       'application.' || quote_ident(table_name),
                       'SELECT,INSERT,UPDATE,DELETE'
                   ) AS mcp_can_access
              FROM unnest(
                       ARRAY[
                           'sql_generation_guide',
                           'sql_generation_guide_version'
                       ]
                   ) AS guide_table(table_name)
             ORDER BY table_name
            """
        ).fetchall()

    assert {row["function_name"] for row in functions} == expected_functions
    assert all(row["is_security_definer"] for row in functions)
    assert all(row["web_can_execute"] for row in functions)
    assert not any(row["mcp_can_execute"] for row in functions)
    assert not any(row["public_can_execute"] for row in functions)
    assert all(row["settings"] == ["search_path=pg_catalog"] for row in functions)
    assert table_access == [
        {
            "table_name": "sql_generation_guide",
            "web_can_select": True,
            "web_can_mutate": False,
            "mcp_can_access": False,
        },
        {
            "table_name": "sql_generation_guide_version",
            "web_can_select": True,
            "web_can_mutate": False,
            "mcp_can_access": False,
        },
    ]
