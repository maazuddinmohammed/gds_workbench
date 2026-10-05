from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, LiteralString, cast

import pytest
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
    MappingAttributeRecord,
    MappingObjectRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    ValidationGroupRecord,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction


@dataclass(frozen=True)
class ExpectedCall:
    method: Literal["one", "all"]
    contains: str
    result: dict[str, Any] | None | list[dict[str, Any]]


@dataclass
class ScriptedTransaction:
    expected: list[ExpectedCall]
    calls: list[tuple[str, LiteralString, tuple[Any, ...]]] = field(default_factory=list)

    def _next(self, method: Literal["one", "all"], query: LiteralString) -> ExpectedCall:
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


def _mapping_object() -> MappingObjectRecord:
    return MappingObjectRecord(
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
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
        modeled_entity_schema_name="silver",
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
            ExpectedCall("one", "SELECT object.object_id", {"object_id": 11, "system_id": 5}),
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
async def test_entity_resolution_distinguishes_schemas() -> None:
    from gds_etl_workbench.application.modeling.modeled_layer import LOGICAL

    transaction = ScriptedTransaction(
        [
            ExpectedCall("one", "SELECT logical_entity_id", {"logical_entity_id": 101}),
            ExpectedCall("one", "SELECT logical_entity_id", {"logical_entity_id": 102}),
        ]
    )
    materializer = _materializer(transaction)
    assert await materializer.resolve_entity(LOGICAL, "sales", "Customer") == 101
    assert await materializer.resolve_entity(LOGICAL, "support", "Customer") == 102
    assert await materializer.resolve_entity(LOGICAL, "SALES", "customer") == 101
    assert transaction.calls[0][2] == (7, "sales", "Customer")
    assert transaction.calls[1][2] == (7, "support", "Customer")
    assert all("logical_entity_schema_name" in call[1] for call in transaction.calls)
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_mapping_materializes_direct_typed_entity_and_attribute_ownership() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall("one", "SELECT mapping_object_id", None),
            ExpectedCall("one", "INSERT INTO workflow.mapping_object", {"mapping_object_id": 301}),
            ExpectedCall("one", "SELECT mapping_attribute_id", None),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.mapping_attribute",
                {"mapping_attribute_id": 302},
            ),
        ]
    )
    materializer = _materializer(transaction)
    materializer._logical_entity_ids[("silver", "customer")] = 101
    materializer._logical_attribute_ids[("silver", "customer", "customerid")] = 102
    materializer._system_ids["crm"] = 55
    materializer._output_template_ids[("mapping_object", "logical_entity", "mapping-object")] = 501
    materializer._output_template_ids[
        ("mapping_attribute", "logical_entity", "mapping-attribute")
    ] = 502
    action_count = await materializer.apply(
        {
            "mapping_object": (_mapping_object(),),
            "mapping_attribute": (_mapping_attribute(),),
        }
    )

    assert action_count == 2
    object_insert = transaction.calls[1]
    assert "logical_entity_id" in object_insert[1]
    assert "mapping_profile" not in object_insert[1]
    assert object_insert[2][:7] == (7, "logical_entity", 101, None, 55, 501, 2)
    attribute_insert = transaction.calls[3]
    assert "logical_attribute_id" in attribute_insert[1]
    assert attribute_insert[2][:8] == (
        301,
        7,
        "logical_entity",
        101,
        None,
        102,
        None,
        502,
    )
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_workflow_mapping_policy_overrides_record_template() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall("one", "SELECT mapping_object_id", None),
            ExpectedCall("one", "INSERT INTO workflow.mapping_object", {"mapping_object_id": 301}),
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
    materializer._logical_entity_ids[("silver", "customer")] = 101
    materializer._system_ids["crm"] = 55

    await materializer.apply({"mapping_object": (_mapping_object(),)})

    insert = transaction.calls[1]
    assert insert[2][5] == 901
    assert insert[2][8] == 44
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_generated_code_uses_server_digest_and_separate_source_assignment() -> None:
    transaction = ScriptedTransaction(
        [
            ExpectedCall(
                "one",
                "list_code_generation_target_context",
                {"code_input_digest": "a" * 64},
            ),
            ExpectedCall("one", "SELECT generated_code_id", None),
            ExpectedCall("one", "INSERT INTO workflow.generated_code", {"generated_code_id": 401}),
            ExpectedCall("one", "SELECT generated_code_source_system_id", None),
            ExpectedCall(
                "one",
                "INSERT INTO workflow.generated_code_source_system",
                {"generated_code_source_system_id": 402},
            ),
        ]
    )
    materializer = _materializer(transaction)
    materializer._logical_entity_ids[("silver", "customer")] = 101
    materializer._system_ids["crm"] = 55
    artifact = GeneratedCodeRecord(
        generated_code_is_locked=False,
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
        modeled_entity_name="Customer",
        artifact_name="Customer.sql",
        artifact_type="sql_file",
        generated_code_content="SELECT 1",
        generated_code_status="active",
    )
    assignment = GeneratedCodeSourceSystemRecord(
        generated_code_source_system_is_locked=False,
        modeled_entity_type="logical_entity",
        modeled_entity_schema_name="silver",
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
    assert code_insert[2][:8] == (
        7,
        "logical_entity",
        101,
        None,
        "Customer.sql",
        "sql_file",
        "SELECT 1",
        "a" * 64,
    )
    source_insert = transaction.calls[4]
    assert source_insert[2][:2] == (401, 55)
    transaction.assert_complete()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
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
                        "modeled_entity_schema_name": "silver",
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
                        "modeled_entity_schema_name": "silver",
                        "modeled_entity_name": "Customer",
                        "artifact_name": "Customer.sql",
                        "artifact_type": "sql_file",
                        "generated_code_digest": "b" * 64,
                        "code_input_digest": "a" * 64,
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
        is_locked=False,
        tenant_code="Tenant-A",
        system_code="CRM",
        validation_group_name="Customer completeness",
        validation_group_description=None,
        is_active=True,
    )

    action_count = await materializer.apply({"validation_group": (group,)})

    mapping_entry = {
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "customer",
        "modeled_entity_schema_name": "silver",
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


@pytest.mark.asyncio
async def test_template_resolution_and_cache_are_scoped_to_mapping_layer() -> None:
    transaction = ScriptedTransaction(
        expected=[
            ExpectedCall("one", "FROM application.output_template", {"output_template_id": 501}),
            ExpectedCall("one", "FROM application.output_template", None),
        ]
    )
    materializer = _materializer(transaction)
    assert (
        await materializer.resolve_output_template(
            "logical_template", "mapping_object", "logical_entity"
        )
        == 501
    )
    with pytest.raises(InvalidRequestError, match="Output Template was not found"):
        await materializer.resolve_output_template(
            "logical_template", "mapping_object", "dimensional_entity"
        )
    assert transaction.calls[0][2] == (
        "logical_template",
        "mapping_object",
        "logical_entity",
    )
    assert transaction.calls[1][2] == (
        "logical_template",
        "mapping_object",
        "dimensional_entity",
    )
    assert "output_template_modeled_entity_type = %s" in transaction.calls[0][1]
    transaction.assert_complete()


@pytest.mark.asyncio
async def test_model_settings_apply_resolves_system_and_preserves_identity() -> None:
    from gds_etl_workbench.domain.modeling_records import ModelDetailsRecord

    from tests.mcp.model_test_fixtures import model_details

    transaction = ScriptedTransaction(
        [
            ExpectedCall("one", "SELECT system_id", {"system_id": 5}),
            ExpectedCall("one", "UPDATE model.model", {"model_id": 7}),
        ]
    )
    record = ModelDetailsRecord.model_validate_json(
        json.dumps(
            {
                **model_details(),
                "logical_entity_scd_type": "type_2",
                "dimensional_entity_scd_type": "type_1",
                "default_mapping_source_system_code": "ERP",
            }
        )
    )
    assert await _materializer(transaction).apply({"model_details": (record,)}) == 1
    query, parameters = transaction.calls[-1][1:]
    assert "SET model_name" not in query
    assert "AND model_name = %s" in query
    assert parameters[-5:] == ("type_2", "type_1", 5, 7, record.model_name)
    transaction.assert_complete()
