"""Transport-neutral orchestration for deterministic bulk Profiling runs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.errors import (
    DatabricksConnectionFailedError,
    DatabricksResultTooLargeError,
    DatabricksStatementFailedError,
    DependencyUnavailableError,
    WorkbenchError,
)
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_runtime.profiling.execution import (
    ProfileMetric,
    ProfileObject,
    ProfilingExecutor,
    ProfilingPolicy,
    build_profile_queries,
    load_default_profiling_policy,
)

_logger = logging.getLogger(__name__)


class ProfilingRunStart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: Literal[
        "queued",
        "running",
        "completed",
        "completed_with_repair",
        "failed",
    ]
    model_revision: int = Field(gt=0)


class ProfilingCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    changed: bool
    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    submitted_profile_count: int = Field(ge=0, le=50_000)
    changed_profile_count: int = Field(ge=0, le=50_000)
    workflow_run_state: Literal["completed"]


@dataclass(frozen=True, slots=True)
class ProfilingExecutionTarget:
    object: ProfileObject
    connection: DatabricksSqlConnection = field(repr=False)


@dataclass(frozen=True, slots=True)
class ProfilingExecutionContext:
    workflow_run_id: int
    model_id: int
    model_revision: int
    requested_batch_id: str | None
    targets: tuple[ProfilingExecutionTarget, ...]

    def __post_init__(self) -> None:
        if self.workflow_run_id < 1 or self.model_id < 1 or self.model_revision < 1:
            raise ValueError("Profiling execution identifiers must be positive")
        if not 1 <= len(self.targets) <= 50_000:
            raise ValueError("Profiling execution targets are incomplete")
        object_ids = tuple(target.object.object_id for target in self.targets)
        if len(object_ids) != len(set(object_ids)):
            raise ValueError("Profiling execution Object IDs must be unique")
        if self.requested_batch_id is not None and (
            not self.requested_batch_id.strip()
            or len(self.requested_batch_id.encode("utf-8")) > 500
        ):
            raise ValueError("Profiling Batch ID must be bounded and nonblank")


class ProfilingWorkflowRepository(Protocol):
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart: ...

    async def load_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingExecutionContext: ...

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        sequence: int,
        stage: str,
        status: str,
        message: str,
        current: int | None,
        total: int | None,
        finding_count: int,
    ) -> None: ...

    async def commit(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        profiles: list[dict[str, object]],
    ) -> ProfilingCommitResult: ...

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> None: ...


class ProfilingWorkflowOrchestrator:
    """Plan, execute, validate, and atomically commit one started run."""

    def __init__(
        self,
        *,
        repository: ProfilingWorkflowRepository,
        executor: ProfilingExecutor,
        policy: ProfilingPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._executor = executor
        self._policy = policy or load_default_profiling_policy()

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart:
        return await self._repository.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
        )

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> None:
        try:
            context = await self._repository.load_context(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            if (
                context.workflow_run_id != workflow_run_id
                or context.model_id != model_id
                or context.model_revision != expected_model_revision
            ):
                raise RuntimeError("Profiling execution context does not match the run")

            plans = tuple(
                (target, query)
                for target in context.targets
                for query in build_profile_queries(
                    target.object,
                    requested_batch_id=context.requested_batch_id,
                    attributes_per_query=self._policy.attributes_per_query,
                )
            )
            await self._repository.append_event(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                sequence=2,
                stage="profiling.prepare",
                status="running",
                message="Profiling queries prepared.",
                current=0,
                total=len(plans),
                finding_count=0,
            )

            completed = 0
            metrics_by_attribute: dict[int, tuple[int, ProfileMetric]] = {}
            for offset in range(0, len(plans), self._policy.max_parallel_queries):
                batch = plans[offset : offset + self._policy.max_parallel_queries]
                results = await asyncio.gather(
                    *(
                        self._executor.execute(
                            connection=target.connection,
                            query=query,
                            timeout_seconds=self._policy.statement_timeout_seconds,
                        )
                        for target, query in batch
                    )
                )
                for (target, query), metrics in zip(batch, results, strict=True):
                    if tuple(metric.attribute_id for metric in metrics) != query.attribute_ids:
                        raise RuntimeError("Profiling result coverage is invalid")
                    for metric in metrics:
                        if metric.attribute_id in metrics_by_attribute:
                            raise RuntimeError("Profiling result coverage is duplicated")
                        metrics_by_attribute[metric.attribute_id] = (
                            target.object.object_id,
                            metric,
                        )
                    completed += 1
                    await self._repository.append_event(
                        principal,
                        workflow_run_id=workflow_run_id,
                        expected_model_revision=expected_model_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        sequence=2 + completed,
                        stage="profiling.execute",
                        status="running",
                        message="A bounded Profiling query completed.",
                        current=completed,
                        total=len(plans),
                        finding_count=len(metrics_by_attribute),
                    )

            attributes = {
                attribute.attribute_id: (target.object, attribute)
                for target in context.targets
                for attribute in target.object.attributes
            }
            if set(metrics_by_attribute) != set(attributes):
                raise RuntimeError("Profiling result coverage is incomplete")
            profiles: list[dict[str, object]] = []
            for attribute_id in sorted(attributes):
                target_object, attribute = attributes[attribute_id]
                object_id, metric = metrics_by_attribute[attribute_id]
                if object_id != target_object.object_id:
                    raise RuntimeError("Profiling result Object membership is invalid")
                profile = metric.model_dump(mode="python")
                profile["object_id"] = object_id
                profile["source_context_digest"] = _source_context_digest(
                    target_object,
                    attribute_id=attribute_id,
                    attribute_name=attribute.name,
                    attribute_data_type=attribute.data_type,
                    requested_batch_id=context.requested_batch_id,
                )
                profiles.append(profile)

            await self._repository.commit(
                principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
                profiles=profiles,
            )
        except Exception as error:
            failure_code, safe_message = _safe_failure(error)
            try:
                await self._repository.fail(
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    workflow_run_claim_token=workflow_run_claim_token,
                    failure_code=failure_code,
                    safe_failure_message=safe_message,
                )
            except Exception:
                _logger.warning(
                    "Profiling failure state could not be persisted.",
                    extra={
                        "workflow_run_id": workflow_run_id,
                        "model_id": model_id,
                        "failure_code": failure_code,
                    },
                )
                raise DependencyUnavailableError() from None


def _source_context_digest(
    target: ProfileObject,
    *,
    attribute_id: int,
    attribute_name: str,
    attribute_data_type: str,
    requested_batch_id: str | None,
) -> str:
    encoded = json.dumps(
        {
            "attribute_data_type": attribute_data_type,
            "attribute_id": attribute_id,
            "attribute_name": attribute_name,
            "batch_attribute_name": target.batch_attribute_name,
            "catalog": target.catalog,
            "object_id": target.object_id,
            "requested_batch_id": requested_batch_id,
            "schema": target.schema_name,
            "table": target.table,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_failure(error: Exception) -> tuple[str, str]:
    if isinstance(error, DatabricksConnectionFailedError):
        return (
            "databricks_connection_failed",
            "The Databricks SQL Warehouse connection failed.",
        )
    if isinstance(error, DatabricksStatementFailedError):
        return (
            "databricks_statement_failed",
            "Databricks rejected a Profiling query. Check registered metadata "
            "and Warehouse permissions.",
        )
    if isinstance(error, DatabricksResultTooLargeError):
        return (
            "databricks_profile_result_invalid",
            "Databricks returned an invalid or incomplete Profiling aggregate result.",
        )
    if isinstance(error, WorkbenchError):
        return error.code[:100], error.message[:2000]
    return (
        "profiling_execution_failed",
        "Profiling failed before results could be committed.",
    )


__all__ = [
    "ProfilingCommitResult",
    "ProfilingExecutionContext",
    "ProfilingExecutionTarget",
    "ProfilingRunStart",
    "ProfilingWorkflowOrchestrator",
    "ProfilingWorkflowRepository",
]
