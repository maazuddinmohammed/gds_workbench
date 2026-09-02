from __future__ import annotations

from typing import cast

import pytest
from pydantic import JsonValue

from gds_workbench_api.features.code_generation.candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
)
from gds_workbench_api.features.code_generation.contracts import SqlArtifactDownload
from gds_workbench_api.features.code_generation.contracts import (
    CodeGenerationTargetObjectReference,
)


def _artifact(
    target_ref: str,
    generated_sql: str,
    *,
    systems: list[str],
) -> dict[str, object]:
    return {
        "target_ref": target_ref,
        "artifact_name": f"{target_ref}.sql",
        "artifact_role": "target_transformation",
        "source_system_codes": systems,
        "generated_sql": generated_sql,
    }


def _validator() -> CodeGenerationCandidateValidator:
    return CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_1",
                object_id=501,
                source_system_codes=("CRM", "ERP"),
            ),
            CodeGenerationTargetReference(
                target_ref="target_2",
                object_id=502,
                source_system_codes=("MDM",),
            ),
        )
    )


@pytest.mark.asyncio
async def test_candidate_requires_exact_target_coverage_and_sql_only() -> None:
    validator = _validator()
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                _artifact("target_1", "SELECT 1;\n", systems=["CRM", "ERP"]),
                _artifact("target_2", "SELECT 2;\n", systems=["MDM"]),
            ]
        },
    )

    result = await validator.validate(candidate)
    parsed = validator.parse_validated(candidate)

    assert result.issues == ()
    assert [artifact.object_id for artifact in parsed] == [501, 502]
    assert "SELECT" not in repr(parsed)


@pytest.mark.asyncio
async def test_candidate_schema_failure_reports_the_exact_artifact_field() -> None:
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                {
                    "target_ref": "target_1",
                    "artifact_name": "target_1.sql",
                    "artifact_role": "target_transformation",
                    "source_system_codes": ["CRM", "ERP"],
                },
                _artifact("target_2", "SELECT 2;", systems=["MDM"]),
            ]
        },
    )

    issues = (await _validator().validate(candidate)).issues

    assert len(issues) == 1
    assert issues[0].code == "candidate.schema_required"
    assert issues[0].path == ("artifacts", 0, "generated_sql")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        (
            {"artifacts": [_artifact("target_1", "SELECT 1;", systems=["CRM", "ERP"])]},
            "candidate.target_coverage",
        ),
        (
            {
                "artifacts": [
                    _artifact("target_1", "SELECT 1;", systems=["CRM", "ERP"]),
                    _artifact("target_1", "SELECT 2;", systems=["CRM", "ERP"]),
                    _artifact("target_2", "SELECT 3;", systems=["MDM"]),
                ]
            },
            "candidate.artifact_name_duplicate",
        ),
        (
            {
                "artifacts": [
                    _artifact(
                        "target_1",
                        "```sql\nSELECT 1;\n```",
                        systems=["CRM", "ERP"],
                    ),
                    _artifact("target_2", "SELECT 2;", systems=["MDM"]),
                ]
            },
            "candidate.sql_invalid",
        ),
        (
            {
                "artifacts": [
                    _artifact(
                        "target_1",
                        "Generate a customer table from the mapping.",
                        systems=["CRM", "ERP"],
                    ),
                    _artifact("target_2", "SELECT 2;", systems=["MDM"]),
                ]
            },
            "candidate.sql_invalid",
        ),
        (
            {
                "artifacts": [
                    _artifact(
                        "target_1",
                        "def build_customer():\n    return 1",
                        systems=["CRM", "ERP"],
                    ),
                    _artifact("target_2", "SELECT 2;", systems=["MDM"]),
                ]
            },
            "candidate.sql_invalid",
        ),
        (
            {
                "artifacts": [
                    _artifact("target_1", "SELECT '\x00';", systems=["CRM", "ERP"]),
                    _artifact("target_2", "SELECT 2;", systems=["MDM"]),
                ]
            },
            "candidate.sql_invalid",
        ),
    ],
)
async def test_candidate_returns_bounded_repair_issues(
    candidate: object,
    code: str,
) -> None:
    result = await _validator().validate(cast(JsonValue, candidate))

    assert result.issues
    assert result.issues[0].code == code
    assert "SELECT" not in repr(result)


@pytest.mark.asyncio
async def test_candidate_accepts_an_artifact_over_400_kib() -> None:
    large_sql = "SELECT '" + ("x" * (400 * 1024)) + "';"
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                _artifact("target_1", large_sql, systems=["CRM", "ERP"]),
                _artifact("target_2", "SELECT 2;", systems=["MDM"]),
            ]
        },
    )

    result = await _validator().validate(candidate)

    assert result.issues == ()


def test_individual_download_contract_has_no_artifact_specific_size_cap() -> None:
    large_sql = "x" * (4 * 1024 * 1024 + 1)

    artifact = SqlArtifactDownload(
        generated_sql_artifact_id=1,
        artifact_name="customer.sql",
        target=CodeGenerationTargetObjectReference(
            object_id=1,
            source_tenant_id=2,
            source_tenant_code="tenant",
            source_tenant_name="Tenant",
            tenant_id=2,
            tenant_code="tenant",
            tenant_name="Tenant",
            system_id=3,
            system_code="system",
            system_name="System",
            connection_id=4,
            connection_code="connection",
            object_schema="schema",
            object_name="object",
            zone_code="silver",
        ),
        entity_type="logical_entity",
        generated_sql=large_sql,
        generated_sql_byte_count=len(large_sql.encode()),
    )

    assert artifact.generated_sql_byte_count > 4 * 1024 * 1024


def test_output_schema_is_bounded_and_does_not_expose_database_ids() -> None:
    schema = _validator().output_schema()
    serialized = str(schema)

    assert "target_ref" in serialized
    assert "generated_sql" in serialized
    assert "object_id" not in serialized
    assert "source_system_id" not in serialized
    definitions = cast(dict[str, object], schema["$defs"])
    artifact_schema = cast(dict[str, object], definitions["_AgentSqlArtifact"])
    properties = cast(dict[str, dict[str, object]], artifact_schema["properties"])
    assert "exact opaque" in cast(str, properties["target_ref"]["description"])
    assert "semicolon" in cast(str, properties["generated_sql"]["description"])
