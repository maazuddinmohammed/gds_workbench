"""Maintained synthetic SQL examples must obey the real Code delivery contract."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from gds_workbench_api.features.code_generation.candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
    downstream_input_contracts,
    project_downstream_inputs,
)
from jsonschema import Draft202012Validator
from pydantic import JsonValue
from sqlglot import exp, parse
from sqlglot.errors import ErrorLevel, ParseError

ROOT = Path(__file__).resolve().parents[2]
CODE_DEFAULT = next(
    row for row in json.loads(
        (ROOT / "database/seed/05_global_prompt_defaults.template.sql")
        .read_text()
        .split("$workflow_defaults$")[1]
    )
    if row["model_workflow"] == "code_generation"
)
SQL_EXAMPLES = re.findall(r"```sql\s*(.*?)```", CODE_DEFAULT["system_prompt"], re.DOTALL)


def test_code_default_contains_all_delivery_examples() -> None:
    assert len(SQL_EXAMPLES) == 4


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
        targets=(CodeGenerationTargetReference(
            target_ref=example["inputs"]["target_ref"],
            modeled_entity_id=1,
            source_system_codes=tuple(requirements["source_system_codes"]),
            file_layout=requirements["file_layout"],
        ),),
    )
    result = await validator.validate(example["candidate"])
    assert not result.issues


@pytest.mark.parametrize(
    ("example_index", "systems", "statement_count", "target_columns", "source_tables"),
    [
        (
            0,
            ("CRM",),
            1,
            ("SourceCustomerID", "SourceSystemID"),
            {("bronze_crm", "customer")},
        ),
        (
            1,
            ("ERP",),
            3,
            ("SourceOrderLineID", "CustomerName", "NetAmount", "SourceSystemID"),
            {("bronze_erp", "order_line"), ("bronze_erp", "customer")},
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
            1,
            ("SourceCustomerID", "CustomerName", "SourceSystemID"),
            {("bronze_crm", "customer")},
        ),
    ],
    ids=("direct", "staged_join", "combined_systems", "partial_mapping"),
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
        pytest.fail(
            "Maintained SQL example does not parse as Databricks SQL", pytrace=False
        )
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
    assert observed_sources == source_tables
    final = statements[-1]
    assert final is not None
    for select in final.find_all(exp.Select):
        assert tuple(select.named_selects) == target_columns
    if example_index == 1:
        joins = [
            join
            for statement in statements
            if statement
            for join in statement.find_all(exp.Join)
        ]
        assert len(joins) == 1 and joins[0].side == "LEFT"
        assert joins[0].args.get("on") is not None
        assert statements[0] is not None
        assert len(list(statements[0].find_all(exp.Where))) == 1
    elif example_index == 3:
        assert isinstance(final, exp.Select)
        placeholder = final.selects[1]
        assert isinstance(placeholder, exp.Alias)
        assert isinstance(placeholder.this, exp.Cast)
        assert isinstance(placeholder.this.this, exp.Null)
    elif example_index == 2:
        assert isinstance(final, exp.Union) and final.args.get("distinct") is False


def test_context_example_matches_direct_sql_and_preserves_source_identity() -> None:
    contexts = re.findall(r"```json\s*(.*?)```", CODE_DEFAULT["system_prompt"], re.DOTALL)
    assert len(contexts) == 1
    context: dict[str, Any] = json.loads(contexts[0])
    object_mapping = context["object_transformations"][0]
    attribute_mappings = context["attribute_transformations"]
    assert object_mapping["source_system_code"] == "CRM"
    entity = object_mapping["entity"]
    assert (entity["entity_schema_name"], entity["entity_name"]) == (
        "silver",
        "Customer",
    )
    source = object_mapping["transformation"]["source_tables"][0]
    source_fields = (
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    )
    assert tuple(source[field] for field in source_fields) == (
        "EXAMPLE",
        "CRM",
        "CRM_INPUT",
        "bronze_crm",
        "customer",
    )
    source_attribute = attribute_mappings[1]["transformation"]["source_columns"][0]
    assert tuple(source_attribute[field] for field in source_fields) == tuple(
        source[field] for field in source_fields
    )
    assert source_attribute["attribute_name"] == "customer_id"
    target_attributes = context["target_metadata"]["attributes"]
    assert [item["target_attribute_name"] for item in attribute_mappings] == [
        item["attribute_name"] for item in target_attributes
    ]
    assert [
        item["target_attribute_ordinal_position"] for item in attribute_mappings
    ] == [1, 2, 3]
    generated_attributes = [
        item["attribute_name"]
        for item in target_attributes
        if item["population"] == "database"
    ]
    assert generated_attributes == ["CustomerID"]
    assert attribute_mappings[0]["transformation"]["source_columns"] == []
    assert context["source_systems"][0]["source_system_value"] == 11
    assert (
        attribute_mappings[2]["transformation"]["transformation_logic"]
        == "CAST(11 AS BIGINT)"
    )
    assert attribute_mappings[2]["transformation"]["source_columns"] == []
    assert all(
        item["transformation"]["default_record"] is None for item in attribute_mappings
    )
    sample = parse(object_mapping["transformation"]["sample_query"], read="databricks")
    assert sample == parse(SQL_EXAMPLES[0], read="databricks")
    final = sample[-1]
    assert isinstance(final, exp.Select)
    assert final.named_selects == [
        item["attribute_name"]
        for item in target_attributes
        if item["population"] == "mapping"
    ]
    assert not set(generated_attributes).intersection(final.named_selects)


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
    sql = (
        stage.sql(dialect="databricks")
        + ";\n"
        + projection.sql(dialect="databricks")
        + ";"
    )
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
        (
            ROOT / "tests/web_backend/fixtures/downstream_prompt_contexts.json"
        ).read_text()
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
            expected_documents[(system_code, f"Attribute{ordinal}")] = deepcopy(
                document
            )

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
            assert (
                row["modeled_entity_schema_name"]
                == base_object["entity"]["entity_schema_name"]
            )
            assert row["modeled_entity_name"] == base_object["entity"]["entity_name"]
            seen[key] = row["transformation"]
        if page["next_cursor"] is None:
            assert page["is_complete"] is True
            break
        assert page["is_complete"] is False
        assert page_count <= 10
        page = catalog.invoke(
            "get_attribute_transformations", {"cursor": page["next_cursor"]}
        )
    assert page_count == 10 and set(seen) == set(expected_documents)
    for key in seen:
        # Preserve every nested custom value and source reference without logging documents.
        assert hashlib.sha256(
            json.dumps(seen[key], sort_keys=True).encode()
        ).digest() == (
            hashlib.sha256(
                json.dumps(expected_documents[key], sort_keys=True).encode()
            ).digest()
        )
    first = catalog.invoke("get_object_transformations", {})
    second = catalog.invoke(
        "get_object_transformations", {"cursor": first["next_cursor"]}
    )
    assert first["items"][0]["source_system_code"] == "CRM"
    assert second["items"][0]["source_system_code"] == "ERP"
    assert len(first["items"][0]["transformation"]["steps"]) == 3
    assert len(second["items"][0]["transformation"]["steps"]) == 3
