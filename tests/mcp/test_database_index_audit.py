from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conftest import DisposablePostgres


def test_schema_has_no_redundant_same_predicate_index_prefixes(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT namespace.nspname || '.' || table_record.relname AS table_name,
                   smaller_index.relname AS smaller_index,
                   larger_index.relname AS covering_index,
                   pg_get_indexdef(smaller.indexrelid) AS smaller_definition,
                   pg_get_indexdef(larger.indexrelid) AS covering_definition
              FROM pg_index AS smaller
              JOIN pg_index AS larger
                ON larger.indrelid = smaller.indrelid
               AND larger.indexrelid <> smaller.indexrelid
              JOIN pg_class AS table_record
                ON table_record.oid = smaller.indrelid
              JOIN pg_namespace AS namespace
                ON namespace.oid = table_record.relnamespace
              JOIN pg_class AS smaller_index
                ON smaller_index.oid = smaller.indexrelid
              JOIN pg_class AS larger_index
                ON larger_index.oid = larger.indexrelid
             WHERE namespace.nspname IN (
                       'reference', 'core', 'security', 'model', 'workflow',
                       'application', 'mcp'
                   )
               AND smaller.indisvalid
               AND larger.indisvalid
               AND smaller.indpred IS NOT DISTINCT FROM larger.indpred
               AND smaller.indexprs IS NULL
               AND larger.indexprs IS NULL
               AND smaller.indnkeyatts <= larger.indnkeyatts
               AND (smaller.indkey::SMALLINT[])[0:smaller.indnkeyatts - 1]
                   = (larger.indkey::SMALLINT[])[0:smaller.indnkeyatts - 1]
               AND smaller_index.relname LIKE 'ix_%'
             ORDER BY table_name, smaller_index.relname, larger_index.relname
            """
        ).fetchall()
    assert rows == []
