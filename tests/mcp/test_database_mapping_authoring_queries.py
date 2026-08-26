from __future__ import annotations

# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING

from gds_etl_workbench.tools.modeling.code_generation_authoring import (
    _REFERENCE_CONTEXT_SQL,
)
from gds_etl_workbench.tools.modeling.mapping_authoring import _AUTHORING_CONTEXT_SQL

if TYPE_CHECKING:
    from conftest import DisposablePostgres


def test_runtime_role_can_execute_read_only_mapping_authoring_queries(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_runtime() as connection, connection.transaction():
        context = connection.execute(
            _AUTHORING_CONTEXT_SQL,
            (9_223_372_036_854_775_000, 1, 1, "logical_entity", 1, 1),
        ).fetchone()
        references = connection.execute(
            _REFERENCE_CONTEXT_SQL,
            (9_223_372_036_854_775_000, "logical_entity", 1, 1),
        ).fetchone()

    assert context is None
    assert references == {
        "references": {
            "source_predecessors": [],
            "target_predecessors": [],
            "provenance": [],
        }
    }


def test_mapping_authoring_query_fences_sources_to_model_scope() -> None:
    assert "eligible_object AS MATERIALIZED" in _AUTHORING_CONTEXT_SQL
    assert "JOIN eligible_object AS source_eligibility" in _AUTHORING_CONTEXT_SQL
    assert "source_eligibility.is_bronze_source_eligible" in _AUTHORING_CONTEXT_SQL
    assert "source_eligibility.is_dimensional_source_eligible" in _AUTHORING_CONTEXT_SQL
    assert "source_tenant.tenant_id = source_eligibility.object_tenant_id" in (
        _AUTHORING_CONTEXT_SQL
    )
