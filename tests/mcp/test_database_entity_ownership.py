"""Fresh-install ownership, schema identity, and modeled lineage contracts."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    RaiseException,
    UniqueViolation,
)
from psycopg.types.json import Jsonb

if TYPE_CHECKING:
    from conftest import DisposablePostgres


def test_schema_lists_validate_shape_and_normalized_duplicates(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        for value, expected in (
            ([], True),
            ([{"schema_name": "sales", "description": None}], True),
            ([{"schema_name": "sales", "description": "Sales entities"}], True),
            ([{"schema_name": "sales"}], False),
            ([{"schema_name": "sales", "description": ""}], False),
            ([{"schema_name": "sales", "description": None, "extra": 1}], False),
            (
                [
                    {"schema_name": "sales", "description": None},
                    {"schema_name": " SALES ", "description": None},
                ],
                False,
            ),
            ({}, False),
            ([{"schema_name": "s" * 401, "description": None}], False),
            ([{"schema_name": "s", "description": "d" * 2001}], False),
            (
                [
                    {"schema_name": f"s{index}", "description": None}
                    for index in range(100)
                ],
                True,
            ),
            (
                [
                    {"schema_name": f"s{index}", "description": None}
                    for index in range(101)
                ],
                False,
            ),
        ):
            row = connection.execute(
                "SELECT model.valid_schema_list(%s) AS valid", (Jsonb(value),)
            ).fetchone()
            assert row is not None and row["valid"] is expected


def test_entity_schema_identity_and_direct_lineage(
    postgres_database: DisposablePostgres,
) -> None:
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            "INSERT INTO core.project (project_code,project_name) VALUES (%s,%s) RETURNING project_id",
            (suffix, suffix),
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            "INSERT INTO core.tenant (project_id,tenant_code,tenant_name,tenant_catalog,gds_admin_catalog) VALUES (%s,%s,%s,%s,%s) RETURNING tenant_id",
            (project["project_id"], suffix, suffix, suffix, suffix),
        ).fetchone()
        assert tenant is not None
        schemas = Jsonb(
            [
                {"schema_name": "sales", "description": None},
                {"schema_name": "finance", "description": None},
            ]
        )
        model = connection.execute(
            "INSERT INTO model.model (tenant_id,model_name,logical_schemas,dimensional_schemas) VALUES (%s,%s,%s,%s) RETURNING model_id",
            (tenant["tenant_id"], suffix, schemas, schemas),
        ).fetchone()
        assert model is not None
        model_id = model["model_id"]
        logical_sql = "INSERT INTO workflow.logical_entity (model_id,logical_entity_schema_name,logical_entity_name,logical_entity_definition,logical_entity_type,logical_entity_grain) VALUES (%s,%s,'Customer','Customer','core','One customer') RETURNING logical_entity_id"
        sales = connection.execute(logical_sql, (model_id, "sales")).fetchone()
        assert sales is not None
        connection.execute(logical_sql, (model_id, "finance"))
        with pytest.raises(UniqueViolation), connection.transaction():
            connection.execute(logical_sql, (model_id, " SALES "))
        with pytest.raises(RaiseException), connection.transaction():
            connection.execute(logical_sql, (model_id, "unconfigured"))
        with pytest.raises(RaiseException), connection.transaction():
            connection.execute(
                "UPDATE model.model SET logical_schemas = '[]'::JSONB WHERE model_id=%s",
                (model_id,),
            )
        dimensional = connection.execute(
            "INSERT INTO workflow.dimensional_entity (model_id,dimensional_entity_schema_name,dimensional_entity_name,dimensional_entity_definition,dimensional_entity_type) VALUES (%s,'sales','Customer','Customer','dimension') RETURNING dimensional_entity_id",
            (model_id,),
        ).fetchone()
        assert dimensional is not None
        connection.execute(
            "INSERT INTO workflow.dimensional_entity_source_mapping (model_id,dimensional_entity_id,support_source_type,source_logical_entity_id,dimensional_entity_source_role,dimensional_entity_source_mapping_rationale) VALUES (%s,%s,'logical_entity',%s,'source','Source meaning')",
            (
                model_id,
                dimensional["dimensional_entity_id"],
                sales["logical_entity_id"],
            ),
        )
        assert connection.execute(
            "SELECT to_regclass('workflow.model_object_binding') IS NULL AS removed"
        ).fetchone() == {"removed": True}
        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(
                "INSERT INTO workflow.dimensional_entity_source_mapping (model_id,dimensional_entity_id,support_source_type,source_logical_entity_id,dimensional_entity_source_role,dimensional_entity_source_mapping_rationale) VALUES (%s,%s,'logical_entity',9223372036854775807,'source','Invalid source')",
                (model_id, dimensional["dimensional_entity_id"]),
            )
        system_type = connection.execute(
            "INSERT INTO reference.system_type (system_type_code,system_type_name) VALUES (%s,%s) RETURNING system_type_id",
            (suffix, suffix),
        ).fetchone()
        assert system_type is not None
        system = connection.execute(
            "INSERT INTO core.system (system_code,system_name,system_type_id) VALUES (%s,%s,%s) RETURNING system_id",
            (suffix, suffix, system_type["system_type_id"]),
        ).fetchone()
        assert system is not None
        mapping = connection.execute(
            "INSERT INTO workflow.mapping_object (model_id,modeled_entity_type,logical_entity_id,source_system_id) VALUES (%s,'logical_entity',%s,%s) RETURNING mapping_object_id",
            (model_id, sales["logical_entity_id"], system["system_id"]),
        ).fetchone()
        assert mapping is not None
        attribute = connection.execute(
            "INSERT INTO workflow.logical_attribute (model_id,logical_entity_id,logical_attribute_name,logical_attribute_definition,logical_attribute_data_type,logical_attribute_ordinal_position) VALUES (%s,%s,'ID','Identifier','BIGINT',1) RETURNING logical_attribute_id",
            (model_id, sales["logical_entity_id"]),
        ).fetchone()
        assert attribute is not None
        connection.execute(
            "INSERT INTO workflow.mapping_attribute (mapping_object_id,model_id,modeled_entity_type,logical_entity_id,logical_attribute_id) VALUES (%s,%s,'logical_entity',%s,%s)",
            (
                mapping["mapping_object_id"],
                model_id,
                sales["logical_entity_id"],
                attribute["logical_attribute_id"],
            ),
        )
        other_attribute = connection.execute(
            "INSERT INTO workflow.logical_attribute (model_id,logical_entity_id,logical_attribute_name,logical_attribute_definition,logical_attribute_data_type,logical_attribute_ordinal_position) VALUES (%s,%s,'OtherID','Other identifier','BIGINT',2) RETURNING logical_attribute_id",
            (model_id, sales["logical_entity_id"]),
        ).fetchone()
        assert other_attribute is not None
        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(
                "INSERT INTO workflow.mapping_attribute (mapping_object_id,model_id,modeled_entity_type,logical_entity_id,logical_attribute_id) VALUES (%s,%s,'logical_entity',9223372036854775807,%s)",
                (
                    mapping["mapping_object_id"],
                    model_id,
                    other_attribute["logical_attribute_id"],
                ),
            )
        with pytest.raises(CheckViolation), connection.transaction():
            connection.execute(
                "INSERT INTO workflow.mapping_object (model_id,modeled_entity_type,logical_entity_id,dimensional_entity_id,source_system_id) VALUES (%s,'logical_entity',%s,%s,%s)",
                (
                    model_id,
                    sales["logical_entity_id"],
                    dimensional["dimensional_entity_id"],
                    system["system_id"],
                ),
            )
        connection.execute(
            "INSERT INTO workflow.generated_code (model_id,modeled_entity_type,logical_entity_id,artifact_name,artifact_type,generated_code_content,code_input_digest) VALUES (%s,'logical_entity',%s,'customer.sql','sql_file','SELECT 1',%s)",
            (model_id, sales["logical_entity_id"], "a" * 64),
        )
        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(
                "INSERT INTO workflow.generated_code (model_id,modeled_entity_type,logical_entity_id,artifact_name,artifact_type,generated_code_content,code_input_digest) VALUES (%s,'logical_entity',9223372036854775807,'other.sql','sql_file','SELECT 1',%s)",
                (model_id, "a" * 64),
            )


def test_frozen_entity_selection_has_only_history_foreign_keys(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        references = connection.execute(
            "SELECT confrelid::regclass::text AS referenced_table "
            "FROM pg_catalog.pg_constraint "
            "WHERE conrelid='application.workflow_run_entity_selection'::regclass "
            "AND contype='f' ORDER BY referenced_table"
        ).fetchall()
        assert references == [{"referenced_table": "application.workflow_run"}]
        pair_references = connection.execute(
            "SELECT confrelid::regclass::text AS referenced_table "
            "FROM pg_catalog.pg_constraint "
            "WHERE conrelid='application.workflow_run_mapping_target_selection'::regclass "
            "AND contype='f' ORDER BY referenced_table"
        ).fetchall()
        assert pair_references == [
            {"referenced_table": "application.workflow_run"},
            {"referenced_table": "application.workflow_run_entity_selection"},
            {"referenced_table": "core.system"},
        ]
