from __future__ import annotations

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError

from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
    render_prompt,
)


def _variables() -> tuple[PromptVariableDefinition, ...]:
    return (
        PromptVariableDefinition(
            name="model_name",
            resolver_key="model.name",
            data_type="text",
            is_required=True,
        ),
        PromptVariableDefinition(
            name="stage_context",
            resolver_key="context.stage",
            data_type="json",
            is_required=True,
        ),
        PromptVariableDefinition(
            name="retry_count",
            resolver_key="run.retry_count",
            data_type="integer",
            is_required=False,
        ),
    )


def test_prompt_renderer_uses_only_allowlisted_resolvers_and_preserves_unknowns() -> None:
    templates = PromptComponentTemplates(
        system="Model {{ model_name }}; future={{future_variable}}",
        instruction="Use {{stage_context}}. Retry {{ retry_count }}.",
        tool_instruction=None,
    )
    rendered = render_prompt(
        templates=templates,
        variables=_variables(),
        resolver_values={
            "model.name": "customer_360",
            "context.stage": {"objects": 25, "raw_rows": False},
            "run.retry_count": 2,
            "unregistered.value": "must-not-appear",
        },
    )

    assert rendered.system == "Model customer_360; future={{future_variable}}"
    assert rendered.instruction == ('Use {"objects":25,"raw_rows":false}. Retry 2.')
    assert rendered.tool_instruction is None
    assert rendered.warning_codes == ("unknown_prompt_placeholder",)
    assert rendered.unknown_placeholders == ("future_variable",)
    representation = repr(rendered)
    assert "customer_360" not in representation
    assert "objects" not in representation
    assert "future_variable" not in repr(templates)
    assert "stage_context" not in repr(templates)


def test_prompt_renderer_fails_before_rendering_when_required_value_is_missing() -> None:
    with pytest.raises(InvalidRequestError, match="required Prompt variable"):
        render_prompt(
            templates=PromptComponentTemplates(
                system="Model {{model_name}}",
                instruction="Use {{stage_context}}",
                tool_instruction=None,
            ),
            variables=_variables(),
            resolver_values={"model.name": "customer_360"},
        )


@pytest.mark.parametrize(
    ("resolver_key", "invalid_value"),
    [
        ("model.name", 42),
        ("context.stage", object()),
        ("run.retry_count", True),
    ],
)
def test_prompt_renderer_rejects_resolver_type_mismatch_without_value_disclosure(
    resolver_key: str,
    invalid_value: object,
) -> None:
    values: dict[str, object] = {
        "model.name": "customer_360",
        "context.stage": {"objects": 25},
        "run.retry_count": 2,
    }
    values[resolver_key] = invalid_value

    with pytest.raises(InvalidRequestError) as captured:
        render_prompt(
            templates=PromptComponentTemplates(
                system="{{model_name}}",
                instruction="{{stage_context}} {{retry_count}}",
                tool_instruction=None,
            ),
            variables=_variables(),
            resolver_values=values,
        )

    assert str(invalid_value) not in str(captured.value)
