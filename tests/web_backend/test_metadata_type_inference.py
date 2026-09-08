from decimal import localcontext

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.metadata_enrichment.inference import (
    infer_sample_data_type,
    normalize_data_type,
)
from pydantic import JsonValue


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], None),
        ([None, "", " \t"], None),
        ([True, False, None], "BOOLEAN"),
        (["true", " FALSE "], "BOOLEAN"),
        ([0, 1], "BIGINT"),
        (["0", "1", None, ""], "BIGINT"),
        ([True, "1"], "STRING"),
        (["yes", "no"], "STRING"),
        (["001", "102"], "STRING"),
        (["-001", "2"], "STRING"),
        (["00.25", "1.25"], "STRING"),
        (["001e2", "10"], "STRING"),
        (["123", "invoice"], "STRING"),
        (["123", "2026-09-05"], "STRING"),
        (["NaN", "Infinity"], "STRING"),
        ([float("inf")], "STRING"),
        ([float("nan")], "STRING"),
        ([{"id": 1}], "STRING"),
        ([[1, 2]], "STRING"),
        (["2024-02-29", "2026-09-05"], "DATE"),
        (["2024-01-01T24:00:00"], "STRING"),
        (["2024-01-01T12:30:60"], "STRING"),
        (["2024-01-01T12:30:00+24:00"], "STRING"),
        (["2024-01-01T12:30:00+05:60"], "STRING"),
        (["2023-02-29"], "STRING"),
        (["09/05/2026"], "STRING"),
        (["2026-09-05T12:00:00.123456"], "TIMESTAMP_NTZ"),
        (["2026-09-05", "2026-09-05 12:00:00"], "TIMESTAMP_NTZ"),
        (["2026-09-05T12:00:00Z", "2026-09-05T12:00:00-04:00"], "TIMESTAMP"),
        (["2026-09-05T12:00:00Z", "2026-09-05T12:00:00"], "STRING"),
        (["2026-09-05T12:00:00Z", "2026-09-05"], "STRING"),
        (["2026-09-05T12:00:00.1234567"], "STRING"),
        (["2026-09-05T25:00:00"], "STRING"),
        ([str(-(2**63)), str(2**63 - 1)], "BIGINT"),
        ([str(-(2**63) - 1)], "DECIMAL(19,0)"),
        ([str(2**63)], "DECIMAL(19,0)"),
        (["9999", "1.25"], "DECIMAL(6,2)"),
        (["0.01", "0.9"], "DECIMAL(2,2)"),
        (["1e3", "0.125"], "DECIMAL(7,3)"),
        (["1e-38"], "DECIMAL(38,38)"),
        (["1e-39"], "STRING"),
        (["1e10000"], "STRING"),
        (["9" * 38], "DECIMAL(38,0)"),
        (["9" * 39], "STRING"),
        (["9" * 20_000], "STRING"),
        (["9" * 38, "0.1"], "STRING"),
    ],
)
def test_sample_inference_preserves_representations(
    values: list[JsonValue], expected: str | None
) -> None:
    # Inference must not depend on a caller's Decimal precision or round values.
    with localcontext() as context:
        context.prec = 3
        assert infer_sample_data_type(values) == expected


@pytest.mark.parametrize("values", [["1"] * 51, ["x" * 20_001]])
def test_sample_inference_rejects_oversized_evidence(values: list[JsonValue]) -> None:
    with pytest.raises(InvalidRequestError, match="sample limits"):
        infer_sample_data_type(values)


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        (" integer ", "INT"),
        ("long", "BIGINT"),
        ("bit", "BOOLEAN"),
        ("nvarchar(max)", "STRING"),
        ("character varying(200)", "STRING"),
        ("datetime2(7)", "TIMESTAMP_NTZ"),
        ("timestamp without time zone", "TIMESTAMP_NTZ"),
        ("datetimeoffset(7)", "TIMESTAMP"),
        ("double precision", "DOUBLE"),
        ("numeric(38, 2)", "DECIMAL(38,2)"),
        ("number(12)", "DECIMAL(12,0)"),
        ("decimal(38,38)", "DECIMAL(38,38)"),
        ("money", "DECIMAL(19,4)"),
        ("varbinary(500)", "BINARY"),
        ("array<int>", "ARRAY<INT>"),
        ("struct<Amount: decimal(12,2)>", "STRUCT<Amount: DECIMAL(12, 2)>"),
        (None, None),
        ("", None),
        ("unknown", None),
        ("decimal", None),
        ("decimal(39,2)", None),
        ("decimal(2,3)", None),
        ("decimal(0,0)", None),
        ("array<decimal(39,2)>", None),
        ("array<unknown>", None),
        ("INT; SELECT 1", None),
        ("x" * 101, None),
    ],
)
def test_native_type_normalization(native: str | None, expected: str | None) -> None:
    assert normalize_data_type(native) == expected
