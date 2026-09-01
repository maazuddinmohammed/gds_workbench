from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, LiteralString, cast

import pytest

from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets import model as model_change_sets
from gds_etl_workbench.tools.change_sets.model import (
    _load_physical_scope,
    _validate_locked_change_set,
)
from gds_etl_workbench.tools.change_sets.model_validation import (
    CodeGenerationTargetContext,
)
from gds_etl_workbench.tools.modeling.common import ModelReadContext


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
                    "system_code": " GDS ",
                    "connection_code": " LakeHouse ",
                    "object_schema": " Silver ",
                    "object_name": " Orders ",
                    "attribute_id": 1001,
                    "attribute_name": " Order_ID ",
                },
                {
                    "model_tenant_code": "TENANT-A",
                    "object_id": 202,
                    "tenant_code": " Tenant-A ",
                    "system_code": " GDS ",
                    "connection_code": " LakeHouse ",
                    "object_schema": " Gold ",
                    "object_name": " Sales ",
                    "attribute_id": 2002,
                    "attribute_name": " Sales_Key ",
                },
            ]
        if normalized.startswith("SELECT system_code FROM core.system"):
            return [
                {"system_code": " ERP "},
                {"system_code": "CRM"},
                {"system_code": " Finance "},
            ]
        if normalized.startswith("SELECT model_name FROM model.model"):
            return []
        if "list_model_object_eligibility" in normalized:
            return [
                {
                    "object_id": 101,
                    "is_bronze_source_eligible": False,
                    "is_dimensional_source_eligible": True,
                    "is_logical_mapping_target_eligible": True,
                    "is_dimensional_mapping_target_eligible": False,
                },
                {
                    "object_id": 202,
                    "is_bronze_source_eligible": False,
                    "is_dimensional_source_eligible": False,
                    "is_logical_mapping_target_eligible": False,
                    "is_dimensional_mapping_target_eligible": True,
                },
            ]
        if "list_model_attribute_eligibility" in normalized:
            return [
                {
                    "attribute_id": 1001,
                    "is_bronze_source_eligible": False,
                    "is_dimensional_source_eligible": True,
                    "is_logical_mapping_target_eligible": True,
                    "is_dimensional_mapping_target_eligible": False,
                },
                {
                    "attribute_id": 2002,
                    "is_bronze_source_eligible": False,
                    "is_dimensional_source_eligible": False,
                    "is_logical_mapping_target_eligible": False,
                    "is_dimensional_mapping_target_eligible": True,
                },
            ]
        if "list_code_generation_target_context" in normalized:
            return [
                {
                    "modeled_entity_type": "logical_entity",
                    "object_id": 101,
                    "mapping_context_digest": f"  {'A' * 64}  ",
                    "source_context_digest": f"  {'B' * 64}  ",
                    "source_context": {
                        "source_systems": [
                            {"system_code": " ERP "},
                            {"system_code": "cRm"},
                        ]
                    },
                },
                {
                    "modeled_entity_type": "dimensional_entity",
                    "object_id": 202,
                    "mapping_context_digest": f"  {'C' * 64}  ",
                    "source_context_digest": f"  {'D' * 64}  ",
                    "source_context": {
                        "source_systems": [{"system_code": " Finance "}]
                    },
                },
            ]
        raise AssertionError(f"Unexpected physical Scope query: {normalized}")


@pytest.mark.asyncio
async def test_load_physical_scope_builds_both_code_generation_context_layers() -> None:
    transaction = PhysicalScopeTransaction()
    model = ModelReadContext(
        model_id=77,
        tenant_id=7,
        model_name="Sales",
        model_revision=4,
    )

    scope = await _load_physical_scope(
        cast(WriteTransaction, transaction),
        model,
    )

    context_query, context_parameters = next(
        (query, parameters)
        for query, parameters in transaction.calls
        if "list_code_generation_target_context" in query
    )
    assert "'logical_entity'," in context_query
    assert "'dimensional_entity'," in context_query
    assert context_parameters == (77, "sql_file", 77, "sql_file")
    assert scope.code_generation_contexts == (
        CodeGenerationTargetContext(
            object_key=("tenant-a", "gds", "lakehouse", "silver", "orders"),
            modeled_entity_type="logical_entity",
            source_system_codes=frozenset({"erp", "crm"}),
            mapping_context_digest="a" * 64,
            source_context_digest="b" * 64,
        ),
        CodeGenerationTargetContext(
            object_key=("tenant-a", "gds", "lakehouse", "gold", "sales"),
            modeled_entity_type="dimensional_entity",
            source_system_codes=frozenset({"finance"}),
            mapping_context_digest="c" * 64,
            source_context_digest="d" * 64,
        ),
    )


@pytest.mark.asyncio
async def test_load_physical_scope_can_include_any_mapping_artifact_for_qa() -> None:
    transaction = PhysicalScopeTransaction()
    model = ModelReadContext(
        model_id=77,
        tenant_id=7,
        model_name="Sales",
        model_revision=4,
    )

    await _load_physical_scope(
        cast(WriteTransaction, transaction),
        model,
        required_artifact_type=None,
    )

    _, context_parameters = next(
        (query, parameters)
        for query, parameters in transaction.calls
        if "list_code_generation_target_context" in query
    )
    assert context_parameters == (77, None, 77, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("qa_records", "code_records", "expected_artifact_type"),
    [
        ([{"validation_group_name": "QA"}], [], None),
        (
            [{"validation_group_name": "QA"}],
            [{"artifact_type": "sql_file"}],
            "sql_file",
        ),
        ([], [{"artifact_type": "sql_file"}], "sql_file"),
    ],
)
async def test_locked_change_set_uses_neutral_context_only_for_qa_without_code(
    monkeypatch: pytest.MonkeyPatch,
    qa_records: list[dict[str, object]],
    code_records: list[dict[str, object]],
    expected_artifact_type: str | None,
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
    row["qa_document"] = {"validation_group": qa_records}
    row["code_generation_document"] = {"generated_code": code_records}
    observed: dict[str, object] = {}
    result = object()

    async def build_snapshot(*args: object, **kwargs: object) -> object:
        return object()

    async def load_scope(
        *args: object,
        required_artifact_type: str | None,
        **kwargs: object,
    ) -> object:
        observed["required_artifact_type"] = required_artifact_type
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
    assert observed["required_artifact_type"] == expected_artifact_type
