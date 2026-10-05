"""Databricks exports preserve model definitions without executing SQL."""

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.model_targets.ddl import build_model_ddl
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
    ddl = build_model_ddl(
        entities=entities,
        attributes=attributes,
        relationships=[
            {
                "from_entity_id": 1,
                "from_attribute_name": "CustomerID",
                "to_entity_id": 2,
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


def test_conceptual_ddl_uses_export_only_artificial_key_and_quotes_names() -> None:
    ddl = build_model_ddl(
        entities=[
            {
                "entity_id": 1,
                "entity_schema_name": "conceptual",
                "entity_name": "Customer`Account",
            }
        ],
        attributes=[],
        conceptual=True,
    )
    assert "`Customer``Account`" in ddl
    assert "`ConceptID` BIGINT NOT NULL GENERATED ALWAYS AS IDENTITY" in ddl
    assert "export-only" in ddl


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
        build_model_ddl(
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
    ddl = build_model_ddl(
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
        build_model_ddl(
            entities=[
                {
                    "entity_id": 1,
                    "entity_schema_name": "conceptual",
                    "entity_name": name,
                }
            ],
            attributes=[],
            conceptual=True,
        )
