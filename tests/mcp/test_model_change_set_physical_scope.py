from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, LiteralString, cast

import pytest

from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.application.change_sets import model as model_change_sets
from gds_etl_workbench.application.change_sets.model import (
    _load_physical_scope,
    _validate_locked_change_set,
)
from gds_etl_workbench.application.change_sets.model_validation import (
    CodeGenerationTargetContext,
    validation_code_context_digest,
    validation_mapping_context_digest,
)
from gds_etl_workbench.application.model_read import ModelReadContext


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
        if "model_tenant.tenant_code AS model_tenant_code" in normalized:
            return [
                {
                    "model_tenant_code": "TENANT-A",
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
                    "model_tenant_code": "TENANT-A",
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
                    "model_tenant_code": "TENANT-A",
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
        if normalized.startswith("SELECT model_name FROM model.model"):
            return [{"model_name": " ExistingModel "}]
        if "list_model_object_eligibility" in normalized:
            return [
                {
                    "object_id": 101,
                    "is_model_input_eligible": True,
                    "is_dimensional_source_eligible": False,
                    "is_logical_mapping_target_eligible": False,
                    "is_dimensional_mapping_target_eligible": False,
                },
                {
                    "object_id": 202,
                    "is_model_input_eligible": True,
                    "is_dimensional_source_eligible": True,
                    "is_logical_mapping_target_eligible": True,
                    "is_dimensional_mapping_target_eligible": False,
                },
                {
                    "object_id": 303,
                    "is_model_input_eligible": False,
                    "is_dimensional_source_eligible": False,
                    "is_logical_mapping_target_eligible": False,
                    "is_dimensional_mapping_target_eligible": True,
                },
            ]
        if "list_model_attribute_eligibility" in normalized:
            return [
                {
                    "attribute_id": 1001,
                    "is_model_input_eligible": True,
                    "is_dimensional_source_eligible": False,
                    "is_logical_mapping_target_eligible": False,
                    "is_dimensional_mapping_target_eligible": False,
                },
                {
                    "attribute_id": 2002,
                    "is_model_input_eligible": True,
                    "is_dimensional_source_eligible": True,
                    "is_logical_mapping_target_eligible": True,
                    "is_dimensional_mapping_target_eligible": False,
                },
                {
                    "attribute_id": 3003,
                    "is_model_input_eligible": False,
                    "is_dimensional_source_eligible": False,
                    "is_logical_mapping_target_eligible": False,
                    "is_dimensional_mapping_target_eligible": True,
                },
            ]
        raise AssertionError(f"Unexpected physical Scope query: {normalized}")


@pytest.mark.asyncio
async def test_load_physical_scope_uses_placement_keys_and_new_eligibility_flags() -> (
    None
):
    transaction = PhysicalScopeTransaction()
    model = ModelReadContext(
        model_id=77,
        tenant_id=7,
        model_name="Sales",
        model_revision=4,
    )

    scope = await _load_physical_scope(cast(WriteTransaction, transaction), model)

    source = ("tenant-a", "erp", "foreign-catalog", "source", "orders")
    silver = ("gds", "gds", "lakehouse", "silver", "orders")
    gold = ("gds", "gds", "lakehouse", "gold", "sales")
    assert scope.model_tenant_code == "TENANT-A"
    assert scope.model_input_objects == frozenset({source, silver})
    assert scope.dimensional_source_objects == frozenset({silver})
    assert scope.logical_mapping_target_objects == frozenset({silver})
    assert scope.dimensional_mapping_target_objects == frozenset({gold})
    assert scope.model_input_attributes == frozenset(
        {(*source, "order_id"), (*silver, "orderid")}
    )
    assert scope.other_model_names == frozenset({"existingmodel"})
    assert scope.active_system_codes == frozenset({"erp", "crm"})
    assert all(
        "list_code_generation_target_context" not in query
        for query, _ in transaction.calls
    )


@pytest.mark.asyncio
async def test_locked_change_set_loads_one_neutral_physical_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = ModelReadContext(
        model_id=77,
        tenant_id=7,
        model_name="Sales",
        model_revision=4,
    )
    row: dict[str, object] = {
        "base_model_revision": 4,
        **{column: {} for column in model_change_sets.READ_SECTION_COLUMNS},
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

    monkeypatch.setattr(model_change_sets, "build_model_snapshot", build_snapshot)
    monkeypatch.setattr(model_change_sets, "_load_physical_scope", load_scope)
    monkeypatch.setattr(model_change_sets, "validate_future_graph", validate_graph)

    actual = await _validate_locked_change_set(
        cast(WriteTransaction, object()),
        model,
        row,
    )

    assert actual is result
    assert observed["scope_kwargs"] == {}
    assert len(cast(tuple[object, ...], observed["scope_args"])) == 2


def test_code_generation_target_context_uses_one_server_derived_digest() -> None:
    context = CodeGenerationTargetContext(
        object_key=("gds", "gds", "lakehouse", "silver", "orders"),
        modeled_entity_type="logical_entity",
        modeled_entity_name="Orders",
        source_system_codes=frozenset({"erp"}),
        code_input_digest="a" * 64,
    )
    generated = SimpleNamespace(
        modeled_entity_type="logical_entity",
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
