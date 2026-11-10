from __future__ import annotations

from typing import Literal, cast

import pytest
from atlas_platform.features.code_generation.candidate import (
    CodeGenerationCandidateValidator,
    CodeGenerationTargetReference,
)
from atlas_platform.features.code_generation.contracts import (
    SqlArtifactDownload,
)
from atlas_platform.features.mapping import ModeledEntityReference
from pydantic import JsonValue


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
                modeled_entity_id=501,
                source_system_codes=("CRM", "ERP"),
            ),
            CodeGenerationTargetReference(
                target_ref="target_2",
                modeled_entity_id=502,
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
    assert [artifact.modeled_entity_id for artifact in parsed] == [501, 502]
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
        target=ModeledEntityReference(
            entity_type="logical_entity",
            entity_id=501,
            entity_schema_name="silver",
            entity_name="Customer",
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
    assert "modeled_entity_id" not in serialized
    assert "source_system_id" not in serialized
    definitions = cast(dict[str, object], schema["$defs"])
    artifact_schema = cast(dict[str, object], definitions["_AgentSqlArtifact"])
    properties = cast(dict[str, dict[str, object]], artifact_schema["properties"])
    assert "exact opaque" in cast(str, properties["target_ref"]["description"])
    assert "semicolon" in cast(str, properties["generated_sql"]["description"])


@pytest.mark.asyncio
async def test_each_entity_requires_only_its_mapped_systems_including_default() -> None:
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="customer",
                modeled_entity_id=501,
                source_system_codes=("CRM",),
                file_layout="per_system",
            ),
            CodeGenerationTargetReference(
                target_ref="orders",
                modeled_entity_id=502,
                source_system_codes=("ERP", "WEB"),
                file_layout="per_system",
            ),
            CodeGenerationTargetReference(
                target_ref="calendar",
                modeled_entity_id=503,
                source_system_codes=("DEFAULT",),
                file_layout="per_system",
            ),
        ),
    )
    artifacts = [
        _artifact("customer", "SELECT 1 AS CustomerID", systems=["CRM"]),
        _artifact("orders", "SELECT 1 AS OrderID", systems=["ERP"]),
        _artifact("orders", "SELECT 1 AS OrderID", systems=["WEB"])
        | {"artifact_name": "orders_web.sql"},
        _artifact("calendar", "SELECT 1 AS DayID", systems=["DEFAULT"]),
    ]
    assert (
        await validator.validate(cast(JsonValue, {"artifacts": artifacts}))
    ).issues == ()
    missing_system = artifacts[:2] + artifacts[3:]
    result = await validator.validate(cast(JsonValue, {"artifacts": missing_system}))
    assert result.issues[0].code == "candidate.source_system_coverage"
    missing_entity = artifacts[:3]
    result = await validator.validate(cast(JsonValue, {"artifacts": missing_entity}))
    assert result.issues[0].code == "candidate.target_coverage"


@pytest.mark.asyncio
@pytest.mark.parametrize("layout", ("combined", "per_system"))
async def test_selected_file_layout_is_enforced_and_preserved_names_cannot_be_reused(
    layout: Literal["combined", "per_system"],
) -> None:
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_1",
                modeled_entity_id=501,
                source_system_codes=("CRM", "ERP"),
                file_layout=layout,
                preserved_artifact_names=("preserved.sql",),
            ),
        )
    )
    combined = _artifact("target_1", "SELECT 1", systems=["CRM", "ERP"])
    separate = [
        dict(
            _artifact("target_1", "SELECT 1", systems=[code]),
            artifact_name=f"{code}.sql",
        )
        for code in ("CRM", "ERP")
    ]
    correct = [combined] if layout == "combined" else separate
    wrong = separate if layout == "combined" else [combined]
    assert not (
        await validator.validate(cast(JsonValue, {"artifacts": correct}))
    ).issues
    assert (await validator.validate(cast(JsonValue, {"artifacts": wrong}))).issues[
        0
    ].code == "candidate.file_layout"
    correct[0]["artifact_name"] = "PRESERVED.SQL"
    assert (await validator.validate(cast(JsonValue, {"artifacts": correct}))).issues[
        0
    ].code == "candidate.preserved_artifact"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "MERGE INTO silver.target USING bronze.source ON false WHEN NOT MATCHED THEN INSERT *",
        "CREATE TABLE silver.target AS SELECT 1",
        "SELECT * FROM bronze.source",
        "SELECT 1 -- explanation",
    ],
)
@pytest.mark.parametrize("layout", [None, "combined", "per_system"])
async def test_requested_transformation_layout_rejects_loading_sql_and_implicit_columns(
    sql: str,
    layout: Literal["combined", "per_system"] | None,
) -> None:
    validator = CodeGenerationCandidateValidator(
        targets=(
            CodeGenerationTargetReference(
                target_ref="target_1",
                modeled_entity_id=501,
                source_system_codes=("CRM",),
                file_layout=layout,
            ),
        )
    )
    result = await validator.validate(
        cast(JsonValue, {"artifacts": [_artifact("target_1", sql, systems=["CRM"])]})
    )
    assert result.issues[0].code == "candidate.transformation_sql_contract"
    valid = (
        "CREATE OR REPLACE TEMPORARY VIEW temp_customer AS SELECT 1 AS id; "
        "SELECT id FROM temp_customer"
    )
    assert not (
        await validator.validate(
            cast(
                JsonValue,
                {"artifacts": [_artifact("target_1", valid, systems=["CRM"])]},
            )
        )
    ).issues


@pytest.mark.parametrize(
    "code", ["missing_requirement_evidence", "conflicting_requirement"]
)
async def test_requirement_failure_returns_safe_diagnostic_and_cannot_be_applied(
    code: str,
) -> None:
    from atlas_mcp.domain.errors import InvalidRequestError

    candidate = cast(JsonValue, {"artifacts": [], "issues": [code]})
    validator = _validator()
    result = await validator.validate(candidate)
    assert result.issues[0].code == f"code_generation.{code}"
    assert "Resolve the requirement" in result.issues[0].message
    with pytest.raises(InvalidRequestError):
        validator.parse_validated(candidate)


@pytest.mark.parametrize("reported_missing", [False, True])
async def test_missing_evidence_keeps_covered_typed_null_sql_for_review(
    reported_missing: bool,
) -> None:
    candidate = cast(
        JsonValue,
        {
            "issues": ["missing_requirement_evidence"] if reported_missing else [],
            "artifacts": [
                _artifact(
                    "target_1",
                    "SELECT CAST(NULL AS STRING) AS name WHERE FALSE",
                    systems=["CRM", "ERP"],
                ),
                _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
            ],
        },
    )
    validator = _validator()

    assert not (await validator.validate(candidate)).issues
    assert len(validator.parse_validated(candidate)) == 2
    assert "code_generation.typed_null_placeholder" in validator.warning_codes(
        candidate
    )
    assert (
        "code_generation.missing_requirement_evidence"
        in validator.warning_codes(candidate)
    ) == reported_missing

    assert isinstance(candidate, dict) and isinstance(candidate["artifacts"], list)
    candidate["artifacts"].pop()
    assert (await validator.validate(candidate)).issues[
        0
    ].code == "candidate.target_coverage"


async def test_conflicting_requirements_still_reject_otherwise_covered_sql() -> None:
    candidate = cast(
        JsonValue,
        {
            "issues": ["missing_requirement_evidence", "conflicting_requirement"],
            "artifacts": [
                _artifact(
                    "target_1",
                    "SELECT CAST(NULL AS STRING) AS name",
                    systems=["CRM", "ERP"],
                ),
                _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
            ],
        },
    )
    result = await _validator().validate(candidate)
    assert [issue.code for issue in result.issues] == [
        "code_generation.conflicting_requirement"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE silver.persisted AS SELECT 1 AS id",
        "INSERT INTO silver.persisted SELECT 1 AS id",
        "DELETE FROM silver.persisted",
        "MERGE INTO silver.persisted USING bronze.source ON false WHEN NOT MATCHED THEN INSERT *",
        "USE CATALOG private_catalog",
    ],
)
async def test_support_artifacts_cannot_bypass_sql_write_restrictions(sql: str) -> None:
    from atlas_mcp.domain.errors import InvalidRequestError

    validator = _validator()
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                _artifact("target_1", "SELECT 1 AS id", systems=["CRM", "ERP"]),
                _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
                {
                    **_artifact("target_1", sql, systems=[]),
                    "artifact_name": "helper.sql",
                    "artifact_role": "support",
                },
            ]
        },
    )
    assert (await validator.validate(candidate)).issues[
        0
    ].code == "candidate.support_sql_contract"
    with pytest.raises(InvalidRequestError, match="artifact delivery contract"):
        validator.parse_validated(candidate)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    [
        "CREATE OR REPLACE TEMPORARY VIEW helper AS SELECT 1 AS id",
        "SELECT 1 AS id",
        "CREATE OR REPLACE TEMPORARY VIEW helper AS SELECT 1 AS id; SELECT id FROM helper",
    ],
)
async def test_support_artifacts_accept_standalone_safe_sql(sql: str) -> None:
    validator = _validator()
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                _artifact("target_1", "SELECT 1 AS id", systems=["CRM", "ERP"]),
                _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
                {
                    **_artifact("target_1", sql, systems=[]),
                    "artifact_name": "helper.sql",
                    "artifact_role": "support",
                },
            ]
        },
    )
    assert not (await validator.validate(candidate)).issues
    assert len(validator.parse_validated(candidate)) == 3


@pytest.mark.parametrize("role", ("target_transformation", "support"))
@pytest.mark.parametrize(
    "sql",
    (
        "SELECT c.CustomerID FROM lake.silver.Customer AS c",
        "SELECT c.CustomerID FROM `lake`.`silver`.`Customer` AS c",
        "WITH customers AS (SELECT c.CustomerID FROM lake.silver.Customer AS c) "
        "SELECT CustomerID FROM customers",
        "SELECT CustomerID FROM "
        "(SELECT c.CustomerID FROM lake.silver.Customer AS c) AS customers",
        "CREATE OR REPLACE TEMPORARY VIEW customers AS "
        "SELECT c.CustomerID FROM lake.silver.Customer AS c; "
        "SELECT CustomerID FROM customers",
        "SELECT c.CustomerID FROM silver.Customer AS c UNION ALL "
        "SELECT c.CustomerID FROM lake.silver.Customer AS c",
        "SELECT lake.silver.Customer.CustomerID FROM silver.Customer",
    ),
    ids=(
        "root", "quoted", "cte", "subquery", "temporary_view", "union_branch",
        "qualified_column",
    ),
)
async def test_generation_rejects_catalog_sources_in_every_query_scope(
    role: str, sql: str
) -> None:
    from atlas_mcp.domain.errors import InvalidRequestError

    artifacts = [
        _artifact("target_1", "SELECT 1 AS id", systems=["CRM", "ERP"]),
        _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
    ]
    if role == "support":
        artifacts.append(
            {
                **_artifact("target_1", sql, systems=[]),
                "artifact_name": "helper.sql",
                "artifact_role": "support",
            }
        )
    else:
        artifacts[0]["generated_sql"] = sql
    validator = _validator()
    candidate = cast(JsonValue, {"artifacts": artifacts})

    result = await validator.validate(candidate)

    expected = (
        "candidate.support_sql_contract"
        if role == "support"
        else "candidate.transformation_sql_contract"
    )
    assert [issue.code for issue in result.issues] == [expected]
    with pytest.raises(InvalidRequestError, match="artifact delivery contract"):
        validator.parse_validated(candidate)


@pytest.mark.parametrize(
    "sql",
    (
        "SELECT c.CustomerID FROM `silver`.`Customer` AS c",
        "WITH customers AS (SELECT c.CustomerID FROM silver.Customer AS c) "
        "SELECT CustomerID FROM customers",
        "CREATE OR REPLACE TEMPORARY VIEW orders AS "
        "SELECT o.OrderID FROM bronze.orders AS o "
        "WHERE o.GDSBatchID = 'wid_gdsbatchid'; SELECT OrderID FROM orders",
        "SELECT o.payload.customer.name AS CustomerName FROM bronze.orders AS o",
        "SELECT payload.customer.name.first AS FirstName FROM bronze.orders",
    ),
    ids=(
        "quoted_schema", "cte", "temporary_view_with_batch_replacement",
        "qualified_struct", "unqualified_struct",
    ),
)
async def test_generation_accepts_runtime_catalog_and_batch_convention(sql: str) -> None:
    validator = _validator()
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                _artifact("target_1", sql, systems=["CRM", "ERP"]),
                _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
            ]
        },
    )

    assert not (await validator.validate(candidate)).issues
    assert len(validator.parse_validated(candidate)) == 2


@pytest.mark.parametrize("role", ("target_transformation", "support"))
@pytest.mark.parametrize("parameter", (":batch_id", "?", "$batch_id", "${batch_id}", "@batch_id"))
async def test_generation_rejects_unbound_sql_parameters(role: str, parameter: str) -> None:
    from atlas_mcp.domain.errors import InvalidRequestError

    sql = (
        "CREATE OR REPLACE TEMPORARY VIEW orders AS "
        "SELECT o.OrderID FROM bronze.orders AS o "
        f"WHERE o.GDSBatchID = {parameter}; SELECT OrderID FROM orders"
    )
    artifacts = [
        _artifact("target_1", "SELECT 1 AS id", systems=["CRM", "ERP"]),
        _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
    ]
    if role == "support":
        artifacts.append(
            {
                **_artifact("target_1", sql, systems=[]),
                "artifact_name": "helper.sql",
                "artifact_role": "support",
            }
        )
    else:
        artifacts[0]["generated_sql"] = sql
    candidate = cast(JsonValue, {"artifacts": artifacts})
    validator = _validator()

    result = await validator.validate(candidate)

    expected = (
        "candidate.support_sql_contract"
        if role == "support"
        else "candidate.transformation_sql_contract"
    )
    assert [issue.code for issue in result.issues] == [expected]
    with pytest.raises(InvalidRequestError, match="artifact delivery contract"):
        validator.parse_validated(candidate)


async def test_generation_preserves_parameter_like_strings_and_quoted_columns() -> None:
    candidate = cast(
        JsonValue,
        {
            "artifacts": [
                _artifact(
                    "target_1",
                    "SELECT ':batch_id ${label}' AS Description, o.`$value` AS Amount "
                    "FROM bronze.orders AS o WHERE o.GDSBatchID = 'wid_gdsbatchid'",
                    systems=["CRM", "ERP"],
                ),
                _artifact("target_2", "SELECT 2 AS id", systems=["MDM"]),
            ]
        },
    )
    assert not (await _validator().validate(candidate)).issues


@pytest.mark.parametrize(
    ("sql", "valid"),
    [
        ("SELECT CAST(11 AS BIGINT) AS SourceSystemID FROM bronze.orders "
         "WHERE load_batch='wid_gdsbatchid'", False),
        ("SELECT id FROM silver.parent WHERE SourceSystemID = '11'", False),
        ("SELECT id FROM silver.parent WHERE CAST(11 AS BIGINT) = SourceSystemID", False),
        ("SELECT id FROM silver.parent WHERE SourceSystemID IN (11, 12)", False),
        (
            "SELECT (SELECT SystemID"
            " FROM meta.system WHERE SystemCode = 'CRM') AS SourceSystemID",
            False,
        ),
        (
            "SELECT sys.SystemID"
            " FROM bronze.orders LEFT JOIN meta.system AS sys ON sys.SystemID = 11 "
            "WHERE orders.load_batch='wid_gdsbatchid'",
            False,
        ),
        (
            "SELECT sys.SystemID"
            " FROM bronze.orders LEFT JOIN meta.system AS sys ON sys.SystemCode = 'UNKNOWN' "
            "WHERE orders.load_batch='wid_gdsbatchid'",
            False,
        ),
        ("SELECT id FROM bronze.orders o WHERE o.load_batch = wid_GDSBatchID", False),
        ('SELECT id FROM bronze.orders o WHERE o.load_batch = "wid_gdsbatchid"', False),
        ("SELECT id FROM bronze.orders o WHERE o.load_batch = 'WID_GDSBatchID'", False),
        ("SELECT id FROM bronze.orders o WHERE o.id = 'wid_gdsbatchid'", False),
        ("SELECT id FROM silver.parent p WHERE p.GDSBatchID = 'wid_gdsbatchid'", False),
        ("SELECT o.id FROM bronze.orders o LEFT JOIN silver.parent p ON p.id = o.id "
         "WHERE o.load_batch = 'wid_gdsbatchid'", True),
        ("SELECT sys.SystemID AS SourceSystemID FROM bronze.orders "
         "LEFT JOIN meta.system sys ON sys.SystemCode='CRM' "
         "LEFT JOIN meta.system p ON p.SystemCode='DIRECTORY' "
         "LEFT JOIN silver.parent d ON d.SourceSystemID=p.SystemID AND d.id=11 "
         "WHERE orders.load_batch='wid_gdsbatchid'", True),
        ("SELECT s.SystemID AS SourceSystemID FROM bronze.orders o "
         "LEFT JOIN meta.system s ON (s.SystemCode = 'CRM') "
         "WHERE o.load_batch='wid_gdsbatchid'", True),
        ("SELECT COALESCE(s.SystemID, 11) AS SourceSystemID FROM bronze.orders o "
         "LEFT JOIN meta.system s ON s.SystemCode = 'CRM' "
         "WHERE o.load_batch='wid_gdsbatchid'", False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch = 'wid_gdsbatchid' - 1", False),
        ("WITH parents AS (SELECT p.id, p.SourceSystemID FROM silver.parent p) "
         "SELECT o.id FROM bronze.orders o JOIN parents p ON o.id = p.id "
         "WHERE o.load_batch='wid_gdsbatchid'", True),
        ("SELECT o.SourceSystemID AS SourceSystemID FROM silver.orders o", False),
        ("SELECT o.id FROM external.orders o WHERE o.external_batch='wid_gdsbatchid'", True),
        ("SELECT o.id FROM registered_fc.orders o WHERE o.AUDIT_BATCH='wid_gdsbatchid'", True),
    ],
)
async def test_runtime_id_and_registered_batch_conventions(sql: str, valid: bool) -> None:
    validator = CodeGenerationCandidateValidator(
        targets=(CodeGenerationTargetReference(
            target_ref="target_1", modeled_entity_id=1, source_system_codes=("CRM",),
            lookup_system_codes=("DIRECTORY",),
            batch_sources=(("bronze", "orders", "load_batch"), ("silver", "parent", None),
                           ("registered_fc", "orders", "AUDIT_BATCH")),
        ),)
    )
    candidate = cast(JsonValue, {"artifacts": [_artifact("target_1", sql, systems=["CRM"])]})
    assert (not (await validator.validate(candidate)).issues) == valid


@pytest.mark.parametrize(
    ("sql", "valid"),
    [
        ("SELECT o.id FROM bronze.orders o", False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' "
         "AND o.load_batch=42", False),
        ("WITH copied AS (SELECT id, load_batch AS slice FROM bronze.orders "
         "WHERE load_batch='wid_gdsbatchid') SELECT id FROM copied "
         "WHERE CAST('42' AS BIGINT)=slice", False),
        ("SELECT o.id FROM bronze.orders o LEFT JOIN silver.parent p "
         "ON p.id=o.id AND p.load_batch=42 WHERE o.load_batch='wid_gdsbatchid' "
         "AND o.status='POSTED' AND o.posted_on=DATE '2025-01-01'", True),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch = "
         "(SELECT MAX(x.load_batch) FROM bronze.orders x)", False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' "
         "AND o.load_batch=(SELECT MAX(x.load_batch) FROM bronze.orders x WHERE x.id=o.id)", False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' AND "
         "o.load_batch=(SELECT MAX(DISTINCT n.load_batch) FROM bronze.orders n WHERE n.id=o.id)",
         False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' AND "
         "o.load_batch=(SELECT MAX(COALESCE(n.load_batch,0)) FROM bronze.orders n WHERE n.id=o.id)",
         False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' AND "
         "o.amount=(SELECT MAX(COALESCE(n.amount,0)) FROM bronze.orders n WHERE n.id=o.id)", True),
        ("SELECT MAX(COALESCE(o.load_batch,0)) AS observed FROM bronze.orders o "
         "WHERE o.load_batch='wid_gdsbatchid'", True),
        ("WITH copied AS (SELECT id, load_batch AS slice FROM bronze.orders), "
         "latest AS (SELECT MAX(slice) AS newest FROM copied) "
         "SELECT c.id FROM copied c JOIN latest l ON c.slice=l.newest "
         "WHERE c.slice='wid_gdsbatchid'", False),
        ("SELECT id FROM bronze.orders WHERE load_batch='wid_gdsbatchid' AND load_batch="
         "(SELECT load_batch FROM bronze.orders ORDER BY load_batch DESC LIMIT 1)", False),
        ("WITH ranked AS (SELECT id, load_batch, ROW_NUMBER() OVER "
         "(PARTITION BY id ORDER BY load_batch DESC) AS rn FROM bronze.orders) "
         "SELECT id FROM ranked WHERE rn=1 AND load_batch='wid_gdsbatchid'", False),
        ("SELECT o.id FROM bronze.orders o LEFT JOIN silver.parent p "
         "ON p.id=o.id AND o.load_batch='wid_gdsbatchid'", False),
        ("SELECT o.id FROM bronze.orders o WHERE o.id=1 OR o.load_batch='wid_gdsbatchid'", False),
        ("WITH both AS (SELECT id, load_batch FROM bronze.orders WHERE load_batch='wid_gdsbatchid' "
         "UNION ALL SELECT id, line_batch FROM bronze.lines WHERE line_batch='wid_gdsbatchid') "
         "SELECT id FROM both WHERE id=42", True),
        ("WITH both(id,slice) AS (SELECT id,load_batch FROM bronze.orders UNION ALL "
         "SELECT id,line_batch FROM bronze.lines) SELECT b.id FROM both b "
         "WHERE b.slice='wid_gdsbatchid'", True),
        ("WITH both(id,slice) AS (SELECT id,load_batch FROM bronze.orders UNION ALL "
         "SELECT id,line_batch FROM bronze.lines) SELECT b.id FROM both b "
         "WHERE b.id='wid_gdsbatchid'", False),
        ("WITH unused AS (SELECT id FROM bronze.orders WHERE load_batch='wid_gdsbatchid') "
         "SELECT id FROM bronze.orders", False),
        ("SELECT id FROM bronze.orders WHERE load_batch='wid_gdsbatchid' "
         "UNION ALL SELECT id FROM bronze.orders", False),
        ("CREATE TEMP VIEW d AS SELECT id, load_batch AS slice FROM bronze.orders; "
         "SELECT id FROM d WHERE slice='wid_gdsbatchid'", True),
        ("WITH copied AS (SELECT id, load_batch AS slice FROM bronze.orders) "
         "SELECT c.id FROM copied c WHERE c.slice='wid_gdsbatchid'", True),
        ("WITH copied AS (SELECT id FROM bronze.orders WHERE load_batch='wid_gdsbatchid') "
         "SELECT id FROM copied", True),
        ("SELECT id FROM bronze.orders WHERE FALSE", True),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' "
         "AND o.amount=(SELECT MAX(o.amount) FROM bronze.orders o)", True),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' "
         "AND o.amount=(SELECT MAX(o.load_batch) FROM silver.parent o)", True),
        ("SELECT p.id FROM silver.parent p LEFT JOIN bronze.orders o ON p.id=o.id", True),
        ("WITH latest AS (SELECT MAX(load_batch) AS newest FROM bronze.orders) "
         "SELECT o.id FROM bronze.orders o LEFT SEMI JOIN latest l ON l.newest=o.load_batch "
         "WHERE o.load_batch='wid_gdsbatchid'", False),
        ("SELECT MAX(o.load_batch) AS batch_observed, MAX(o.amount) AS max_amount "
         "FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid'", True),
        ("WITH diagnostics AS (SELECT MAX(o.load_batch) AS most_recent FROM bronze.orders o) "
         "SELECT o.id, d.most_recent FROM bronze.orders o CROSS JOIN diagnostics d "
         "WHERE o.load_batch='wid_gdsbatchid'", True),
        ("SELECT o.id FROM bronze.orders o JOIN bronze.lines l "
         "ON l.id=o.id AND l.line_batch=o.load_batch WHERE o.load_batch='wid_gdsbatchid'", True),
        ("SELECT o.id FROM bronze.orders o JOIN bronze.lines l ON l.id=o.id "
         "WHERE l.line_batch='wid_gdsbatchid'", False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' "
         "QUALIFY DENSE_RANK() OVER (PARTITION BY id ORDER BY o.load_batch DESC)=1", False),
        ("SELECT o.id FROM bronze.orders o WHERE o.load_batch='wid_gdsbatchid' AND EXISTS "
         "(SELECT 1 WHERE o.load_batch=(SELECT MAX(o.load_batch)))", False),
    ],
)
async def test_orchestrator_batch_is_the_driving_rowset_selector(sql: str, valid: bool) -> None:
    from atlas_mcp.domain.errors import InvalidRequestError

    validator = CodeGenerationCandidateValidator(targets=(CodeGenerationTargetReference(
        target_ref="target_1", modeled_entity_id=1, source_system_codes=("CRM",),
        batch_sources=(("bronze", "orders", "load_batch"), ("bronze", "lines", "line_batch"),
                       ("silver", "parent", None)),
    ),))
    candidate = cast(JsonValue, {"artifacts": [_artifact("target_1", sql, systems=["CRM"])]})

    if valid:
        assert not (await validator.validate(candidate)).issues
        assert len(validator.parse_validated(candidate)) == 1
    else:
        assert (await validator.validate(candidate)).issues[0].code == (
            "candidate.transformation_sql_contract"
        )
        with pytest.raises(InvalidRequestError):
            validator.parse_validated(candidate)
