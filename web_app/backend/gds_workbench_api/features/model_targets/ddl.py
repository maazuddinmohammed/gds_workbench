"""Deterministic Databricks Delta DDL downloads from applied model definitions."""

from collections.abc import Mapping, Sequence
from typing import Any

from gds_etl_workbench.domain.errors import InvalidRequestError
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


def _identifier(value: object, *, object_name: bool = False) -> str:
    text = str(value)
    if (
        not text.strip()
        or len(text) > 255
        or any(ord(char) < 32 or ord(char) == 127 for char in text)
    ):
        raise InvalidRequestError("DDL identifiers must be nonblank without control characters.")
    # UC schema/table restrictions apply even to quoted identifiers; column mapping
    # permits these characters in columns. Never silently rename the saved model.
    # https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-names
    if object_name and any(char in text for char in (".", " ", "/")):
        raise InvalidRequestError(
            "Databricks schema and table names cannot contain spaces, dots, or slashes."
        )
    return "`" + text.replace("`", "``") + "`"


def _data_type(value: object) -> str:
    raw = str(value)
    if any(part in raw for part in (";", "--", "/*", "*/", "\n", "\r")):
        raise InvalidRequestError("A model column has an unsupported Databricks data type.")
    try:
        parsed = parse_one(raw, read="databricks", into=exp.DataType)
        allowed = {
            "BIGINT",
            "INT",
            "SMALLINT",
            "TINYINT",
            "BOOLEAN",
            "FLOAT",
            "DOUBLE",
            "DECIMAL",
            "CHAR",
            "VARCHAR",
            "TEXT",
            "BINARY",
            "VARBINARY",
            "DATE",
            "TIMESTAMP",
            "TIMESTAMPTZ",
            "TIMESTAMPNTZ",
            "ARRAY",
            "MAP",
            "STRUCT",
            "VARIANT",
            "NULL",
        }
        for item in parsed.find_all(exp.DataType):
            if item.this.value not in allowed:
                raise ValueError
            kind = item.this.value
            if kind == "DECIMAL" and item.expressions:
                numbers = [int(parameter.this.this) for parameter in item.expressions]
                if (
                    len(numbers) not in (1, 2)
                    or not 1 <= numbers[0] <= 38
                    or (len(numbers) > 1 and not 0 <= numbers[1] <= numbers[0])
                ):
                    raise ValueError
            elif kind in {"CHAR", "VARCHAR"} and item.expressions:
                if (
                    len(item.expressions) != 1
                    or not 1 <= int(item.expressions[0].this.this) <= 2_147_483_647
                ):
                    raise ValueError
            elif kind in {"ARRAY", "MAP"}:
                if len(item.expressions) != (1 if kind == "ARRAY" else 2):
                    raise ValueError
            elif kind == "STRUCT":
                if not item.expressions:
                    raise ValueError
            elif item.expressions:
                raise ValueError
        return parsed.sql(dialect="databricks")
    except ParseError, ValueError, TypeError, AttributeError:
        raise InvalidRequestError(
            "A model column has an unsupported Databricks data type."
        ) from None


def build_model_ddl(
    *,
    entities: Sequence[Mapping[str, Any]],
    attributes: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]] = (),
    conceptual: bool = False,
) -> str:
    if not entities or len(entities) > 200 or len(attributes) > 5000:
        raise InvalidRequestError(
            "Export requires 1–200 active Entities and at most 5,000 columns."
        )
    tables = {row["entity_id"]: row for row in entities}
    if len(tables) != len(entities):
        raise InvalidRequestError("DDL Entity identities must be unique.")
    lines = [
        "-- Databricks Delta DDL. Review before executing in the intended catalog.",
        "-- Primary and foreign keys are informational and require Unity Catalog.",
    ]
    if conceptual:
        lines.append("-- Conceptual skeleton: ConceptID is an artificial export-only column.")
    names: dict[object, str] = {}
    keys: dict[object, str] = {}
    types: dict[tuple[object, str], str] = {}
    for schema in sorted({str(row["entity_schema_name"]) for row in entities}):
        lines.append(f"CREATE SCHEMA IF NOT EXISTS {_identifier(schema, object_name=True)};")
    for entity in entities:
        entity_id = entity["entity_id"]
        table = (
            f"{_identifier(entity['entity_schema_name'], object_name=True)}."
            f"{_identifier(entity['entity_name'], object_name=True)}"
        )
        names[entity_id] = table
        columns = sorted(
            (row for row in attributes if row["entity_id"] == entity_id),
            key=lambda row: (row["ordinal_position"], str(row["attribute_name"])),
        )
        if conceptual:
            columns = [
                {
                    "attribute_name": "ConceptID",
                    "data_type": "BIGINT",
                    "is_nullable": False,
                    "is_surrogate_key": True,
                    "definition": "Artificial Conceptual export key.",
                }
            ]
        if not columns:
            raise InvalidRequestError("Each exported Entity must have active columns.")
        own_keys = [row for row in columns if row["is_surrogate_key"]]
        if len(own_keys) > 1:
            raise InvalidRequestError(
                "An exported table cannot have multiple generated identity columns."
            )
        normalized = [str(row["attribute_name"]).strip().casefold() for row in columns]
        if len(normalized) != len(set(normalized)):
            raise InvalidRequestError("DDL column names must be unique.")
        definitions: list[str] = []
        for column in columns:
            name = str(column["attribute_name"])
            data_type = _data_type(column["data_type"])
            types[(entity_id, name)] = data_type
            sql = f"  {_identifier(name)} {data_type}"
            if not column["is_nullable"]:
                sql += " NOT NULL"
            if column["is_surrogate_key"]:
                if data_type != "BIGINT" or column["is_nullable"]:
                    raise InvalidRequestError(
                        "Databricks generated keys require non-null BIGINT columns."
                    )
                sql += " GENERATED ALWAYS AS IDENTITY"
                keys[entity_id] = name
            if column.get("definition"):
                sql += " COMMENT " + exp.Literal.string(str(column["definition"])).sql(
                    dialect="databricks"
                )
            definitions.append(sql)
        if entity_id in keys:
            definitions.append(f"  PRIMARY KEY ({_identifier(keys[entity_id])}) NOT ENFORCED")
        table_comment = exp.Literal.string(str(entity.get("definition") or "")).sql(
            dialect="databricks"
        )
        lines.append(
            f"\nCREATE TABLE {table} (\n"
            + ",\n".join(definitions)
            + f"\n) USING DELTA\nCOMMENT {table_comment}\n"
            + "TBLPROPERTIES ('delta.columnMapping.mode' = 'name');"
        )
    seen: set[tuple[object, str, object, str]] = set()
    for relation in relationships:
        left = (relation["from_entity_id"], str(relation["from_attribute_name"]))
        right = (relation["to_entity_id"], str(relation["to_attribute_name"]))
        if left[0] not in tables or right[0] not in tables:
            lines.append("-- Relationship omitted: its other Entity is outside this export.")
            continue
        if keys.get(right[0]) == right[1]:
            child, parent = left, right
        elif keys.get(left[0]) == left[1]:
            child, parent = right, left
        else:
            lines.append(
                "-- Relationship retained in the Model: "
                "no single generated key endpoint for a foreign key."
            )
            continue
        if child == parent or (*child, *parent) in seen:
            continue
        if types.get(child) != types.get(parent) or child not in types:
            raise InvalidRequestError(
                "A relationship has missing columns or incompatible Databricks types."
            )
        seen.add((*child, *parent))
        lines.append(
            f"ALTER TABLE {names[child[0]]} ADD FOREIGN KEY ({_identifier(child[1])}) "
            f"REFERENCES {names[parent[0]]} ({_identifier(parent[1])}) NOT ENFORCED;"
        )
    result = "\n".join(lines) + "\n"
    if len(result.encode("utf-8")) > 16 * 1024 * 1024:
        raise InvalidRequestError("DDL export exceeds its download limit.")
    return result
