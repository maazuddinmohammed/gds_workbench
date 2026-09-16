"""Conservative type inference; sample values stay inside this process."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue
from sqlglot import exp
from sqlglot.errors import ParseError

_ALIASES = {
    "BOOL": "BOOLEAN",
    "BOOLEAN": "BOOLEAN",
    "BIT": "BOOLEAN",
    "BYTE": "TINYINT",
    "TINYINT": "TINYINT",
    "SHORT": "SMALLINT",
    "SMALLINT": "SMALLINT",
    "INT": "INT",
    "INTEGER": "INT",
    "INT4": "INT",
    "LONG": "BIGINT",
    "BIGINT": "BIGINT",
    "INT8": "BIGINT",
    "FLOAT": "FLOAT",
    "REAL": "FLOAT",
    "DOUBLE": "DOUBLE",
    "DOUBLE PRECISION": "DOUBLE",
    "FLOAT8": "DOUBLE",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMP_LTZ": "TIMESTAMP",
    "TIMESTAMP_NTZ": "TIMESTAMP_NTZ",
    "DATETIME": "TIMESTAMP_NTZ",
    "TIMESTAMP WITHOUT TIME ZONE": "TIMESTAMP_NTZ",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMP",
    "TIMESTAMPTZ": "TIMESTAMP",
    "STRING": "STRING",
    "TEXT": "STRING",
    "NTEXT": "STRING",
    "UUID": "STRING",
    "UNIQUEIDENTIFIER": "STRING",
    "XML": "STRING",
    "BINARY": "BINARY",
    "VARBINARY": "BINARY",
    "BYTEA": "BINARY",
    "VARIANT": "VARIANT",
    "MONEY": "DECIMAL(19,4)",
    "SMALLMONEY": "DECIMAL(10,4)",
}
_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")
_INTEGER = re.compile(r"^[+-]?[0-9]+$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_TIMESTAMP = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ](?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?$"
)


def normalize_data_type(value: str | None) -> str | None:
    """Translate known native types into bounded Databricks type names."""
    if value is None or not value.strip() or len(value) > 100 or "\x00" in value:
        return None
    native = re.sub(r"\s+", " ", value.strip()).upper()
    if native in _ALIASES:
        return _ALIASES[native]
    if re.fullmatch(
        r"(?:N?VARCHAR|N?CHAR|CHARACTER(?: VARYING)?)(?:\s*\((?:[0-9]+|MAX)\))?", native
    ):
        return "STRING"
    if re.fullmatch(r"(?:VARBINARY|BINARY)\s*\([0-9]+\)", native):
        return "BINARY"
    if re.fullmatch(r"DATETIME2(?:\s*\([0-9]\))?", native):
        return "TIMESTAMP_NTZ"
    if re.fullmatch(r"DATETIMEOFFSET(?:\s*\([0-9]\))?", native):
        return "TIMESTAMP"
    decimal = re.fullmatch(
        r"(?:DECIMAL|NUMERIC|NUMBER)\s*\(\s*([0-9]+)\s*(?:,\s*([0-9]+)\s*)?\)", native
    )
    if decimal:
        precision, scale = int(decimal[1]), int(decimal[2] or 0)
        return (
            f"DECIMAL({precision},{scale})"
            if 1 <= precision <= 38 and 0 <= scale <= precision
            else None
        )
    # Complex source schemas are useful evidence too. Parse a type expression,
    # never SQL statements, and retain field-name case in STRUCT declarations.
    if re.match(r"^(ARRAY|MAP|STRUCT)\s*<", native):
        try:
            parsed = exp.DataType.build(value.strip(), dialect="databricks")
            for nested in parsed.find_all(exp.DataType):
                if (
                    nested.this
                    not in {
                        exp.DataType.Type.ARRAY,
                        exp.DataType.Type.MAP,
                        exp.DataType.Type.STRUCT,
                    }
                    and normalize_data_type(nested.sql(dialect="databricks")) is None
                ):
                    return None
            normalized = parsed.sql(dialect="databricks")
        except (ParseError, ValueError):
            return None
        if len(normalized) <= 100:
            return normalized
    return None


def infer_sample_data_type(values: Sequence[JsonValue]) -> str | None:
    """Infer a provisional primitive type from at most 50 non-persisted observations.

    Nulls and blanks carry no narrowing evidence. Identifiers with leading zeros,
    incompatible values and values outside exact decimal capacity remain STRING.
    Decimal samples retain observed scale but reserve the full precision; sample
    magnitude cannot establish a production bound or prove a whole-column cast.
    """
    if len(values) > 50 or any(isinstance(value, str) and len(value) > 20_000 for value in values):
        raise InvalidRequestError("Metadata inference sample limits were exceeded.")
    observed = [
        value
        for value in values
        if value is not None and not (isinstance(value, str) and not value.strip())
    ]
    if not observed:
        return None
    if all(isinstance(value, bool) for value in observed):
        return "BOOLEAN"
    if any(isinstance(value, bool | dict | list) for value in observed):
        return "STRING"
    if any(isinstance(value, float) and not isfinite(value) for value in observed):
        return "STRING"
    try:
        text_values = [str(value).strip() for value in observed]
    except ValueError:
        return "STRING"
    if all(value.casefold() in {"true", "false"} for value in text_values):
        return "BOOLEAN"

    temporal_kinds: set[str] = set()
    for value in text_values:
        try:
            if _DATE.fullmatch(value):
                date.fromisoformat(value)
                temporal_kinds.add("date")
            elif _TIMESTAMP.fullmatch(value):
                timestamp = datetime.fromisoformat(value)
                temporal_kinds.add("zoned" if timestamp.tzinfo is not None else "naive")
            else:
                temporal_kinds.clear()
                break
        except ValueError:
            temporal_kinds.clear()
            break
    if temporal_kinds:
        if temporal_kinds == {"date"}:
            return "DATE"
        if temporal_kinds <= {"date", "naive"}:
            return "TIMESTAMP_NTZ"
        return "TIMESTAMP" if temporal_kinds == {"zoned"} else "STRING"

    if not all(_NUMBER.fullmatch(value) for value in text_values):
        return "STRING"
    integer_digits = 0
    scale = 0
    for value in text_values:
        significand = re.split(r"[eE]", value.lstrip("+-"), maxsplit=1)[0]
        integer_part = significand.split(".", maxsplit=1)[0]
        if len(integer_part) > 1 and integer_part.startswith("0"):
            return "STRING"
        try:
            parsed = Decimal(value).as_tuple()
        except InvalidOperation:
            return "STRING"
        exponent = parsed.exponent
        if not isinstance(exponent, int):
            return "STRING"
        # Tuple arithmetic does not round under Decimal's default 28-digit context.
        integer_digits = max(integer_digits, len(parsed.digits) + exponent, 0)
        scale = max(scale, -exponent, 0)
        if integer_digits + scale > 38:
            return "STRING"
    if all(_INTEGER.fullmatch(value) for value in text_values) and all(
        -(2**63) <= int(value) <= 2**63 - 1 for value in text_values
    ):
        return "BIGINT"
    return f"DECIMAL(38,{scale})"
