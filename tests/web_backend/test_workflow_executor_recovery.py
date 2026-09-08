"""Every authoring executor preserves exact rejected output through one handoff."""

# Existing executor fixtures own valid candidates and their workflow-specific setup.
# pyright: reportPrivateUsage=false

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import ModelValidationIssue
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetValidationError,
)

from tests.web_backend import (
    test_analysis_executor as analysis,
)
from tests.web_backend import (
    test_code_generation_executor as code_generation,
)
from tests.web_backend import (
    test_conceptual_executor as conceptual,
)
from tests.web_backend import (
    test_dimensional_executor as dimensional,
)
from tests.web_backend import (
    test_logical_executor as logical,
)
from tests.web_backend import (
    test_mapping_executor as mapping,
)
from tests.web_backend import (
    test_validation_executor as validation,
)
from tests.web_backend.mapping_fixtures import mapping_preparation
from tests.web_backend.workflow_recovery_fixtures import RetainingHandoff


@pytest.mark.parametrize(
    "workflow",
    [
        "analysis",
        "conceptual",
        "logical",
        "dimensional",
        "mapping",
        "code_generation",
        "validation",
    ],
)
@pytest.mark.parametrize("retention_fails", [False, True])
async def test_authoritative_rejection_retains_exact_candidate_without_separate_run_failure(
    workflow: str,
    retention_fails: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service: Any
    handoff: Any
    lifecycle: Any
    claim_token = UUID("44444444-4444-4444-4444-444444444444")
    if workflow == "mapping":
        service, _finalize, _no_op, fail = mapping._executor(
            mapping_preparation(), mapping._RecordingFake()
        )
        handoff = RetainingHandoff()
        lifecycle = SimpleNamespace(fail=fail)
        monkeypatch.setattr(service, "_handoff", handoff)
    elif workflow == "code_generation":
        setup = code_generation._service(
            executor=code_generation._AgentExecutor(
                responses=[
                    {"artifacts": [{"target_ref": "target_1", "generated_sql": "SELECT 1;"}]},
                    {"artifacts": [{"target_ref": "target_2", "generated_sql": "SELECT 2;"}]},
                ]
            )
        )
        service, _, _, handoff, _, lifecycle = setup
    elif workflow == "validation":
        service, _, _, handoff, _, lifecycle = validation._service(context=validation._context())
    else:
        fixture: Any = {
            "analysis": analysis,
            "conceptual": conceptual,
            "logical": logical,
            "dimensional": dimensional,
        }[workflow]
        service, _, _, handoff, lifecycle = fixture._service(
            agent=fixture._AgentExecutor(responses=[fixture._candidate()])
        )
        claim_token = fixture._CLAIM_TOKEN

    issues = (
        ModelValidationIssue(
            code="active_dependency_invalid",
            dataset="logical_entity" if workflow == "logical" else "test_dependency",
            record_number=1,
            fields=(),
            message="An applied dependency prevents this candidate from being accepted.",
        ),
    )
    rejection = WorkflowChangeSetValidationError(issues)
    attempted_changes: list[tuple[StageModelChange, ...]] = []

    async def reject_finalization(
        principal: RequestPrincipal,
        *,
        changes: tuple[StageModelChange, ...],
        **parameters: Any,
    ) -> None:
        del principal, parameters
        attempted_changes.append(changes)
        raise rejection

    monkeypatch.setattr(handoff, "finalize", reject_finalization, raising=False)
    retention_error = DependencyUnavailableError()
    if retention_fails:
        handoff.retention_error = retention_error
    retention = AsyncMock(wraps=handoff.retain_failed_candidate)
    monkeypatch.setattr(handoff, "retain_failed_candidate", retention)
    expected_error = (
        DependencyUnavailableError if retention_fails else WorkflowChangeSetValidationError
    )

    with pytest.raises(expected_error) as caught:
        await service.execute_started(
            analysis._principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=claim_token,
        )

    assert len(attempted_changes) == 1
    assert attempted_changes[0]
    retention.assert_awaited_once()
    assert retention.await_args is not None
    retained = retention.await_args.kwargs
    assert retained["changes"] == attempted_changes[0]
    assert retained["issues"] == issues
    assert retained["expected_workflow"] == workflow
    assert retained["tenant_id"] == 7
    assert retained["model_id"] == 18
    assert retained["workflow_run_id"] == 1048
    assert retained["expected_model_revision"] == 7
    assert retained["workflow_run_claim_token"] == claim_token
    assert retained["failure_code"] == rejection.code
    assert "draft" in retained["safe_failure_message"].lower()
    if workflow == "mapping":
        lifecycle.fail.assert_not_awaited()
    else:
        assert lifecycle.failed is None
    if retention_fails:
        assert caught.value.code == retention_error.code
        assert handoff.retained == []
    else:
        assert caught.value is rejection
        assert handoff.retained == [retained]
