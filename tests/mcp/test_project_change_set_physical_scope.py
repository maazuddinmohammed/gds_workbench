from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, LiteralString, cast

import pytest
from gds_etl_workbench.application.change_sets import project as project_change_sets
from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
    validate_locked_project_change_set,
)
from gds_etl_workbench.application.change_sets.project_validation import (
    CodeGenerationTargetContext,
    validation_code_context_digest,
    validation_mapping_context_digest,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.infrastructure.postgres import WriteTransaction


@dataclass
class PhysicalScopeTransaction:
    calls: list[tuple[LiteralString, tuple[Any, ...]]] = field(default_factory=list)

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append((query, parameters))
        normalized = " ".join(query.split())
        if "project_tenant.tenant_code AS project_tenant_code" in normalized:
            return [
                {
                    "project_tenant_code": "TENANT-A",
                    "object_id": 101,
                    "tenant_code": " Tenant-A ",
                    "system_code": " ERP ",
                    "connection_code": " Foreign-Catalog ",
                    "object_schema": " Source ",
                    "object_name": " Orders ",
                    "attribute_id": 1001,
                    "attribute_name": " Order_ID ",
                },
                {
                    "project_tenant_code": "TENANT-A",
                    "object_id": 202,
                    "tenant_code": " GDS ",
                    "system_code": " GDS ",
                    "connection_code": " LakeHouse ",
                    "object_schema": " Silver ",
                    "object_name": " Orders ",
                    "attribute_id": 2002,
                    "attribute_name": " OrderID ",
                },
                {
                    "project_tenant_code": "TENANT-A",
                    "object_id": 303,
                    "tenant_code": " GDS ",
                    "system_code": " GDS ",
                    "connection_code": " LakeHouse ",
                    "object_schema": " Gold ",
                    "object_name": " Sales ",
                    "attribute_id": 3003,
                    "attribute_name": " SalesKey ",
                },
            ]
        if normalized.startswith("SELECT system_code FROM core.system"):
            return [{"system_code": " ERP "}, {"system_code": "CRM"}]
        if normalized.startswith("SELECT project_name FROM project.project"):
            return [{"project_name": " ExistingProject "}]
        if "list_project_object_eligibility" in normalized:
            return [
                {
                    "object_id": 101,
                    "is_project_input_eligible": True,
                },
                {
                    "object_id": 202,
                    "is_project_input_eligible": True,
                },
                {
                    "object_id": 303,
                    "is_project_input_eligible": False,
                },
            ]
        if "list_project_attribute_eligibility" in normalized:
            return [
                {
                    "attribute_id": 1001,
                    "is_project_input_eligible": True,
                },
                {
                    "attribute_id": 2002,
                    "is_project_input_eligible": True,
                },
                {
                    "attribute_id": 3003,
                    "is_project_input_eligible": False,
                },
            ]
        raise AssertionError(f"Unexpected physical Scope query: {normalized}")


@pytest.mark.asyncio
async def test_load_physical_scope_uses_placement_keys_and_new_eligibility_flags() -> (
    None
):
    transaction = PhysicalScopeTransaction()
    project = ProjectReadContext(
        project_id=77,
        tenant_id=7,
        project_name="Sales",
        project_revision=4,
    )

    scope = await load_project_physical_scope(
        cast(WriteTransaction, transaction), project
    )

    source = ("tenant-a", "erp", "foreign-catalog", "source", "orders")
    silver = ("gds", "gds", "lakehouse", "silver", "orders")
    assert scope.project_tenant_code == "TENANT-A"
    assert scope.project_input_objects == frozenset({source, silver})
    assert scope.project_input_attributes == frozenset(
        {(*source, "order_id"), (*silver, "orderid")}
    )
    assert scope.other_project_names == frozenset({"existingproject"})
    assert scope.active_system_codes == frozenset({"erp", "crm"})
    assert all(
        "list_code_generation_target_context" not in query
        for query, _ in transaction.calls
    )


@pytest.mark.asyncio
async def test_locked_change_set_loads_one_neutral_physical_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = ProjectReadContext(
        project_id=77,
        tenant_id=7,
        project_name="Sales",
        project_revision=4,
    )
    row: dict[str, object] = {
        "base_project_revision": 4,
        **{column: {} for column in project_change_sets.READ_SECTION_COLUMNS},
    }
    observed: dict[str, object] = {}
    result = object()

    async def build_snapshot(*args: object, **kwargs: object) -> object:
        return object()

    async def load_scope(*args: object, **kwargs: object) -> object:
        observed["scope_args"] = args
        observed["scope_kwargs"] = kwargs
        return object()

    def validate_graph(*args: object, **kwargs: object) -> object:
        return result

    monkeypatch.setattr(project_change_sets, "build_project_snapshot", build_snapshot)
    monkeypatch.setattr(project_change_sets, "load_project_physical_scope", load_scope)
    monkeypatch.setattr(project_change_sets, "validate_future_graph", validate_graph)

    actual = await validate_locked_project_change_set(
        cast(WriteTransaction, object()),
        project,
        row,
    )

    assert actual is result
    assert observed["scope_kwargs"] == {}
    assert len(cast(tuple[object, ...], observed["scope_args"])) == 2


def test_code_generation_target_context_uses_one_server_derived_digest() -> None:
    context = CodeGenerationTargetContext(
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
        modeled_entity_name="Orders",
        source_system_codes=frozenset({"erp"}),
        code_input_digest="a" * 64,
    )
    generated = SimpleNamespace(
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
        modeled_entity_name="Orders",
        source_system_codes=("ERP",),
        artifact_name="Orders.sql",
        artifact_type="sql_file",
        generated_code_content="SELECT 1",
        generated_code_status="active",
    )

    mapping_digest = validation_mapping_context_digest((context,), "ERP")
    code_digest = validation_code_context_digest((context,), (generated,), "ERP")

    assert mapping_digest is not None and len(mapping_digest) == 64
    assert code_digest is not None and len(code_digest) == 64
    assert mapping_digest != code_digest
