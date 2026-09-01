from __future__ import annotations

from typing import Any, cast

import pytest
from gds_etl_workbench.domain.modeling_records import (
    ValidationCheckRecord,
    ValidationGroupRecord,
)
from pydantic import JsonValue

from gds_workbench_api.features.qa.candidate import (
    QASystemCandidateValidator,
    reconcile_qa_candidates,
)
from gds_workbench_api.features.qa.context import (
    QAExecutionContext,
    QASystemAuthoringContext,
)


def _group(*, active: bool = True) -> ValidationGroupRecord:
    return ValidationGroupRecord(
        tenant_code="acme",
        system_code="erp",
        validation_group_name="reconciliation",
        validation_group_description="Counts reconcile.",
        mapping_context_digest="a" * 64,
        code_context_digest="b" * 64,
        is_active=active,
    )


def _check(*, active: bool = True) -> ValidationCheckRecord:
    return ValidationCheckRecord(
        tenant_code="acme",
        system_code="erp",
        validation_group_name="reconciliation",
        validation_check_name="row_count_nonnegative",
        validation_check_description="Count is valid.",
        validation_category_code="technical.count",
        validation_severity="blocking",
        validation_query_sql="SELECT count(*) FROM catalog.gold.dim_customer",
        validation_comparison_query_sql=None,
        validation_result_data_type="integer",
        validation_comparison_operator="greater_than_or_equal",
        validation_comparison_value_type="literal",
        validation_comparison_value=0,
        is_active=active,
    )


def _context(
    *,
    groups: tuple[ValidationGroupRecord, ...] = (),
    checks: tuple[ValidationCheckRecord, ...] = (),
) -> QASystemAuthoringContext:
    return QASystemAuthoringContext(
        system_ref="system_1",
        tenant_code="acme",
        system_code="erp",
        mapping_context_digest="a" * 64,
        code_context_digest="b" * 64,
        applied_groups=groups,
        applied_checks=checks,
        agent_context={"scope": {"system_code": "erp"}},
    )


def _candidate(*, query: str | None = None) -> JsonValue:
    return cast(
        JsonValue,
        {
            "system_ref": "system_1",
            "validation_groups": [
                {
                    "validation_group_name": "reconciliation",
                    "validation_group_description": "Counts reconcile.",
                    "validation_checks": [
                        {
                            "validation_check_name": "row_count_nonnegative",
                            "validation_check_description": "Count is valid.",
                            "validation_category_code": "technical.count",
                            "validation_severity": "blocking",
                            "validation_query_sql": query
                            or "SELECT count(*) FROM catalog.gold.dim_customer",
                            "validation_comparison_query_sql": None,
                            "validation_result_data_type": "integer",
                            "validation_comparison_operator": "greater_than_or_equal",
                            "validation_comparison_value_type": "literal",
                            "validation_comparison_value": 0,
                        }
                    ],
                }
            ],
        },
    )


def test_candidate_schema_publishes_the_scalar_runtime_contract() -> None:
    schema = QASystemCandidateValidator(context=_context()).output_schema()
    definitions = cast(dict[str, Any], schema["$defs"])
    check = cast(dict[str, Any], definitions["_AgentValidationCheck"])
    properties = cast(dict[str, dict[str, Any]], check["properties"])

    query_a_description = cast(str, properties["validation_query_sql"]["description"])
    assert "exactly one row and one column" in query_a_description
    assert "query-contract execution error, not an assertion failure" in (query_a_description)
    assert "catalog.schema.table" in query_a_description
    assert "unqualified temporary" in query_a_description
    query_b_description = cast(
        str,
        properties["validation_comparison_query_sql"]["description"],
    )
    assert "exactly one row and one column" in query_b_description
    assert "catalog.schema.table" in query_b_description
    result_description = cast(
        str,
        properties["validation_result_data_type"]["description"],
    )
    assert "single Query A cell" in result_description
    assert "result shape is ignored" in result_description


@pytest.mark.asyncio
async def test_candidate_builds_typed_group_and_static_value_check() -> None:
    validator = QASystemCandidateValidator(context=_context())

    validation = await validator.validate(_candidate())
    parsed = validator.parse_validated(_candidate())

    assert validation.issues == ()
    assert parsed.groups == (_group(),)
    assert parsed.checks == (_check(),)


@pytest.mark.asyncio
async def test_candidate_supports_execute_successfully_and_query_comparison() -> None:
    validator = QASystemCandidateValidator(context=_context())
    candidate = cast(
        JsonValue,
        {
            "system_ref": "system_1",
            "validation_groups": [
                {
                    "validation_group_name": "technical",
                    "validation_group_description": None,
                    "validation_checks": [
                        {
                            "validation_check_name": "query_executes",
                            "validation_check_description": None,
                            "validation_category_code": "technical.execution",
                            "validation_severity": "blocking",
                            "validation_query_sql": (
                                "CREATE TEMP VIEW qa_customer AS "
                                "SELECT * FROM catalog.gold.dim_customer"
                            ),
                            "validation_comparison_query_sql": None,
                            "validation_result_data_type": None,
                            "validation_comparison_operator": "executes_successfully",
                            "validation_comparison_value_type": "none",
                            "validation_comparison_value": None,
                        },
                        {
                            "validation_check_name": "counts_match",
                            "validation_check_description": None,
                            "validation_category_code": "business.reconciliation",
                            "validation_severity": "warning",
                            "validation_query_sql": (
                                "SELECT count(*) FROM catalog.silver.customer"
                            ),
                            "validation_comparison_query_sql": (
                                "SELECT count(*) FROM catalog.gold.dim_customer"
                            ),
                            "validation_result_data_type": "integer",
                            "validation_comparison_operator": "equal",
                            "validation_comparison_value_type": "query",
                            "validation_comparison_value": None,
                        },
                    ],
                }
            ],
        },
    )

    validation = await validator.validate(candidate)

    assert validation.issues == ()
    assert len(validator.parse_validated(candidate).checks) == 2


@pytest.mark.asyncio
async def test_candidate_reports_assertion_contract_failure_at_the_check() -> None:
    candidate = cast(dict[str, object], _candidate())
    groups = cast(list[dict[str, object]], candidate["validation_groups"])
    checks = cast(list[dict[str, object]], groups[0]["validation_checks"])
    checks[0]["validation_comparison_value_type"] = "none"
    checks[0]["validation_comparison_value"] = None

    issues = (
        await QASystemCandidateValidator(context=_context()).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert len(issues) == 1
    assert issues[0].code == "candidate.validation_contract_invalid"
    assert issues[0].path == ("validation_groups", 0, "validation_checks", 0)


@pytest.mark.asyncio
async def test_candidate_rejects_unsafe_or_non_row_comparison_sql() -> None:
    validator = QASystemCandidateValidator(context=_context())

    unsafe = await validator.validate(_candidate(query="DELETE FROM catalog.gold.dim_customer"))
    unqualified = await validator.validate(_candidate(query="SELECT count(*) FROM dim_customer"))
    non_row = await validator.validate(
        _candidate(
            query=("CREATE TEMP VIEW qa_customer AS SELECT * FROM catalog.gold.dim_customer")
        )
    )

    assert unsafe.issues[0].code == "candidate.validation_query_invalid"
    assert "catalog.schema.table" in unsafe.issues[0].message
    assert "unqualified temporary" in unsafe.issues[0].message
    assert unqualified.issues[0].code == "candidate.validation_query_invalid"
    assert unqualified.issues[0].path[-1] == "validation_query_sql"
    assert non_row.issues[0].code == "candidate.validation_query_result_invalid"


def test_reconciliation_returns_no_op_for_identical_applied_state() -> None:
    system = _context(groups=(_group(),), checks=(_check(),))
    candidate = QASystemCandidateValidator(context=system).parse_validated(_candidate())

    changes = reconcile_qa_candidates(
        context=QAExecutionContext(systems=(system,)),
        candidates=(candidate,),
    )

    assert changes == ()


@pytest.mark.asyncio
async def test_candidate_rejects_empty_group_list() -> None:
    validation = await QASystemCandidateValidator(context=_context()).validate(
        cast(JsonValue, {"system_ref": "system_1", "validation_groups": []})
    )

    assert validation.issues[0].code == "candidate.schema_bound"
    assert validation.issues[0].path == ("validation_groups",)


def test_reconciliation_uses_inactive_tombstones_for_omitted_applied_qa() -> None:
    legacy_group = _group().model_copy(update={"validation_group_name": "legacy_reconciliation"})
    legacy_check = _check().model_copy(update={"validation_group_name": "legacy_reconciliation"})
    system = _context(groups=(legacy_group,), checks=(legacy_check,))
    candidate = QASystemCandidateValidator(context=system).parse_validated(_candidate())

    changes = reconcile_qa_candidates(
        context=QAExecutionContext(systems=(system,)),
        candidates=(candidate,),
    )

    assert [change.dataset for change in changes] == [
        "validation_group",
        "validation_check",
    ]
    assert any(record["is_active"] is False for record in changes[0].records)
    assert any(record["is_active"] is False for record in changes[1].records)
