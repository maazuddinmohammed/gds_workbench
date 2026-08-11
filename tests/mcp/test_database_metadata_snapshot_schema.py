from __future__ import annotations

from typing import TYPE_CHECKING

from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    TABLES,
    ColumnDefinition,
    ColumnType,
    ForeignKeyDefinition,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


POSTGRES_TYPES: dict[str, ColumnType] = {
    "ARRAY": "bigint[]",
    "bigint": "bigint",
    "boolean": "boolean",
    "character varying": "varchar",
    "date": "date",
    "integer": "integer",
    "text": "text",
    "timestamp with time zone": "timestamptz",
}


def test_snapshot_table_contract_matches_canonical_database(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        for table in TABLES:
            database_schema, table_name = table.database_table.split(".", maxsplit=1)
            column_rows = connection.execute(
                """
                SELECT column_name, data_type, udt_name, is_nullable, is_identity
                  FROM information_schema.columns
                 WHERE table_schema = %s
                   AND table_name = %s
                 ORDER BY ordinal_position
                """,
                (database_schema, table_name),
            ).fetchall()
            actual_columns = tuple(
                ColumnDefinition(
                    name=row["column_name"],
                    type=POSTGRES_TYPES[row["data_type"]],
                    nullable=row["is_nullable"] == "YES",
                    generated=row["is_identity"] == "YES",
                )
                for row in column_rows
            )
            assert actual_columns == table.columns, table.database_table

            foreign_key_rows = connection.execute(
                """
                SELECT constraint_record.conname,
                       array_agg(
                           local_attribute.attname
                           ORDER BY key_position.position
                       ) AS columns,
                       referenced_namespace.nspname
                           || '.' || referenced_class.relname
                           AS references_table,
                       array_agg(
                           referenced_attribute.attname
                           ORDER BY key_position.position
                       ) AS references_columns
                  FROM pg_constraint AS constraint_record
                  JOIN pg_class AS local_class
                    ON local_class.oid = constraint_record.conrelid
                  JOIN pg_namespace AS local_namespace
                    ON local_namespace.oid = local_class.relnamespace
                  JOIN pg_class AS referenced_class
                    ON referenced_class.oid = constraint_record.confrelid
                  JOIN pg_namespace AS referenced_namespace
                    ON referenced_namespace.oid = referenced_class.relnamespace
                 CROSS JOIN LATERAL unnest(
                       constraint_record.conkey,
                       constraint_record.confkey
                 ) WITH ORDINALITY AS key_position(
                       local_attnum,
                       referenced_attnum,
                       position
                 )
                  JOIN pg_attribute AS local_attribute
                    ON local_attribute.attrelid = local_class.oid
                   AND local_attribute.attnum = key_position.local_attnum
                  JOIN pg_attribute AS referenced_attribute
                    ON referenced_attribute.attrelid = referenced_class.oid
                   AND referenced_attribute.attnum = key_position.referenced_attnum
                 WHERE constraint_record.contype = 'f'
                   AND local_namespace.nspname = %s
                   AND local_class.relname = %s
                 GROUP BY constraint_record.conname,
                          referenced_namespace.nspname,
                          referenced_class.relname
                 ORDER BY constraint_record.conname
                """,
                (database_schema, table_name),
            ).fetchall()
            actual_foreign_keys = {
                ForeignKeyDefinition(
                    columns=tuple(row["columns"]),
                    references_table=row["references_table"],
                    references_columns=tuple(row["references_columns"]),
                )
                for row in foreign_key_rows
            }
            assert actual_foreign_keys == set(table.foreign_keys), table.database_table

            unique_indexes = connection.execute(
                """
                SELECT pg_get_indexdef(index_record.indexrelid) AS definition
                  FROM pg_index AS index_record
                  JOIN pg_class AS table_record
                    ON table_record.oid = index_record.indrelid
                  JOIN pg_namespace AS table_namespace
                    ON table_namespace.oid = table_record.relnamespace
                 WHERE table_namespace.nspname = %s
                   AND table_record.relname = %s
                   AND index_record.indisunique
                   AND NOT index_record.indisprimary
                 ORDER BY index_record.indexrelid::REGCLASS::TEXT
                """,
                (database_schema, table_name),
            ).fetchall()
            assert len(unique_indexes) == len(table.unique_column_groups)
            for column_group in table.unique_column_groups:
                assert any(
                    all(column_name in row["definition"] for column_name in column_group)
                    for row in unique_indexes
                ), (table.database_table, column_group)
