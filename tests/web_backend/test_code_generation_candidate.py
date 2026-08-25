from __future__ import annotations

from typing import cast

import pytest
from pydantic import JsonValue

from gds_workbench_api.features.code_generation.candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
)


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


def test_output_schema_is_bounded_and_does_not_expose_database_ids() -> None:
    schema = _validator().output_schema()
    serialized = str(schema)

    assert "target_ref" in serialized
    assert "generated_sql" in serialized
    assert "object_id" not in serialized
    assert "source_system_id" not in serialized
