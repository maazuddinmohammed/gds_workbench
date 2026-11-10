from __future__ import annotations

# pyright: reportPrivateUsage=false
from typing import Any, LiteralString, Protocol, cast
from uuid import UUID

import pytest
from atlas_mcp.application.mapping_context import mapping_context_issues, project_mapping_inputs
from atlas_platform.features.mapping import assess_mapping_readiness
from atlas_platform.features.mapping import preparation_repository as preparation
from atlas_platform.features.mapping.preparation_contracts import MappingModeledEntity
from atlas_platform.features.mapping.read_service import (
    _MAPPING_GENERATION_TARGETS_SQL,
    _UNSUPPLIED_ENTITY_COUNT_SQL,
)
from psycopg import Connection
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_mapping_source_context import _load, _seed_mapping_scope


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...


def _sql(name: str) -> LiteralString:
    value = vars(preparation).get(name)
    if not isinstance(value, str):
        raise AssertionError(f"missing Mapping preparation query {name}")
    return cast(LiteralString, value)


def test_mapping_preparation_queries_compile_against_disposable_postgres(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    correlation_id = UUID("33333333-3333-3333-3333-333333333333")
    queries: tuple[tuple[LiteralString, tuple[Any, ...]], ...] = (
        (
            _MAPPING_GENERATION_TARGETS_SQL,
            (7, 18, "logical_entity", 7, 18, "logical_entity", 201, 0),
        ),
        (_UNSUPPLIED_ENTITY_COUNT_SQL, (7, 18, "logical_entity", 18, "logical_entity")),
        (_sql("_MAPPING_RUN_PLAN_SQL"), (7, 18, 1048, 7, 77)),
        (
            _sql("_MAPPING_CONTEXT_ANCHOR_SQL"),
            (
                7,
                7,
                1048,
                18,
                77,
                correlation_id,
                501,
                31,
                "logical_entity",
                "logical_to_silver",
                "build",
            ),
        ),
        (_sql("_MAPPING_TARGET_NODES_SQL"), (18, "logical_entity")),
        (_sql("_MAPPING_TARGET_EDGES_SQL"), (18, "logical_entity")),
        (_sql("_MAPPING_ENTITY_CONTEXT_SQL"), (18, 501, "logical_entity", 31)),
        (
            _sql("MAPPING_SOURCE_CONTEXT_SQL"),
            (18, 501, "logical_entity", 31),
        ),
        (_sql("_MAPPING_UPSTREAM_PHYSICAL_CONTEXT_SQL"), (501, 18, 18, 31)),
        (_sql("_MAPPING_UPSTREAM_TEMPLATE_IDS_SQL"), (18, [401, 402], [501])),
        (_sql("_MAPPING_OUTPUT_TEMPLATE_CONTEXT_SQL"), ([801, 802],)),
    )

    with web_postgres_database.connect_owner() as connection:
        for query, parameters in queries:
            connection.execute(f"EXPLAIN {query}", parameters).fetchall()


@pytest.mark.parametrize("dimensional", (False, True))
async def test_reviewed_self_reference_is_available_to_code(
    web_postgres_database: DisposablePostgres,
    dimensional: bool,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=dimensional, generate=True)
    target_id = scope.plan.pair.modeled_entity_id
    layer = "dimensional" if dimensional else "logical"
    plan = scope.plan
    with web_postgres_database.connect_owner() as connection:
        # A saved Mapping alone must not make the Entity eligible as its own source.
        connection.execute(
            f"""INSERT INTO workflow.mapping_object (
                    project_id, modeled_entity_type, {layer}_entity_id, source_system_id,
                    mapping_transformation_document
                ) VALUES (%s,%s,%s,%s,'{{}}') ON CONFLICT DO NOTHING""",
            (plan.project_id, plan.modeled_entity_type, target_id, scope.source_system_id),
        )
    before = await _load(web_postgres_database, scope)
    assert not any(
        isinstance(item.object, MappingModeledEntity)
        and item.object.entity_type == plan.modeled_entity_type
        and item.object.entity_id == target_id
        for item in before.sources
    )
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            f"""
            WITH parent AS (
                SELECT project_id, {layer}_entity_id, {layer}_attribute_id
                  FROM workflow.{layer}_attribute
                 WHERE project_id=%s AND {layer}_entity_id=%s
                   AND {layer}_attribute_ordinal_position=1
            ), children AS (
                INSERT INTO workflow.{layer}_attribute (
                    project_id, {layer}_entity_id, {layer}_attribute_name,
                    {layer}_attribute_definition, {layer}_attribute_data_type,
                    {layer}_attribute_ordinal_position
                )
                SELECT project_id, {layer}_entity_id, field.name, 'Related customer.',
                       'bigint', field.ordinal FROM parent CROSS JOIN (
                    VALUES ('parent_id', 2), ('referrer_id', 3), ('former_parent_id', 4)
                ) AS field(name, ordinal)
                RETURNING {layer}_attribute_id, {layer}_attribute_name
            )
            INSERT INTO workflow.{layer}_relationship (
                project_id, {layer}_relationship_from_entity_id,
                {layer}_relationship_from_attribute_id, {layer}_relationship_to_entity_id,
                {layer}_relationship_to_attribute_id, {layer}_relationship_basis,
                {layer}_relationship_is_active
            )
            SELECT parent.project_id, parent.{layer}_entity_id, children.{layer}_attribute_id,
                   parent.{layer}_entity_id, parent.{layer}_attribute_id, 'Fixture relationship.',
                   children.{layer}_attribute_name <> 'former_parent_id'
              FROM parent CROSS JOIN children
            """,
            (scope.plan.project_id, target_id),
        )
    context = await _load(web_postgres_database, scope)
    (edge,) = context.target_dependency_graph.edges
    assert edge.predecessor_modeled_entity_id == context.target.entity_id
    assert edge.successor_modeled_entity_id == context.target.entity_id
    assert edge.child_attribute_names == ("parent_id", "referrer_id")
    self_lookups = [
        item
        for item in context.sources
        if isinstance(item.object, MappingModeledEntity)
        and item.object.entity_type == plan.modeled_entity_type
        and item.object.entity_id == target_id
    ]
    assert [item.role for item in self_lookups] == ["lookup"]
    readiness = assess_mapping_readiness(plan=scope.plan, context=context)
    assert readiness.ready
    assert readiness.deferred_dependency_attributes == edge.child_attribute_names
    assert readiness.warnings[0].code == "dependency.cycle"
    assert "parent_id, referrer_id" in readiness.warnings[0].message
    wrong_role = context.model_copy(
        update={"sources": (self_lookups[0].model_copy(update={"role": "support"}),)}
    )
    assert "source.self_reference" in {
        issue.code for issue in assess_mapping_readiness(plan=plan, context=wrong_role).issues
    }

    reviewed = {
        "source_columns": [
            {
                "entity_type": plan.modeled_entity_type,
                "entity_schema_name": context.target.entity_schema_name,
                "entity_name": context.target.entity_name,
                "attribute_name": "customer_id",
            }
        ],
        "transformation_logic": "Resolve the reviewed parent key after the base row is loaded.",
    }
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            f"""INSERT INTO workflow.mapping_attribute (
                    mapping_object_id, project_id, modeled_entity_type, {layer}_entity_id,
                    {layer}_attribute_id, attribute_mapping_transformation_document
                ) SELECT m.mapping_object_id, m.project_id, m.modeled_entity_type,
                         m.{layer}_entity_id, a.{layer}_attribute_id, %s
                    FROM workflow.mapping_object m JOIN workflow.{layer}_attribute a
                      ON a.{layer}_entity_id=m.{layer}_entity_id AND a.project_id=m.project_id
                   WHERE a.{layer}_attribute_name='parent_id' AND m.{layer}_entity_id=%s
                     AND m.project_id=%s""",
            (Jsonb(reviewed), target_id, plan.project_id),
        )
        code_query: LiteralString = (
            "SELECT source_context FROM workflow.list_code_generation_target_context(%s,%s,NULL) "
            "WHERE modeled_entity_id=%s"
        )
        parameters = (plan.project_id, plan.modeled_entity_type, target_id)
        result = connection.execute(code_query, parameters).fetchone()
        assert result is not None
        values = project_mapping_inputs(result["source_context"], workflow="code_generation")
        assert reviewed in [row["transformation"] for row in values["attribute_transformations"]]
        assert "mapping_source_attribute_missing_or_ineligible" not in mapping_context_issues(
            values
        )
        connection.execute(
            f"UPDATE workflow.{layer}_relationship SET {layer}_relationship_is_active=FALSE "
            f"WHERE project_id=%s AND {layer}_relationship_from_entity_id=%s",
            (plan.project_id, target_id),
        )
        result = connection.execute(code_query, parameters).fetchone()
        assert result is not None
        values = project_mapping_inputs(result["source_context"], workflow="code_generation")
        assert "mapping_source_attribute_missing_or_ineligible" in mapping_context_issues(values)
