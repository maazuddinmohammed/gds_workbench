"""Effective Gold templates shared by prompt inputs and deterministic projection."""

from collections.abc import Mapping
from copy import deepcopy

from .audit_policy import effective_audit_template

_DEFAULT_TECHNICAL: dict[str, object] = {
    "schema_version": "1.0",
    "dimension_surrogate_key": {
        "semantic_name_template": "{entity_name}Key",
        "data_type": "BIGINT",
        "nullable": False,
        "definition_template": "Surrogate key for {entity_name}.",
    },
    "fact_bridge_foreign_key": {
        "with_role_semantic_name_template": "{role_name}Key",
        "without_role_semantic_name_template": "{entity_name}Key",
        "definition_template": "Foreign key to {entity_name}.",
    },
    "type_2": {
        "effective_from": {
            "semantic_name": "RecordStartTime",
            "data_type": "TIMESTAMP",
            "nullable": False,
            "definition": "Inclusive start of this dimension version.",
        },
        "effective_to": {
            "semantic_name": "RecordEndTime",
            "data_type": "TIMESTAMP",
            "nullable": True,
            "definition": "Exclusive end of this dimension version.",
        },
        "is_current": {
            "semantic_name": "IsCurrentRecord",
            "data_type": "BOOLEAN",
            "nullable": False,
            "definition": "Whether this is the current dimension version.",
        },
    },
}


def effective_gold_templates(
    technical: Mapping[str, object] | None,
    audit: Mapping[str, object] | None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Blank settings use shared keys, history fields and audit columns.

    Explicit templates remain authoritative, including an empty audit column list.
    Validation of supplied templates stays with the Gold policy projector.
    """
    # Existing Models may still have a separate stored key/history policy.
    # The combined audit template takes precedence when a Model is customized.
    keys = deepcopy(dict(_DEFAULT_TECHNICAL if technical is None else technical))
    columns = effective_audit_template(audit)
    for name in ("dimension_surrogate_key", "fact_bridge_foreign_key", "type_2"):
        if name in columns:
            value = columns.pop(name)
            if value is not None:
                keys[name] = value
    return keys, columns
