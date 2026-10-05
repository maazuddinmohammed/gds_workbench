"""Public built-in templates, using the same defaults as workflow projection."""

from typing import cast

from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.audit_policy import effective_audit_template
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates
from gds_workbench_api.features.workflows.authoring.naming import effective_naming_instructions


def default_model_templates() -> dict[str, JsonValue]:
    technical, audit = effective_gold_templates(None, None)
    return cast(
        dict[str, JsonValue],
        {
            "silver_model_naming_instructions": effective_naming_instructions("logical", None),
            "silver_model_audit_columns_template": effective_audit_template(None),
            "gold_model_naming_instructions": effective_naming_instructions("dimensional", None),
            "gold_model_technical_columns_template": technical,
            "gold_model_audit_columns_template": audit,
        },
    )
