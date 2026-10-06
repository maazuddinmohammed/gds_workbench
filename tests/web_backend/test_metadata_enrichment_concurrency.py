"""Concurrent tables retain sequential table-local authoring and guarded completion."""

# pyright: reportPrivateUsage=false
import asyncio
from copy import deepcopy
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.features.metadata_enrichment.contracts import (
    EnrichmentObject,
    MetadataEnrichmentContext,
)
from gds_workbench_api.features.metadata_enrichment.service import (
    DatabaseMetadataEnrichmentExecutor,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import (
    AgentStageOutcome,
    AgentStageRunner,
)
from pydantic import JsonValue

from tests.web_backend.test_agent_stage_runner import _plan
from tests.web_backend.test_metadata_enrichment_evidence import _object


def executor_fixture() -> tuple[DatabaseMetadataEnrichmentExecutor, AsyncMock, AsyncMock]:
    objects: list[EnrichmentObject] = []
    for index in range(3):
        item = _object(columns=2)
        key = {
            "tenant_code": "TEST",
            "system_code": "GDS",
            "connection_code": "BRONZE",
            "object_schema": "bronze",
            "object_name": f"table_{index}",
        }
        attributes = tuple(
            attribute.model_copy(update={"attribute_id": 1000 + 10 * index + number})
            for number, attribute in enumerate(item.attributes)
        )
        objects.append(
            item.model_copy(
                update={
                    "object_id": 20 + index,
                    "object_name": key["object_name"],
                    "attributes": attributes,
                    "prompt_inputs": {
                        "source_context": [],
                        "gds_context": [],
                        "ingestion_mapping": [],
                        "object_context": [{**key, "object_description": f"Existing {index}"}],
                        "object_attribute_context": [
                            {
                                **key,
                                "selected_attribute_names": [],
                                "attributes": [
                                    {"attribute_name": a.attribute_name} for a in attributes
                                ],
                            }
                        ],
                    },
                }
            )
        )
    repository = AsyncMock()
    repository.load.return_value = (
        _plan(),
        MetadataEnrichmentContext(
            workflow_run_id=1,
            model_id=1,
            model_revision=1,
            baseline_digest="a" * 64,
            objects=tuple(objects),
        ),
    )
    lifecycle = AsyncMock()
    executor = DatabaseMetadataEnrichmentExecutor(
        repository=repository,
        agent_executor=AsyncMock(),
        lifecycle=lifecycle,
    )
    return executor, repository, lifecycle


class ControlledStage:
    def __init__(self) -> None:
        self.started: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self.release = {f"table_{index}": asyncio.Event() for index in range(3)}
        self.inputs: dict[tuple[str, str], dict[str, Any]] = {}
        self.active = 0
        self.peak = 0

    async def run(self, **kwargs: Any) -> AgentStageOutcome:
        inputs = kwargs["context"]["prompt_inputs"]
        table = inputs["object_context"][0]["object_name"]
        workflow = kwargs["prompt_workflow"]
        self.inputs[table, workflow] = deepcopy(inputs)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await self.started.put((table, workflow))
            await self.release[table].wait()
            refs = kwargs["validator"].targets
            candidate: dict[str, JsonValue] = {
                "descriptions": {ref: f"Description for {table}" for ref in refs}
            }
            if kwargs["validator"].attributes:
                candidate["attributes"] = {
                    ref: {
                        key: None
                        for key in (
                            "is_natural_key",
                            "is_primary_key",
                            "is_nullable",
                            "is_pii",
                        )
                    }
                    for ref in refs
                }
            return AgentStageOutcome(
                candidate=candidate,
                warning_codes=(),
                unknown_placeholders=(),
                attempt_count=1,
                was_repaired=False,
                turn_count=1,
                tool_call_count=0,
            )
        finally:
            self.active -= 1


async def execute(executor: DatabaseMetadataEnrichmentExecutor) -> None:
    await executor.execute_started(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN, entra_tenant_id=UUID(int=1), entra_object_id=UUID(int=2)
        ),
        tenant_id=7,
        model_id=1,
        workflow_run_id=1,
        expected_model_revision=1,
        workflow_run_claim_token=UUID(int=3),
    )


async def test_two_tables_overlap_but_each_attribute_receives_its_own_object_result() -> None:
    executor, repository, lifecycle = executor_fixture()
    stage = ControlledStage()
    executor._stage = cast(AgentStageRunner, stage)
    task = asyncio.create_task(execute(executor))
    try:
        first = await asyncio.wait_for(stage.started.get(), timeout=1)
        second = await asyncio.wait_for(stage.started.get(), timeout=1)
        assert {first, second} == {
            ("table_0", "metadata_enrichment_object"),
            ("table_1", "metadata_enrichment_object"),
        }
        repository.complete.assert_not_awaited()
        # Finish the second table first. Its worker can start a third table while
        # the first remains blocked, without borrowing either table's description.
        stage.release["table_1"].set()
        assert await asyncio.wait_for(stage.started.get(), timeout=1) == (
            "table_1",
            "metadata_enrichment_attribute",
        )
        assert await asyncio.wait_for(stage.started.get(), timeout=1) == (
            "table_2",
            "metadata_enrichment_object",
        )
        assert stage.peak == 2
        stage.release["table_0"].set()
        stage.release["table_2"].set()
        await asyncio.wait_for(task, timeout=1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert stage.active == 0 and stage.peak == 2
    for index in range(3):
        table = f"table_{index}"
        inputs = stage.inputs[table, "metadata_enrichment_attribute"]
        assert inputs["object_context"][0]["object_description"] == f"Description for {table}"
        assert len(inputs["object_attribute_context"][0]["attributes"]) == 2
    repository.complete.assert_awaited_once()
    assert repository.complete.await_args is not None
    results = repository.complete.await_args.kwargs["results"]
    assert len(results) == 39
    for result in results:
        if result.field_name.endswith("description"):
            assert result.applied_value == f"Description for table_{result.object_id - 20}"
    events = [call.kwargs["event"] for call in lifecycle.append_event.await_args_list]
    assert [event.sequence for event in events] == list(range(2, 10))
    assert [event.current for event in events if event.stage == "candidate_authoring"] == list(
        range(1, 7)
    )


async def test_cancellation_stops_both_tables_before_any_completion_write() -> None:
    executor, repository, lifecycle = executor_fixture()
    stage = ControlledStage()
    executor._stage = cast(AgentStageRunner, stage)
    task = asyncio.create_task(execute(executor))
    try:
        await asyncio.wait_for(stage.started.get(), timeout=1)
        await asyncio.wait_for(stage.started.get(), timeout=1)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert stage.active == 0
    assert len(stage.inputs) == 2
    repository.complete.assert_not_awaited()
    lifecycle.fail.assert_not_awaited()


async def test_progress_failure_stops_sibling_before_marking_run_failed() -> None:
    executor, repository, lifecycle = executor_fixture()
    stage = ControlledStage()
    executor._stage = cast(AgentStageRunner, stage)
    lifecycle.append_event.side_effect = [
        None,
        WorkbenchError(code="claim_lost", message="Lost claim."),
    ]
    task = asyncio.create_task(execute(executor))
    try:
        await asyncio.wait_for(stage.started.get(), timeout=1)
        await asyncio.wait_for(stage.started.get(), timeout=1)
        stage.release["table_0"].set()
        with pytest.raises(WorkbenchError) as caught:
            await asyncio.wait_for(task, timeout=1)
        assert caught.value.code == "claim_lost"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert stage.active == 0
    assert len(stage.inputs) == 2
    repository.complete.assert_not_awaited()
    lifecycle.fail.assert_awaited_once()
