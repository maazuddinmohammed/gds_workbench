"""Versioned record validations exported to local Snapshot clients."""

from __future__ import annotations

from typing import Final

CONTRACT_VERSION: Final = "1.0"

METADATA_RECORD_VALIDATIONS: Final[dict[str, tuple[str, ...]]] = {
    "tenant": ("tenant_gds_connection_key",),
    "ingestion_object_mapping": ("ingestion_object_endpoints",),
    "ingestion_attribute_mapping": ("ingestion_attribute_endpoints",),
    "copy": ("copy_record_limit",),
}

MODEL_RECORD_VALIDATIONS: Final[dict[str, tuple[str, ...]]] = {
    "model_details": ("model_details_policy",),
    "profiling_profile": ("profiling_profile",),
    "analysis_result": ("analysis_result",),
    "modeling_assertion_document": ("modeling_assertion_document",),
    "modeling_assertion_record": ("modeling_assertion_record",),
    "conceptual_object": ("conceptual_object",),
    "conceptual_relationship": ("conceptual_relationship",),
    "logical_entity": ("logical_entity",),
    "logical_attribute": ("logical_attribute",),
    "logical_relationship": ("logical_relationship",),
    "dimensional_entity": ("dimensional_entity",),
    "dimensional_attribute": ("dimensional_attribute",),
    "dimensional_relationship": ("dimensional_relationship",),
    "mapping_object": ("mapping_object",),
    "mapping_attribute": ("mapping_attribute",),
    "generated_code": ("generated_code",),
    "validation_group": ("validation_group",),
    "validation_check": ("validation_check",),
}


def record_validation_contract(rules: tuple[str, ...]) -> dict[str, object]:
    """Return the small portable contract consumed by both local helpers."""
    return {"version": CONTRACT_VERSION, "rules": list(rules)}

