"""Synthetic examples exercise Code delivery and runtime lookup semantics."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from atlas_platform.features.code_generation.candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
)
from atlas_platform.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
    downstream_input_contracts,
    project_downstream_inputs,
)
from jsonschema import Draft202012Validator
from pydantic import JsonValue
from sqlglot import exp, parse
from sqlglot.errors import ErrorLevel, ParseError

from tests.web_backend.test_code_orchestration_contract import execute_fixture_sql

ROOT = Path(__file__).resolve().parents[2]
SQL_EXAMPLES = list(
    json.loads((Path(__file__).parent / "fixtures/code_sql_examples.json").read_text()).values()
)


@pytest.mark.asyncio
async def test_review_example_delivers_complete_inputs_and_valid_sql() -> None:
    example = json.loads((Path(__file__).parent / "fixtures/code_review_example.json").read_text())
    contracts = downstream_input_contracts("code_generation")
    assert set(example["inputs"]) == set(contracts)
    for name, value in example["inputs"].items():
        assert not list(
            Draft202012Validator(contracts[name][0]).iter_errors(value)  # pyright: ignore[reportUnknownMemberType]
        )
    requirements = example["inputs"]["artifact_requirements"]
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref=example["inputs"]["target_ref"],
                modeled_entity_id=1,
                source_system_codes=tuple(requirements["source_system_codes"]),
                file_layout=requirements["file_layout"],
            ),
        ),
    )
    result = await validator.validate(example["candidate"])
    assert not result.issues


@pytest.mark.parametrize(
    ("example_index", "systems", "statement_count", "target_columns", "source_tables"),
    [
        (
            0,
            ("CRM",),
            2,
            ("SourceCustomerID", "SourceSystemID"),
            {("bronze_crm", "customer")},
        ),
        (
            1,
            ("ERP",),
            2,
            (
                "SourceOrderLineID",
                "BillToCustomerID",
                "ShipToCustomerID",
                "NetAmount",
                "SourceSystemID",
            ),
            {
                ("bronze_erp", "order_line"),
                ("bronze_erp", "line_adjustment"),
                ("silver", "Customer"),
            },
        ),
        (
            2,
            ("CRM", "ERP"),
            3,
            ("SourceCustomerID", "SourceSystemID"),
            {("bronze_crm", "customer"), ("bronze_erp", "customer")},
        ),
        (
            3,
            ("CRM",),
            2,
            ("SourceCustomerID", "CustomerName"),
            {("bronze_crm", "customer")},
        ),
    ],
    ids=("direct", "role_lookups", "combined_systems", "partial_mapping"),
)
async def test_sql_examples_parse_and_pass_real_artifact_validation(
    example_index: int,
    systems: tuple[str, ...],
    statement_count: int,
    target_columns: tuple[str, ...],
    source_tables: set[tuple[str, str]],
) -> None:
    sql = SQL_EXAMPLES[example_index]
    try:
        statements = parse(sql, read="databricks", error_level=ErrorLevel.RAISE)
    except ParseError:
        pytest.fail("Maintained SQL example does not parse as Databricks SQL", pytrace=False)
    assert len(statements) == statement_count
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_1",
                modeled_entity_id=1,
                source_system_codes=systems,
                file_layout="combined",
            ),
        )
    )
    candidate = cast(
        JsonValue,
        {
            "issues": ["missing_requirement_evidence"] if example_index == 3 else [],
            "artifacts": [
                {
                    "target_ref": "target_1",
                    "artifact_name": "example.sql",
                    "artifact_role": "target_transformation",
                    "source_system_codes": list(systems),
                    "generated_sql": sql,
                }
            ],
        },
    )
    validation = await validator.validate(candidate)
    assert not validation.issues
    artifacts = validator.parse_validated(candidate)
    assert len(artifacts) == 1
    assert artifacts[0].source_system_codes == systems

    # Every unqualified reference must be a stage declared earlier in this file.
    declared: set[str] = set()
    observed_sources: set[tuple[str, str]] = set()
    for statement in statements:
        assert statement is not None
        query = statement.expression if isinstance(statement, exp.Create) else statement
        assert isinstance(query, exp.Query)
        for table in query.find_all(exp.Table):
            assert not table.catalog
            if table.db:
                observed_sources.add((table.db, table.name))
            else:
                assert table.name in declared
        if isinstance(statement, exp.Create):
            assert statement.kind == "VIEW"
            assert isinstance(statement.this, exp.Table)
            assert not statement.this.db and not statement.this.catalog
            assert statement.this.name not in declared
            declared.add(statement.this.name)
    metadata_sources: set[tuple[str, str]] = {("meta", "system")} if example_index != 3 else set()
    assert observed_sources == source_tables | metadata_sources
    final = statements[-1]
    assert final is not None
    for select in final.find_all(exp.Select):
        assert tuple(select.named_selects) == target_columns
    if example_index == 1:
        joins = [
            join for statement in statements if statement for join in statement.find_all(exp.Join)
        ]
        assert len(joins) == 5
        adjustment = joins[2]
        assert adjustment.side == "LEFT" and adjustment.this.alias == "adj"
        assert {
            (column.table, column.name) for column in adjustment.args["on"].find_all(exp.Column)
        } == {
            (alias, name)
            for alias in ("adj", "l")
            for name in ("order_line_id", "instance_code", "GDSBatchID")
        }
        for join, role in zip(joins[3:], ("bill", "ship"), strict=True):
            assert join.side == "LEFT"
            assert join.this.alias == role
            predicate = join.args["on"]
            assert {(col.table, col.name) for col in predicate.find_all(exp.Column)} == {
                (role, "SourceCustomerNumber"),
                ("l", f"{role}_to_number"),
                (role, "SourceSystemID"),
                ("sys" if role == "bill" else "ship_sys", "SystemID"),
                (role, "InstanceCode"),
                ("l", "instance_code"),
            }
            assert {literal.this for literal in predicate.find_all(exp.Literal)} == set()
            assert (predicate.find(exp.Trim) is not None) == (role == "bill")
        stage = statements[0]
        assert isinstance(stage, exp.Create) and isinstance(stage.expression, exp.Select)
        projection = stage.expression
        role_outputs = {
            item.alias: (item.this.table, item.this.name)
            for item in projection.selects
            if isinstance(item, exp.Alias) and isinstance(item.this, exp.Column)
        }
        assert role_outputs == {
            "BillToCustomerID": ("bill", "CustomerID"),
            "ShipToCustomerID": ("ship", "CustomerID"),
        }
        where = projection.args.get("where")
        assert isinstance(where, exp.Where)
        assert {(col.table, col.name) for col in where.find_all(exp.Column)} == {
            ("l", "status"),
            ("l", "GDSBatchID"),
        }
    elif example_index == 3:
        stage = statements[0]
        assert isinstance(stage, exp.Create) and isinstance(stage.expression, exp.Select)
        placeholder = stage.expression.selects[1]
        assert isinstance(placeholder, exp.Alias)
        assert isinstance(placeholder.this, exp.Cast)
        assert isinstance(placeholder.this.this, exp.Null)
    elif example_index == 2:
        assert isinstance(final, exp.Union) and final.args.get("distinct") is False


def test_role_lookup_example_executes_with_batch_and_complete_parent_key() -> None:
    # Exercise the maintained prompt example through the supplied runner's exact
    # substitution contract. All data and SQLite schemas live only in memory.
    sql = SQL_EXAMPLES[1]
    assert "'wid_gdsbatchid'" in sql
    statements = parse(
        sql.replace("wid_gdsbatchid", "42"),
        read="databricks",
        error_level=ErrorLevel.RAISE,
    )
    with sqlite3.connect(":memory:") as connection:
        connection.executescript(
            """
            ATTACH DATABASE ':memory:' AS bronze_erp;
            ATTACH DATABASE ':memory:' AS silver;
            ATTACH DATABASE ':memory:' AS meta;
            CREATE TABLE meta.system (SystemCode TEXT PRIMARY KEY, SystemID INTEGER);
            INSERT INTO meta.system VALUES ('ERP', 22), ('DIRECTORY', 52);
            CREATE TABLE bronze_erp.order_line (
                order_line_id INTEGER, instance_code TEXT, bill_to_number TEXT,
                ship_to_number TEXT, quantity NUMERIC, unit_price NUMERIC,
                status TEXT, GDSBatchID INTEGER
            );
            CREATE TABLE bronze_erp.line_adjustment (
                order_line_id INTEGER, instance_code TEXT, discount_amount NUMERIC,
                GDSBatchID INTEGER
            );
            CREATE TABLE silver.Customer (
                CustomerID INTEGER, SourceCustomerNumber TEXT, InstanceCode TEXT,
                SourceSystemID INTEGER, GDSBatchID INTEGER
            );
            """
        )
        connection.executemany(
            "INSERT INTO bronze_erp.order_line VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (1, "EAST", " C1 ", "C2", 2, 10, "posted", 42),
                (1, "EAST", " C1 ", "C2", 2, 99, "posted", 41),
                (2, "EAST", "MISSING", "C2", 1, 15, "posted", 42),
                (3, "WEST", " C1 ", "C2", 1, 40, "posted", 42),
                (4, "EAST", "C1", "C2", 1, 50, "draft", 42),
            ),
        )
        connection.executemany(
            "INSERT INTO bronze_erp.line_adjustment VALUES (?, ?, ?, ?)",
            (
                (1, "EAST", 3, 42),
                (1, "EAST", 9, 41),
                (1, "WEST", 8, 42),
                (3, "WEST", 5, 42),
            ),
        )
        connection.executemany(
            "INSERT INTO silver.Customer VALUES (?, ?, ?, ?, ?)",
            (
                (101, "C1", "EAST", 22, 7),
                (102, "C2", "EAST", 52, 12),
                (301, "C1", "WEST", 22, 5),
                (302, "C2", "WEST", 52, 6),
                (901, "C1", "EAST", 11, 42),
                (902, "C2", "EAST", 22, 42),
            ),
        )
        for statement in statements[:-1]:
            assert isinstance(statement, exp.Create)
            # SQLite lacks OR REPLACE VIEW. The isolated database is empty, so
            # removing that flag preserves this example's create semantics.
            local_stage = statement.copy()
            local_stage.set("replace", False)
            connection.execute(local_stage.sql(dialect="sqlite"))
        final = statements[-1]
        assert isinstance(final, exp.Query)
        cursor = connection.execute(final.sql(dialect="sqlite"))
        assert tuple(column[0] for column in cursor.description) == (
            "SourceOrderLineID",
            "BillToCustomerID",
            "ShipToCustomerID",
            "NetAmount",
            "SourceSystemID",
        )
        assert sorted(cursor.fetchall()) == [
            (1, 101, 102, 17, 22),
            (2, None, 102, 15, 22),
            (3, 301, 302, 35, 22),
        ]


@pytest.mark.parametrize("system_code", ("CRM", "ERP"))
async def test_combined_example_branches_are_self_contained_for_per_system_layout(
    system_code: str,
) -> None:
    statements = parse(SQL_EXAMPLES[2], read="databricks", error_level=ErrorLevel.RAISE)
    branch_index = 0 if system_code == "CRM" else 1
    stage = statements[branch_index]
    final = statements[-1]
    assert isinstance(stage, exp.Create) and isinstance(final, exp.Union)
    projection = final.this if branch_index == 0 else final.expression
    assert isinstance(projection, exp.Select)
    sql = stage.sql(dialect="databricks") + ";\n" + projection.sql(dialect="databricks") + ";"
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_1",
                modeled_entity_id=1,
                source_system_codes=(system_code,),
                file_layout="per_system",
            ),
        )
    )
    result = await validator.validate(
        {
            "artifacts": [
                {
                    "target_ref": "target_1",
                    "artifact_name": "example.sql",
                    "artifact_role": "target_transformation",
                    "source_system_codes": [system_code],
                    "generated_sql": sql,
                }
            ]
        }
    )
    assert not result.issues


def test_full_mapping_documents_remain_grouped_by_system_across_reader_pages() -> None:
    raw = json.loads(
        (ROOT / "tests/web_backend/fixtures/downstream_prompt_contexts.json").read_text()
    )["code_generation"]
    context = raw["targets"][0]["context"]
    base_object = deepcopy(context["object_mappings"][0])
    base_attribute = deepcopy(context["attribute_mappings"][0])
    context["source_systems"] = []
    context["object_mappings"] = []
    context["attribute_mappings"] = []
    expected_documents: dict[tuple[str, str], dict[str, Any]] = {}
    for system_id, system_code in ((31, "CRM"), (32, "ERP")):
        context["source_systems"].append(
            {
                "source_system_id": system_id,
                "system_code": system_code,
                "system_name": system_code,
            }
        )
        object_mapping = deepcopy(base_object)
        object_mapping.update(mapping_object_id=system_id, source_system_id=system_id)
        object_mapping["transformation"] = {
            "steps": ["Prepare source", "Apply evidenced joins", "Project attributes"],
            "custom": {"business_rule_id": f"{system_code}-rule", "sequence": [2, 1]},
        }
        context["object_mappings"].append(object_mapping)
        for ordinal in range(1, 6):
            attribute = deepcopy(base_attribute)
            attribute.update(
                mapping_object_id=system_id,
                source_system_id=system_id,
                target_attribute_name=f"Attribute{ordinal}",
                target_attribute_ordinal_position=ordinal,
            )
            document = {
                "expression": f"CONCAT(a.value_{ordinal}, b.value_{ordinal})",
                "source_attributes": [
                    {
                        "tenant_code": "EXAMPLE",
                        "system_code": system_code,
                        "connection_code": "INPUT",
                        "object_schema": "bronze",
                        "object_name": table,
                        "attribute_name": f"value_{ordinal}",
                    }
                    for table in ("first_source", "second_source")
                ],
                "custom": {
                    "business_rule_id": ordinal,
                    "nested": {"keep": [False, 0, None]},
                },
            }
            attribute["transformation"] = document
            context["attribute_mappings"].append(attribute)
            expected_documents[(system_code, f"Attribute{ordinal}")] = deepcopy(document)

    values = project_downstream_inputs("code_generation", raw)
    catalog = build_downstream_readers(
        "code_generation",
        values,
        max_result_bytes=100_000,
        max_page_records=1,
        max_cumulative_result_bytes=500_000,
    )
    values["attribute_transformations"].clear()
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    page = catalog.invoke("get_attribute_transformations", {})
    page_count = 0
    while True:
        page_count += 1
        for row in page["items"]:
            key = (row["source_system_code"], row["target_attribute_name"])
            assert key not in seen
            assert row["modeled_entity_schema_name"] == base_object["entity"]["entity_schema_name"]
            assert row["modeled_entity_name"] == base_object["entity"]["entity_name"]
            seen[key] = row["transformation"]
        if page["next_cursor"] is None:
            assert page["is_complete"] is True
            break
        assert page["is_complete"] is False
        assert page_count <= 10
        page = catalog.invoke("get_attribute_transformations", {"cursor": page["next_cursor"]})
    assert page_count == 10 and set(seen) == set(expected_documents)
    for key in seen:
        # Preserve every nested custom value and source reference without logging documents.
        assert hashlib.sha256(json.dumps(seen[key], sort_keys=True).encode()).digest() == (
            hashlib.sha256(json.dumps(expected_documents[key], sort_keys=True).encode()).digest()
        )
    first = catalog.invoke("get_object_transformations", {})
    second = catalog.invoke("get_object_transformations", {"cursor": first["next_cursor"]})
    assert first["items"][0]["source_system_code"] == "CRM"
    assert second["items"][0]["source_system_code"] == "ERP"
    assert len(first["items"][0]["transformation"]["steps"]) == 3
    assert len(second["items"][0]["transformation"]["steps"]) == 3


async def test_embedded_code_examples_deliver_the_mapped_rows_at_runtime() -> None:
    """Run the exact SQL shown to the model, including the JSON it must return."""
    studio = (
        ROOT / "web_app/prompt_studio/prompts/code_generation.common.sql_generation.md"
    ).read_text()
    system = studio.split("<!-- ===== INSTRUCTION PROMPT ===== -->", 1)[0]
    billing, combined = re.findall(r"^```sql\n(.*?)\n```$", system, re.M | re.S)
    inputs, object_document, response = [
        json.loads(block) for block in re.findall(r"^```json\n(.*?)\n```$", system, re.M | re.S)
    ]
    layout = inputs["artifact_requirements"]
    target = inputs["target_metadata"]
    plan, steps = object_document["sample_query"].split("\n\n-- Object-level transformations\n")
    assert plan.startswith("-- Join plan\nFROM posted_headers AS h\n")
    assert "bronze_erp.billing_header" in steps and "posted_headers" in steps
    assert "SELECT " not in object_document["sample_query"].upper()
    assert "h.GDSBatchID = 'wid_gdsbatchid'" in object_document["filter_criteria"]
    assert parse(response["artifacts"][0]["generated_sql"], read="databricks") == parse(
        billing, read="databricks"
    )
    for sql, branches in ((billing, ["erp"]), (combined, ["crm", "erp"])):
        *views, final = parse(sql, read="databricks")
        assert len(views) == len(branches)
        for view, branch in zip(views, branches, strict=True):
            assert isinstance(view, exp.Create) and isinstance(view.expression, exp.Subquery)
            assert view.this.name.endswith(f"_{branch}")
        assert isinstance(final, exp.Query)
    joined_tables = {
        (table["object_schema"], table["object_name"])
        for table in object_document["source_tables"]
        if "object_schema" in table
    }
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref=inputs["target_ref"],
                modeled_entity_id=1,
                source_system_codes=tuple(layout["source_system_codes"]),
                file_layout=layout["file_layout"],
                batch_sources=tuple(
                    (schema, table, "GDSBatchID") for schema, table in joined_tables
                ),
                lookup_system_codes=(),
            ),
        )
    )
    assert not (await validator.validate(response)).issues
    assert validator.parse_validated(response)[0].source_system_codes == ("ERP",)

    # The prior header/line, another instance, another System, and a missing
    # optional Client distinguish correct joins from a query that only parses.
    sources = {
        "bronze_erp.billing_header": {
            "columns": ["invoice_no", "instance_code", "client_no", "GDSBatchID", "status"],
            "rows": [
                ["I01", "EAST", "001", 28, "POSTED"],
                ["I01", "WEST", "404", 28, "POSTED"],
                ["I01", "EAST", "001", 27, "POSTED"],
                ["I01", "EAST", "001", 29, "POSTED"],
                ["X", "EAST", "001", 28, "DRAFT"],
            ],
        },
        "bronze_erp.billing_line": {
            "columns": [
                "invoice_no",
                "instance_code",
                "line_no",
                "GDSBatchID",
                "quantity",
                "unit_price",
            ],
            "rows": [
                ["I01", "EAST", 1, 28, 2, 9],
                ["I01", "WEST", 1, 28, 3, 9],
                ["I01", "EAST", 1, 27, 20, 9],
                ["I01", "EAST", 1, 29, 30, 9],
                ["X", "EAST", 1, 28, 2, 9],
            ],
        },
        "silver.Client": {
            "columns": [
                "SourceClientNo",
                "InstanceCode",
                "SourceSystemID",
                "ClientID",
                "GDSBatchID",
            ],
            "rows": [
                ["001", "EAST", 72, 101, 3],
                ["001", "WEST", 72, 102, 3],
                ["001", "EAST", 87, 103, 28],
            ],
        },
        "meta.system": {"columns": ["SystemCode", "SystemID"], "rows": [["ERP", 72], ["CRM", 87]]},
    }
    columns, rows = execute_fixture_sql(billing.replace("'wid_gdsbatchid'", "28"), sources)
    assert columns == [
        a["attribute_name"] for a in target["attributes"] if a["population"] == "mapping"
    ]
    assert rows == [("I01", "EAST", 1, 101, 18, 72), ("I01", "WEST", 1, None, 27, 72)]

    multi = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_2",
                modeled_entity_id=2,
                source_system_codes=("CRM", "ERP"),
                file_layout="combined",
                lookup_system_codes=(),
            ),
        )
    )
    assert not (
        await multi.validate(
            {
                "issues": [],
                "artifacts": [
                    {
                        "target_ref": "target_2",
                        "artifact_name": "customer.sql",
                        "artifact_role": "target_transformation",
                        "source_system_codes": ["CRM", "ERP"],
                        "generated_sql": combined,
                    }
                ],
            }
        )
    ).issues
    columns, rows = execute_fixture_sql(
        combined,
        {
            "bronze_crm.customer": {"columns": ["customer_id"], "rows": [["01"]]},
            "bronze_erp.customer": {"columns": ["customer_key"], "rows": [["01"]]},
            "meta.system": sources["meta.system"],
        },
    )
    assert columns == ["SourceCustomerID", "SourceSystemID"]
    assert rows == [(1, 72), (1, 87)]
