"""Code authoring accepts partial saved Mapping; Validation keeps complete inputs."""

# These helpers create only fixture-owned disposable PostgreSQL contents.
# pyright: reportPrivateUsage=false

from typing import Any

import pytest
from gds_workbench_api.features.code_generation.contracts import CodeGenerationTargetSummary
from gds_workbench_api.features.code_generation.read_service import _CODE_GENERATION_TARGETS_SQL
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_mapping_source_context import (
    _seed_assertion_mapping_target,
    _seed_mapping_scope,
)


@pytest.mark.parametrize("dimensional", [False, True], ids=["logical", "dimensional"])
@pytest.mark.parametrize(
    "shape",
    [
        "complete",
        "object_only",
        "attribute_only",
        "partial",
        "empty",
        "inactive",
        "inactive_attribute",
        "inactive_target_attribute",
    ],
)
def test_code_keeps_partial_system_pairs_and_all_active_target_attributes(
    web_postgres_database: DisposablePostgres,
    dimensional: bool,
    shape: str,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False, create_run=False)
    entity_id, _ = _seed_assertion_mapping_target(
        web_postgres_database, scope, dimensional=dimensional
    )
    layer = "dimensional" if dimensional else "logical"
    entity_type = f"{layer}_entity"
    with web_postgres_database.connect_owner() as connection:
        columns = [
            "model_id",
            f"{layer}_entity_id",
            f"{layer}_attribute_name",
            f"{layer}_attribute_definition",
            f"{layer}_attribute_data_type",
            f"{layer}_attribute_ordinal_position",
        ]
        values = "%s, %s, 'field_' || position, 'Synthetic field.', 'bigint', position"
        if dimensional:
            columns.append("dimensional_attribute_role")
            values += ", 'descriptor'"
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.{} ({}) SELECT {} FROM generate_series(2,10) position"
            ).format(
                sql.Identifier(f"{layer}_attribute"),
                sql.SQL(",").join(map(sql.Identifier, columns)),
                sql.SQL(values),
            ),
            (scope.plan.model_id, entity_id),
        )
        attributes = connection.execute(
            "SELECT modeled_attribute_id, attribute_name FROM workflow.modeled_attribute "
            "WHERE model_id=%s AND modeled_entity_type=%s AND modeled_entity_id=%s "
            "ORDER BY ordinal_position",
            (scope.plan.model_id, entity_type, entity_id),
        ).fetchall()
        assert len(attributes) == 10
        mapping_ids: list[int] = []
        for index, system_id in enumerate([scope.source_system_id, scope.other_system_id]):
            object_document = (
                None
                if index == 1
                and shape
                in {"attribute_only", "empty", "inactive_attribute", "inactive_target_attribute"}
                else Jsonb({"steps": ["Generate the reference row."]})
            )
            mapping = require_row(
                connection.execute(
                    sql.SQL(
                        "INSERT INTO workflow.mapping_object (model_id,modeled_entity_type,{},"
                        "source_system_id,mapping_transformation_document,object_mapping_status) "
                        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING mapping_object_id"
                    ).format(sql.Identifier(f"{layer}_entity_id")),
                    (
                        scope.plan.model_id,
                        entity_type,
                        entity_id,
                        system_id,
                        object_document,
                        "inactive" if index == 1 and shape == "inactive" else "active",
                    ),
                ).fetchone()
            )
            mapping_ids.append(mapping["mapping_object_id"])
            for ordinal, attribute in enumerate(attributes, 1):
                # Include both absent rows and saved blanks for the partial branch.
                if (
                    index == 1
                    and shape not in {"complete", "inactive_target_attribute"}
                    and ordinal > 8
                ):
                    continue
                present = (
                    index == 0
                    or shape == "complete"
                    or (
                        shape in {"attribute_only", "partial", "inactive_attribute"}
                        and ordinal <= 5
                    )
                    or (shape == "inactive_target_attribute" and ordinal == 10)
                )
                connection.execute(
                    sql.SQL(
                        "INSERT INTO workflow.mapping_attribute (mapping_object_id,model_id,"
                        "modeled_entity_type,{},{},attribute_mapping_transformation_document,"
                        "attribute_mapping_status) VALUES (%s,%s,%s,%s,%s,%s,%s)"
                    ).format(
                        sql.Identifier(f"{layer}_entity_id"),
                        sql.Identifier(f"{layer}_attribute_id"),
                    ),
                    (
                        mapping["mapping_object_id"],
                        scope.plan.model_id,
                        entity_type,
                        entity_id,
                        attribute["modeled_attribute_id"],
                        Jsonb({"transformation": str(ordinal)}) if present else None,
                        "inactive" if index == 1 and shape == "inactive_attribute" else "active",
                    ),
                )
        if shape == "inactive_target_attribute":
            connection.execute(
                sql.SQL("UPDATE workflow.{} SET {}='inactive' WHERE {}=%s").format(
                    sql.Identifier(f"{layer}_attribute"),
                    sql.Identifier(f"{layer}_attribute_status"),
                    sql.Identifier(f"{layer}_attribute_id"),
                ),
                (attributes[-1]["modeled_attribute_id"],),
            )
            attributes = attributes[:-1]
        query = (
            "SELECT code_input_digest, source_system_count, source_context "
            "FROM workflow.list_code_generation_target_context(%s,%s,%s) "
            "WHERE modeled_entity_id=%s"
        )
        code = require_row(
            connection.execute(
                query, (scope.plan.model_id, entity_type, "sql_file", entity_id)
            ).fetchone()
        )
        strict = connection.execute(
            query, (scope.plan.model_id, entity_type, None, entity_id)
        ).fetchone()
        retained_partial = shape not in {
            "empty",
            "inactive",
            "inactive_attribute",
            "inactive_target_attribute",
        }
        assert code["source_system_count"] == (2 if retained_partial else 1)
        context: dict[str, Any] = code["source_context"]
        assert {row["source_system_id"] for row in context["source_systems"]} == (
            {scope.source_system_id, scope.other_system_id}
            if retained_partial
            else {scope.source_system_id}
        )
        picker_rows = connection.execute(
            _CODE_GENERATION_TARGETS_SQL,
            (scope.tenant_id, scope.plan.model_id, entity_type, entity_type, *([None] * 8), 200, 0),
        ).fetchall()
        picker = CodeGenerationTargetSummary.model_validate(
            next(row for row in picker_rows if row["target"]["entity_id"] == entity_id),
            strict=False,
        )
        assert {system.system_id for system in picker.source_systems} == {
            row["source_system_id"] for row in context["source_systems"]
        }
        assert picker.mapping_support_count == code["source_system_count"]
        for support in picker.mapping_supports:
            is_partial = support.source_system.system_id == scope.other_system_id
            assert support.object_transformation_missing == (
                is_partial and shape == "attribute_only"
            )
            assert support.unmapped_attribute_count == (
                10
                if is_partial and shape == "object_only"
                else 5
                if is_partial and shape in {"attribute_only", "partial"}
                else 0
            )
            assert support.unmapped_attribute_names == tuple(
                row["target_attribute_name"]
                for row in context["attribute_mappings"]
                if row["source_system_id"] == support.source_system.system_id
                and row["transformation"] is None
            )
        for system_id in [scope.source_system_id, scope.other_system_id]:
            mapped = [
                row for row in context["attribute_mappings"] if row["source_system_id"] == system_id
            ]
            if system_id == scope.other_system_id and not retained_partial:
                assert mapped == []
                continue
            assert [row["target_attribute_name"] for row in mapped] == [
                attribute["attribute_name"] for attribute in attributes
            ]
            expected_count = (
                len(attributes)
                if system_id == scope.source_system_id or shape == "complete"
                else 0
                if shape == "object_only"
                else 5
            )
            assert sum(row["transformation"] is not None for row in mapped) == expected_count
            if system_id == scope.other_system_id and shape != "complete":
                assert all(row["mapping_attribute_id"] is None for row in mapped[-2:])
        if shape == "attribute_only":
            assert (
                next(
                    row
                    for row in context["object_mappings"]
                    if row["source_system_id"] == scope.other_system_id
                )["transformation"]
                is None
            )
        if shape in {"complete", "inactive"}:
            assert strict is not None
            assert strict == code  # Complete contexts retain the same canonical digest.
        else:
            assert strict is None
        # With the complete pair inactive, only real partial results keep the Entity available.
        connection.execute(
            "UPDATE workflow.mapping_object SET object_mapping_status='inactive' "
            "WHERE mapping_object_id=%s",
            (mapping_ids[0],),
        )
        remaining = connection.execute(
            query, (scope.plan.model_id, entity_type, "sql_file", entity_id)
        ).fetchone()
        assert (remaining is not None) == retained_partial
