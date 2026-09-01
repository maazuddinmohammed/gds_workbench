from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, LiteralString, cast

import pytest
from psycopg.types.json import Jsonb

from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    AssertionRecordKey,
    AttributeAssertionSourceRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    GeneratedCodeRecord,
    LogicalAssertionSourceRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
    LogicalSubmodelRecord,
    MappingDependencyRecord,
    MappingAttributeRecord,
    MappingObjectRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    ProfilingProfileRecord,
    SubmodelMembershipRecord,
    ValidationCheckRecord,
    ValidationGroupRecord,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets.model_apply import ModelMaterializer


@dataclass
class FakeWriteTransaction:
    calls: list[tuple[LiteralString, tuple[Any, ...]]] = field(
        default_factory=lambda: list[tuple[LiteralString, tuple[Any, ...]]]()
    )

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "JOIN core.attribute AS attribute" in query:
            if parameters[4] == "orders":
                return {"object_id": 11, "attribute_id": 12, "system_id": 5}
            if parameters[4] == "customers":
                return {"object_id": 21, "attribute_id": 22, "system_id": 5}
            raise AssertionError("unexpected physical Attribute lookup")
        if "SELECT object.object_id" in query:
            return {"object_id": 11, "system_id": 5}
        return {"analysis_result_id": 1}


@dataclass
class LayerFakeWriteTransaction:
    calls: list[tuple[LiteralString, tuple[Any, ...]]] = field(
        default_factory=lambda: list[tuple[LiteralString, tuple[Any, ...]]](),
    )
    next_id: int = 100
    existing: bool = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        normalized = " ".join(query.split())
        if normalized.startswith("SELECT") and "FOR UPDATE" in normalized:
            if not self.existing:
                return None
            for field_name in (
                "logical_submodel_id",
                "logical_entity_id",
                "logical_entity_submodel_id",
                "logical_entity_source_mapping_id",
                "logical_attribute_id",
                "logical_attribute_source_mapping_id",
                "logical_relationship_id",
                "dimensional_entity_id",
                "dimensional_attribute_id",
                "dimensional_relationship_id",
            ):
                if f"SELECT {field_name}" in normalized:
                    self.next_id += 1
                    return {field_name: self.next_id}
            raise AssertionError(f"unexpected layer identity query: {normalized}")
        if "SELECT modeling_assertion_record_id" in normalized:
            return {"modeling_assertion_record_id": 80}
        for field_name in (
            "logical_submodel_id",
            "logical_entity_id",
            "logical_entity_submodel_id",
            "logical_entity_source_mapping_id",
            "logical_attribute_id",
            "logical_attribute_source_mapping_id",
            "logical_relationship_id",
            "dimensional_entity_id",
            "dimensional_attribute_id",
            "dimensional_relationship_id",
        ):
            if (
                f"RETURNING {field_name}" in normalized
                or f"SELECT {field_name}" in normalized
            ):
                self.next_id += 1
                return {field_name: self.next_id}
        raise AssertionError(f"unexpected layer materializer query: {normalized}")


@dataclass
class MappingFakeWriteTransaction:
    calls: list[tuple[LiteralString, tuple[Any, ...]]] = field(
        default_factory=lambda: list[tuple[LiteralString, tuple[Any, ...]]](),
    )
    existing: bool = False
    existing_attribute: bool = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        normalized = " ".join(query.split())
        if "JOIN core.attribute AS attribute" in normalized:
            return {"object_id": 11, "attribute_id": 12, "system_id": 5}
        if "SELECT object.object_id" in normalized:
            return {"object_id": 11, "system_id": 5}
        if normalized.startswith("SELECT system_id"):
            return {"system_id": 6}
        if normalized.startswith("SELECT logical_entity_id"):
            return {"logical_entity_id": 21}
        if normalized.startswith("SELECT attribute.logical_attribute_id"):
            return {"logical_attribute_id": 22}
        if normalized.startswith(
            "INSERT INTO workflow.mapping_source_system_dependency"
        ):
            return {"mapping_source_system_dependency_id": 41}
        if normalized.startswith("SELECT mapping_object_id"):
            return {"mapping_object_id": 31} if self.existing else None
        if normalized.startswith("SELECT mapping_attribute_id"):
            return {"mapping_attribute_id": 32} if self.existing_attribute else None
        if normalized.startswith("INSERT INTO workflow.mapping_object"):
            return {"mapping_object_id": 31}
        if normalized.startswith("UPDATE workflow.mapping_object"):
            return {"mapping_object_id": 31}
        if normalized.startswith("INSERT INTO workflow.mapping_attribute"):
            return {"mapping_attribute_id": 32}
        if normalized.startswith("UPDATE workflow.mapping_attribute"):
            return {"mapping_attribute_id": 32}
        raise AssertionError(f"unexpected Mapping materializer query: {normalized}")


@dataclass
class CodeQaFakeWriteTransaction:
    calls: list[tuple[LiteralString, tuple[Any, ...]]] = field(
        default_factory=lambda: list[tuple[LiteralString, tuple[Any, ...]]](),
    )
    existing: bool = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        normalized = " ".join(query.split())
        if "SELECT object.object_id" in normalized:
            return {"object_id": 11, "system_id": 5}
        if normalized.startswith("SELECT tenant_id"):
            return {"tenant_id": 7}
        if normalized.startswith("SELECT system_id"):
            return {"system_id": 6}
        identities = {
            "SELECT generated_code_id": ("generated_code_id", 31),
            "SELECT validation_group_id": ("validation_group_id", 32),
            "SELECT validation_check_id": ("validation_check_id", 33),
        }
        for prefix, (field_name, value) in identities.items():
            if normalized.startswith(prefix):
                return {field_name: value} if self.existing else None
        returned = {
            "RETURNING generated_code_id": ("generated_code_id", 31),
            "RETURNING validation_group_id": ("validation_group_id", 32),
            "RETURNING validation_check_id": ("validation_check_id", 33),
        }
        for marker, (field_name, value) in returned.items():
            if marker in normalized:
                return {field_name: value}
        raise AssertionError(f"unexpected Code/QA materializer query: {normalized}")


def _logical_records() -> dict[str, tuple[Any, ...]]:
    assertion = AssertionRecordKey(modeling_assertion_record_key="customer_domain")
    return {
        "logical_submodel": (
            LogicalSubmodelRecord(
                logical_submodel_name="Customer Domain",
                logical_submodel_definition="Customer subject area.",
                logical_submodel_status="active",
                logical_submodel_is_locked=False,
            ),
        ),
        "logical_entity": (
            LogicalEntityRecord(
                logical_entity_name="Customer",
                logical_entity_definition="A customer.",
                logical_entity_type="core",
                logical_entity_type_detail=None,
                logical_entity_grain="One row per customer.",
                logical_entity_dependency_order=0,
                logical_entity_confidence="high",
                logical_entity_status="active",
                logical_entity_is_locked=False,
                submodels=(
                    SubmodelMembershipRecord(
                        submodel_name="Customer Domain",
                        membership_status="active",
                        membership_is_locked=False,
                    ),
                ),
                sources=(
                    LogicalAssertionSourceRecord(
                        support_source_type="assertion",
                        assertion_record=assertion,
                        source_order=1,
                        rationale="Approved domain assertion.",
                        status="active",
                        is_locked=False,
                    ),
                ),
            ),
            LogicalEntityRecord(
                logical_entity_name="Order",
                logical_entity_definition="A customer order.",
                logical_entity_type="transaction",
                logical_entity_type_detail=None,
                logical_entity_grain="One row per order.",
                logical_entity_dependency_order=1,
                logical_entity_confidence="high",
                logical_entity_status="active",
                logical_entity_is_locked=False,
                submodels=(),
                sources=(),
            ),
        ),
        "logical_attribute": (
            LogicalAttributeRecord(
                logical_entity_name="Customer",
                logical_attribute_name="Customer Id",
                logical_attribute_definition="Customer identifier.",
                logical_attribute_data_type="bigint",
                logical_attribute_is_nullable=False,
                logical_attribute_is_primary_key=True,
                logical_attribute_is_natural_key=False,
                logical_attribute_is_surrogate_key=True,
                logical_attribute_ordinal_position=1,
                logical_attribute_is_audit_column=False,
                logical_attribute_status="active",
                logical_attribute_is_locked=False,
                sources=(
                    AttributeAssertionSourceRecord(
                        support_source_type="assertion",
                        assertion_record=assertion,
                        source_order=1,
                        rationale="Approved identifier assertion.",
                        status="active",
                        is_locked=False,
                    ),
                ),
            ),
            LogicalAttributeRecord(
                logical_entity_name="Order",
                logical_attribute_name="Customer Id",
                logical_attribute_definition="Ordering customer identifier.",
                logical_attribute_data_type="bigint",
                logical_attribute_is_nullable=False,
                logical_attribute_is_primary_key=False,
                logical_attribute_is_natural_key=False,
                logical_attribute_is_surrogate_key=False,
                logical_attribute_ordinal_position=1,
                logical_attribute_is_audit_column=False,
                logical_attribute_status="active",
                logical_attribute_is_locked=False,
                sources=(),
            ),
        ),
        "logical_relationship": (
            LogicalRelationshipRecord(
                logical_relationship_name="Order Customer",
                logical_relationship_definition="Each order belongs to a customer.",
                from_logical_entity_name="Order",
                from_logical_attribute_name="Customer Id",
                to_logical_entity_name="Customer",
                to_logical_attribute_name="Customer Id",
                logical_relationship_cardinality="many_to_one",
                logical_relationship_confidence="high",
                logical_relationship_basis="Matching customer identifiers.",
                logical_relationship_cardinality_basis="Many orders may share one customer.",
                logical_relationship_status="active",
                logical_relationship_is_locked=False,
            ),
        ),
    }


def _dimensional_records() -> dict[str, tuple[Any, ...]]:
    return {
        "dimensional_entity": (
            DimensionalEntityRecord(
                dimensional_entity_name="Fact Sale",
                dimensional_entity_definition="Sales facts.",
                dimensional_entity_type="fact",
                dimensional_fact_type="transaction",
                dimensional_entity_grain_definition="One row per sale.",
                dimensional_entity_dependency_order=1,
                dimensional_entity_confidence="high",
                dimensional_entity_status="active",
                dimensional_entity_is_locked=False,
                submodels=(),
                sources=(),
            ),
            DimensionalEntityRecord(
                dimensional_entity_name="Dim Customer",
                dimensional_entity_definition="Customer dimension.",
                dimensional_entity_type="dimension",
                dimensional_fact_type=None,
                dimensional_entity_grain_definition=None,
                dimensional_entity_dependency_order=0,
                dimensional_entity_confidence="high",
                dimensional_entity_status="active",
                dimensional_entity_is_locked=False,
                submodels=(),
                sources=(),
            ),
        ),
        "dimensional_attribute": (
            DimensionalAttributeRecord(
                dimensional_entity_name="Fact Sale",
                dimensional_attribute_name="Customer Key",
                dimensional_attribute_definition="Customer foreign key.",
                dimensional_attribute_data_type="bigint",
                dimensional_attribute_is_nullable=False,
                dimensional_attribute_ordinal_position=1,
                dimensional_attribute_role="key",
                dimensional_attribute_key_role="foreign",
                dimensional_attribute_is_grain_component=True,
                dimensional_attribute_additivity=None,
                dimensional_attribute_default_aggregation=None,
                dimensional_attribute_aggregation_basis=None,
                dimensional_attribute_change_behavior=None,
                dimensional_attribute_is_audit_column=False,
                dimensional_attribute_confidence="high",
                dimensional_attribute_status="active",
                dimensional_attribute_is_locked=False,
                sources=(),
            ),
            DimensionalAttributeRecord(
                dimensional_entity_name="Dim Customer",
                dimensional_attribute_name="Customer Key",
                dimensional_attribute_definition="Customer surrogate key.",
                dimensional_attribute_data_type="bigint",
                dimensional_attribute_is_nullable=False,
                dimensional_attribute_ordinal_position=1,
                dimensional_attribute_role="key",
                dimensional_attribute_key_role="surrogate",
                dimensional_attribute_is_grain_component=True,
                dimensional_attribute_additivity=None,
                dimensional_attribute_default_aggregation=None,
                dimensional_attribute_aggregation_basis=None,
                dimensional_attribute_change_behavior=None,
                dimensional_attribute_is_audit_column=False,
                dimensional_attribute_confidence="high",
                dimensional_attribute_status="active",
                dimensional_attribute_is_locked=False,
                sources=(),
            ),
        ),
        "dimensional_relationship": (
            DimensionalRelationshipRecord(
                dimensional_relationship_name="Sale Customer",
                dimensional_relationship_definition="Sales reference customers.",
                from_dimensional_entity_name="Fact Sale",
                from_dimensional_attribute_name="Customer Key",
                to_dimensional_entity_name="Dim Customer",
                to_dimensional_attribute_name="Customer Key",
                dimensional_relationship_kind="fact_dimension",
                dimensional_relationship_cardinality="many_to_one",
                dimensional_relationship_is_optional=True,
                dimensional_relationship_role_name="Customer",
                dimensional_relationship_confidence="high",
                dimensional_relationship_basis="The fact carries a customer key.",
                dimensional_relationship_cardinality_basis="Many sales share one customer.",
                dimensional_relationship_status="active",
                dimensional_relationship_is_locked=False,
            ),
        ),
    }


def _analysis(*, with_validation: bool) -> AnalysisResultRecord:
    document: dict[str, object] = {
        "from_tenant_code": "northwind",
        "from_system_code": "erp",
        "from_connection_code": "source",
        "from_object_schema": "sales",
        "from_object_name": "orders",
        "from_attribute_name": "customer_id",
        "to_tenant_code": "northwind",
        "to_system_code": "erp",
        "to_connection_code": "source",
        "to_object_schema": "sales",
        "to_object_name": "customers",
        "to_attribute_name": "customer_id",
        "relationship_kind": "foreign_key_candidate",
        "relationship_confidence": "high",
        "relationship_basis": "Names and values suggest a relationship.",
        "analysis_result_status": "active",
        "analysis_result_is_locked": False,
    }
    if with_validation:
        document.update(
            {
                "validation_policy_version": "1.0.0",
                "validation_result": "supported",
                "validation_source_non_null_count": 90,
                "validation_source_distinct_count": 45,
                "validation_target_non_null_count": 50,
                "validation_target_distinct_count": 50,
                "validation_source_missing_target_count": 0,
                "validation_unused_target_count": 5,
                "validation_duplicate_target_key_count": 0,
            }
        )
    return AnalysisResultRecord.model_validate(document)


def _profile() -> ProfilingProfileRecord:
    return ProfilingProfileRecord.model_validate(
        {
            "tenant_code": "northwind",
            "system_code": "erp",
            "connection_code": "source",
            "object_schema": "sales",
            "object_name": "orders",
            "attribute_name": "customer_id",
            "row_count": 10,
            "non_null_count": 9,
            "null_count": 1,
            "blank_count": 0,
            "distinct_count": 5,
            "min_data_length": 1,
            "max_data_length": 5,
            "avg_data_length": Decimal("2"),
            "percent_populated": Decimal("90"),
            "percent_duplicates": Decimal("44.4444"),
            "percent_null": Decimal("10"),
            "percent_blank": Decimal("0"),
            "percent_distinct": Decimal("55.5556"),
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("with_validation", [False, True])
async def test_analysis_materializer_only_digests_complete_validation_evidence(
    with_validation: bool,
) -> None:
    transaction = FakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
    )

    action_count = await materializer.apply(
        {"analysis_result": (_analysis(with_validation=with_validation),)}
    )

    assert action_count == 1
    assert len(transaction.calls) == 3
    query = transaction.calls[-1][0]
    parameters = transaction.calls[-1][1]
    assert "agent_run_id" in query
    assert "inference_workflow_run_id" in query
    assert "validation_workflow_run_id" in query
    assert parameters[1] is None
    if with_validation:
        assert parameters[9] == "1.0.0"
        assert isinstance(parameters[10], str) and len(parameters[10]) == 64
        assert all(value is not None for value in parameters[11:19])
    else:
        assert parameters[9:19] == (None,) * 10


@pytest.mark.asyncio
async def test_analysis_materializer_stamps_web_inference_provenance() -> None:
    transaction = FakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=1048,
    )

    await materializer.apply({"analysis_result": (_analysis(with_validation=True),)})

    query, parameters = transaction.calls[-1]
    assert parameters[1] == 1048
    assert "inference_workflow_run_id = EXCLUDED.inference_workflow_run_id" in query
    assert "validation_workflow_run_id = CASE" in query
    assert "ELSE current_result.validation_workflow_run_id" in query
    assert "validation_source_context_digest = CASE" in query
    assert "ELSE current_result.validation_source_context_digest" in query
    for field_name in (
        "validation_policy_version",
        "validation_policy_digest",
        "validation_result",
        "validation_source_non_null_count",
        "validation_source_distinct_count",
        "validation_target_non_null_count",
        "validation_target_distinct_count",
        "validation_source_missing_target_count",
        "validation_unused_target_count",
        "validation_duplicate_target_key_count",
        "analysis_result_status",
        "analysis_result_is_locked",
    ):
        assert f"ELSE current_result.{field_name}" in query


@pytest.mark.asyncio
async def test_analysis_materializer_clears_web_validation_context_for_manual_write() -> (
    None
):
    transaction = FakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
    )

    await materializer.apply({"analysis_result": (_analysis(with_validation=True),)})

    query, _ = transaction.calls[-1]
    assert "validation_source_context_digest = CASE" in query
    assert "WHEN EXCLUDED.inference_workflow_run_id IS NULL" in query
    assert "THEN NULL" in query


@pytest.mark.asyncio
async def test_profile_materializer_clears_prior_workflow_provenance() -> None:
    transaction = FakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
    )

    action_count = await materializer.apply({"profiling_profile": (_profile(),)})

    assert action_count == 1
    assert len(transaction.calls) == 2
    query = transaction.calls[-1][0]
    assert "agent_run_id = NULL" in query
    assert "workflow_run_id = NULL" in query


@pytest.mark.asyncio
async def test_physical_resolvers_use_discovery_assigned_tenant_for_gds_objects() -> (
    None
):
    transaction = FakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
    )

    await materializer.resolve_object(
        PhysicalObjectKey(
            tenant_code="northwind",
            system_code="erp",
            connection_code="gds",
            object_schema="bronze",
            object_name="orders",
        )
    )
    await materializer.resolve_attribute(
        PhysicalAttributeKey(
            tenant_code="northwind",
            system_code="erp",
            connection_code="gds",
            object_schema="bronze",
            object_name="orders",
            attribute_name="customer_id",
        )
    )

    assert len(transaction.calls) == 2
    for query, _ in transaction.calls:
        assert "core.tenant_metadata_discovery_scope AS scope" in query
        assert "scope.tenant_id = tenant.tenant_id" in query
        assert "scope.gds_connection_id = connection.connection_id" in query
        assert "scope.zone_id = object.zone_id" in query
        assert "AND scope.is_active" in query
        assert "ON tenant.tenant_id = connection.tenant_id" not in query


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow_run_id", [None, 1048])
async def test_logical_materializer_stamps_all_seven_families_and_counts_once(
    workflow_run_id: int | None,
) -> None:
    transaction = LayerFakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=workflow_run_id,
    )

    action_count = await materializer.apply(_logical_records())

    assert action_count == 9
    inserts = [
        (query, parameters)
        for query, parameters in transaction.calls
        if "INSERT INTO workflow.logical_" in query
    ]
    assert {
        query.split("INSERT INTO ", 1)[1].split(" ", 1)[0].split("(", 1)[0].strip()
        for query, _ in inserts
    } == {
        "workflow.logical_submodel",
        "workflow.logical_entity",
        "workflow.logical_entity_submodel",
        "workflow.logical_entity_source_mapping",
        "workflow.logical_attribute",
        "workflow.logical_attribute_source_mapping",
        "workflow.logical_relationship",
    }
    assert all("workflow_run_id" in query for query, _ in inserts)
    assert all(parameters[1] == workflow_run_id for _, parameters in inserts)


@pytest.mark.asyncio
async def test_dimensional_relationship_lookup_uses_canonical_kind_and_role_identity() -> (
    None
):
    transaction = LayerFakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=1048,
    )

    action_count = await materializer.apply(_dimensional_records())

    assert action_count == 5
    lookup_query, lookup_parameters = next(
        (query, parameters)
        for query, parameters in transaction.calls
        if "SELECT dimensional_relationship_id" in query
    )
    assert "dimensional_relationship_kind" in lookup_query
    assert "dimensional_relationship_role_name" in lookup_query
    assert "dimensional_relationship_name" not in lookup_query
    assert lookup_parameters[-2:] == ("fact_dimension", "Customer")
    insert_query, insert_parameters = next(
        (query, parameters)
        for query, parameters in transaction.calls
        if "INSERT INTO workflow.dimensional_relationship" in query
    )
    assert "dimensional_relationship_is_optional" in insert_query
    assert insert_parameters[6] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow_run_id", [None, 1048])
async def test_logical_materializer_updates_all_seven_family_provenance(
    workflow_run_id: int | None,
) -> None:
    transaction = LayerFakeWriteTransaction(existing=True)
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=workflow_run_id,
    )

    action_count = await materializer.apply(_logical_records())

    assert action_count == 9
    updates = [
        (query, parameters)
        for query, parameters in transaction.calls
        if "UPDATE workflow.logical_" in query
    ]
    assert {
        query.split("UPDATE ", 1)[1].split(" ", 1)[0].strip() for query, _ in updates
    } == {
        "workflow.logical_submodel",
        "workflow.logical_entity",
        "workflow.logical_entity_submodel",
        "workflow.logical_entity_source_mapping",
        "workflow.logical_attribute",
        "workflow.logical_attribute_source_mapping",
        "workflow.logical_relationship",
    }
    assert all("workflow_run_id = %s" in query for query, _ in updates)
    assert all(parameters[0] == workflow_run_id for _, parameters in updates)


@pytest.mark.asyncio
async def test_mapping_materializer_persists_resolved_profile_and_package_digests() -> (
    None
):
    transaction = MappingFakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
    )
    package: dict[str, object] = {
        "schema_version": "1.0",
        "package_ref": "customer_crm",
        "route": "logical_to_silver",
        "target_object_id": 101,
        "source_system_id": 201,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic SQL.",
        "pydantic_profile": {
            "key": "mapping.standard",
            "version": "1.0.0",
            "schema_digest": (
                "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
            ),
        },
        "executable_sources": [
            {
                "object_id": 401,
                "alias": "customer_source",
                "role": "Customer source",
                "batch_rule": None,
            }
        ],
        "non_executable_provenance": [],
        "runtime_parameters": [],
        "source_system_dependencies": [],
        "target_dependencies": [],
        "steps": [
            {
                "name": "load_customer",
                "depends_on": [],
                "inputs": ["customer_source"],
                "output": "customer_rows",
                "logic": "Load the governed Customer rows.",
            }
        ],
        "grain_and_deduplication": "One row per Customer.",
        "load": {
            "write_mode": "merge",
            "merge_keys": [301],
            "partition_basis": None,
            "concurrent_system_write_mode": "idempotent_merge",
            "concurrent_write_basis": "Customer key.",
        },
    }
    record = MappingObjectRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        object_dependency_order=0,
        artifact_type="sql_file",
        artifact_generation_instructions="Generate deterministic SQL.",
        mapping_profile_key="mapping.standard",
        mapping_profile_version="1.0.0",
        mapping_package_document=package,
        object_mapping_transformation_document={
            "schema_version": "1.0",
            "transformation_kind": "direct",
        },
        object_mapping_status="active",
        object_mapping_is_locked=False,
    )

    action_count = await materializer.apply({"mapping_object": (record,)})

    assert action_count == 1
    _, parameters = next(
        (query, values)
        for query, values in transaction.calls
        if "INSERT INTO workflow.mapping_object" in query
    )
    assert parameters[13] == (
        "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
    )
    assert parameters[15] == (
        "071b0c37998d57f813320aa3bc5ee42bd0c27994c21ae1d84780606bcf6b066a"
    )


@pytest.mark.asyncio
async def test_generic_mapping_insert_has_null_workflow_and_template_provenance() -> (
    None
):
    transaction = MappingFakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=44,
    )
    record = MappingObjectRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        object_dependency_order=0,
        artifact_type=None,
        artifact_generation_instructions=None,
        mapping_profile_key=None,
        mapping_profile_version=None,
        mapping_package_document=None,
        object_mapping_transformation_document=None,
        object_mapping_status="active",
        object_mapping_is_locked=False,
    )

    await materializer.apply({"mapping_object": (record,)})

    query, parameters = next(
        (query, values)
        for query, values in transaction.calls
        if "INSERT INTO workflow.mapping_object" in query
    )
    assert "workflow_run_id" in query
    assert "output_template_id" in query
    assert parameters[1:3] == (None, None)


@pytest.mark.asyncio
async def test_generic_mapping_update_clears_run_provenance_and_preserves_template() -> (
    None
):
    transaction = MappingFakeWriteTransaction(existing=True)
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=44,
    )
    record = MappingObjectRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        object_dependency_order=0,
        artifact_type=None,
        artifact_generation_instructions=None,
        mapping_profile_key=None,
        mapping_profile_version=None,
        mapping_package_document=None,
        object_mapping_transformation_document=None,
        object_mapping_status="active",
        object_mapping_is_locked=False,
    )

    await materializer.apply({"mapping_object": (record,)})

    query, parameters = next(
        (query, values)
        for query, values in transaction.calls
        if "UPDATE workflow.mapping_object" in query
    )
    assert "workflow_run_id = %s" in query
    assert "ELSE output_template_id" in query
    assert parameters[:3] == (None, False, None)


@pytest.mark.asyncio
async def test_generic_mapping_dependency_stamps_null_workflow_provenance() -> None:
    transaction = MappingFakeWriteTransaction()
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=44,
    )
    record = MappingDependencyRecord(
        modeled_entity_type="logical_entity",
        source_system_code="CRM",
        source_system_dependency_order=0,
        mapping_source_system_dependency_status="active",
        mapping_source_system_dependency_is_locked=False,
    )

    await materializer.apply({"mapping_dependency": (record,)})

    query, parameters = next(
        (query, values)
        for query, values in transaction.calls
        if "INSERT INTO workflow.mapping_source_system_dependency" in query
    )
    assert "workflow_run_id" in query
    assert "workflow_run_id = EXCLUDED.workflow_run_id" in query
    assert parameters[1] is None


@pytest.mark.asyncio
async def test_generic_mapping_attribute_insert_has_null_run_and_template() -> None:
    transaction = MappingFakeWriteTransaction(existing=True)
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=44,
    )
    record = MappingAttributeRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        attribute_name="customer_id",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        modeled_attribute_name="Customer Id",
        attribute_mapping_transformation_document=None,
        attribute_mapping_status="active",
        attribute_mapping_is_locked=False,
    )

    await materializer.apply({"mapping_attribute": (record,)})

    query, parameters = next(
        (query, values)
        for query, values in transaction.calls
        if "INSERT INTO workflow.mapping_attribute" in query
    )
    assert "workflow_run_id" in query
    assert "output_template_id" in query
    assert parameters[1:3] == (None, None)


@pytest.mark.asyncio
async def test_generic_mapping_attribute_update_preserves_template() -> None:
    transaction = MappingFakeWriteTransaction(existing=True, existing_attribute=True)
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=44,
    )
    record = MappingAttributeRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        attribute_name="customer_id",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        modeled_attribute_name="Customer Id",
        attribute_mapping_transformation_document=None,
        attribute_mapping_status="active",
        attribute_mapping_is_locked=False,
    )

    await materializer.apply({"mapping_attribute": (record,)})

    query, parameters = next(
        (query, values)
        for query, values in transaction.calls
        if "UPDATE workflow.mapping_attribute" in query
    )
    assert "workflow_run_id = %s" in query
    assert "ELSE output_template_id" in query
    assert parameters[:3] == (None, False, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_output_template_id", "attribute_output_template_id"),
    ((501, 502), (501, None), (None, 502)),
)
async def test_web_mapping_policy_stamps_run_and_independent_templates(
    object_output_template_id: int | None,
    attribute_output_template_id: int | None,
) -> None:
    transaction = MappingFakeWriteTransaction()
    materializer = ModelMaterializer.for_workflow_apply(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=44,
        model_workflow="mapping",
        mapping_object_output_template_id=object_output_template_id,
        mapping_attribute_output_template_id=attribute_output_template_id,
    )
    dependency = MappingDependencyRecord(
        modeled_entity_type="logical_entity",
        source_system_code="CRM",
        source_system_dependency_order=0,
        mapping_source_system_dependency_status="active",
        mapping_source_system_dependency_is_locked=False,
    )
    mapping_object = MappingObjectRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        object_dependency_order=0,
        artifact_type=None,
        artifact_generation_instructions=None,
        mapping_profile_key=None,
        mapping_profile_version=None,
        mapping_package_document=None,
        object_mapping_transformation_document=None,
        object_mapping_status="active",
        object_mapping_is_locked=False,
    )
    mapping_attribute = MappingAttributeRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        attribute_name="customer_id",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        modeled_attribute_name="Customer Id",
        attribute_mapping_transformation_document=None,
        attribute_mapping_status="active",
        attribute_mapping_is_locked=False,
    )

    await materializer.apply(
        {
            "mapping_dependency": (dependency,),
            "mapping_object": (mapping_object,),
            "mapping_attribute": (mapping_attribute,),
        }
    )

    dependency_parameters = next(
        values
        for query, values in transaction.calls
        if "INSERT INTO workflow.mapping_source_system_dependency" in query
    )
    object_parameters = next(
        values
        for query, values in transaction.calls
        if "INSERT INTO workflow.mapping_object" in query
    )
    attribute_parameters = next(
        values
        for query, values in transaction.calls
        if "INSERT INTO workflow.mapping_attribute" in query
    )
    assert dependency_parameters[1] == 44
    assert object_parameters[1:3] == (44, object_output_template_id)
    assert attribute_parameters[1:3] == (44, attribute_output_template_id)


@pytest.mark.asyncio
async def test_web_mapping_policy_explicit_null_clears_changed_row_templates() -> None:
    transaction = MappingFakeWriteTransaction(existing=True, existing_attribute=True)
    materializer = ModelMaterializer.for_workflow_apply(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="a" * 64,
        workflow_run_id=44,
        model_workflow="mapping",
        mapping_object_output_template_id=None,
        mapping_attribute_output_template_id=None,
    )
    mapping_object = MappingObjectRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        object_dependency_order=0,
        artifact_type=None,
        artifact_generation_instructions=None,
        mapping_profile_key=None,
        mapping_profile_version=None,
        mapping_package_document=None,
        object_mapping_transformation_document=None,
        object_mapping_status="active",
        object_mapping_is_locked=False,
    )
    mapping_attribute = MappingAttributeRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        attribute_name="customer_id",
        source_system_code="CRM",
        modeled_entity_type="logical_entity",
        modeled_entity_name="Customer",
        modeled_attribute_name="Customer Id",
        attribute_mapping_transformation_document=None,
        attribute_mapping_status="active",
        attribute_mapping_is_locked=False,
    )

    await materializer.apply(
        {
            "mapping_object": (mapping_object,),
            "mapping_attribute": (mapping_attribute,),
        }
    )

    object_parameters = next(
        values
        for query, values in transaction.calls
        if "UPDATE workflow.mapping_object" in query
    )
    attribute_parameters = next(
        values
        for query, values in transaction.calls
        if "UPDATE workflow.mapping_attribute" in query
    )
    assert object_parameters[:3] == (44, True, None)
    assert attribute_parameters[:3] == (44, True, None)


def test_mapping_materialization_policy_is_rejected_outside_mapping() -> None:
    with pytest.raises(
        InvalidRequestError,
        match="unavailable outside Mapping",
    ):
        ModelMaterializer.for_workflow_apply(
            transaction=cast(WriteTransaction, MappingFakeWriteTransaction()),
            model_id=7,
            source_context_digest="a" * 64,
            workflow_run_id=44,
            model_workflow="logical",
            mapping_object_output_template_id=501,
            mapping_attribute_output_template_id=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_code_and_qa_materialize_in_parent_order_and_clear_generic_provenance(
    existing: bool,
) -> None:
    transaction = CodeQaFakeWriteTransaction(existing=existing)
    materializer = ModelMaterializer(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="d" * 64,
        workflow_run_id=44,
    )
    content = "SELECT * FROM main.sales.orders"
    generated_code = GeneratedCodeRecord(
        tenant_code="DEMO",
        system_code="ERP",
        connection_code="SOURCE",
        object_schema="silver",
        object_name="customer",
        modeled_entity_type="logical_entity",
        artifact_type="sql_file",
        generated_code_content=content,
        mapping_context_digest="a" * 64,
        source_context_digest="b" * 64,
        generated_code_digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        generated_code_status="active",
        generated_code_is_locked=False,
    )
    validation_group = ValidationGroupRecord(
        tenant_code="DEMO",
        system_code="ERP",
        validation_group_name="Customer QA",
        validation_group_description="Customer pipeline validations.",
        mapping_context_digest="c" * 64,
        code_context_digest="d" * 64,
        is_active=True,
    )
    validation_check = ValidationCheckRecord(
        tenant_code="DEMO",
        system_code="ERP",
        validation_group_name="Customer QA",
        validation_check_name="Allowed states",
        validation_check_description="Result must be an allowed state.",
        validation_category_code="business.state",
        validation_severity="blocking",
        validation_query_sql="SELECT state FROM main.sales.customer",
        validation_comparison_query_sql=None,
        validation_result_data_type="integer",
        validation_comparison_operator="in",
        validation_comparison_value_type="literal_list",
        validation_comparison_value=(1, 2),
        is_active=True,
    )

    action_count = await materializer.apply(
        {
            "generated_code": (generated_code,),
            "validation_group": (validation_group,),
            "validation_check": (validation_check,),
        }
    )

    mutations = [
        (" ".join(query.split()), parameters)
        for query, parameters in transaction.calls
        if query.lstrip().startswith(("INSERT", "UPDATE"))
    ]
    assert action_count == 3
    assert [
        next(
            table
            for table in (
                "workflow.generated_code",
                "workflow.validation_group",
                "workflow.validation_check",
            )
            if table in query
        )
        for query, _ in mutations
    ] == [
        "workflow.generated_code",
        "workflow.validation_group",
        "workflow.validation_check",
    ]
    code_query, code_parameters = mutations[0]
    group_query, group_parameters = mutations[1]
    _, check_parameters = mutations[2]
    assert "agent_run_id = NULL" in code_query or "agent_run_id" in code_query
    assert "agent_run_id = NULL" in group_query or "agent_run_id" in group_query
    assert code_parameters[0 if existing else 1] is None
    assert group_parameters[0 if existing else 3] is None
    comparison_value = check_parameters[9 if existing else 10]
    assert isinstance(comparison_value, Jsonb)
    assert comparison_value.obj == (1, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_workflow", "dataset", "expected_table", "workflow_parameter"),
    [
        ("code_generation", "generated_code", "workflow.generated_code", 1),
        ("qa", "validation_group", "workflow.validation_group", 3),
    ],
)
async def test_code_and_qa_workflows_stamp_only_their_own_provenance(
    model_workflow: str,
    dataset: str,
    expected_table: str,
    workflow_parameter: int,
) -> None:
    transaction = CodeQaFakeWriteTransaction()
    materializer = ModelMaterializer.for_workflow_apply(
        transaction=cast(WriteTransaction, transaction),
        model_id=7,
        source_context_digest="d" * 64,
        workflow_run_id=44,
        model_workflow=model_workflow,
        mapping_object_output_template_id=None,
        mapping_attribute_output_template_id=None,
    )
    content = "SELECT 1"
    record = (
        GeneratedCodeRecord(
            tenant_code="DEMO",
            system_code="ERP",
            connection_code="SOURCE",
            object_schema="silver",
            object_name="customer",
            modeled_entity_type="logical_entity",
            artifact_type="sql_file",
            generated_code_content=content,
            mapping_context_digest="a" * 64,
            source_context_digest="b" * 64,
            generated_code_digest=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            generated_code_status="active",
            generated_code_is_locked=False,
        )
        if dataset == "generated_code"
        else ValidationGroupRecord(
            tenant_code="DEMO",
            system_code="ERP",
            validation_group_name="Customer QA",
            validation_group_description=None,
            mapping_context_digest="c" * 64,
            code_context_digest=None,
            is_active=True,
        )
    )

    await materializer.apply({dataset: (record,)})

    query, parameters = next(
        (query, parameters)
        for query, parameters in transaction.calls
        if query.lstrip().startswith("INSERT") and expected_table in query
    )
    assert "agent_run_id" in query
    assert parameters[workflow_parameter] == 44
