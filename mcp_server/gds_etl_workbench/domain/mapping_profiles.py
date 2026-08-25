"""Shared immutable Mapping profile identity and canonical digest rules."""

from __future__ import annotations

import hashlib
import json
from typing import cast

MAPPING_STANDARD_PROFILE_KEY = "mapping.standard"
MAPPING_STANDARD_PROFILE_VERSION = "1.0.0"
MAPPING_STANDARD_SCHEMA_DIGEST = "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"

_SUPPORTED_SCHEMA_DIGESTS = {
    (MAPPING_STANDARD_PROFILE_KEY, MAPPING_STANDARD_PROFILE_VERSION): (
        MAPPING_STANDARD_SCHEMA_DIGEST
    ),
}


class UnknownMappingProfileError(ValueError):
    """A Mapping profile identity is not deployed by this release."""


class InvalidMappingPackageError(ValueError):
    """A Mapping package cannot be bound to its declared profile."""


def resolve_mapping_profile_schema_digest(key: str, version: str) -> str:
    """Resolve one exact deployed Mapping profile identity."""

    try:
        return _SUPPORTED_SCHEMA_DIGESTS[(key, version)]
    except KeyError as exc:
        raise UnknownMappingProfileError(f"Unsupported Mapping profile: {key}@{version}.") from exc


def canonical_mapping_json_bytes(value: object) -> bytes:
    """Encode strict Mapping canonical JSON v1."""

    _validate_canonical_json_value(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def mapping_package_digest(package: object) -> str:
    """Return the lowercase SHA-256 for one object-root Mapping package."""

    if not isinstance(package, dict):
        raise ValueError("Mapping package canonical JSON must have an object root.")
    package_object = cast(dict[object, object], package)
    return hashlib.sha256(canonical_mapping_json_bytes(package_object)).hexdigest()


def validate_mapping_package_profile(package: object, key: str, version: str) -> None:
    """Require canonical package data bound to the resolved profile identity."""

    expected_digest = resolve_mapping_profile_schema_digest(key, version)
    if not isinstance(package, dict):
        raise InvalidMappingPackageError("Mapping package must have an object root.")
    package_object = cast(dict[object, object], package)
    canonical_mapping_json_bytes(package_object)
    if package_object.get("schema_version") != "1.0":
        raise InvalidMappingPackageError("Mapping package schema_version is invalid.")
    profile = package_object.get("pydantic_profile")
    expected_profile = {
        "key": key,
        "version": version,
        "schema_digest": expected_digest,
    }
    if not isinstance(profile, dict):
        raise InvalidMappingPackageError("Mapping package pydantic_profile must be an object.")
    if cast(dict[object, object], profile) != expected_profile:
        raise InvalidMappingPackageError(
            "Mapping package pydantic_profile does not match the resolved profile."
        )


def _validate_canonical_json_value(value: object) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        raise ValueError("Floating-point values are not allowed in Mapping canonical JSON.")
    if isinstance(value, list):
        for item in cast(list[object], value):
            _validate_canonical_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise ValueError("Mapping canonical JSON object keys must be strings.")
            _validate_canonical_json_value(item)
        return
    raise ValueError(f"Unsupported Mapping canonical JSON value: {type(value).__name__}.")
