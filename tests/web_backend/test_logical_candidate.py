from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.application.change_sets.project_validation import (
    PhysicalProjectCatalog,
    ProjectValidationIssue,
    validate_future_graph,
)
from gds_etl_workbench.domain.modeling_records import (
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_etl_workbench.domain.snapshots.project import (
    LogicalSection,
    ProjectChangeSetDataset,
)
from jsonschema import Draft202012Validator
from pydantic import JsonValue
from tests.mcp.project_test_fixtures import LOGICAL_ENTITY_TYPES, snapshot_from_graph

from gds_workbench_api.features.logical.candidate import LogicalCandidateValidator
from gds_workbench_api.features.logical.policy import project_logical_audit_policy


def _object(name: str = "customer_raw") -> PhysicalObjectKey:
    return PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name=name,
    )


def _attribute(name: str = "customer_id", table: str = "customer_raw") -> PhysicalAttributeKey:
    return PhysicalAttributeKey(**_object(table).model_dump(), attribute_name=name)


_COLUMNS = {
    "customer_raw": ("customer_id", "customer_name"),
    "order_raw": ("order_no", "customer_id", "order_dt"),
    "new_selected_raw": ("id",),
}


def _validator(
    *,
    applied: LogicalSection | None = None,
    tables: tuple[str, ...] = ("customer_raw", "order_raw"),
    described: bool = True,
    reserved: tuple[str, ...] = ("Created At",),
    coverage_threshold_percent: int = 70,
) -> LogicalCandidateValidator:
    attributes = tuple(_attribute(column, table) for table in tables for column in _COLUMNS[table])
    return LogicalCandidateValidator(
        selected_object_keys=tuple(_object(table) for table in tables),
        selected_attribute_keys=attributes,
        context_record_ids=(),
        applied=applied,
        entity_types=LOGICAL_ENTITY_TYPES,
        coverage_threshold_percent=coverage_threshold_percent,
        attribute_descriptions=(
            {key: f"Source {key.attribute_name}." for key in attributes} if described else {}
        ),
        reserved_attribute_names=reserved,
    )


def _customer() -> dict[str, Any]:
    return {
        "schema": "silver",
        "name": "Customer",
        "type": "core",
        "definition": "One customer of the business.",
        "grain": "One row per CRM customer id.",
        "sources": ["t1"],
        "attributes": [
            {
                "name": "SourceCustomerID",
                "type": "BIGINT",
                "natural_key": True,
                "from": "t1.customer_id",
            },
            {
                "name": "CustomerName",
                "type": "STRING",
                "nullable": True,
                "from": "t1.customer_name",
            },
        ],
    }


def _order() -> dict[str, Any]:
    return {
        "schema": "silver",
        "name": "SalesOrder",
        "type": "transaction",
        "definition": "One customer order.",
        "grain": "One row per order number.",
        "sources": ["t2"],
        "attributes": [
            {
                "name": "SourceOrderNumber",
                "type": "STRING",
                "natural_key": True,
                "from": "t2.order_no",
            },
            {
                "name": "CustomerID",
                "type": "BIGINT",
                "nullable": False,
                "from": "t2.customer_id",
                "note": "Looked up from Customer by customer_id.",
            },
            {
                "name": "OrderDate",
                "type": "DATE",
                "nullable": False,
                "from": "t2.order_dt",
            },
        ],
    }


def _relationship(
    basis: str = "Analysis: orders.customer_id to customers, supported.",
) -> dict[str, Any]:
    return {
        "from": {"schema": "silver", "entity": "SalesOrder", "attribute": "CustomerID"},
        "to": {"schema": "silver", "entity": "Customer"},
        "cardinality": "many_to_one",
        "basis": basis,
    }


def _answer(*, relationships: bool = True) -> dict[str, Any]:
    return {
        "entities": [_customer(), _order()],
        "relationships": [_relationship()] if relationships else [],
        "retire": [],
    }


def _records(
    validator: LogicalCandidateValidator, answer: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    return {
        change.dataset: cast(list[dict[str, Any]], change.records)
        for change in validator.parse_validated(cast(JsonValue, answer))
    }


def _applied(answer: dict[str, Any]) -> LogicalSection:
    records = _records(_validator(), answer)
    return LogicalSection(
        entities=tuple(
            LogicalEntityRecord.model_validate_json(json.dumps(item), strict=True)
            for item in records.get("logical_entity", [])
        ),
        attributes=tuple(
            LogicalAttributeRecord.model_validate_json(json.dumps(item), strict=True)
            for item in records.get("logical_attribute", [])
        ),
        relationships=tuple(
            LogicalRelationshipRecord.model_validate_json(json.dumps(item), strict=True)
            for item in records.get("logical_relationship", [])
        ),
    )


async def _issues(
    validator: LogicalCandidateValidator, answer: dict[str, Any]
) -> set[tuple[str, tuple[str | int, ...]]]:
    return {
        (issue.code, issue.path)
        for issue in (await validator.validate(cast(JsonValue, answer))).issues
    }


async def test_compact_answer_expands_to_complete_logical_records() -> None:
    validator = _validator()
    assert await _issues(validator, _answer()) == set()
    records = _records(validator, _answer())

    assert sorted(records) == [
        "logical_attribute",
        "logical_entity",
        "logical_relationship",
    ]
    customer, order = records["logical_entity"]
    # A straight table source needs no rationale.
    assert customer["sources"] == [
        {
            "support_source_type": "object",
            "source_object": _object().model_dump(mode="json"),
            "rationale": None,
            "is_active": True,
            "is_locked": False,
        }
    ]
    # Parents come first.
    assert (
        customer["logical_entity_dependency_order"],
        order["logical_entity_dependency_order"],
    ) == (0, 1)
    attributes = {
        (item["logical_entity_name"], item["logical_attribute_name"]): item
        for item in records["logical_attribute"]
    }
    generated = attributes[("Customer", "CustomerID")]
    assert generated["logical_attribute_is_surrogate_key"] is True
    assert generated["logical_attribute_ordinal_position"] == 1
    assert generated["sources"] == []
    key = attributes[("Customer", "SourceCustomerID")]
    # A natural key is never nullable; a missing definition copies the column description.
    assert key["logical_attribute_is_nullable"] is False
    assert key["logical_attribute_definition"] == "Source customer_id."
    assert key["logical_attribute_ordinal_position"] == 2
    assert key["sources"][0]["source_attribute"] == _attribute().model_dump(mode="json")
    assert attributes[("SalesOrder", "CustomerID")]["sources"][0]["rationale"] == (
        "Looked up from Customer by customer_id."
    )
    # Child -> parent: the child's foreign key references the parent's generated key.
    (relationship,) = records["logical_relationship"]
    assert relationship == {
        "from_logical_entity_schema_name": "silver",
        "to_logical_entity_schema_name": "silver",
        "from_logical_entity_name": "SalesOrder",
        "from_logical_attribute_name": "CustomerID",
        "to_logical_entity_name": "Customer",
        "to_logical_attribute_name": "CustomerID",
        "logical_relationship_cardinality": "many_to_one",
        "logical_relationship_basis": "Analysis: orders.customer_id to customers, supported.",
        "logical_relationship_is_active": True,
        "logical_relationship_is_locked": False,
    }


async def test_unknown_short_ids_are_reported_at_the_answer_path() -> None:
    answer = _answer()
    answer["entities"][0]["sources"] = ["t9"]
    answer["entities"][1]["attributes"][2]["from"] = [
        "t2.order_dt",
        "t2.missing_column",
    ]

    assert await _issues(_validator(), answer) == {
        ("candidate.table_unknown", ("entities", 0, "sources", 0)),
        ("candidate.column_unknown", ("entities", 1, "attributes", 2, "from", 1)),
    }


async def test_definition_is_required_without_one_described_source_column() -> None:
    answer = _answer()
    assert await _issues(_validator(described=False), answer) >= {
        (
            "candidate.definition_required",
            ("entities", 0, "attributes", 0, "definition"),
        ),
    }
    answer["entities"][0]["attributes"][0]["definition"] = "CRM customer business key."
    issues = await _issues(_validator(described=False), answer)
    assert (
        "candidate.definition_required",
        ("entities", 0, "attributes", 0, "definition"),
    ) not in issues


async def test_new_records_need_their_judgment_fields() -> None:
    answer = _answer()
    del answer["entities"][0]["grain"]
    del answer["entities"][1]["attributes"][2]["nullable"]

    assert await _issues(_validator(), answer) == {
        ("candidate.new_record_field_required", ("entities", 0, "grain")),
        ("candidate.new_record_field_required", ("entities", 1, "attributes", 2)),
    }


async def test_generated_key_and_audit_names_are_reserved() -> None:
    answer = _answer(relationships=False)
    answer["entities"][0]["attributes"].append(
        {
            "name": "customerid",
            "type": "BIGINT",
            "nullable": False,
            "from": "t1.customer_id",
        }
    )
    answer["entities"][1]["attributes"].append(
        {
            "name": "created at",
            "type": "TIMESTAMP",
            "nullable": True,
            "definition": "Created.",
        }
    )

    assert await _issues(_validator(), answer) == {
        ("candidate.generated_key_reserved", ("entities", 0, "attributes", 2, "name")),
        ("candidate.audit_name_reserved", ("entities", 1, "attributes", 3, "name")),
    }


async def test_record_rules_are_reported_at_the_answer_path_without_values() -> None:
    answer = _answer()
    # The schema allows it, but a Relationship from Customer's own key to Customer has
    # identical endpoints.
    answer["relationships"][0]["from"] = {
        "schema": "silver",
        "entity": "Customer",
        "attribute": "CustomerID",
    }
    answer["relationships"][0]["basis"] = "never-copy-this-candidate-value"
    validator = _validator()
    assert (
        tuple(
            Draft202012Validator(validator.output_schema()).iter_errors(  # pyright: ignore[reportUnknownMemberType]
                cast(JsonValue, answer)
            )
        )
        == ()
    )

    issues = (await validator.validate(cast(JsonValue, answer))).issues

    assert [(issue.code, issue.path) for issue in issues] == [
        ("candidate.cross_field_invalid", ("relationships", 0))
    ]
    assert "never-copy-this-candidate-value" not in issues[0].model_dump_json()


async def test_entity_types_are_the_snapshot_reference_codes() -> None:
    answer = _answer()
    # A code outside the snapshot's reference list is neither offered nor accepted.
    answer["entities"][1]["type"] = "lookup"
    validator = _validator()
    entity_schema = cast(dict[str, Any], validator.output_schema()["$defs"])["_CompactEntity"]

    assert entity_schema["properties"]["type"]["anyOf"][0] == {"enum": list(LOGICAL_ENTITY_TYPES)}
    assert await _issues(validator, answer) == {
        ("candidate.entity_type_unknown", ("entities", 1, "type")),
    }


async def test_saved_records_accept_identity_plus_changes() -> None:
    applied = _applied(_answer())
    answer = {
        "entities": [
            {
                "schema": "SILVER",
                "name": "customer",
                "attributes": [
                    {"name": "CustomerName", "nullable": False},
                    {
                        "name": "CustomerSince",
                        "type": "DATE",
                        "nullable": True,
                        "definition": "First order date.",
                    },
                ],
            }
        ],
        "relationships": [],
        "retire": [],
    }
    validator = _validator(applied=applied)
    assert await _issues(validator, answer) == set()
    records = _records(validator, answer)

    # The Entity itself is unchanged, so only the two Attributes are staged.
    assert sorted(records) == ["logical_attribute"]
    name, since = records["logical_attribute"]
    assert (name["logical_attribute_name"], name["logical_attribute_is_nullable"]) == (
        "CustomerName",
        False,
    )
    assert name["logical_attribute_ordinal_position"] == 3
    assert name["sources"] == [
        source.model_dump(mode="json")
        for attribute in applied.attributes
        if attribute.logical_attribute_name == "CustomerName"
        for source in attribute.sources
    ]
    assert (
        since["logical_entity_name"],
        since["logical_attribute_ordinal_position"],
    ) == (
        "Customer",
        4,
    )


async def test_saved_relationship_is_staged_only_when_restated_differently() -> None:
    validator = _validator(applied=_applied(_answer()))
    unchanged = {"entities": [], "relationships": [_relationship()], "retire": []}
    assert _records(validator, unchanged) == {}

    changed = {
        "entities": [],
        "relationships": [_relationship("Validated: 0 orphans.")],
        "retire": [],
    }
    (record,) = _records(validator, changed)["logical_relationship"]
    assert record["logical_relationship_basis"] == "Validated: 0 orphans."


async def test_retiring_an_entity_retires_its_attributes_and_relationships() -> None:
    validator = _validator(applied=_applied(_answer()))
    answer = {
        "entities": [],
        "relationships": [],
        "retire": [{"schema": "silver", "entity": "Customer"}],
    }
    assert await _issues(validator, answer) == set()
    records = _records(validator, answer)

    assert [item["logical_entity_is_active"] for item in records["logical_entity"]] == [False]
    assert {
        (item["logical_attribute_name"], item["logical_attribute_is_active"])
        for item in records["logical_attribute"]
    } == {
        ("CustomerID", False),
        ("SourceCustomerID", False),
        ("CustomerName", False),
    }
    # The retired Entity keeps its saved sources; only the lifecycle changes.
    assert records["logical_entity"][0]["sources"][0]["is_active"] is True
    assert [item["logical_relationship_is_active"] for item in records["logical_relationship"]] == [
        False
    ]


async def test_retirements_name_saved_records_only() -> None:
    validator = _validator(applied=_applied(_answer()))
    answer = {
        "entities": [_customer()],
        "relationships": [],
        "retire": [
            {"schema": "silver", "entity": "Missing"},
            {"schema": "silver", "entity": "Customer"},
            {
                "schema": "silver",
                "entity": "SalesOrder",
                "attribute": "OrderDate",
                "source": "t2.order_dt",
            },
        ],
    }

    assert await _issues(validator, answer) == {
        ("candidate.record_missing", ("retire", 0)),
        ("candidate.retire_conflict", ("retire", 1)),
    }


@pytest.mark.parametrize("locked", [False, True])
async def test_saved_history_outside_the_selection_is_kept_and_never_restated(
    locked: bool,
) -> None:
    applied = _applied(_answer())
    if locked:
        applied = applied.model_copy(
            update={
                "entities": tuple(
                    entity.model_copy(update={"logical_entity_is_locked": True})
                    for entity in applied.entities
                )
            }
        )
    # This run selects a different table, so the saved sources are outside it.
    validator = _validator(applied=applied, tables=("new_selected_raw",))
    echo: dict[str, Any] = {
        "entities": [
            {
                "schema": "silver",
                "name": "Customer",
                "definition": "One customer of the business.",
            }
        ],
        "relationships": [],
        "retire": [],
    }
    empty: dict[str, Any] = {"entities": [], "relationships": [], "retire": []}
    for answer in (echo, empty):
        assert await _issues(validator, answer) == set()
        assert _records(validator, answer) == {}

    # A saved Entity can gain new evidence; its saved sources stay without being restated.
    extended = deepcopy(echo)
    extended["entities"][0]["sources"] = ["t1"]
    extended["entities"][0]["attributes"] = [
        {"name": "NewSourceID", "type": "STRING", "nullable": True, "from": "t1.id"}
    ]
    expected = (
        {("candidate.record_locked", ("entities", 0))}
        if locked
        else set[tuple[str, tuple[str | int, ...]]]()
    )
    assert await _issues(validator, extended) == expected
    if not locked:
        (entity,) = _records(validator, extended)["logical_entity"]
        assert [source["source_object"]["object_name"] for source in entity["sources"]] == [
            "customer_raw",
            "new_selected_raw",
        ]

    # Tables outside this run have no short id, so they cannot be cited again.
    restated = deepcopy(echo)
    restated["entities"][0]["sources"] = ["t2"]
    assert await _issues(validator, restated) == {
        ("candidate.table_unknown", ("entities", 0, "sources", 0))
    }
    duplicate = deepcopy(echo)
    duplicate["entities"].append(deepcopy(echo["entities"][0]))
    assert ("candidate.duplicate_record", ("entities", 1)) in await _issues(validator, duplicate)


async def test_locked_saved_records_cannot_change() -> None:
    applied = _applied(_answer())
    applied = applied.model_copy(
        update={
            "entities": tuple(
                entity.model_copy(update={"logical_entity_is_locked": True})
                for entity in applied.entities
            )
        }
    )
    answer = {
        "entities": [{"schema": "silver", "name": "Customer", "definition": "Changed."}],
        "relationships": [],
        "retire": [],
    }

    assert await _issues(_validator(applied=applied), answer) == {
        ("candidate.record_locked", ("entities", 0))
    }


async def test_coverage_names_missing_tables_by_short_id() -> None:
    validator = _validator(coverage_threshold_percent=100)
    answer = _answer(relationships=False)
    answer["entities"] = [answer["entities"][0]]

    (issue,) = validator.validate_coverage(cast(JsonValue, answer))

    assert (issue.code, issue.path) == (
        "candidate.object_coverage_incomplete",
        ("entities",),
    )
    assert issue.source_refs == ({"table": "t2", **_object("order_raw").model_dump(mode="json")},)
    assert validator.validate_coverage(cast(JsonValue, _answer())) == ()


def test_output_schema_is_the_compact_contract() -> None:
    schema = _validator().output_schema()
    encoded = json.dumps(schema)

    assert set(cast(dict[str, Any], schema["properties"])) == {
        "entities",
        "relationships",
        "retire",
    }
    assert schema["required"] == ["entities", "relationships", "retire"]
    for removed in (
        "_is_locked",
        "submodel",
        "ordinal",
        "dependency_order",
        "audit_column",
        "cardinality_basis",
    ):
        assert removed not in encoded
    assert "table_index" in encoded


def test_whole_graph_issues_point_at_the_answer() -> None:
    validator = _validator()
    answer = cast(JsonValue, _answer())
    staged: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
        change.dataset: change.records for change in validator.parse_validated(answer)
    }
    position = next(
        index
        for index, record in enumerate(staged["logical_attribute"])
        if record["logical_attribute_name"] == "OrderDate"
    )

    issues = validator.agent_issues(
        answer,
        (
            ProjectValidationIssue(
                code="record_schema_invalid",
                dataset="logical_attribute",
                record_number=position + 1,
                fields=("logical_attribute_data_type",),
                message="Use a supported type.",
            ),
            ProjectValidationIssue(
                code="active_dependency_invalid",
                dataset="logical_relationship",
                record_number=None,
                fields=("to_logical_entity_name",),
                message="An active Relationship needs active endpoints.",
            ),
        ),
        staged,
    )

    assert [(issue.code, issue.path) for issue in issues] == [
        ("candidate.record_schema_invalid", ("entities", 1, "attributes", 2, "type")),
        ("candidate.active_dependency_invalid", ("relationships", "to")),
    ]


def test_expanded_answer_passes_policy_projection_and_whole_graph_validation() -> None:
    validator = _validator()
    changes = project_logical_audit_policy(
        changes=validator.parse_validated(cast(JsonValue, _answer())),
        applied=None,
        raw_template={
            "schema_version": "1.0",
            "columns": [
                {
                    "semantic_name": "Created At",
                    "data_type": "TIMESTAMP",
                    "nullable": False,
                    "definition": None,
                }
            ],
        },
    )
    tables = ("customer_raw", "order_raw")
    objects = frozenset(
        tuple(str(value).casefold() for value in _object(table).model_dump().values())
        for table in tables
    )
    attributes = frozenset(
        (
            *tuple(str(value).casefold() for value in _object(table).model_dump().values()),
            column,
        )
        for table in tables
        for column in _COLUMNS[table]
    )
    graph: dict[ProjectChangeSetDataset, list[dict[str, object]]] = {
        "project_details": [
            {
                "project_name": "Customer Project",
                "project_description": None,
                "silver_model_naming_instructions": None,
                "silver_model_audit_columns_template": None,
                "gold_model_naming_instructions": None,
                "gold_model_technical_columns_template": None,
                "gold_model_audit_columns_template": None,
                "logical_schemas": [{"schema_name": "silver", "description": None}],
            }
        ],
        "project_input_scope": [
            {
                **_object(table).model_dump(mode="json"),
                "project_input_scope_is_locked": False,
                "is_active": True,
            }
            for table in tables
        ],
    }
    checked = validate_future_graph(
        snapshot=snapshot_from_graph(graph),
        staged_documents={change.dataset: change.records for change in changes},
        physical_scope=PhysicalProjectCatalog(
            project_tenant_code="NWA",
            active_system_codes=frozenset({"crm"}),
            objects=cast(Any, objects),
            attributes=cast(Any, attributes),
            project_input_objects=cast(Any, objects),
            project_input_attributes=cast(Any, attributes),
        ),
    )

    assert checked.issues == ()
    staged = {change.dataset: change.records for change in changes}
    assert {
        cast(str, record["logical_attribute_name"])
        for record in staged["logical_attribute"]
        if record["logical_entity_name"] == "Customer"
    } == {"CustomerID", "SourceCustomerID", "CustomerName", "Created At"}


def test_compact_answer_is_a_fraction_of_the_expanded_records() -> None:
    # A synthetic 91-table model: 25 columns per table, one Entity per table and one
    # Relationship per non-root Entity. The ratio is the point, not the exact bytes.
    tables = tuple(f"table_{index:03d}" for index in range(1, 92))
    columns = tuple(f"column_{index:02d}" for index in range(1, 26))
    keys = tuple(
        PhysicalAttributeKey(**_object(table).model_dump(), attribute_name=column)
        for table in tables
        for column in columns
    )
    validator = LogicalCandidateValidator(
        selected_object_keys=tuple(_object(table) for table in tables),
        selected_attribute_keys=keys,
        context_record_ids=(),
        applied=None,
        entity_types=LOGICAL_ENTITY_TYPES,
        attribute_descriptions={key: f"Business meaning of {key.attribute_name}." for key in keys},
    )
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    for position, table in enumerate(tables, start=1):
        name = f"Entity{position:03d}"
        attributes: list[dict[str, Any]] = [
            {
                "name": f"Source{name}ID",
                "type": "STRING",
                "natural_key": True,
                "from": f"t{position}.column_01",
            }
        ]
        attributes.extend(
            {
                "name": f"Field{index:02d}",
                "type": "STRING",
                "nullable": True,
                "from": f"t{position}.{column}",
            }
            for index, column in enumerate(columns[1:], start=2)
        )
        if position > 1:
            attributes.append(
                {
                    "name": "ParentID",
                    "type": "BIGINT",
                    "nullable": True,
                    "from": f"t{position}.column_25",
                    "note": "Looked up from the parent by column_25.",
                }
            )
            relationships.append(
                {
                    "from": {
                        "schema": "silver",
                        "entity": name,
                        "attribute": "ParentID",
                    },
                    "to": {"schema": "silver", "entity": f"Entity{position - 1:03d}"},
                    "cardinality": "many_to_one",
                    "basis": "Analysis edge validated as supported with no missing parents.",
                }
            )
        entities.append(
            {
                "schema": "silver",
                "name": name,
                "type": "core",
                "definition": f"One business record from {table}.",
                "grain": f"One row per {table} business key.",
                "sources": [f"t{position}"],
                "attributes": attributes,
            }
        )
    answer = {"entities": entities, "relationships": relationships, "retire": []}
    records = _records(validator, deepcopy(answer))

    compact_bytes = len(json.dumps(answer, separators=(",", ":")))
    expanded_bytes = len(json.dumps(records, separators=(",", ":")))
    attribute_count = sum(len(entity["attributes"]) for entity in entities)
    assert len(records["logical_attribute"]) == attribute_count + len(entities)
    assert expanded_bytes >= 6 * compact_bytes
    assert compact_bytes / attribute_count < 140
