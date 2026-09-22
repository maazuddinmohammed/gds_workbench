from __future__ import annotations

import json

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
        templates=PromptComponentTemplates(system="Use metadata", instruction="{{stage_context}}"),
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


def test_large_loops_render_every_item_without_work_budget() -> None:
    rendered = render_prompt(
        templates=PromptComponentTemplates(
            system="Use metadata",
            instruction="{% for value in stage_context %}{{value}}{% endfor %}",
        ),
        variables=_variables(),
        resolver_values={"context.stage": ["x"] * 200_001},
    )
    assert rendered.instruction == "x" * 200_001


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


@pytest.mark.parametrize("expression", ["{{stage_context}}", "{{stage_context|tojson}}"])
def test_large_json_projection_renders_complete_content(expression: str) -> None:
    value = ["é" * 2000] * 1000
    rendered = render_prompt(
        templates=PromptComponentTemplates(system="Metadata", instruction=expression),
        variables=_variables(),
        resolver_values={"context.stage": value},
    )
    assert json.loads(rendered.instruction) == value


def test_large_template_and_filtered_text_are_not_truncated() -> None:
    content = "é" * 1_000_001 + "complete suffix"
    rendered = render_prompt(
        templates=PromptComponentTemplates(
            system=content,
            instruction="{{model_name|default('missing')}}",
            tool_instruction="{{model_name}}",
        ),
        variables=_variables(),
        resolver_values={"model.name": content},
    )
    assert rendered.system == content
    assert rendered.instruction == content
    assert rendered.tool_instruction == content


def test_large_template_keeps_all_valid_expressions() -> None:
    rendered = render_prompt(
        templates=PromptComponentTemplates(system="Metadata", instruction="{{model_name}}" * 5001),
        variables=_variables(),
        resolver_values={"model.name": "x"},
    )
    assert rendered.instruction == "x" * 5001
