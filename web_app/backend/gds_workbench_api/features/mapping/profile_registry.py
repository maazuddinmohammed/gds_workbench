"""Verified registry for the one Release-1 Mapping profile."""

from __future__ import annotations

from importlib.resources import files
from typing import Literal, Self

from gds_etl_workbench.domain.mapping_profiles import (
    resolve_mapping_profile_schema_digest,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic.version import VERSION as PYDANTIC_VERSION

from gds_workbench_api.features.mapping.contracts import (
    MAPPING_PROFILE_KEY,
    MAPPING_PROFILE_VERSION,
    SCHEMA_BUNDLE_VERSION,
    mapping_schema_bundle_digest,
    parse_contract_json,
)

_ROOT_MODEL_ORDER = [
    "AttributeMapperBatchOutputV1",
    "GeneratorDocumentV1",
    "HeaderMapperOutputV1",
]


class MappingProfileConfigurationError(ValueError):
    """The deployed Mapping profile metadata differs from executable code."""


class MappingProfileRegistration(BaseModel):
    """Globally reusable identity for one immutable deployed profile."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"]
    key: Literal["mapping.standard"]
    version: Literal["1.0.0"]
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_bundle_version: Literal["1.0"]
    json_schema_mode: Literal["validation"]
    pydantic_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    root_models: list[
        Literal[
            "AttributeMapperBatchOutputV1",
            "GeneratorDocumentV1",
            "HeaderMapperOutputV1",
        ]
    ] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_root_order(self) -> Self:
        if self.root_models != _ROOT_MODEL_ORDER:
            raise ValueError("Mapping profile root models must use canonical class-name order")
        return self


def load_mapping_profile_registry(
    raw: str | bytes | bytearray | None = None,
) -> MappingProfileRegistration:
    """Load metadata and prove it matches generated schemas and runtime."""

    if raw is None:
        raw = (
            files("gds_workbench_api")
            .joinpath("config/mapping_profiles.json")
            .read_text(encoding="utf-8")
        )
    try:
        parsed = parse_contract_json(raw)
        registration = MappingProfileRegistration.model_validate(parsed)
    except (OSError, ValueError, ValidationError) as exc:
        raise MappingProfileConfigurationError(
            "Mapping profile registry configuration is invalid"
        ) from exc

    if registration.key != MAPPING_PROFILE_KEY or registration.version != MAPPING_PROFILE_VERSION:
        raise MappingProfileConfigurationError("Mapping profile identity does not match code")
    if registration.schema_bundle_version != SCHEMA_BUNDLE_VERSION:
        raise MappingProfileConfigurationError("Mapping schema-bundle version does not match code")
    if registration.pydantic_version != PYDANTIC_VERSION:
        raise MappingProfileConfigurationError(
            "Mapping profile Pydantic version does not match the deployed runtime"
        )
    deployed_digest = resolve_mapping_profile_schema_digest(
        registration.key,
        registration.version,
    )
    if mapping_schema_bundle_digest() != deployed_digest:
        raise MappingProfileConfigurationError(
            "Generated Mapping schemas do not match the shared deployed profile"
        )
    if registration.schema_digest != deployed_digest:
        raise MappingProfileConfigurationError(
            "Mapping profile schema digest does not match the shared deployed profile"
        )
    return registration
