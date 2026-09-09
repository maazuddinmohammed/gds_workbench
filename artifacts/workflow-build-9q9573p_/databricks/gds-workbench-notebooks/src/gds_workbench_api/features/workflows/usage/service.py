"""Durable, claim-fenced numeric usage for the shared Run execution path."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import LiteralString, Protocol
from uuid import UUID, uuid4

from gds_etl_workbench.domain.errors import DependencyUnavailableError, InvalidRequestError
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    LifecycleTransaction,
    workflow_identity_triple,
)
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionClaim
from psycopg.types.json import Jsonb

from .contracts import FoundryModelPricing, ModelRequestRecorder, ModelTokenUsage

_BEGIN_RUN_SQL: LiteralString = """
SELECT application.begin_workflow_run_usage(%s, %s, %s, %s, %s, %s) AS agent_model_code
"""
_BEGIN_REQUEST_SQL: LiteralString = """
SELECT application.begin_workflow_run_model_request(
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
) AS request_id
"""
_COMPLETE_REQUEST_SQL: LiteralString = """
SELECT application.complete_workflow_run_model_request(
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
) AS recorded
"""


class WorkflowUsageDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[LifecycleTransaction]: ...


@dataclass(frozen=True, slots=True)
class _RunBinding:
    recorder: DatabaseWorkflowUsageRecorder = field(repr=False)
    claim: WorkflowExecutionClaim = field(repr=False)
    database: WorkflowUsageDatabase = field(repr=False)
    pricing: FoundryModelPricing | None = field(repr=False)


_CURRENT_RUN: ContextVar[_RunBinding | None] = ContextVar("workflow_usage_run", default=None)


class DatabaseWorkflowUsageRecorder:
    """Bind server-owned identity once; every provider write still rechecks its claim."""

    def __init__(
        self,
        *,
        database: WorkflowUsageDatabase,
        pricing_by_model: Mapping[str, FoundryModelPricing] | None = None,
    ) -> None:
        self._database = database
        self._pricing_by_model = dict(pricing_by_model or {})

    @asynccontextmanager
    async def track_run(self, claim: WorkflowExecutionClaim) -> AsyncGenerator[None, None]:
        identity = workflow_identity_triple(claim.principal)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _BEGIN_RUN_SQL,
                identity
                + (claim.workflow_run_id, claim.model_revision, claim.workflow_run_claim_token),
            )
            if row is None:
                raise DependencyUnavailableError()
        # Only the persisted Run chooses a deployment's pricing, including replay.
        pricing = self._pricing_by_model.get(row["agent_model_code"])
        token = _CURRENT_RUN.set(_RunBinding(self, claim, self._database, pricing))
        try:
            yield
        finally:
            # Terminal transitions clear claims; receipts are already durable.
            _CURRENT_RUN.reset(token)

    def make_invocation_recorder(
        self,
        *,
        workflow_run_id: int,
        stage_code: str,
        invocation_id: UUID,
        authoring_attempt: int,
    ) -> ModelRequestRecorder:
        binding = _CURRENT_RUN.get()
        if (
            binding is None
            or binding.recorder is not self
            or binding.claim.workflow_run_id != workflow_run_id
            or type(authoring_attempt) is not int
            or not 1 <= authoring_attempt <= 6
            or not re.fullmatch(r"[a-z][a-z0-9_]{0,99}", stage_code)
        ):
            raise InvalidRequestError("The model request has no matching Workflow Run claim.")
        return _InvocationRecorder(binding, invocation_id, stage_code, authoring_attempt)


class _InvocationRecorder:
    def __init__(
        self, binding: _RunBinding, invocation_id: UUID, stage_code: str, authoring_attempt: int
    ) -> None:
        self._binding = binding
        self._invocation_id = invocation_id
        self._stage_code = stage_code
        self._authoring_attempt = authoring_attempt
        self._request_ids: dict[int, UUID] = {}

    async def begin_request(self, request_ordinal: int) -> UUID:
        if type(request_ordinal) is not int or not 1 <= request_ordinal <= 150:
            raise InvalidRequestError("The model request ordinal is invalid.")
        if _CURRENT_RUN.get() is not self._binding:
            raise InvalidRequestError("The model request has no matching Workflow Run claim.")
        request_id = self._request_ids.setdefault(request_ordinal, uuid4())
        claim = self._binding.claim
        async with self._binding.database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _BEGIN_REQUEST_SQL,
                workflow_identity_triple(claim.principal)
                + (
                    claim.workflow_run_id,
                    claim.model_revision,
                    claim.workflow_run_claim_token,
                    request_id,
                    self._invocation_id,
                    self._stage_code,
                    self._authoring_attempt,
                    request_ordinal,
                    Jsonb(self._binding.pricing.model_dump(mode="json"))
                    if self._binding.pricing is not None
                    else None,
                ),
            )
        if row is None or row["request_id"] != request_id:
            raise DependencyUnavailableError()
        return request_id

    async def complete_request(self, request_id: UUID, usage: ModelTokenUsage) -> None:
        if _CURRENT_RUN.get() is not self._binding or request_id not in self._request_ids.values():
            raise InvalidRequestError("The model request has no matching Workflow Run claim.")
        claim = self._binding.claim
        async with self._binding.database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _COMPLETE_REQUEST_SQL,
                workflow_identity_triple(claim.principal)
                + (
                    claim.workflow_run_id,
                    claim.model_revision,
                    claim.workflow_run_claim_token,
                    request_id,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.total_tokens,
                    usage.cached_input_tokens,
                    usage.cache_write_input_tokens,
                    usage.reasoning_output_tokens,
                    usage.other_token_types,
                ),
            )
        if row is None:
            raise DependencyUnavailableError()
