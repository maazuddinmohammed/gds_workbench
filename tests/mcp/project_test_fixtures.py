from __future__ import annotations

from copy import deepcopy

from gds_etl_workbench.application.change_sets.project_validation import (
    PhysicalProjectCatalog,
)
from gds_etl_workbench.domain.snapshots.project import (
    ProjectChangeSetDataset,
    ProjectSnapshot,
)

SOURCE_ORDERS = ("TENANT-A", "ERP", "FC", "src", "orders")
SOURCE_CUSTOMERS = ("TENANT-A", "ERP", "FC", "src", "customers")
BRONZE_ORDERS = ("GDS", "GDS", "LAKEHOUSE", "bronze", "orders")
SILVER_ORDER = ("GDS", "GDS", "LAKEHOUSE", "silver", "Order")
SILVER_CUSTOMER = ("GDS", "GDS", "LAKEHOUSE", "silver", "Customer")
GOLD_SALES_FACT = ("GDS", "GDS", "LAKEHOUSE", "gold", "SalesFact")
GOLD_CUSTOMER = ("GDS", "GDS", "LAKEHOUSE", "gold", "CustomerDimension")
# Mirrors the seeded rows in database/01_reference.sql.
LOGICAL_ENTITY_TYPES = (
    "association",
    "core",
    "event",
    "history",
    "reference",
    "snapshot",
    "transaction",
)
DIMENSIONAL_FACT_TYPES = (
    "accumulating_snapshot",
    "factless",
    "periodic_snapshot",
    "transaction",
)


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


def project_input_scope_records() -> list[dict[str, object]]:
    return [
        {
            **physical_object(key),
            "project_input_scope_is_locked": False,
            "is_active": True,
        }
        for key in (SOURCE_ORDERS, SOURCE_CUSTOMERS, BRONZE_ORDERS)
    ]


def complete_project_graph(
    *, include_enrichment: bool = False
) -> dict[ProjectChangeSetDataset, list[dict[str, object]]]:
    source_order = physical_object(SOURCE_ORDERS)
    source_customer = physical_object(SOURCE_CUSTOMERS)
    source_order_id = physical_attribute(SOURCE_ORDERS, "order_id")
    source_order_customer_id = physical_attribute(SOURCE_ORDERS, "customer_id")
    source_customer_id = physical_attribute(SOURCE_CUSTOMERS, "customer_id")

    graph: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
        "project_details": [project_details()],
        "project_input_scope": project_input_scope_records(),
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
        "object_enrichment": [
            {
                **source_order,
                "object_description": "Customer orders.",
                "is_locked": False,
            }
        ],
        "attribute_enrichment": [
            {
                **source_order_id,
                "attribute_description": "Order business identifier.",
                "attribute_inferred_data_type": "BIGINT",
                "is_natural_key": True,
                "is_primary_key": True,
                "is_nullable": False,
                "is_pii": None,
                "is_locked": False,
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
                "inferred_cardinality": "many_to_one",
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
        "context_group": [
            {
                "context_group_name": "Business rules",
                "context_type_name": "Business Requirement",
                "source_system_code": "ERP",
                "context_group_description": "Approved rules.",
                "is_active": True,
            }
        ],
        "context_record": [
            {
                "context_record_id": "00000000-0000-4000-8000-000000000001",
                "context_group_name": "Business rules",
                "context_text": "Every order belongs to a customer.",
                "source_reference": None,
                "status": "active",
                "is_locked": False,
            }
        ],
        "subject_area": [
            {
                "subject_area_name": "Sales",
                "subject_area_definition": "Customer orders and the customers who place them.",
                "subject_area_is_active": True,
                "subject_area_is_locked": False,
            }
        ],
        "subject_area_table": [
            subject_area_table("Sales", source_order),
            subject_area_table("Sales", source_customer),
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
                natural=True,
            ),
            logical_attribute("Order", "CustomerID", 2, source_order_customer_id),
            logical_attribute(
                "Customer",
                "CustomerID",
                1,
                source_customer_id,
                natural=True,
            ),
        ],
        "logical_relationship": [logical_relationship()],
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
        "mapping_object": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver",
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
                "generated_code_is_locked": False,
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver",
                "modeled_entity_name": "Order",
                "artifact_name": "Order.sql",
                "artifact_type": "sql_file",
                "code_storage_type": "table",
                "code_repository_url": None,
                "code_commit_path": None,
                "code_entry_point": None,
                "code_parameters": None,
                "generated_code_content": "SELECT * FROM main.silver.Order",
                "generated_code_status": "active",
            }
        ],
        "generated_code_source_system": [
            {
                "generated_code_source_system_is_locked": False,
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver",
                "modeled_entity_name": "Order",
                "artifact_name": "Order.sql",
                "source_system_code": "ERP",
                "generated_code_source_system_status": "active",
            }
        ],
        "validation_group": [
            {
                "is_locked": False,
                "tenant_code": "TENANT-A",
                "system_code": "ERP",
                "validation_group_name": "OrderValidation",
                "validation_group_description": "Order pipeline checks.",
                "is_active": True,
            }
        ],
        "validation_check": [validation_check()],
    }
    if not include_enrichment:
        graph.pop("object_enrichment")
        graph.pop("attribute_enrichment")
    return graph


def project_details(project_name: str = "SalesProject") -> dict[str, object]:
    return {
        "project_name": project_name,
        "project_description": "Sales project.",
        "logical_schemas": [{"schema_name": "silver", "description": None}],
        "dimensional_schemas": [{"schema_name": "gold", "description": None}],
        "silver_model_naming_instructions": "Use PascalCase and an ID suffix.",
        "silver_model_audit_columns_template": None,
        "gold_model_naming_instructions": "Use PascalCase and a Key suffix.",
        "gold_model_technical_columns_template": None,
        "gold_model_audit_columns_template": None,
    }


def subject_area_table(area: str, source: dict[str, object]) -> dict[str, object]:
    return {
        "subject_area_name": area,
        **source,
        "subject_area_table_is_active": True,
        "subject_area_table_is_locked": False,
    }


def logical_entity(
    name: str,
    entity_type: str,
    source: dict[str, object],
) -> dict[str, object]:
    return {
        "logical_entity_schema_name": "silver",
        "logical_entity_name": name,
        "logical_entity_definition": f"Normalized {name} entity.",
        "logical_entity_type": entity_type,
        "logical_entity_grain": f"One {name}.",
        "logical_entity_dependency_order": 0,
        "logical_entity_is_active": True,
        "logical_entity_is_locked": False,
        "sources": [
            {
                "support_source_type": "object",
                "source_object": source,
                "rationale": "Primary physical source.",
                "is_active": True,
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
    natural: bool = False,
) -> dict[str, object]:
    return {
        "logical_entity_schema_name": "silver",
        "logical_entity_name": entity,
        "logical_attribute_name": name,
        "logical_attribute_definition": f"{name} attribute.",
        "logical_attribute_data_type": "bigint",
        "logical_attribute_is_nullable": False,
        "logical_attribute_is_natural_key": natural,
        "logical_attribute_is_surrogate_key": False,
        "logical_attribute_ordinal_position": ordinal,
        "logical_attribute_is_audit_column": False,
        "logical_attribute_is_active": True,
        "logical_attribute_is_locked": False,
        "sources": [
            {
                "support_source_type": "attribute",
                "source_attribute": source,
                "rationale": "Direct physical source.",
                "is_active": True,
                "is_locked": False,
            }
        ],
    }


def logical_relationship() -> dict[str, object]:
    return {
        "from_logical_entity_schema_name": "silver",
        "from_logical_entity_name": "Order",
        "from_logical_attribute_name": "CustomerID",
        "to_logical_entity_schema_name": "silver",
        "to_logical_entity_name": "Customer",
        "to_logical_attribute_name": "CustomerID",
        "logical_relationship_cardinality": "many_to_one",
        "logical_relationship_basis": "Many Orders per Customer.",
        "logical_relationship_is_active": True,
        "logical_relationship_is_locked": False,
    }


def dimensional_entity(name: str, entity_type: str) -> dict[str, object]:
    is_fact = entity_type == "fact"
    return {
        "dimensional_entity_schema_name": "gold",
        "dimensional_entity_name": name,
        "dimensional_entity_definition": f"{name} entity.",
        "dimensional_entity_type": entity_type,
        "dimensional_fact_type": "transaction" if is_fact else None,
        "dimensional_entity_grain_definition": "One Order." if is_fact else None,
        "dimensional_entity_dependency_order": 0,
        "dimensional_entity_is_active": True,
        "dimensional_entity_is_locked": False,
        "sources": [
            {
                "support_source_type": "context_record",
                "context_record": {
                    "context_record_id": "00000000-0000-4000-8000-000000000001"
                },
                "rationale": "Approved dimensional requirement.",
                "is_active": True,
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
        "dimensional_entity_schema_name": "gold",
        "dimensional_entity_name": entity,
        "dimensional_attribute_name": name,
        "dimensional_attribute_definition": f"{name} attribute.",
        "dimensional_attribute_data_type": "bigint",
        "dimensional_attribute_is_nullable": False,
        "dimensional_attribute_ordinal_position": (
            1 if name in {"SalesKey", "CustomerKey"} else 2
        ),
        "dimensional_attribute_is_natural_key": key_role == "business",
        "dimensional_attribute_is_surrogate_key": key_role == "surrogate",
        "dimensional_attribute_is_audit_column": False,
        "dimensional_attribute_is_active": True,
        "dimensional_attribute_is_locked": False,
        "sources": [
            {
                "support_source_type": "context_record",
                "context_record": {
                    "context_record_id": "00000000-0000-4000-8000-000000000001"
                },
                "rationale": "Approved dimensional requirement.",
                "is_active": True,
                "is_locked": False,
            }
        ],
    }


def dimensional_relationship() -> dict[str, object]:
    return {
        "from_dimensional_entity_schema_name": "gold",
        "from_dimensional_entity_name": "SalesFact",
        "from_dimensional_attribute_name": "CustomerKey",
        "to_dimensional_entity_schema_name": "gold",
        "to_dimensional_entity_name": "CustomerDimension",
        "to_dimensional_attribute_name": "CustomerKey",
        "dimensional_relationship_role_name": None,
        "dimensional_relationship_basis": "Star schema.",
        "dimensional_relationship_is_active": True,
        "dimensional_relationship_is_locked": False,
    }


def mapping_attribute(
    modeled_attribute_name: str,
    source_attribute_name: str,
) -> dict[str, object]:
    return {
        "modeled_entity_type": "logical_entity",
        "modeled_entity_schema_name": "silver",
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
        "is_locked": False,
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


def empty_project_snapshot() -> ProjectSnapshot:
    return snapshot_from_graph({})


def snapshot_from_graph(
    graph: dict[ProjectChangeSetDataset, list[dict[str, object]]],
) -> ProjectSnapshot:
    records = deepcopy(graph)

    def rows(dataset: ProjectChangeSetDataset) -> list[dict[str, object]]:
        return records.get(dataset, [])

    details = rows("project_details") or [project_details()]
    return ProjectSnapshot.model_validate(
        {
            "project_id": 1,
            "project_name": details[0]["project_name"],
            "project_revision": 2,
            "project_input_scope": {
                "details": details[0],
                "objects": rows("project_input_scope"),
            },
            "profiling": {"profiles": rows("profiling_profile")},
            "enrichment": {
                "objects": rows("object_enrichment"),
                "attributes": rows("attribute_enrichment"),
            },
            "analysis": {"relationships": rows("analysis_result")},
            "context": {
                "types": (
                    {
                        "context_type_name": "Business Requirement",
                        "context_type_description": "Business outcomes.",
                    },
                ),
                "groups": rows("context_group"),
                "records": rows("context_record"),
            },
            "subject_area": {
                "areas": rows("subject_area"),
                "tables": rows("subject_area_table"),
            },
            "logical": {
                "entity_types": [
                    {
                        "logical_entity_type_code": code,
                        "logical_entity_type_description": f"The {code} Entity type.",
                        "logical_entity_type_is_active": True,
                    }
                    for code in LOGICAL_ENTITY_TYPES
                ],
                "entities": rows("logical_entity"),
                "attributes": rows("logical_attribute"),
                "relationships": rows("logical_relationship"),
            },
            "dimensional": {
                "fact_types": [
                    {
                        "dimensional_fact_type_code": code,
                        "dimensional_fact_type_description": f"The {code} fact type.",
                        "dimensional_fact_type_is_active": True,
                    }
                    for code in DIMENSIONAL_FACT_TYPES
                ],
                "entities": rows("dimensional_entity"),
                "attributes": rows("dimensional_attribute"),
                "relationships": rows("dimensional_relationship"),
            },
            "mapping": {
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


def complete_physical_scope() -> PhysicalProjectCatalog:
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
    return PhysicalProjectCatalog(
        project_tenant_code="TENANT-A",
        active_system_codes=frozenset({"erp", "gds"}),
        objects=input_objects | target_objects,
        attributes=input_attributes
        | logical_target_attributes
        | dimensional_target_attributes,
        project_input_objects=input_objects,
        project_input_attributes=input_attributes,
    )
