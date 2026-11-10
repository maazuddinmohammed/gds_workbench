"""The orchestrator selects the load for freshly authored standard Object rules."""

import pytest
from atlas_platform.features.mapping.complete_candidate import CompleteMappingCandidateValidator
from atlas_platform.features.mapping.preparation_contracts import MappingPreparation
from atlas_platform.features.workflows.authoring.downstream_inputs import downstream_input_contracts
from pydantic import JsonValue

from tests.web_backend.mapping_fixtures import mapping_preparation

PLAN = (
    "-- Join plan\nFROM bronze_crm.customer AS m\n"
    "LEFT JOIN meta.system sys ON sys.SystemCode = 'CRM'"
)
CURRENT = "m.gds_batch_id = 'wid_gdsbatchid'"
LATEST = (
    "m.gds_batch_id = (SELECT MAX(h.gds_batch_id) FROM bronze_crm.customer AS h "
    "WHERE h.source_system_id = m.source_system_id AND h.customer_id = m.customer_id)"
)


def _preparation(*, existing: bool = False) -> MappingPreparation:
    preparation = mapping_preparation(existing=existing)
    frozen = preparation.model_dump(mode="json")
    obj = frozen["context"]["sources"][0]["object"]
    obj["batch_attribute_name"] = "gds_batch_id"
    obj["attributes"].append(
        {
            **obj["attributes"][0],
            "attribute_name": "gds_batch_id",
            "attribute_id": 999,
            "attribute_ordinal_position": 2,
        }
    )
    return type(preparation).model_validate(frozen, strict=False)


def _answer(plan: str, filters: str | None) -> JsonValue:
    return {
        "schema_version": "1.0",
        "attribute_mappings": [],
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {"sample_query": plan, "filter_criteria": filters},
        },
    }


@pytest.mark.parametrize(
    "extra",
    [
        LATEST,
        LATEST.replace("MAX(h.gds_batch_id)", "MAX(DISTINCT h.gds_batch_id)"),
        LATEST.replace("MAX(h.gds_batch_id)", "MAX(COALESCE(h.gds_batch_id, 0))"),
        "retain only MAX(m.gds_batch_id)",
        "m.gds_batch_id = 42",
        "m.gds_batch_id = '42'",
        "42 = m.gds_batch_id",
        "m.gds_batch_id = (SELECT gds_batch_id FROM bronze_crm.customer AS h "
        "ORDER BY h.gds_batch_id DESC LIMIT 1)",
        "m.gds_batch_id = (SELECT TOP 1 h.gds_batch_id FROM bronze_crm.customer h "
        "ORDER BY h.gds_batch_id DESC)",
        "QUALIFY ROW_NUMBER() OVER (PARTITION BY m.customer_id ORDER BY m.gds_batch_id DESC) = 1",
        "Keep the first row from (SELECT ROW_NUMBER() OVER (PARTITION BY h.customer_id "
        "ORDER BY h.gds_batch_id DESC) AS load_rank FROM bronze_crm.customer h) r "
        "WHERE r.load_rank = 1",
    ],
)
@pytest.mark.parametrize("field", ["filter_criteria", "sample_query"])
async def test_current_batch_plus_latest_selector_needs_repair(extra: str, field: str) -> None:
    plan, filters = PLAN, f"Apply to m: {CURRENT}"
    if field == "filter_criteria":
        filters += f" AND {extra}. This retains the highest load for this key."
    else:
        plan += f"\n-- Object-level transformations\n{extra}"
    validator = CompleteMappingCandidateValidator(preparation=_preparation())
    issues = (await validator.validate(_answer(plan, filters))).issues
    assert len(issues) == 1 and "batch reduction" in issues[0].message
    assert not (await validator.validate(_answer(PLAN, CURRENT))).issues


@pytest.mark.parametrize(
    "filters",
    [
        None,
        "m.gds_batch_id = 'WID_GDSBatchID'",
        "m.gds_batch_id = wid_gdsbatchid",
        'm.gds_batch_id = "wid_gdsbatchid"',
        "m.gds_batch_id = 24",
        "m.customer_id = 'wid_gdsbatchid'",
        "sys.gds_batch_id = 'wid_gdsbatchid'",
        "Apply to m: m.gds_batch_id = 'wid_gdsbatchid' OR m.customer_id = 1.",
        "m.customer_id IN (SELECT customer_id FROM silver.parent m "
        "WHERE m.gds_batch_id = 'wid_gdsbatchid')",
    ],
)
async def test_registered_driver_needs_exact_orchestration_equality(filters: str | None) -> None:
    validation = await CompleteMappingCandidateValidator(preparation=_preparation()).validate(
        _answer(PLAN, filters)
    )
    assert len(validation.issues) == 1 and "'wid_gdsbatchid'" in validation.issues[0].message


@pytest.mark.parametrize(
    ("plan", "filters"),
    [
        (PLAN, f"{CURRENT}. Retain MAX(m.amount) at customer grain."),
        (PLAN, "'wid_gdsbatchid' = `m`.`GDS_BATCH_ID`"),
        (PLAN, "(m.gds_batch_id) = 'wid_gdsbatchid' AND (m.customer_id = 1 OR m.status = 2)"),
        ("FROM bronze_crm.customer", "gds_batch_id = 'wid_gdsbatchid'"),
        (PLAN, f"{CURRENT} AND m.customer_id IN (SELECT MAX(m.gds_batch_id) FROM silver.parent m)"),
        (PLAN + "\nLEFT JOIN silver.parent p ON p.id = m.customer_id", CURRENT),
        (PLAN + "\nLEFT JOIN bronze_crm.customer h ON h.gds_batch_id = m.gds_batch_id", CURRENT),
        (PLAN, f"{CURRENT} AND m.label = 'MAX(m.gds_batch_id)'"),
        ("Assess the available source evidence.", None),
    ],
)
async def test_valid_row_rules_and_partial_evidence(plan: str, filters: str | None) -> None:
    validation = await CompleteMappingCandidateValidator(preparation=_preparation()).validate(
        _answer(plan, filters)
    )
    assert not validation.issues


async def test_known_unbatched_source_keeps_only_its_business_filters() -> None:
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    assert (await validator.validate(_answer(PLAN, CURRENT))).issues
    assert not (await validator.validate(_answer(PLAN, "m.customer_id IS NOT NULL"))).issues


async def test_named_preparation_step_binds_its_own_batch_column() -> None:
    plan = (
        "-- Join plan\nFROM customer_totals AS totals\n\n-- Object-level transformations\n"
        "customer_totals: read bronze_crm.customer AS m using filter_criteria. Sum m.amount."
    )
    validator = CompleteMappingCandidateValidator(preparation=_preparation())
    assert not (await validator.validate(_answer(plan, CURRENT))).issues
    assert (await validator.validate(_answer(plan, CURRENT + " AND MAX(m.gds_batch_id)"))).issues
    assert (await validator.validate(_answer(plan, "m.customer_id IS NOT NULL"))).issues
    assert not (
        await validator.validate(_answer(plan.replace("customer_totals:", "other:"), None))
    ).issues


async def test_saved_rule_with_older_token_is_untouched() -> None:
    preparation = _preparation(existing=True)
    saved = {"sample_query": PLAN, "filter_criteria": CURRENT.upper() + " AND " + LATEST}
    header = preparation.context.headers[0].model_copy(update={"transformation_document": saved})
    preparation = preparation.model_copy(
        update={"context": preparation.context.model_copy(update={"headers": (header,)})}
    )
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    answer = _answer(PLAN, saved["filter_criteria"])
    assert not (await validator.validate(answer)).issues
    assert all(c.dataset != "mapping_object" for c in validator.parse_validated(answer).changes)


async def test_custom_object_template_owns_its_same_named_fields() -> None:
    preparation = _preparation()
    frozen = preparation.model_dump(mode="json")
    template = {
        **downstream_input_contracts("mapping")["object_output_template"][2],
        "output_template_id": 901,
        "code": "custom_object_notes",
        "schema_digest": "a" * 64,
        "schema_digest_is_valid": True,
    }
    for part in ("plan", "context"):
        frozen[part]["output_template_selections"]["mapping_object"] = {
            "output_template_id": 901,
            "schema_digest": "a" * 64,
        }
    frozen["context"]["output_templates"] = {"ids": [901], "definitions": [template]}
    preparation = type(preparation).model_validate(frozen, strict=False)
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert not (await validator.validate(_answer(PLAN, LATEST))).issues
