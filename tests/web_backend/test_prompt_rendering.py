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


def test_prompt_renderer_uses_only_registered_data_and_renders_once() -> None:
    templates = PromptComponentTemplates(
        system="Model {{ model_name }}",
        instruction="Use {{stage_context}}. Retry {{ retry_count }}.",
    )
    rendered = render_prompt(
        templates=templates,
        variables=_variables(),
        resolver_values={
            "model.name": "{{never_render_again}}",
            "context.stage": {"objects": 25},
            "run.retry_count": 2,
            "unregistered.value": "must-not-appear",
        },
    )
    assert rendered.system == "Model {{never_render_again}}"
    assert rendered.instruction == 'Use {"objects":25}. Retry 2.'
    assert rendered.warning_codes == ()
    assert "objects" not in repr(rendered)
    assert "stage_context" not in repr(templates)


def test_known_missing_data_is_null_and_unreferenced_values_are_optional() -> None:
    rendered = render_prompt(
        templates=PromptComponentTemplates(
            system="Use metadata", instruction="{{stage_context}}"
        ),
        variables=_variables(),
        resolver_values={},
    )
    assert rendered.instruction == "null"


@pytest.mark.parametrize(
    "body",
    [
        "{{unknown}}",
        "{{stage_context.missing}}",
        "{{stage_context.__class__}}",
        "{{stage_context.items()}}",
        "{{ 10 ** 100 }}",
        "{% include 'anything' %}",
        "{% for x in stage_context recursive %}x{% endfor %}",
        "{% set x = 1 %}{{x}}",
        "{{model_name|attr('__class__')}}",
        "{{ broken",
    ],
)
def test_renderer_rejects_unknown_fields_calls_and_unsupported_syntax(
    body: str,
) -> None:
    with pytest.raises(InvalidRequestError):
        render_prompt(
            templates=PromptComponentTemplates(system="Use metadata", instruction=body),
            variables=_variables(),
            resolver_values={"context.stage": {"objects": 25}},
        )


def test_renderer_supports_projection_filtering_and_conditional_loops() -> None:
    rendered = render_prompt(
        templates=PromptComponentTemplates(
            system="Use metadata",
            instruction="{{stage_context|selectattr('active')|map(attribute='name')|list}} "
            "{% for row in stage_context %}{% if row.active %}"
            "{{loop.index}}={{row.name}}{% endif %}{% endfor %}",
        ),
        variables=_variables(),
        resolver_values={
            "context.stage": [
                {"name": "Order", "active": True},
                {"name": "Old", "active": False},
            ]
        },
    )
    assert rendered.instruction == '["Order"] 1=Order'


def test_empty_output_nested_loops_still_have_work_budget() -> None:
    with pytest.raises(InvalidRequestError, match="work limit"):
        render_prompt(
            templates=PromptComponentTemplates(
                system="Use metadata",
                instruction="{% for x in stage_context %}{% for y in stage_context %}"
                "{% endfor %}{% endfor %}",
            ),
            variables=_variables(),
            resolver_values={"context.stage": list(range(500))},
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


def test_large_json_projection_is_bounded_before_full_materialization() -> None:
    with pytest.raises(InvalidRequestError, match="size"):
        render_prompt(
            templates=PromptComponentTemplates(
                system="Metadata", instruction="{{stage_context}}"
            ),
            variables=_variables(),
            resolver_values={"context.stage": ["x" * 2000] * 1000},
        )
