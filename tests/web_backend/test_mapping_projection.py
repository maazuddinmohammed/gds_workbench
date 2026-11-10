"""New mappings keep join instructions separate from values. Older prompts can use shorthand."""

from typing import Any

import pytest
from atlas_platform.features.mapping.complete_candidate import CompleteMappingCandidateValidator
from atlas_platform.features.mapping.preparation_contracts import ModeledEntityType
from atlas_platform.features.mapping.readiness import assess_mapping_readiness
from atlas_platform.features.workflows.authoring.downstream_inputs import downstream_input_contracts
from pydantic import JsonValue

from tests.web_backend.mapping_fixtures import mapping_preparation


def _answer(query: str, rules: dict[str, str]) -> dict[str, JsonValue]:
    return {
        "schema_version": "1.0",
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {"sample_query": query},
        },
        "attribute_mappings": [
            {
                "modeled_attribute_name": name,
                "attribute_mapping_transformation_document": {
                    "transformation_logic": rule,
                    "default_record": None,
                    "source_columns": [],
                },
            }
            for name, rule in rules.items()
        ],
    }


async def test_join_instructions_and_field_rules_reach_draft_separately() -> None:
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    joins = "FROM bronze.customer c LEFT JOIN meta.system sys ON sys.SystemCode = 'CRM'"
    candidate = _answer(joins, {"CustomerID": "Use c.customer_number"})
    assert not (await validator.validate(candidate)).issues
    changes = validator.parse_validated(candidate).changes
    documents = {change.dataset: change.records[0] for change in changes}
    assert documents["mapping_object"]["mapping_transformation_document"] == {"sample_query": joins}
    attribute = documents["mapping_attribute"]["attribute_mapping_transformation_document"]
    assert isinstance(attribute, dict)
    assert attribute["transformation_logic"] == "Use c.customer_number"


@pytest.mark.parametrize("layer", ["logical_entity", "dimensional_entity"])
async def test_projection_is_ordered_by_frozen_target_and_saved_expanded(
    layer: ModeledEntityType,
) -> None:
    prep = mapping_preparation(attribute_count=6, modeled_entity_type=layer)
    data = prep.model_dump(mode="json")
    attrs = data["context"]["target"]["attributes"]
    for attr, name in zip(
        attrs, ["OwnID", "SourceSystemID", "Audit", "A`B", "Amount", "Missing"], strict=True
    ):
        attr["attribute_name"] = name
    attrs[0]["is_surrogate_key"] = True
    attrs[1]["is_audit_column"] = attrs[2]["is_audit_column"] = True
    data["context"]["headers"][0]["modeled_entity"]["attributes"] = attrs
    prep = type(prep).model_validate(data, strict=False)
    validator = CompleteMappingCandidateValidator(preparation=prep)
    answer = _answer(
        "SELECT <mapped_columns> FROM bronze.lines l WHERE l.batch = :requested",
        {
            "Amount": "l.amount",
            "sourceSYSTEMid": "CAST(<CRM System ID> AS BIGINT)",
            "OwnID": "generated",
            "Audit": "framework",
            "A`B": "TRIM(l.code)",
        },
    )
    assert not (await validator.validate(answer)).issues
    result = validator.parse_validated(answer)
    obj = result.normalized.object_mapping
    assert obj is not None and obj.mapping_transformation_document is not None
    expected = (
        "SELECT TRIM(l.code) AS `A``B`,\n    l.amount AS `Amount`,\n    "
        "CAST(<CRM System ID> AS BIGINT) AS `SourceSystemID` "
        "FROM bronze.lines l WHERE l.batch = :requested"
    )
    assert obj.mapping_transformation_document["sample_query"] == expected
    assert result.is_partial
    record = next(c.records[0] for c in result.changes if c.dataset == "mapping_object")
    assert record["mapping_transformation_document"] == {"sample_query": expected}
    assert (
        validator.parse_validated(result.normalized.model_dump(mode="json")).changes
        == result.changes
    )


async def test_outer_projection_after_current_version_ctes() -> None:
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    ctes = (
        "WITH scoped AS (SELECT id, batch FROM bronze.customer WHERE label <> ')'),\n"
        "current_rows AS (SELECT id FROM scoped QUALIFY "
        "ROW_NUMBER() OVER (PARTITION BY id ORDER BY batch DESC) = 1)\n"
    )
    answer = _answer(ctes + "SELECT <mapped_columns> FROM current_rows c", {"CustomerID": "c.id"})
    assert not (await validator.validate(answer)).issues
    result = validator.parse_validated(answer).normalized.object_mapping
    assert result and result.mapping_transformation_document == {
        "sample_query": ctes + "SELECT c.id AS `CustomerID` FROM current_rows c"
    }


async def test_projection_keeps_foreign_parent_namespace_placeholders_for_code() -> None:
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    query = (
        "SELECT <mapped_columns> FROM bronze.customer c "
        "LEFT JOIN silver.Parent p ON p.SourceID = c.parent_id "
        "AND p.SourceSystemID = CAST(<REFERENCE System ID> AS BIGINT) "
        "WHERE c.GDSBatchID = wid_GDSBatchID"
    )
    answer = _answer(query, {"CustomerID": "p.ParentID"})
    assert not (await validator.validate(answer)).issues
    result = validator.parse_validated(answer).normalized.object_mapping
    assert result and result.mapping_transformation_document == {
        "sample_query": query.replace("<mapped_columns>", "p.ParentID AS `CustomerID`")
    }


@pytest.mark.parametrize(
    ("query", "expr"),
    [
        ("SELECT <mapped_columns>", "42"),
        ("SELECT <mapped_columns> FROM t", ""),
        ("SELECT <mapped_columns> FROM t", "*"),
        ("SELECT <mapped_columns> FROM t", "t.c AS OldAlias"),
        ("SELECT <mapped_columns> FROM t", "t.x, t.y"),
        ("SELECT <mapped_columns> FROM t", "t.c; DROP TABLE t"),
        ("SELECT <mapped_columns> FROM t UNION ALL SELECT 1 FROM u", "t.c"),
        ("WITH c AS (SELECT <mapped_columns> FROM t) SELECT id AS CustomerID FROM c", "t.id"),
        ("WITH c AS (SELECT <mapped_columns> FROM t) SELECT <mapped_columns> FROM c", "c.id"),
        ("WITH c AS (SELECT id FROM t) SELECT <mapped_columns>", "42"),
        ("WITH c AS (DELETE FROM t) SELECT <mapped_columns> FROM c", "c.id"),
        ("WITH c AS (SELECT id INTO other FROM t) SELECT <mapped_columns> FROM c", "c.id"),
        ("WITH c AS (SELECT id FROM t) SELECT <mapped_columns> FROM c; SELECT 1", "c.id"),
        (
            "WITH c AS (SELECT id FROM t) SELECT id FROM c UNION SELECT <mapped_columns> FROM u",
            "id",
        ),
        ("SELECT <mapped_columns> FROM t WHERE", "t.c"),
        ("SELECT t.x, <mapped_columns> FROM t", "t.c"),
    ],
)
async def test_invalid_shorthand_returns_repair_issue(query: str, expr: str) -> None:
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    outcome = await validator.validate(_answer(query, {"CustomerID": expr}))
    assert [issue.code for issue in outcome.issues] == ["candidate.mapping_integrity_invalid"]


async def test_expanded_projection_uses_existing_document_byte_limit() -> None:
    prep = mapping_preparation(attribute_count=10)
    # Each UTF-8 field document fits independently. The completed Object document does not.
    expression = "'" + "é" * 28_000 + "'"
    answer = _answer(
        "SELECT <mapped_columns> FROM t",
        {a.attribute_name: expression for a in prep.context.target.attributes},
    )
    outcome = await CompleteMappingCandidateValidator(preparation=prep).validate(answer)
    assert outcome.issues


@pytest.mark.parametrize("template", ["standard", "edited_fields", "custom", "legacy"])
async def test_only_selected_layer_defaults_enable_projection(template: str) -> None:
    prep = mapping_preparation()
    data = prep.model_dump(mode="json")
    definitions: list[dict[str, Any]] = []
    contracts = downstream_input_contracts("mapping")
    for index, kind in enumerate(("object", "attribute"), start=1):
        definition: dict[str, Any] = dict(contracts[f"{kind}_output_template"][2])
        if kind == "attribute":
            if template == "custom":
                definition["code"] = "custom_attribute"
            if template == "legacy":
                definition["code"] = "mapping_attribute_default"
            if template == "edited_fields":
                definition["fields"] = definition["fields"][:1]
        definition.update(
            output_template_id=index, schema_digest="a" * 64, schema_digest_is_valid=True
        )
        definitions.append(definition)
        selection = {"output_template_id": index, "schema_digest": "a" * 64}
        for part in ("plan", "context"):
            data[part]["output_template_selections"][f"mapping_{kind}"] = selection
    data["context"]["output_templates"] = {"ids": [1, 2], "definitions": definitions}
    prep = type(prep).model_validate(data, strict=False)
    validator = CompleteMappingCandidateValidator(preparation=prep)
    shorthand = "SELECT <mapped_columns> FROM bronze.customer"
    description = str(validator.output_schema()["description"])
    assert ("In sample_query describe the driver" in description) == (template == "standard")
    result = validator.parse_validated(_answer(shorthand, {"CustomerID": "id"}))
    obj = result.normalized.object_mapping
    assert obj and obj.mapping_transformation_document
    assert obj.mapping_transformation_document["sample_query"] == (
        "SELECT id AS `CustomerID` FROM bronze.customer" if template == "standard" else shorthand
    )


async def test_shorthand_preserves_frozen_object_and_complete_queries() -> None:
    prep = mapping_preparation(attribute_count=2, existing=True)
    header = prep.context.headers[0]
    plan = prep.plan.model_copy(
        update={"selected_attribute_ids": (header.modeled_entity.attributes[0].attribute_id,)}
    )
    prep = prep.model_copy(
        update={
            "plan": plan,
            "readiness": assess_mapping_readiness(plan=plan, context=prep.context),
        }
    )
    validator = CompleteMappingCandidateValidator(preparation=prep)
    query = "SELECT <mapped_columns> FROM other"
    answer = _answer(query, {"CustomerID1": "id"})
    assert (await validator.validate(answer)).issues
    answer["object_mapping"] = None
    assert not (await validator.validate(answer)).issues
    assert all(c.dataset != "mapping_object" for c in validator.parse_validated(answer).changes)

    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    query = "SELECT '<mapped_columns>' AS tag UNION ALL SELECT 'other'"
    result = validator.parse_validated(_answer(query, {})).normalized.object_mapping
    assert result and result.mapping_transformation_document == {"sample_query": query}


async def test_new_shorthand_cannot_bypass_a_preserved_field_without_saved_object() -> None:
    prep = mapping_preparation(existing=True, attribute_count=2)
    header = prep.context.headers[0].model_copy(update={"transformation_document": None})
    context = prep.context.model_copy(update={"headers": (header,)})
    plan = prep.plan.model_copy(update={"selected_attribute_ids": (701,)})
    prep = prep.model_copy(
        update={
            "context": context,
            "plan": plan,
            "readiness": assess_mapping_readiness(plan=plan, context=context),
        }
    )
    validator = CompleteMappingCandidateValidator(preparation=prep)
    answer = _answer("SELECT <mapped_columns> FROM bronze.customer c", {"CustomerID1": "c.id"})
    outcome = await validator.validate(answer)
    assert len(outcome.issues) == 1
    assert "Keep existing Object logic unchanged" in outcome.issues[0].message
    answer["object_mapping"] = None
    result = validator.parse_validated(answer)
    assert not result.has_object_transformation and result.is_partial
    assert [record["modeled_attribute_name"] for c in result.changes for record in c.records] == [
        "CustomerID1"
    ]
