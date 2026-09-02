from __future__ import annotations

from copy import deepcopy

from gds_etl_workbench.tools.change_sets.model_validation import PhysicalModelCatalog
from gds_etl_workbench.tools.snapshots.model.contracts import (
    ModelChangeSetDataset,
    ModelSnapshot,
)

SOURCE_ORDERS = ("TENANT-A", "ERP", "FC", "src", "orders")
SOURCE_CUSTOMERS = ("TENANT-A", "ERP", "FC", "src", "customers")
BRONZE_ORDERS = ("GDS", "GDS", "LAKEHOUSE", "bronze", "orders")
SILVER_ORDER = ("GDS", "GDS", "LAKEHOUSE", "silver", "Order")
SILVER_CUSTOMER = ("GDS", "GDS", "LAKEHOUSE", "silver", "Customer")
GOLD_SALES_FACT = ("GDS", "GDS", "LAKEHOUSE", "gold", "SalesFact")
GOLD_CUSTOMER = ("GDS", "GDS", "LAKEHOUSE", "gold", "CustomerDimension")


def physical_object(key: tuple[str, str, str, str, str]) -> dict[str, object]:
    return dict(
        zip(
            (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            ),
            key,
            strict=True,
        )
    )


def physical_attribute(
    key: tuple[str, str, str, str, str],
    attribute_name: str,
) -> dict[str, object]:
    return {**physical_object(key), "attribute_name": attribute_name}


def model_input_scope_records() -> list[dict[str, object]]:
    return [
        {
            **physical_object(key),
            "model_input_scope_is_locked": False,
            "is_active": True,
        }
        for key in (SOURCE_ORDERS, SOURCE_CUSTOMERS, BRONZE_ORDERS)
    ]


def complete_model_graph() -> dict[ModelChangeSetDataset, list[dict[str, object]]]:
    source_order = physical_object(SOURCE_ORDERS)
    source_customer = physical_object(SOURCE_CUSTOMERS)
    source_order_id = physical_attribute(SOURCE_ORDERS, "order_id")
    source_order_customer_id = physical_attribute(SOURCE_ORDERS, "customer_id")
    source_customer_id = physical_attribute(SOURCE_CUSTOMERS, "customer_id")

    graph: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        "model_details": [model_details()],
        "model_input_scope": model_input_scope_records(),
        "profiling_profile": [
            {
                **source_order_customer_id,
                "row_count": 10,
                "non_null_count": 9,
                "null_count": 1,
                "blank_count": 0,
                "distinct_count": 5,
                "min_data_length": 1,
                "max_data_length": 5,
                "avg_data_length": 2,
                "percent_populated": 90,
                "percent_duplicates": 44.4444,
                "percent_null": 10,
                "percent_blank": 0,
                "percent_distinct": 55.5556,
            }
        ],
        "analysis_result": [
            {
                "from_tenant_code": SOURCE_ORDERS[0],
                "from_system_code": SOURCE_ORDERS[1],
                "from_connection_code": SOURCE_ORDERS[2],
                "from_object_schema": SOURCE_ORDERS[3],
                "from_object_name": SOURCE_ORDERS[4],
                "from_attribute_name": "customer_id",
                "to_tenant_code": SOURCE_CUSTOMERS[0],
                "to_system_code": SOURCE_CUSTOMERS[1],
                "to_connection_code": SOURCE_CUSTOMERS[2],
                "to_object_schema": SOURCE_CUSTOMERS[3],
                "to_object_name": SOURCE_CUSTOMERS[4],
                "to_attribute_name": "customer_id",
                "relationship_kind": "foreign_key_candidate",
                "relationship_confidence": "high",
                "relationship_basis": "Values overlap.",
                "validation_policy_version": "1.0.0",
                "validation_result": "supported",
                "validation_source_non_null_count": 9,
                "validation_source_distinct_count": 5,
                "validation_target_non_null_count": 5,
                "validation_target_distinct_count": 5,
                "validation_source_missing_target_count": 0,
                "validation_unused_target_count": 0,
                "validation_duplicate_target_key_count": 0,
                "analysis_result_status": "active",
                "analysis_result_is_locked": False,
            }
        ],
        "modeling_assertion_document": [
            {
                "modeling_assertion_document_name": "Business rules",
                "tenant_code": "TENANT-A",
                "system_code": "ERP",
                "modeling_assertion_file_pattern": None,
                "modeling_assertion_document_type": "requirements",
                "modeling_assertion_document_description": "Approved rules.",
                "modeling_assertion_document_metadata": {},
                "is_active": True,
            }
        ],
        "modeling_assertion_record": [
            {
                "modeling_assertion_record_key": "order.customer",
                "modeling_assertion_document_name": "Business rules",
                "modeling_assertion_record_type": "business_rule",
                "modeling_assertion_text": "Every order belongs to a customer.",
                "modeling_assertion_details": {},
                "modeling_assertion_source_location": None,
                "modeling_assertion_applicable_layers": [
                    "conceptual",
                    "logical",
                    "dimensional",
                    "mapping",
                ],
                "modeling_assertion_confidence": "high",
                "modeling_assertion_record_status": "active",
                "modeling_assertion_record_is_locked": False,
            }
        ],
        "conceptual_object": [
            conceptual_object("Order", "transaction", source_order),
            conceptual_object("Customer", "party", source_customer),
        ],
        "conceptual_relationship": [conceptual_relationship()],
        "logical_submodel": [
            {
                "logical_submodel_name": "Sales",
                "logical_submodel_definition": "Sales operations.",
                "logical_submodel_status": "active",
                "logical_submodel_is_locked": False,
            }
        ],
        "logical_entity": [
            logical_entity("Order", "transaction", source_order),
            logical_entity("Customer", "core", source_customer),
        ],
        "logical_attribute": [
            logical_attribute(
                "Order",
                "OrderID",
                1,
                source_order_id,
                primary=True,
                natural=True,
            ),
            logical_attribute("Order", "CustomerID", 2, source_order_customer_id),
            logical_attribute(
                "Customer",
                "CustomerID",
                1,
                source_customer_id,
                primary=True,
                natural=True,
            ),
        ],
        "logical_relationship": [logical_relationship()],
        "dimensional_submodel": [
            {
                "dimensional_submodel_name": "SalesMart",
                "dimensional_submodel_definition": "Sales analytics.",
                "dimensional_submodel_status": "active",
                "dimensional_submodel_is_locked": False,
            }
        ],
        "dimensional_entity": [
            dimensional_entity("SalesFact", "fact"),
            dimensional_entity("CustomerDimension", "dimension"),
        ],
        "dimensional_attribute": [
            dimensional_attribute("SalesFact", "SalesKey", key_role="surrogate"),
            dimensional_attribute("SalesFact", "CustomerKey", key_role="foreign"),
            dimensional_attribute(
                "CustomerDimension",
                "CustomerKey",
                key_role="surrogate",
            ),
        ],
        "dimensional_relationship": [dimensional_relationship()],
        "model_object_binding": [
            object_binding("logical_entity", "Order", SILVER_ORDER),
            object_binding("logical_entity", "Customer", SILVER_CUSTOMER),
            object_binding("dimensional_entity", "SalesFact", GOLD_SALES_FACT),
            object_binding("dimensional_entity", "CustomerDimension", GOLD_CUSTOMER),
        ],
        "model_attribute_binding": [
            attribute_binding("logical_entity", "Order", "OrderID", "OrderID"),
            attribute_binding("logical_entity", "Order", "CustomerID", "CustomerID"),
            attribute_binding(
                "logical_entity",
                "Customer",
                "CustomerID",
                "CustomerID",
            ),
            attribute_binding(
                "dimensional_entity",
                "SalesFact",
                "SalesKey",
                "SalesKey",
            ),
            attribute_binding(
                "dimensional_entity",
                "SalesFact",
                "CustomerKey",
                "CustomerKey",
            ),
            attribute_binding(
                "dimensional_entity",
                "CustomerDimension",
                "CustomerKey",
                "CustomerKey",
            ),
        ],
        "mapping_dependency": [
            {
                "modeled_entity_type": "logical_entity",
                "source_system_code": "ERP",
                "source_system_dependency_order": 0,
                "mapping_source_system_dependency_status": "active",
                "mapping_source_system_dependency_is_locked": False,
            }
        ],
        "mapping_object": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Order",
                "source_system_code": "ERP",
                "output_template_code": None,
                "object_dependency_order": 0,
                "mapping_transformation_document": {
                    "kind": "select",
                    "source": "orders",
                },
                "object_mapping_status": "active",
                "object_mapping_is_locked": False,
            }
        ],
        "mapping_attribute": [
            mapping_attribute("OrderID", "order_id"),
            mapping_attribute("CustomerID", "customer_id"),
        ],
        "generated_code": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Order",
                "artifact_name": "Order.sql",
                "artifact_type": "sql_file",
                "generated_code_content": "SELECT * FROM main.silver.Order",
                "generated_code_status": "active",
            }
        ],
        "generated_code_source_system": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Order",
                "artifact_name": "Order.sql",
                "source_system_code": "ERP",
                "generated_code_source_system_status": "active",
            }
        ],
        "validation_group": [
            {
                "tenant_code": "TENANT-A",
                "system_code": "ERP",
                "validation_group_name": "OrderValidation",
                "validation_group_description": "Order pipeline checks.",
                "is_active": True,
            }
        ],
        "validation_check": [validation_check()],
    }
    return graph


def model_details(model_name: str = "SalesModel") -> dict[str, object]:
    return {
        "model_name": model_name,
        "model_description": "Sales model.",
        "silver_model_naming_instructions": "Use PascalCase and an ID suffix.",
        "silver_model_audit_columns_template": None,
        "gold_model_naming_instructions": "Use PascalCase and a Key suffix.",
        "gold_model_technical_columns_template": None,
        "gold_model_audit_columns_template": None,
    }


def conceptual_object(
    name: str,
    object_type: str,
    source: dict[str, object],
) -> dict[str, object]:
    return {
        "conceptual_object_name": name,
        "conceptual_object_definition": f"Business concept for {name}.",
        "conceptual_object_type": object_type,
        "conceptual_object_grain": f"One {name}.",
        "conceptual_object_aliases": [],
        "conceptual_object_confidence": "high",
        "conceptual_object_status": "active",
        "conceptual_object_is_locked": False,
        "supports": [
            {
                "support_source_type": "object",
                "source_object": source,
                "support_role": "evidence",
                "support_reason": "The source represents the concept.",
                "support_reason_detail": None,
                "support_confidence": "high",
                "support_status": "active",
                "support_is_locked": False,
            }
        ],
    }


def conceptual_relationship() -> dict[str, object]:
    return {
        "from_conceptual_object_name": "Order",
        "to_conceptual_object_name": "Customer",
        "conceptual_relationship_name": "OrderBelongsToCustomer",
        "conceptual_relationship_type": "association",
        "conceptual_relationship_definition": "An Order belongs to a Customer.",
        "conceptual_relationship_cardinality": "many_to_one",
        "conceptual_relationship_basis": "Approved business rule.",
        "conceptual_relationship_cardinality_basis": "Many Orders per Customer.",
        "conceptual_relationship_confidence": "high",
        "conceptual_relationship_status": "active",
        "conceptual_relationship_is_locked": False,
        "supports": [assertion_support()],
    }


def assertion_support() -> dict[str, object]:
    return {
        "support_source_type": "assertion",
        "assertion_record": {"modeling_assertion_record_key": "order.customer"},
        "support_role": "cardinality",
        "support_reason": "The rule defines the relationship.",
        "support_reason_detail": None,
        "support_confidence": "high",
        "support_status": "active",
        "support_is_locked": False,
    }


def logical_entity(
    name: str,
    entity_type: str,
    source: dict[str, object],
) -> dict[str, object]:
    return {
        "logical_entity_name": name,
        "logical_entity_definition": f"Normalized {name} entity.",
        "logical_entity_type": entity_type,
        "logical_entity_type_detail": None,
        "logical_entity_grain": f"One {name}.",
        "logical_entity_dependency_order": 0,
        "logical_entity_confidence": "high",
        "logical_entity_status": "active",
        "logical_entity_is_locked": False,
        "submodels": [
            {
                "submodel_name": "Sales",
                "membership_status": "active",
                "membership_is_locked": False,
            }
        ],
        "sources": [
            {
                "support_source_type": "object",
                "source_object": source,
                "source_order": 1,
                "rationale": "Primary physical source.",
                "status": "active",
                "is_locked": False,
            }
        ],
    }


def logical_attribute(
    entity: str,
    name: str,
    ordinal: int,
    source: dict[str, object],
    *,
    primary: bool = False,
    natural: bool = False,
) -> dict[str, object]:
    return {
        "logical_entity_name": entity,
        "logical_attribute_name": name,
        "logical_attribute_definition": f"{name} attribute.",
        "logical_attribute_data_type": "bigint",
        "logical_attribute_is_nullable": False,
        "logical_attribute_is_primary_key": primary,
        "logical_attribute_is_natural_key": natural,
        "logical_attribute_is_surrogate_key": False,
        "logical_attribute_ordinal_position": ordinal,
        "logical_attribute_is_audit_column": False,
        "logical_attribute_status": "active",
        "logical_attribute_is_locked": False,
        "sources": [
            {
                "support_source_type": "attribute",
                "source_attribute": source,
                "source_order": 1,
                "rationale": "Direct physical source.",
                "status": "active",
                "is_locked": False,
            }
        ],
    }


def logical_relationship() -> dict[str, object]:
    return {
        "logical_relationship_name": "OrderCustomer",
        "logical_relationship_definition": "Order references Customer.",
        "from_logical_entity_name": "Order",
        "from_logical_attribute_name": "CustomerID",
        "to_logical_entity_name": "Customer",
        "to_logical_attribute_name": "CustomerID",
        "logical_relationship_cardinality": "many_to_one",
        "logical_relationship_confidence": "high",
        "logical_relationship_basis": "Source relationship.",
        "logical_relationship_cardinality_basis": "Many Orders per Customer.",
        "logical_relationship_status": "active",
        "logical_relationship_is_locked": False,
    }


def dimensional_entity(name: str, entity_type: str) -> dict[str, object]:
    is_fact = entity_type == "fact"
    return {
        "dimensional_entity_name": name,
        "dimensional_entity_definition": f"{name} entity.",
        "dimensional_entity_type": entity_type,
        "dimensional_fact_type": "transaction" if is_fact else None,
        "dimensional_entity_grain_definition": "One Order." if is_fact else None,
        "dimensional_entity_dependency_order": 0,
        "dimensional_entity_confidence": "high",
        "dimensional_entity_status": "active",
        "dimensional_entity_is_locked": False,
        "submodels": [
            {
                "submodel_name": "SalesMart",
                "membership_status": "active",
                "membership_is_locked": False,
            }
        ],
        "sources": [
            {
                "support_source_type": "assertion",
                "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                "source_role": "business_rule",
                "source_order": 1,
                "rationale": "Approved dimensional requirement.",
                "status": "active",
                "is_locked": False,
            }
        ],
    }


def dimensional_attribute(
    entity: str,
    name: str,
    *,
    key_role: str,
) -> dict[str, object]:
    return {
        "dimensional_entity_name": entity,
        "dimensional_attribute_name": name,
        "dimensional_attribute_definition": f"{name} attribute.",
        "dimensional_attribute_data_type": "bigint",
        "dimensional_attribute_is_nullable": False,
        "dimensional_attribute_ordinal_position": (
            1 if name in {"SalesKey", "CustomerKey"} else 2
        ),
        "dimensional_attribute_role": "key",
        "dimensional_attribute_key_role": key_role,
        "dimensional_attribute_is_grain_component": True,
        "dimensional_attribute_additivity": None,
        "dimensional_attribute_default_aggregation": None,
        "dimensional_attribute_aggregation_basis": None,
        "dimensional_attribute_change_behavior": None,
        "dimensional_attribute_is_audit_column": False,
        "dimensional_attribute_confidence": "high",
        "dimensional_attribute_status": "active",
        "dimensional_attribute_is_locked": False,
        "sources": [
            {
                "support_source_type": "assertion",
                "assertion_record": {"modeling_assertion_record_key": "order.customer"},
                "source_order": 1,
                "rationale": "Approved dimensional requirement.",
                "status": "active",
                "is_locked": False,
            }
        ],
    }


def dimensional_relationship() -> dict[str, object]:
    return {
        "dimensional_relationship_name": "SalesCustomer",
        "dimensional_relationship_definition": "Fact joins Customer Dimension.",
        "from_dimensional_entity_name": "SalesFact",
        "from_dimensional_attribute_name": "CustomerKey",
        "to_dimensional_entity_name": "CustomerDimension",
        "to_dimensional_attribute_name": "CustomerKey",
        "dimensional_relationship_kind": "fact_dimension",
        "dimensional_relationship_cardinality": "many_to_one",
        "dimensional_relationship_is_optional": False,
        "dimensional_relationship_role_name": None,
        "dimensional_relationship_confidence": "high",
        "dimensional_relationship_basis": "Star schema.",
        "dimensional_relationship_cardinality_basis": "Many Facts per Customer.",
        "dimensional_relationship_status": "active",
        "dimensional_relationship_is_locked": False,
    }


def object_binding(
    entity_type: str,
    entity_name: str,
    target: tuple[str, str, str, str, str],
) -> dict[str, object]:
    return {
        **physical_object(target),
        "modeled_entity_type": entity_type,
        "modeled_entity_name": entity_name,
        "model_object_binding_status": "active",
        "model_object_binding_is_locked": False,
    }


def attribute_binding(
    entity_type: str,
    entity_name: str,
    attribute_name: str,
    target_attribute_name: str,
) -> dict[str, object]:
    return {
        "modeled_entity_type": entity_type,
        "modeled_entity_name": entity_name,
        "modeled_attribute_name": attribute_name,
        "attribute_name": target_attribute_name,
        "model_attribute_binding_status": "active",
        "model_attribute_binding_is_locked": False,
    }


def mapping_attribute(
    modeled_attribute_name: str,
    source_attribute_name: str,
) -> dict[str, object]:
    return {
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "Order",
        "modeled_attribute_name": modeled_attribute_name,
        "source_system_code": "ERP",
        "output_template_code": None,
        "attribute_mapping_transformation_document": {
            "kind": "direct",
            "source_attribute": source_attribute_name,
        },
        "attribute_mapping_status": "active",
        "attribute_mapping_is_locked": False,
    }


def validation_check() -> dict[str, object]:
    return {
        "tenant_code": "TENANT-A",
        "system_code": "ERP",
        "validation_group_name": "OrderValidation",
        "validation_check_name": "OrderQueryExecutes",
        "validation_check_description": "Generated Order SQL can be queried.",
        "validation_category_code": "technical.execution",
        "validation_severity": "blocking",
        "validation_query_sql": "SELECT COUNT(*) FROM main.silver.Order",
        "validation_comparison_query_sql": None,
        "validation_result_data_type": None,
        "validation_comparison_operator": "executes_successfully",
        "validation_comparison_value_type": "none",
        "validation_comparison_value": None,
        "is_active": True,
    }


def empty_model_snapshot() -> ModelSnapshot:
    return snapshot_from_graph({})


def snapshot_from_graph(
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]],
) -> ModelSnapshot:
    records = deepcopy(graph)

    def rows(dataset: ModelChangeSetDataset) -> list[dict[str, object]]:
        return records.get(dataset, [])

    details = rows("model_details") or [model_details()]
    return ModelSnapshot.model_validate(
        {
            "model_id": 1,
            "model_name": details[0]["model_name"],
            "model_revision": 2,
            "model_input_scope": {
                "details": details[0],
                "objects": rows("model_input_scope"),
            },
            "profiling": {"profiles": rows("profiling_profile")},
            "analysis": {"relationships": rows("analysis_result")},
            "assertion": {
                "documents": rows("modeling_assertion_document"),
                "records": rows("modeling_assertion_record"),
            },
            "conceptual": {
                "objects": rows("conceptual_object"),
                "relationships": rows("conceptual_relationship"),
            },
            "logical": {
                "submodels": rows("logical_submodel"),
                "entities": rows("logical_entity"),
                "attributes": rows("logical_attribute"),
                "relationships": rows("logical_relationship"),
            },
            "dimensional": {
                "submodels": rows("dimensional_submodel"),
                "entities": rows("dimensional_entity"),
                "attributes": rows("dimensional_attribute"),
                "relationships": rows("dimensional_relationship"),
            },
            "model_binding": {
                "objects": rows("model_object_binding"),
                "attributes": rows("model_attribute_binding"),
            },
            "mapping": {
                "dependencies": rows("mapping_dependency"),
                "objects": rows("mapping_object"),
                "attributes": rows("mapping_attribute"),
            },
            "code_generation": {
                "artifacts": rows("generated_code"),
                "source_systems": rows("generated_code_source_system"),
            },
            "validation": {
                "groups": rows("validation_group"),
                "checks": rows("validation_check"),
            },
        },
        strict=False,
    )


def complete_physical_scope() -> PhysicalModelCatalog:
    input_objects = frozenset(
        tuple(part.casefold() for part in key)
        for key in (SOURCE_ORDERS, SOURCE_CUSTOMERS, BRONZE_ORDERS)
    )
    target_objects = frozenset(
        tuple(part.casefold() for part in key)
        for key in (SILVER_ORDER, SILVER_CUSTOMER, GOLD_SALES_FACT, GOLD_CUSTOMER)
    )
    input_attributes = frozenset(
        {
            (*tuple(part.casefold() for part in SOURCE_ORDERS), "order_id"),
            (*tuple(part.casefold() for part in SOURCE_ORDERS), "customer_id"),
            (*tuple(part.casefold() for part in SOURCE_CUSTOMERS), "customer_id"),
            (*tuple(part.casefold() for part in BRONZE_ORDERS), "order_id"),
            (*tuple(part.casefold() for part in BRONZE_ORDERS), "customer_id"),
        }
    )
    logical_target_attributes = frozenset(
        {
            (*tuple(part.casefold() for part in SILVER_ORDER), "orderid"),
            (*tuple(part.casefold() for part in SILVER_ORDER), "customerid"),
            (*tuple(part.casefold() for part in SILVER_CUSTOMER), "customerid"),
        }
    )
    dimensional_target_attributes = frozenset(
        {
            (*tuple(part.casefold() for part in GOLD_SALES_FACT), "saleskey"),
            (*tuple(part.casefold() for part in GOLD_SALES_FACT), "customerkey"),
            (*tuple(part.casefold() for part in GOLD_CUSTOMER), "customerkey"),
        }
    )
    return PhysicalModelCatalog(
        model_tenant_code="TENANT-A",
        active_system_codes=frozenset({"erp", "gds"}),
        objects=input_objects | target_objects,
        attributes=input_attributes
        | logical_target_attributes
        | dimensional_target_attributes,
        model_input_objects=input_objects,
        model_input_attributes=input_attributes,
        dimensional_source_objects=frozenset(),
        dimensional_source_attributes=frozenset(),
        logical_mapping_target_objects=frozenset(
            tuple(part.casefold() for part in key)
            for key in (SILVER_ORDER, SILVER_CUSTOMER)
        ),
        logical_mapping_target_attributes=logical_target_attributes,
        dimensional_mapping_target_objects=frozenset(
            tuple(part.casefold() for part in key)
            for key in (GOLD_SALES_FACT, GOLD_CUSTOMER)
        ),
        dimensional_mapping_target_attributes=dimensional_target_attributes,
    )
