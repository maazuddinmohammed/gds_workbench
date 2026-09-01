from __future__ import annotations

from typing import cast

import pytest
from pydantic import JsonValue

from gds_workbench_api.features.code_generation.candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
)
from gds_workbench_api.features.code_generation.contracts import SqlArtifactDownload
from gds_workbench_api.features.mapping.read_contracts import PhysicalObjectReference


def _validator() -> CodeGenerationCandidateValidator:
    return CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_1",
                object_id=501,
            ),
            CodeGenerationTargetReference(
                target_ref="target_2",
                object_id=502,
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
                {"target_ref": "target_1", "generated_sql": "SELECT 1;\n"},
                {"target_ref": "target_2", "generated_sql": "SELECT 2;\n"},
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
                {"target_ref": "target_1"},
                {"target_ref": "target_2", "generated_sql": "SELECT 2;"},
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
            {"artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 1;"}]},
            "candidate.target_coverage",
        ),
        (
            {
                "artifacts": [
                    {"target_ref": "target_1", "generated_sql": "SELECT 1;"},
                    {"target_ref": "target_1", "generated_sql": "SELECT 2;"},
                ]
            },
            "candidate.target_ref_duplicate",
        ),
        (
            {
                "artifacts": [
                    {
                        "target_ref": "target_1",
                        "generated_sql": "```sql\nSELECT 1;\n```",
                    },
                    {"target_ref": "target_2", "generated_sql": "SELECT 2;"},
                ]
            },
            "candidate.sql_invalid",
        ),
        (
            {
                "artifacts": [
                    {
                        "target_ref": "target_1",
                        "generated_sql": "Generate a customer table from the mapping.",
                    },
                    {"target_ref": "target_2", "generated_sql": "SELECT 2;"},
                ]
            },
            "candidate.sql_invalid",
        ),
        (
            {
                "artifacts": [
                    {
                        "target_ref": "target_1",
                        "generated_sql": "def build_customer():\n    return 1",
                    },
                    {"target_ref": "target_2", "generated_sql": "SELECT 2;"},
                ]
            },
            "candidate.sql_invalid",
        ),
        (
            {
                "artifacts": [
                    {"target_ref": "target_1", "generated_sql": "SELECT '\x00';"},
                    {"target_ref": "target_2", "generated_sql": "SELECT 2;"},
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
                {"target_ref": "target_1", "generated_sql": large_sql},
                {"target_ref": "target_2", "generated_sql": "SELECT 2;"},
            ]
        },
    )

    result = await _validator().validate(candidate)

    assert result.issues == ()


def test_individual_download_contract_has_no_artifact_specific_size_cap() -> None:
    large_sql = "x" * (4 * 1024 * 1024 + 1)

    artifact = SqlArtifactDownload(
        generated_sql_artifact_id=1,
        target=PhysicalObjectReference(
            object_id=1,
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
        generated_sql_digest="a" * 64,
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
