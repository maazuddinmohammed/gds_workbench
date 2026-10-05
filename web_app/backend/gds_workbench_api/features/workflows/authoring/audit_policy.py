"""Reusable audit defaults; explicit Model templates remain authoritative."""

from collections.abc import Mapping
from copy import deepcopy


def effective_audit_template(template: Mapping[str, object] | None) -> dict[str, object]:
    if template is not None:
        return deepcopy(dict(template))
    return {
        "schema_version": "1.0",
        "columns": [
            {
                "semantic_name": name,
                "data_type": data_type,
                "nullable": True,
                "definition": definition,
            }
            for name, data_type, definition in (
                ("SourceSystemID", "BIGINT", "Originating source System identifier."),
                ("IsDataValid", "BOOLEAN", "Framework data validation flag."),
                ("HashKey", "STRING", "Framework change-detection hash."),
                ("IsActive", "BOOLEAN", "Framework active-record flag."),
                ("GDSBatchID", "BIGINT", "Framework batch identifier."),
                ("PipelineRunID", "STRING", "Framework pipeline run identifier."),
                ("CreatedDate", "TIMESTAMP", "Framework record creation time."),
                ("UpdatedDate", "TIMESTAMP", "Framework record update time."),
                ("CreatedBy", "STRING", "Framework record creator."),
                ("UpdatedBy", "STRING", "Framework record updater."),
            )
        ],
    }
