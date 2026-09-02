from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import psycopg
import pytest
from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres


def test_sql_generation_guide_versions_are_audited_and_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    content = "Follow approved SQL conventions."
    digest = hashlib.sha256(content.encode()).hexdigest()
    with postgres_database.connect_owner() as connection:
        principal_id = require_row(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type, principal_display_name,
                    principal_email, is_super_admin
                ) VALUES (
                    'user', 'SQL Guide Administrator',
                    'sql-guide-administrator@example.test', TRUE
                )
                RETURNING principal_id
                """
            ).fetchone()
        )["principal_id"]
        guide_id = require_row(
            connection.execute(
                """
                INSERT INTO application.sql_generation_guide (
                    sql_generation_guide_code, sql_generation_guide_name,
                    created_by_principal_id, updated_by_principal_id
                ) VALUES ('default_web_sql', 'Default Web SQL', %s, %s)
                RETURNING sql_generation_guide_id
                """,
                (principal_id, principal_id),
            ).fetchone()
        )["sql_generation_guide_id"]
        version_id = require_row(
            connection.execute(
                """
                INSERT INTO application.sql_generation_guide_version (
                    sql_generation_guide_id, sql_generation_guide_version_number,
                    sql_generation_guide_content, sql_generation_guide_digest,
                    created_by_principal_id, updated_by_principal_id
                ) VALUES (%s, 1, %s, %s, %s, %s)
                RETURNING sql_generation_guide_version_id
                """,
                (guide_id, content, digest, principal_id, principal_id),
            ).fetchone()
        )["sql_generation_guide_version_id"]
        connection.execute(
            """
            UPDATE application.sql_generation_guide_version
               SET sql_generation_guide_version_status = 'published',
                   published_time = CURRENT_TIMESTAMP,
                   published_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE sql_generation_guide_version_id = %s
            """,
            (principal_id, principal_id, version_id),
        )

    with pytest.raises(psycopg.errors.RaiseException, match="published.*immutable"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.sql_generation_guide_version
                   SET sql_generation_guide_content = 'Changed after publication.'
                 WHERE sql_generation_guide_version_id = %s
                """,
                (version_id,),
            )

    with postgres_database.connect_owner() as connection:
        retired = require_row(
            connection.execute(
                """
                UPDATE application.sql_generation_guide_version
                   SET sql_generation_guide_version_status = 'retired',
                       retired_time = CURRENT_TIMESTAMP,
                       retired_by_principal_id = %s,
                       updated_by_principal_id = %s,
                       updated_time = CURRENT_TIMESTAMP
                 WHERE sql_generation_guide_version_id = %s
                RETURNING sql_generation_guide_version_status
                """,
                (principal_id, principal_id, version_id),
            ).fetchone()
        )
    assert retired["sql_generation_guide_version_status"] == "retired"


def test_sql_generation_guide_lifecycle_actor_matches_update_actor(
    postgres_database: DisposablePostgres,
) -> None:
    content = "Approved placeholder."
    with postgres_database.connect_owner() as connection:
        principals = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type, principal_display_name,
                principal_email, is_super_admin
            ) VALUES
                ('user', 'Guide Publisher', 'guide-publisher@example.test', TRUE),
                ('user', 'Different Guide Actor',
                 'different-guide-actor@example.test', TRUE)
            RETURNING principal_id
            """
        ).fetchall()
        guide_id = require_row(
            connection.execute(
                """
                INSERT INTO application.sql_generation_guide (
                    sql_generation_guide_code, sql_generation_guide_name,
                    created_by_principal_id, updated_by_principal_id
                ) VALUES ('actor_checked_guide', 'Actor Checked Guide', %s, %s)
                RETURNING sql_generation_guide_id
                """,
                (principals[0]["principal_id"], principals[0]["principal_id"]),
            ).fetchone()
        )["sql_generation_guide_id"]
        version_id = require_row(
            connection.execute(
                """
                INSERT INTO application.sql_generation_guide_version (
                    sql_generation_guide_id, sql_generation_guide_version_number,
                    sql_generation_guide_content, sql_generation_guide_digest,
                    created_by_principal_id, updated_by_principal_id
                ) VALUES (%s, 1, %s, %s, %s, %s)
                RETURNING sql_generation_guide_version_id
                """,
                (
                    guide_id,
                    content,
                    hashlib.sha256(content.encode()).hexdigest(),
                    principals[0]["principal_id"],
                    principals[0]["principal_id"],
                ),
            ).fetchone()
        )["sql_generation_guide_version_id"]

    with pytest.raises(psycopg.errors.CheckViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.sql_generation_guide_version
                   SET sql_generation_guide_version_status = 'published',
                       published_time = CURRENT_TIMESTAMP,
                       published_by_principal_id = %s,
                       updated_by_principal_id = %s,
                       updated_time = CURRENT_TIMESTAMP
                 WHERE sql_generation_guide_version_id = %s
                """,
                (
                    principals[0]["principal_id"],
                    principals[1]["principal_id"],
                    version_id,
                ),
            )
