"""Exact Model template contracts shared by plugin Change Sets and web projection."""

from __future__ import annotations

from string import Formatter
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

type _Nonblank255 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
]
type _Nonblank100 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"\S"),
]
type _Nonblank2000 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=2_000, pattern=r"\S"),
]


class GoldPolicyColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    semantic_name: _Nonblank255
    data_type: _Nonblank100
    nullable: bool
    definition: _Nonblank2000 | None


class _DimensionSurrogateKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    semantic_name_template: _Nonblank255
    data_type: _Nonblank100
    nullable: Literal[False]
    definition_template: _Nonblank2000

    @model_validator(mode="after")
    def validate_templates(self) -> _DimensionSurrogateKey:
        _validate_template(
            self.semantic_name_template,
            allowed={"entity_name"},
            required="entity_name",
        )
        _validate_template(self.definition_template, allowed={"entity_name"})
        return self


class _FactBridgeForeignKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    with_role_semantic_name_template: _Nonblank255
    without_role_semantic_name_template: _Nonblank255
    definition_template: _Nonblank2000

    @model_validator(mode="after")
    def validate_templates(self) -> _FactBridgeForeignKey:
        _validate_template(
            self.with_role_semantic_name_template,
            allowed={"role_name"},
            required="role_name",
        )
        _validate_template(
            self.without_role_semantic_name_template,
            allowed={"entity_name"},
            required="entity_name",
        )
        _validate_template(
            self.definition_template,
            allowed={"entity_name", "role_name"},
        )
        return self


class _Type2Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    effective_from: GoldPolicyColumn
    effective_to: GoldPolicyColumn
    is_current: GoldPolicyColumn

    @model_validator(mode="after")
    def validate_nullability(self) -> _Type2Policy:
        if (
            self.effective_from.nullable
            or not self.effective_to.nullable
            or self.is_current.nullable
        ):
            raise ValueError("Gold Type 2 policy nullability is invalid")
        names = [
            item.semantic_name.strip(" ").casefold()
            for item in (self.effective_from, self.effective_to, self.is_current)
        ]
        if len(names) != len(set(names)):
            raise ValueError("Gold Type 2 policy names must be unique")
        return self


class GoldTechnicalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    dimension_surrogate_key: _DimensionSurrogateKey
    fact_bridge_foreign_key: _FactBridgeForeignKey
    type_2: _Type2Policy


class GoldAuditPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    columns: tuple[GoldPolicyColumn, ...] = Field(min_length=0, max_length=32)

    @model_validator(mode="after")
    def validate_names(self) -> GoldAuditPolicy:
        names = [column.semantic_name.strip(" ").casefold() for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("Gold audit policy names must be unique")
        return self


def _validate_template(
    value: str,
    *,
    allowed: set[str],
    required: str | None = None,
) -> None:
    try:
        parsed = tuple(Formatter().parse(value))
    except ValueError:
        raise ValueError("Gold policy template syntax is invalid") from None
    fields = [field for _, field, _, _ in parsed if field is not None]
    if (
        any(field not in allowed for field in fields)
        or (required is not None and required not in fields)
        or any(format_spec or conversion for _, _, format_spec, conversion in parsed)
    ):
        raise ValueError("Gold policy template placeholders are invalid")
