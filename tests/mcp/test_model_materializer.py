from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, LiteralString, cast

import pytest

from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
    MappingAttributeRecord,
    MappingDependencyRecord,
    MappingObjectRecord,
    ModelAttributeBindingRecord,
    ModelInputScopeRecord,
    ModelObjectBindingRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    ValidationGroupRecord,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer


@dataclass(frozen=True)
class ExpectedCall:
    method: Literal["one", "all"]
    contains: str
    result: dict[str, Any] | None | list[dict[str, Any]]


@dataclass
class ScriptedTransaction:
    expected: list[ExpectedCall]
    calls: list[tuple[str, LiteralString, tuple[Any, ...]]] = field(
        default_factory=list
    )

    def _next(
        self, method: Literal["one", "all"], query: LiteralString
    ) -> ExpectedCall:
        assert self.expected, f"unexpected {method} query: {' '.join(query.split())}"
        expected = self.expected.pop(0)
        assert expected.method == method
        assert expected.contains in query
        return expected

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        expected = self._next("one", query)
        self.calls.append(("one", query, parameters))
        assert expected.result is None or isinstance(expected.result, dict)
        return expected.result

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        expected = self._next("all", query)
        self.calls.append(("all", query, parameters))
        assert isinstance(expected.result, list)
        return expected.result

    def assert_complete(self) -> None:
        assert not self.expected


def _materializer(transaction: ScriptedTransaction) -> ModelMaterializer:
    return ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="f" * 64,
    )


def _object_binding() -> ModelObjectBindingRecord:
    return ModelObjectBindingRecord(
        tenant_code="GDS",
        system_code="GDS",
        connection_code="GDS",
        object_schema="silver",
        object_name="Customer",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        model_object_binding_status="active",
        model_object_binding_is_locked=False,
    )


def _attribute_binding() -> ModelAttributeBindingRecord:
    return ModelAttributeBindingRecord(
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        modeled_attribute_name="CustomerID",
        attribute_name="CustomerID",
        model_attribute_binding_status="active",
        model_attribute_binding_is_locked=False,
    )


def _mapping_object() -> MappingObjectRecord:
    return MappingObjectRecord(
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        source_system_code="CRM",
        output_template_code="mapping-object",
        object_dependency_order=2,
        mapping_transformation_document={"kind": "merge", "key": "CustomerID"},
        object_mapping_status="active",
        object_mapping_is_locked=False,
    )


def _mapping_attribute() -> MappingAttributeRecord:
    return MappingAttributeRecord(
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        modeled_attribute_name="CustomerID",
        source_system_code="CRM",
        output_template_code="mapping-attribute",
        attribute_mapping_transformation_document={"expression": "CustomerID"},
        attribute_mapping_status="active",
        attribute_mapping_is_locked=False,
    )


@pytest.mark.asyncio
async def test_physical_keys_use_placement_tenant_and_fence_source_to_model() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall(
                "one", "SELECT object.object_id", {"object_id": 11, "system_id": 5}
            ),
            ExpectedCall(
                "one",
                "JOIN core.attribute AS attribute",
                {"object_id": 11, "attribute_id": 12, "system_id": 5},
            ),
        ]
    )
    materializer = _materializer(transaction)

    await materializer.resolve_object(
        PhysicalObjectKey(
            tenant_code="GDS",
            system_code="GDS",
            connection_code="GDS",
            object_schema="silver",
            object_name="Customer",
        )
    )
    await materializer.resolve_attribute(
        PhysicalAttributeKey(
            tenant_code="GDS",
            system_code="GDS",
            connection_code="GDS",
            object_schema="silver",
            object_name="Customer",
            attribute_name="CustomerID",
        )
    )

    for _, query, parameters in transaction.calls:
        assert "placement_tenant.tenant_id = connection.tenant_id" in query
        assert "object.source_tenant_id = target_model.tenant_id" in query
        assert parameters[:2] == ("gds", 7)
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_model_input_scope_materializes_before_model_bindings() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall(
                "one", "SELECT object.object_id", {"object_id": 11, "system_id": 5}
            ),
            ExpectedCall(
                "one",
                "INSERT INTO model.model_input_scope",
                {"model_input_scope_id": 1},
            ),
            ExpectedCall("one", "SELECT logical_entity_id", {"logical_entity_id": 101}),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.model_object_binding",
                {"model_object_binding_id": 201, "object_id": 11},
            ),
        ]
    )
    materializer = _materializer(transaction)
    scope = ModelInputScopeRecord(
        tenant_code="GDS",
        system_code="GDS",
        connection_code="GDS",
        object_schema="silver",
        object_name="Customer",
        model_input_scope_is_locked=False,
        is_active=True,
    )

    action_count = await materializer.apply(
        {"model_input_scope": (scope,), "model_object_binding": (_object_binding(),)}
    )

    assert action_count == 2
    assert "model.model_input_scope" in transaction.calls[1][1]
    assert "workflow.model_object_binding" in transaction.calls[3][1]
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_bindings_resolve_target_attributes_under_the_bound_object() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall(
                "one", "SELECT object.object_id", {"object_id": 11, "system_id": 5}
            ),
            ExpectedCall("one", "SELECT logical_entity_id", {"logical_entity_id": 101}),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.model_object_binding",
                {"model_object_binding_id": 201, "object_id": 11},
            ),
            ExpectedCall(
                "one",
                "SELECT attribute.logical_attribute_id",
                {"logical_attribute_id": 102},
            ),
            ExpectedCall(
                "one", "JOIN core.attribute AS attribute", {"attribute_id": 12}
            ),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.model_attribute_binding",
                {"model_attribute_binding_id": 202},
            ),
        ]
    )
    materializer = _materializer(transaction)

    action_count = await materializer.apply(
        {
            "model_object_binding": (_object_binding(),),
            "model_attribute_binding": (_attribute_binding(),),
        }
    )

    assert action_count == 2
    attribute_lookup = transaction.calls[4]
    assert attribute_lookup[2] == ("CustomerID", 201, 7)
    attribute_insert = transaction.calls[5]
    assert attribute_insert[2][:4] == (201, 102, None, 12)
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_mapping_materializes_only_through_bindings() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall(
                "one",
                "INSERT INTO workflow.mapping_source_system_dependency",
                {"mapping_source_system_dependency_id": 1},
            ),
            ExpectedCall("one", "SELECT mapping_object_id", None),
            ExpectedCall(
                "one", "INSERT INTO workflow.mapping_object", {"mapping_object_id": 301}
            ),
            ExpectedCall("one", "SELECT mapping_attribute_id", None),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.mapping_attribute",
                {"mapping_attribute_id": 302},
            ),
        ]
    )
    materializer = _materializer(transaction)
    materializer._model_object_bindings[("logical_entity", "customer")] = (201, 11)
    materializer._model_attribute_bindings[
        ("logical_entity", "customer", "customerid")
    ] = 202
    materializer._system_ids["crm"] = 55
    materializer._output_template_ids[("mapping_object", "mapping-object")] = 501
    materializer._output_template_ids[("mapping_attribute", "mapping-attribute")] = 502
    dependency = MappingDependencyRecord(
        modeled_entity_type="logical_entity",
        source_system_code="CRM",
        source_system_dependency_order=1,
        mapping_source_system_dependency_status="active",
        mapping_source_system_dependency_is_locked=False,
    )

    action_count = await materializer.apply(
        {
            "mapping_dependency": (dependency,),
            "mapping_object": (_mapping_object(),),
            "mapping_attribute": (_mapping_attribute(),),
        }
    )

    assert action_count == 3
    object_insert = transaction.calls[2]
    assert "model_object_binding_id" in object_insert[1]
    assert "mapping_profile" not in object_insert[1]
    assert object_insert[2][:5] == (7, 201, 55, 501, 2)
    attribute_insert = transaction.calls[4]
    assert "model_attribute_binding_id" in attribute_insert[1]
    assert attribute_insert[2][:3] == (301, 202, 502)
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_workflow_mapping_policy_overrides_record_template() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall("one", "SELECT mapping_object_id", None),
            ExpectedCall(
                "one", "INSERT INTO workflow.mapping_object", {"mapping_object_id": 301}
            ),
        ]
    )
    materializer = ModelMaterializer.for_workflow_apply(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="f" * 64,
        workflow_run_id=44,
        model_workflow="mapping",
        mapping_object_output_template_id=901,
        mapping_attribute_output_template_id=902,
    )
    materializer._model_object_bindings[("logical_entity", "customer")] = (201, 11)
    materializer._system_ids["crm"] = 55

    await materializer.apply({"mapping_object": (_mapping_object(),)})

    insert = transaction.calls[1]
    assert insert[2][3] == 901
    assert insert[2][6] == 44
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_generated_code_uses_server_digest_and_separate_source_assignment() -> (
    None
):
    transaction = ScriptedTransaction(
        [
            ExpectedCall(
                "one",
                "list_code_generation_target_context",
                {"code_input_digest": "a" * 64},
            ),
            ExpectedCall("one", "SELECT generated_code_id", None),
            ExpectedCall(
                "one", "INSERT INTO workflow.generated_code", {"generated_code_id": 401}
            ),
            ExpectedCall("one", "SELECT generated_code_source_system_id", None),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.generated_code_source_system",
                {"generated_code_source_system_id": 402},
            ),
        ]
    )
    materializer = _materializer(transaction)
    materializer._model_object_bindings[("logical_entity", "customer")] = (201, 11)
    materializer._system_ids["crm"] = 55
    artifact = GeneratedCodeRecord(
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        artifact_name="Customer.sql",
        artifact_type="sql_file",
        generated_code_content="SELECT 1",
        generated_code_status="active",
    )
    assignment = GeneratedCodeSourceSystemRecord(
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        artifact_name="Customer.sql",
        source_system_code="CRM",
        generated_code_source_system_status="active",
    )

    action_count = await materializer.apply(
        {"generated_code": (artifact,), "generated_code_source_system": (assignment,)}
    )

    assert action_count == 2
    code_insert = transaction.calls[2]
    assert "code_input_digest" in code_insert[1]
    assert "generated_code_digest" not in code_insert[1]
    assert code_insert[2][:5] == (201, "Customer.sql", "sql_file", "SELECT 1", "a" * 64)
    source_insert = transaction.calls[4]
    assert source_insert[2][:2] == (401, 55)
    transaction.assert_complete()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


@pytest.mark.asyncio
async def test_validation_digests_are_derived_after_mapping_and_code() -> None:
    source_context = {
        "target": {
            "tenant_code": "Tenant-A",
            "system_code": "GDS",
            "connection_code": "GDS",
            "object_schema": "silver",
            "object_name": "Customer",
        },
        "source_systems": [{"system_code": "CRM"}],
    }
    transaction = ScriptedTransaction(
        [
            ExpectedCall(
                "all",
                "list_code_generation_target_context",
                [
                    {
                        "modeled_entity_type": "logical_entity",
                        "modeled_entity_name": "Customer",
                        "code_input_digest": "a" * 64,
                        "source_context": source_context,
                    }
                ],
            ),
            ExpectedCall(
                "all",
                "FROM workflow.generated_code AS generated",
                [
                    {
                        "modeled_entity_type": "logical_entity",
                        "modeled_entity_name": "Customer",
                        "artifact_name": "Customer.sql",
                        "artifact_type": "sql_file",
                        "generated_code_digest": "b" * 64,
                        "generated_code_status": "active",
                        "source_system_codes": ["CRM"],
                    }
                ],
            ),
            ExpectedCall("one", "SELECT validation_group_id", None),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.validation_group",
                {"validation_group_id": 501},
            ),
        ]
    )
    materializer = _materializer(transaction)
    materializer._tenant_ids["tenant-a"] = 1
    materializer._system_ids["crm"] = 55
    group = ValidationGroupRecord(
        tenant_code="Tenant-A",
        system_code="CRM",
        validation_group_name="Customer completeness",
        validation_group_description=None,
        is_active=True,
    )

    action_count = await materializer.apply({"validation_group": (group,)})

    target = {
        "tenant_code": "tenant-a",
        "system_code": "gds",
        "connection_code": "gds",
        "object_schema": "silver",
        "object_name": "customer",
    }
    mapping_entry = {
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "customer",
        "target": target,
        "code_input_digest": "a" * 64,
    }
    expected_mapping_digest = _digest([mapping_entry])
    expected_code_digest = _digest(
        [
            {
                **mapping_entry,
                "artifact_name": "Customer.sql",
                "artifact_type": "sql_file",
                "generated_code_digest": "b" * 64,
            }
        ]
    )
    assert action_count == 1
    group_insert = transaction.calls[3]
    assert group_insert[2][6:8] == (expected_mapping_digest, expected_code_digest)
    transaction.assert_complete()
