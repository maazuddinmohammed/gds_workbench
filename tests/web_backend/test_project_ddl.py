"""Databricks exports preserve project definitions without executing SQL."""

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.project_targets.ddl import build_project_ddl
from sqlglot import parse


def test_delta_ddl_preserves_types_order_identity_comments_and_relationships() -> None:
    entities = [
        {
            "entity_id": 1,
            "entity_schema_name": "silver",
            "entity_name": "Customer",
            "definition": "Customer's record",
        },
        {
            "entity_id": 2,
            "entity_schema_name": "silver",
            "entity_name": "Order",
            "definition": "Orders",
        },
    ]
    attributes = [
        {
            "entity_id": 1,
            "attribute_name": "CustomerID",
            "data_type": "BIGINT",
            "ordinal_position": 1,
            "is_nullable": False,
            "is_surrogate_key": True,
        },
        {
            "entity_id": 2,
            "attribute_name": "CustomerID",
            "data_type": "BIGINT",
            "ordinal_position": 1,
            "is_nullable": False,
            "is_surrogate_key": False,
        },
        {
            "entity_id": 2,
            "attribute_name": "Amount",
            "data_type": "DECIMAL(18,2)",
            "ordinal_position": 2,
            "is_nullable": True,
            "is_surrogate_key": False,
        },
    ]
    ddl = build_project_ddl(
        entities=entities,
        attributes=attributes,
        # Child -> parent: Order's foreign key points at Customer's key.
        relationships=[
            {
                "from_entity_id": 2,
                "from_attribute_name": "CustomerID",
                "to_entity_id": 1,
                "to_attribute_name": "CustomerID",
            }
        ],
    )
    assert ddl.count("GENERATED ALWAYS AS IDENTITY") == 1
    assert "`Amount` DECIMAL(18, 2)" in ddl
    assert (
        "ALTER TABLE `silver`.`Order` ADD FOREIGN KEY (`CustomerID`) REFERENCES `silver`.`Customer`"
        in ddl
    )
    assert len(parse(ddl, read="databricks")) == 4


def test_ddl_keeps_links_whose_parent_is_not_a_generated_key_or_not_exported() -> None:
    entities = [
        {"entity_id": 1, "entity_schema_name": "silver", "entity_name": "Customer"},
        {"entity_id": 2, "entity_schema_name": "silver", "entity_name": "Order"},
    ]
    attributes = [
        {
            "entity_id": entity_id,
            "attribute_name": "CustomerCode",
            "data_type": "STRING",
            "ordinal_position": 1,
            "is_nullable": False,
            "is_surrogate_key": False,
        }
        for entity_id in (1, 2)
    ]
    ddl = build_project_ddl(
        entities=entities,
        attributes=attributes,
        relationships=[
            # The parent column is a natural key, which Unity Catalog cannot reference.
            {
                "from_entity_id": 2,
                "from_attribute_name": "CustomerCode",
                "to_entity_id": 1,
                "to_attribute_name": "CustomerCode",
            },
            {
                "from_entity_id": 2,
                "from_attribute_name": "CustomerCode",
                "to_entity_id": 9,
                "to_attribute_name": "CustomerCode",
            },
        ],
    )
    assert "FOREIGN KEY" not in ddl
    assert "its parent column is not the parent table's generated key" in ddl
    assert "its other Entity is outside this export" in ddl


def test_ddl_rejects_a_foreign_key_whose_type_differs_from_the_parent_key() -> None:
    with pytest.raises(InvalidRequestError):
        build_project_ddl(
            entities=[
                {"entity_id": 1, "entity_schema_name": "silver", "entity_name": "Customer"},
                {"entity_id": 2, "entity_schema_name": "silver", "entity_name": "Order"},
            ],
            attributes=[
                {
                    "entity_id": 1,
                    "attribute_name": "CustomerID",
                    "data_type": "BIGINT",
                    "ordinal_position": 1,
                    "is_nullable": False,
                    "is_surrogate_key": True,
                },
                {
                    "entity_id": 2,
                    "attribute_name": "CustomerID",
                    "data_type": "STRING",
                    "ordinal_position": 1,
                    "is_nullable": True,
                    "is_surrogate_key": False,
                },
            ],
            relationships=[
                {
                    "from_entity_id": 2,
                    "from_attribute_name": "CustomerID",
                    "to_entity_id": 1,
                    "to_attribute_name": "CustomerID",
                }
            ],
        )


def test_ddl_escapes_backticks_in_quoted_names() -> None:
    ddl = build_project_ddl(
        entities=[
            {
                "entity_id": 1,
                "entity_schema_name": "silver",
                "entity_name": "Customer`Account",
            }
        ],
        attributes=[
            {
                "entity_id": 1,
                "attribute_name": "Account`ID",
                "data_type": "BIGINT",
                "ordinal_position": 1,
                "is_nullable": False,
                "is_surrogate_key": True,
            }
        ],
    )
    assert "CREATE TABLE `silver`.`Customer``Account` (" in ddl
    assert "`Account``ID` BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY" in ddl
    assert len(parse(ddl, read="databricks")) == 2


@pytest.mark.parametrize(
    "data_type",
    [
        "INT); DROP TABLE x; --",
        "DECIMAL(50,2)",
        "unknown_type",
        "BIGINT(8)",
        "VARCHAR(0)",
        "MAP<STRING>",
        "DECIMAL(10,2,3)",
    ],
)
def test_ddl_rejects_unsafe_or_unsupported_types(data_type: str) -> None:
    with pytest.raises(InvalidRequestError):
        build_project_ddl(
            entities=[{"entity_id": 1, "entity_schema_name": "s", "entity_name": "T"}],
            attributes=[
                {
                    "entity_id": 1,
                    "attribute_name": "A",
                    "data_type": data_type,
                    "ordinal_position": 1,
                    "is_nullable": True,
                    "is_surrogate_key": False,
                }
            ],
        )


def test_nested_databricks_types_are_preserved() -> None:
    ddl = build_project_ddl(
        entities=[{"entity_id": 1, "entity_schema_name": "s", "entity_name": "T"}],
        attributes=[
            {
                "entity_id": 1,
                "attribute_name": "Amounts",
                "data_type": "MAP<STRING, ARRAY<STRUCT<Amount: DECIMAL(12,2)>>>",
                "ordinal_position": 1,
                "is_nullable": True,
                "is_surrogate_key": False,
            }
        ],
    )
    assert "MAP<STRING, ARRAY<STRUCT<Amount: DECIMAL(12, 2)>>>" in ddl
    assert len(parse(ddl, read="databricks")) == 2


@pytest.mark.parametrize(
    "name", ["Customer Account", "Customer.Account", "Customer/Account", "X" * 256]
)
def test_ddl_rejects_names_databricks_would_reject_even_when_quoted(name: str) -> None:
    with pytest.raises(InvalidRequestError):
        build_project_ddl(
            entities=[
                {
                    "entity_id": 1,
                    "entity_schema_name": "silver",
                    "entity_name": name,
                }
            ],
            attributes=[
                {
                    "entity_id": 1,
                    "attribute_name": "CustomerID",
                    "data_type": "BIGINT",
                    "ordinal_position": 1,
                    "is_nullable": False,
                    "is_surrogate_key": False,
                }
            ],
        )
