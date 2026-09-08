"""Real SDK JSON transport and canonical repair; in-memory HTTP only."""

# pyright: reportPrivateUsage=false
import json
from copy import deepcopy
from typing import Any
from uuid import UUID

import httpx2
import pytest
from gds_workbench_api.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    ValidationRepairRunner,
    load_default_agent_context_policy,
)
from mapping_fixtures import mapping_candidate, mapping_preparation
from pydantic import JsonValue

from tests.web_backend.test_agent_usage import (
    MemoryRecorder,
    _request,
    _response,
    _router,
)
from tests.web_backend.test_conceptual_candidate import _object, _validator


@pytest.mark.parametrize("workflow", ["conceptual", "mapping"])
@pytest.mark.parametrize(
    ("tools", "effort"),
    [
        (False, "default"),
        (False, "none"),
        *((True, effort) for effort in ("default", "none", "low", "medium", "high", "xhigh")),
    ],
)
@pytest.mark.parametrize("invalid", ["malformed", "wrong_type"])
async def test_json_mode_preserves_actual_candidate_schema_tools_repairs_and_usage(
    monkeypatch: pytest.MonkeyPatch,
    workflow: str,
    tools: bool,
    invalid: str,
    effort: str,
) -> None:
    stage = "mapping_authoring" if workflow == "mapping" else "candidate_authoring"
    validator = (
        CompleteMappingCandidateValidator(
            preparation=mapping_preparation(execution_mode="tool_assisted" if tools else "one_shot")
        )
        if workflow == "mapping"
        else _validator()
    )
    candidate: dict[str, JsonValue] = (
        mapping_candidate()
        if workflow == "mapping"
        else {"objects": [_object()], "relationships": []}
    )
    wrong_type = deepcopy(candidate)
    wrong_type["attribute_mappings" if workflow == "mapping" else "objects"] = "invalid type"
    responses = iter(
        (
            '{"incomplete":' if invalid == "malformed" else json.dumps(wrong_type),
            json.dumps(candidate),
        )
    )
    schema = validator.output_schema()
    formats: list[object] = []
    schema_preserved: list[bool] = []
    repair_issue_codes: list[list[str]] = []

    class Recorder(MemoryRecorder):
        def make_invocation_recorder(
            self,
            *,
            workflow_run_id: int,
            stage_code: str,
            invocation_id: UUID,
            authoring_attempt: int,
        ) -> MemoryRecorder:
            assert workflow_run_id == 101 and stage_code == stage
            self.invocations.append((invocation_id, authoring_attempt))
            return self

    recorder = Recorder()

    def handler(request: httpx2.Request) -> httpx2.Response:
        body: dict[str, Any] = json.loads(request.content)
        if effort == "default":
            assert "reasoning_effort" not in body
        else:
            assert body["reasoning_effort"] == effort
        formats.append(body.get("response_format"))
        user_message = next(item for item in body["messages"] if item["role"] == "user")
        payload = json.loads(user_message["content"])
        schema_preserved.append(payload["required_output_schema"] == schema)
        repair = payload["context"]["repair"]
        repair_issue_codes.append(
            [] if repair is None else [item["code"] for item in repair["validation_issues"]]
        )
        tool_response = tools and len(formats) == 1
        return httpx2.Response(
            200,
            json=_response(
                {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
                tool=tool_response,
                content="" if tool_response else next(responses),
            ),
        )

    request = _request(tools=tools).model_copy(
        update={
            "workflow": workflow,
            "stage": stage,
            "output_schema": schema,
        }
    )
    request = request.model_copy(
        update={"selection": request.selection.model_copy(update={"reasoning_effort_code": effort})}
    )
    router = _router(monkeypatch, recorder, handler)
    try:
        result = await ValidationRepairRunner(
            executor=router, policy=load_default_agent_context_policy()
        ).run(request=request, validator=validator)
    finally:
        await router.close()
    assert result.candidate == candidate
    assert result.attempt_count == 2 and result.was_repaired
    assert result.tool_call_count == int(tools)
    calls = 3 if tools else 2
    assert result.turn_count == calls
    assert formats == [{"type": "json_object"}] * calls
    assert all(schema_preserved)
    assert repair_issue_codes[-1] == ["candidate.output_schema_type"]
    assert [attempt for _, attempt in recorder.invocations] == [1, 2]
    assert recorder.invocations[0][0] == recorder.invocations[1][0]
    assert len(recorder.started) == len(recorder.completed) == calls
    assert sum(usage.total_tokens or 0 for _, usage in recorder.completed) == calls * 12
    if workflow == "mapping":
        # Flexible transformation documents remain valid; no strict-schema conversion.
        definitions = schema.get("$defs")
        assert isinstance(definitions, dict)
        json_object = definitions.get("JsonObject")
        assert isinstance(json_object, dict)
        assert json_object.get("additionalProperties") is not False
