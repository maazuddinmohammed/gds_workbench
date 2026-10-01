from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import pytest
from gds_workbench_api.features.analysis import workbook as analysis_workbook
from gds_workbench_api.features.analysis.read_contracts import (
    AnalysisEndpoint,
    AnalysisFindingSummary,
)
from gds_workbench_api.features.analysis.workbook import (
    AnalysisWorkbookBuildError,
    build_analysis_workbook,
)
from openpyxl import load_workbook


@pytest.fixture
def finding() -> AnalysisFindingSummary:
    endpoint = AnalysisEndpoint(
        object_id=1,
        attribute_id=2,
        source_tenant_id=3,
        source_tenant_code="DEMO",
        source_tenant_name="Demo Tenant",
        system_id=4,
        system_code="CRM",
        system_name="CRM",
        connection_id=5,
        connection_code="BRONZE",
        object_schema="bronze_crm",
        object_name="Order",
        attribute_name="CustomerId",
        attribute_data_type="int",
    )
    return AnalysisFindingSummary(
        analysis_result_id=7,
        from_endpoint=endpoint,
        to_endpoint=endpoint.model_copy(
            update={"object_id": 8, "attribute_id": 9, "object_name": "Customer"}
        ),
        relationship_kind="reference",
        relationship_confidence="high",
        validation_state="validated",
        validation_result="supported",
        inferred_cardinality="many_to_one",
        observed_cardinality="one_to_one",
        cardinality_mismatch=True,
        from_row_count=1000,
        to_row_count=2000,
        source_missing_target_count=3,
        unused_target_count=0,
        source_missing_target_percent=25,
        unused_target_percent=0,
        status="active",
        is_locked=False,
        updated_at=datetime(2026, 9, 30, tzinfo=UTC),
    )


def test_analysis_export_is_one_flat_sheet_with_the_visible_table_columns(
    finding: AnalysisFindingSummary,
) -> None:
    workbook = load_workbook(BytesIO(build_analysis_workbook(findings=(finding,))))
    try:
        assert workbook.sheetnames == ["Analysis"]
        sheet = workbook["Analysis"]
        assert list(sheet.values) == [
            (
                "FromObjectSchema",
                "FromObjectName",
                "FromAttributeName",
                "ToObjectSchema",
                "ToObjectName",
                "ToAttributeName",
                "Relationship",
                "InferredCardinality",
                "ObservedCardinality",
                "Confidence",
                "FromRowCount",
                "ToRowCount",
                "SourceMissingTargetCount",
                "UnusedTargetCount",
                "SourceMissingTargetPercent",
                "UnusedTargetPercent",
                "Status",
                "IsLocked",
            ),
            (
                "bronze_crm",
                "Order",
                "CustomerId",
                "bronze_crm",
                "Customer",
                "CustomerId",
                "Reference",
                "Many to one",
                "One to one\nDiffers from inference",
                "high",
                1000,
                2000,
                3,
                0,
                0.25,
                0,
                "Active",
                False,
            ),
        ]
        assert sheet["O2"].number_format == "0.00%"
        assert sheet["P2"].number_format == "0.00%"
        assert sheet["P2"].data_type == "n"
        assert sheet["R2"].data_type == "b"
    finally:
        workbook.close()


def test_missing_validation_is_distinct_from_measured_zero_and_empty_population(
    finding: AnalysisFindingSummary,
) -> None:
    empty = finding.model_copy(
        update={
            "observed_cardinality": None,
            "cardinality_mismatch": False,
            "from_row_count": None,
            "to_row_count": 0,
            "source_missing_target_count": 0,
            "unused_target_count": None,
            "source_missing_target_percent": None,
            "unused_target_percent": None,
        }
    )
    unvalidated = empty.model_copy(
        update={
            "validation_state": "unvalidated",
            "validation_result": None,
            "source_missing_target_count": None,
        }
    )
    workbook = load_workbook(BytesIO(build_analysis_workbook(findings=(empty, unvalidated))))
    try:
        sheet = workbook["Analysis"]
        assert sheet["I2"].value == "Unavailable"
        assert tuple(cell.value for cell in sheet[2][10:16]) == (
            "Not profiled",
            0,
            0,
            "Unavailable",
            "N/A",
            "Unavailable",
        )
        assert sheet["I3"].value == "Not validated"
        assert tuple(cell.value for cell in sheet[3][12:16]) == ("Not validated",) * 4
    finally:
        workbook.close()


def test_large_saved_counts_survive_excel_without_numeric_rounding(
    finding: AnalysisFindingSummary,
) -> None:
    count = 9_223_372_036_854_775_807
    finding = finding.model_copy(update={"from_row_count": count})
    workbook = load_workbook(BytesIO(build_analysis_workbook(findings=(finding,))))
    try:
        cell = workbook["Analysis"]["K2"]
        assert cell.value == str(count)
        assert cell.data_type == "s"
    finally:
        workbook.close()


@pytest.mark.parametrize("literal", ["=1+1", '=HYPERLINK("https://example.test")', "#N/A"])
def test_source_names_remain_literal_text_without_excel_formulas_or_external_links(
    finding: AnalysisFindingSummary,
    literal: str,
) -> None:
    finding = finding.model_copy(
        update={
            "from_endpoint": finding.from_endpoint.model_copy(update={"object_name": literal}),
        }
    )
    content = build_analysis_workbook(findings=(finding,))
    workbook = load_workbook(BytesIO(content), data_only=False)
    try:
        assert workbook["Analysis"]["B2"].value == literal
        assert workbook["Analysis"]["B2"].data_type == "s"
    finally:
        workbook.close()
    with ZipFile(BytesIO(content)) as package:
        assert not any("externallinks" in name.lower() for name in package.namelist())
        for name in package.namelist():
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                assert b"<f" not in package.read(name)
            if name.endswith(".rels"):
                assert b'TargetMode="External"' not in package.read(name)


@pytest.mark.parametrize("text", ["private\x00text", "private\ufffftext", "x" * 32_768])
def test_invalid_or_oversized_text_fails_without_truncation_or_echoing_content(
    finding: AnalysisFindingSummary,
    text: str,
) -> None:
    finding = finding.model_copy(
        update={
            "from_endpoint": finding.from_endpoint.model_copy(update={"object_name": text}),
        }
    )
    with pytest.raises(AnalysisWorkbookBuildError) as error:
        build_analysis_workbook(findings=(finding,))
    assert text not in str(error.value)


def test_no_findings_produces_the_header_only_without_a_fake_record() -> None:
    workbook = load_workbook(BytesIO(build_analysis_workbook(findings=())))
    try:
        assert workbook.sheetnames == ["Analysis"]
        assert workbook["Analysis"].max_row == 1
        assert workbook["Analysis"].max_column == 18
    finally:
        workbook.close()


@pytest.mark.parametrize(
    "limit",
    [
        "MAX_ANALYSIS_FINDINGS",
        "MAX_ANALYSIS_CELL_CHARACTERS",
        "MAX_ANALYSIS_TEXT_CHARACTERS",
        "MAX_ANALYSIS_XLSX_BYTES",
        "MAX_ANALYSIS_UNCOMPRESSED_BYTES",
    ],
)
def test_export_limits_fail_instead_of_returning_a_partial_workbook(
    finding: AnalysisFindingSummary,
    monkeypatch: pytest.MonkeyPatch,
    limit: str,
) -> None:
    monkeypatch.setattr(analysis_workbook, limit, 0)
    with pytest.raises(AnalysisWorkbookBuildError):
        build_analysis_workbook(findings=(finding,))
