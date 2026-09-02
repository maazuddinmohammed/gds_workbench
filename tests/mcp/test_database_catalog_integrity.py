from __future__ import annotations

import re
from pathlib import Path

from tests.mcp.conftest import DisposablePostgres

RELEASE_SCHEMAS = (
    "reference",
    "core",
    "security",
    "model",
    "workflow",
    "application",
    "mcp",
)
INVENTORY = Path(__file__).parents[2] / "docs" / "database-inventory.md"


def _inventory_section(document: str, start: str, end: str) -> str:
    return document.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]


def test_installed_catalog_matches_the_exhaustive_inventory(
    postgres_database: DisposablePostgres,
) -> None:
    inventory = INVENTORY.read_text(encoding="utf-8")
    expected_tables = sorted(
        re.findall(
            r"^- `((?:reference|core|security|model|workflow|application|mcp)"
            r"\.[a-z][a-z0-9_]*)` —",
            _inventory_section(inventory, "## 1. Tables", "## 2. Functions"),
            re.MULTILINE,
        )
    )
    expected_functions = sorted(
        re.findall(
            r"^- `((?:reference|core|security|model|workflow|application|mcp)"
            r"\.[a-z][a-z0-9_]*)` —",
            _inventory_section(
                inventory, "## 2. Functions", "## 3. Installed triggers"
            ),
            re.MULTILINE,
        )
    )
    trigger_pairs = sorted(
        re.findall(
            r"^- `([a-z][a-z0-9_]*)` on "
            r"`((?:reference|core|security|model|workflow|application|mcp)"
            r"\.[a-z][a-z0-9_]*)` —",
            _inventory_section(
                inventory,
                "## 3. Installed triggers",
                "## 4. Explicit exclusions",
            ),
            re.MULTILINE,
        )
    )

    with postgres_database.connect_owner() as connection:
        tables = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || relation.relname AS name
              FROM pg_catalog.pg_class AS relation
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND relation.relkind IN ('r', 'p')
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        functions = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || function_record.proname AS name
              FROM pg_catalog.pg_proc AS function_record
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = function_record.pronamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND function_record.prokind = 'f'
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        triggers = connection.execute(
            """
            SELECT trigger_record.tgname AS trigger_name,
                   namespace_record.nspname || '.' || relation.relname
                       AS relation_name,
                   trigger_function.proname AS function_name
              FROM pg_catalog.pg_trigger AS trigger_record
              JOIN pg_catalog.pg_class AS relation
                ON relation.oid = trigger_record.tgrelid
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
              JOIN pg_catalog.pg_proc AS trigger_function
                ON trigger_function.oid = trigger_record.tgfoid
             WHERE namespace_record.nspname = ANY (%s)
               AND NOT trigger_record.tgisinternal
             ORDER BY trigger_name, relation_name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        row = connection.execute(
            """
            SELECT (
                       SELECT count(*)
                         FROM pg_catalog.pg_class AS relation
                         JOIN pg_catalog.pg_namespace AS namespace_record
                           ON namespace_record.oid = relation.relnamespace
                        WHERE namespace_record.nspname = ANY (%s)
                          AND relation.relkind IN ('r', 'p')
                   ) AS table_count,
                   (
                       SELECT count(*)
                         FROM pg_catalog.pg_proc AS function_record
                         JOIN pg_catalog.pg_namespace AS namespace_record
                           ON namespace_record.oid = function_record.pronamespace
                        WHERE namespace_record.nspname = ANY (%s)
                          AND function_record.prokind = 'f'
                   ) AS function_count,
                   (
                       SELECT count(*)
                         FROM pg_catalog.pg_trigger AS trigger_record
                         JOIN pg_catalog.pg_class AS relation
                           ON relation.oid = trigger_record.tgrelid
                         JOIN pg_catalog.pg_namespace AS namespace_record
                           ON namespace_record.oid = relation.relnamespace
                        WHERE namespace_record.nspname = ANY (%s)
                          AND NOT trigger_record.tgisinternal
                   ) AS trigger_count
            """,
            (list(RELEASE_SCHEMAS),) * 3,
        ).fetchone()

    assert [table["name"] for table in tables] == expected_tables
    assert [function["name"] for function in functions] == expected_functions
    assert [
        (trigger["trigger_name"], trigger["relation_name"]) for trigger in triggers
    ] == trigger_pairs
    assert all(
        trigger["function_name"] == trigger["trigger_name"] for trigger in triggers
    )
    assert row == {"table_count": 100, "function_count": 79, "trigger_count": 15}


def test_every_release_table_has_a_valid_primary_key_and_valid_constraints(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        tables_without_primary_keys = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || relation.relname AS name
              FROM pg_catalog.pg_class AS relation
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND relation.relkind IN ('r', 'p')
               AND NOT EXISTS (
                       SELECT 1
                         FROM pg_catalog.pg_constraint AS constraint_record
                        WHERE constraint_record.conrelid = relation.oid
                          AND constraint_record.contype = 'p'
                          AND constraint_record.convalidated
                   )
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        invalid_constraints = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || relation.relname
                       || '.' || constraint_record.conname AS name
              FROM pg_catalog.pg_constraint AS constraint_record
              JOIN pg_catalog.pg_class AS relation
                ON relation.oid = constraint_record.conrelid
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND NOT constraint_record.convalidated
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        non_no_action_foreign_keys = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || relation.relname
                       || '.' || constraint_record.conname AS name
              FROM pg_catalog.pg_constraint AS constraint_record
              JOIN pg_catalog.pg_class AS relation
                ON relation.oid = constraint_record.conrelid
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND constraint_record.contype = 'f'
               AND (
                       constraint_record.confupdtype <> 'a'
                       OR constraint_record.confdeltype <> 'a'
                   )
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()

    assert tables_without_primary_keys == []
    assert invalid_constraints == []
    assert non_no_action_foreign_keys == []


def test_release_indexes_triggers_and_identity_columns_are_ready(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        invalid_indexes = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || index_relation.relname AS name
              FROM pg_catalog.pg_index AS index_record
              JOIN pg_catalog.pg_class AS relation
                ON relation.oid = index_record.indrelid
              JOIN pg_catalog.pg_class AS index_relation
                ON index_relation.oid = index_record.indexrelid
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND (
                       NOT index_record.indisvalid
                       OR NOT index_record.indisready
                       OR NOT index_record.indislive
                   )
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        disabled_triggers = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || relation.relname
                       || '.' || trigger_record.tgname AS name
              FROM pg_catalog.pg_trigger AS trigger_record
              JOIN pg_catalog.pg_class AS relation
                ON relation.oid = trigger_record.tgrelid
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND NOT trigger_record.tgisinternal
               AND trigger_record.tgenabled <> 'O'
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        non_always_identity_columns = connection.execute(
            """
            SELECT column_record.table_schema || '.' || column_record.table_name
                       || '.' || column_record.column_name AS name
              FROM information_schema.columns AS column_record
             WHERE column_record.table_schema = ANY (%s)
               AND column_record.is_identity = 'YES'
               AND column_record.identity_generation <> 'ALWAYS'
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()

    assert invalid_indexes == []
    assert disabled_triggers == []
    assert non_always_identity_columns == []


def test_release_functions_and_object_ownership_remain_hardened(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        unsafe_definers = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || function_record.proname AS name
              FROM pg_catalog.pg_proc AS function_record
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = function_record.pronamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND function_record.prosecdef
               AND (
                       function_record.proconfig IS NULL
                       OR NOT EXISTS (
                              SELECT 1
                                FROM unnest(function_record.proconfig) AS setting(value)
                               WHERE setting.value LIKE 'search_path=%%'
                                 AND setting.value NOT LIKE '%%public%%'
                                 AND setting.value NOT LIKE '%%$user%%'
                          )
                       OR has_function_privilege(
                              'public', function_record.oid, 'EXECUTE'
                          )
                   )
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        public_functions = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || function_record.proname AS name
              FROM pg_catalog.pg_proc AS function_record
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = function_record.pronamespace
             WHERE namespace_record.nspname = ANY (%s)
               AND has_function_privilege(
                       'public', function_record.oid, 'EXECUTE'
                   )
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()
        runtime_owned_objects = connection.execute(
            """
            SELECT namespace_record.nspname || '.' || relation.relname AS name
              FROM pg_catalog.pg_class AS relation
              JOIN pg_catalog.pg_namespace AS namespace_record
                ON namespace_record.oid = relation.relnamespace
              JOIN pg_catalog.pg_roles AS owner_role
                ON owner_role.oid = relation.relowner
             WHERE namespace_record.nspname = ANY (%s)
               AND owner_role.rolname IN (
                       'gds_app_write',
                       'gds_web_write',
                       'gds_mcp_runtime',
                       'gds_web_runtime',
                       'gds_notebook_runtime'
                   )
             ORDER BY name
            """,
            (list(RELEASE_SCHEMAS),),
        ).fetchall()

    assert unsafe_definers == []
    assert public_functions == []
    assert runtime_owned_objects == []
