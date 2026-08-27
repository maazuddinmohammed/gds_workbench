"""Governed PostgreSQL control plane for independent notebook Workflows."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from .errors import (
    NotebookAuthorizationError,
    NotebookConfigurationError,
    NotebookDatabaseError,
)

if TYPE_CHECKING:
    from .notebook import NotebookWorkflowRequest

_CREATE_PAYLOAD_KEYS = frozenset(
    {
        "expected_model_revision",
        "model_workflow",
        "workflow_execution_mode",
        "selected_object_ids",
        "modeled_entity_type",
        "requested_batch_id",
        "mapping_operation",
        "mapping_coverage_mode",
        "mapping_artifact_type",
        "mapping_source_system_id",
        "mapping_object_output_template_id",
        "mapping_attribute_output_template_id",
        "code_generation_coverage_mode",
        "sql_generation_guide_version_id",
        "agent",
        "prompt_overrides",
    }
)
_WORKFLOW_STATES = {
    "queued",
    "running",
    "completed",
    "completed_with_repair",
    "failed",
}
_WORKFLOWS = {
    "profiling",
    "analysis",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
}


@dataclass(frozen=True, slots=True)
class NotebookPrincipal:
    display_name: str
    principal_type: str
    databricks_environment_code: str
    entra_tenant_id: UUID = field(repr=False)
    entra_object_id: UUID = field(repr=False)


@dataclass(frozen=True, slots=True)
class WorkflowCreateResult:
    workflow_run_id: int
    workflow: str
    state: str
    created: bool
    correlation_id: UUID
    model_revision: int
    selected_scope_count: int
    prompt_snapshot_count: int
    created_time: datetime
    denial_code: str | None = None
    code_generation_coverage_mode: str | None = None
    sql_generation_guide_version_id: int | None = None


@dataclass(frozen=True, slots=True)
class WorkflowClaimResult:
    workflow_run_id: int
    tenant_id: int
    model_id: int
    model_revision: int
    workflow: str
    workflow_execution_mode: str | None
    correlation_id: UUID
    actor_principal_type: str
    actor_entra_tenant_id: UUID
    actor_entra_object_id: UUID
    claim_token: UUID = field(repr=False)
    claimed_time: datetime
    expires_time: datetime
    recovery_count: int


@dataclass(frozen=True, slots=True)
class WorkflowLeaseResult:
    workflow_run_id: int
    succeeded: bool
    heartbeat_time: datetime | None = None
    expires_time: datetime | None = None


class NotebookWorkflowControlClient:
    """Call only actor-free notebook Workflow wrappers on one connection."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def current_principal(self) -> NotebookPrincipal:
        row = self._fetchone(
            """
            SELECT principal_display_name,
                   principal_type,
                   databricks_environment_code,
                   entra_tenant_id,
                   entra_object_id,
                   is_super_admin
              FROM security.current_notebook_principal()
            """,
            None,
            operation="resolve the notebook workload identity",
        )
        if row is None:
            raise NotebookAuthorizationError(
                "The notebook database login has no active Super Admin workload binding."
            )
        if row.get("is_super_admin") is not True:
            raise NotebookAuthorizationError(
                "The notebook database login has no active Super Admin workload binding."
            )
        principal_type = _required_text(row.get("principal_type"), maximum=30)
        if principal_type != "service_principal":
            raise NotebookAuthorizationError(
                "The notebook database login has no active Super Admin workload binding."
            )
        environment_code = _required_text(
            row.get("databricks_environment_code"),
            maximum=100,
        )
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,99}", environment_code) is None:
            raise NotebookDatabaseError(
                "The notebook database returned an invalid workload identity."
            )
        return NotebookPrincipal(
            display_name=_required_text(row.get("principal_display_name"), maximum=200),
            principal_type=principal_type,
            databricks_environment_code=environment_code,
            entra_tenant_id=_required_uuid(row.get("entra_tenant_id")),
            entra_object_id=_required_uuid(row.get("entra_object_id")),
        )

    def create_workflow_run(
        self,
        request: NotebookWorkflowRequest,
    ) -> WorkflowCreateResult:
        parameters = _create_parameters(request)
        row = self._fetchone(
            """
            SELECT created,
                   denial_code,
                   workflow_run_id,
                   workflow_run_state,
                   correlation_id,
                   prompt_snapshot_count,
                   created_time,
                   model_revision,
                   selected_scope_count,
                   code_generation_coverage_mode,
                   sql_generation_guide_version_id
              FROM application.create_notebook_workflow_run(
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::INTEGER,
                  %s::INTEGER,
                  %s::BIGINT[],
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::UUID,
                  %s::JSONB,
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::VARCHAR,
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::VARCHAR,
                  %s::BIGINT
              )
            """,
            parameters,
            operation="create the notebook Workflow Run",
        )
        result = _required_row(row, operation="create")
        workflow_run_id = _positive_integer(result.get("workflow_run_id"))
        correlation_id = _required_uuid(result.get("correlation_id"))
        if correlation_id != request.idempotency_key:
            raise NotebookDatabaseError(
                "The notebook database returned an invalid Workflow create result."
            )
        state = _required_text(result.get("workflow_run_state"), maximum=30)
        if state not in _WORKFLOW_STATES:
            raise NotebookDatabaseError(
                "The notebook database returned an invalid Workflow create result."
            )
        created = result.get("created")
        if type(created) is not bool:
            raise NotebookDatabaseError(
                "The notebook database returned an invalid Workflow create result."
            )
        return WorkflowCreateResult(
            workflow_run_id=workflow_run_id,
            workflow=request.workflow,
            state=state,
            created=created,
            correlation_id=correlation_id,
            model_revision=_positive_integer(result.get("model_revision")),
            selected_scope_count=_positive_integer(result.get("selected_scope_count")),
            prompt_snapshot_count=_nonnegative_integer(result.get("prompt_snapshot_count")),
            created_time=_required_timestamp(result.get("created_time")),
            denial_code=_optional_code(result.get("denial_code"), maximum=50),
            code_generation_coverage_mode=_optional_code(
                result.get("code_generation_coverage_mode"),
                maximum=30,
            ),
            sql_generation_guide_version_id=_optional_positive_integer(
                result.get("sql_generation_guide_version_id")
            ),
        )

    def start_and_claim_workflow_run(
        self,
        request: NotebookWorkflowRequest,
        created_run: WorkflowCreateResult,
        *,
        lease_duration_seconds: int,
    ) -> WorkflowClaimResult:
        _validate_lease_duration(lease_duration_seconds)
        if (
            created_run.workflow != request.workflow
            or created_run.correlation_id != request.idempotency_key
            or created_run.model_revision != request.expected_model_revision
        ):
            raise NotebookConfigurationError(
                "The Workflow create result does not match the notebook request."
            )
        row = self._fetchone(
            """
            SELECT workflow_run_id,
                   tenant_id,
                   model_id,
                   model_revision,
                   model_workflow,
                   workflow_execution_mode,
                   correlation_id,
                   actor_principal_type,
                   actor_entra_tenant_id,
                   actor_entra_object_id,
                   workflow_run_claim_token,
                   workflow_run_claimed_time,
                   workflow_run_claim_expires_time,
                   workflow_run_recovery_count
              FROM application.start_and_claim_notebook_workflow_run(
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::VARCHAR,
                  %s::INTEGER
              )
            """,
            (
                request.tenant_id,
                request.model_id,
                created_run.workflow_run_id,
                request.expected_model_revision,
                request.workflow,
                lease_duration_seconds,
            ),
            operation="start and claim the notebook Workflow Run",
        )
        result = _required_row(row, operation="claim")
        claim = WorkflowClaimResult(
            workflow_run_id=_positive_integer(result.get("workflow_run_id")),
            tenant_id=_positive_integer(result.get("tenant_id")),
            model_id=_positive_integer(result.get("model_id")),
            model_revision=_positive_integer(result.get("model_revision")),
            workflow=_required_text(result.get("model_workflow"), maximum=30),
            workflow_execution_mode=_optional_code(
                result.get("workflow_execution_mode"),
                maximum=50,
            ),
            correlation_id=_required_uuid(result.get("correlation_id")),
            actor_principal_type=_required_text(
                result.get("actor_principal_type"),
                maximum=30,
            ),
            actor_entra_tenant_id=_required_uuid(result.get("actor_entra_tenant_id")),
            actor_entra_object_id=_required_uuid(result.get("actor_entra_object_id")),
            claim_token=_required_uuid(result.get("workflow_run_claim_token")),
            claimed_time=_required_timestamp(result.get("workflow_run_claimed_time")),
            expires_time=_required_timestamp(result.get("workflow_run_claim_expires_time")),
            recovery_count=_bounded_integer(result.get("workflow_run_recovery_count"), 0, 5),
        )
        if (
            claim.workflow_run_id != created_run.workflow_run_id
            or claim.tenant_id != request.tenant_id
            or claim.model_id != request.model_id
            or claim.model_revision != request.expected_model_revision
            or claim.workflow != request.workflow
            or claim.correlation_id != request.idempotency_key
            or claim.actor_principal_type != "service_principal"
            or claim.expires_time <= claim.claimed_time
        ):
            raise NotebookDatabaseError(
                "The notebook database returned an invalid Workflow claim result."
            )
        return claim

    def renew_workflow_run_claim(
        self,
        claim: WorkflowClaimResult,
        *,
        lease_duration_seconds: int,
    ) -> WorkflowLeaseResult:
        _validate_lease_duration(lease_duration_seconds)
        row = self._fetchone(
            """
            SELECT workflow_run_id,
                   workflow_run_claim_heartbeat_time,
                   workflow_run_claim_expires_time
              FROM application.renew_notebook_workflow_run_claim(
                  %s::BIGINT,
                  %s::UUID,
                  %s::INTEGER
              )
            """,
            (claim.workflow_run_id, claim.claim_token, lease_duration_seconds),
            operation="renew the notebook Workflow Run claim",
        )
        result = _required_row(row, operation="renew")
        workflow_run_id = _positive_integer(result.get("workflow_run_id"))
        heartbeat_time = _required_timestamp(result.get("workflow_run_claim_heartbeat_time"))
        expires_time = _required_timestamp(result.get("workflow_run_claim_expires_time"))
        if workflow_run_id != claim.workflow_run_id or expires_time <= heartbeat_time:
            raise NotebookDatabaseError(
                "The notebook database returned an invalid Workflow lease result."
            )
        return WorkflowLeaseResult(
            workflow_run_id=workflow_run_id,
            succeeded=True,
            heartbeat_time=heartbeat_time,
            expires_time=expires_time,
        )

    def release_workflow_run_claim(
        self,
        claim: WorkflowClaimResult,
    ) -> WorkflowLeaseResult:
        row = self._fetchone(
            """
            SELECT application.release_notebook_workflow_run_claim(
                       %s::BIGINT,
                       %s::UUID
                   ) AS released
            """,
            (claim.workflow_run_id, claim.claim_token),
            operation="release the notebook Workflow Run claim",
        )
        result = _required_row(row, operation="release")
        released = result.get("released")
        if type(released) is not bool:
            raise NotebookDatabaseError(
                "The notebook database returned an invalid Workflow lease result."
            )
        return WorkflowLeaseResult(
            workflow_run_id=claim.workflow_run_id,
            succeeded=released,
        )

    def _fetchone(
        self,
        statement: str,
        parameters: tuple[object, ...] | None,
        *,
        operation: str,
    ) -> Mapping[str, Any] | None:
        try:
            row = self._connection.execute(statement, parameters).fetchone()
        except (NotebookAuthorizationError, NotebookConfigurationError, NotebookDatabaseError):
            raise
        except Exception:
            raise NotebookDatabaseError(f"The notebook database could not {operation}.") from None
        if row is None:
            return None
        if not isinstance(row, Mapping):
            raise NotebookDatabaseError(
                "The notebook database returned an invalid Workflow control result."
            )
        return cast(Mapping[str, Any], row)


def _create_parameters(request: NotebookWorkflowRequest) -> tuple[object, ...]:
    payload = request.create_payload
    if request.workflow not in _WORKFLOWS or frozenset(payload) != _CREATE_PAYLOAD_KEYS:
        raise NotebookConfigurationError("The notebook Workflow create payload is invalid.")
    if (
        payload["expected_model_revision"] != request.expected_model_revision
        or payload["model_workflow"] != request.workflow
    ):
        raise NotebookConfigurationError(
            "The notebook Workflow create payload does not match its request."
        )
    selected_object_ids = payload["selected_object_ids"]
    if not isinstance(selected_object_ids, list):
        raise NotebookConfigurationError("The notebook Workflow selected scope is invalid.")
    selected_values = cast(list[object], selected_object_ids)
    if any(type(object_id) is not int for object_id in selected_values):
        raise NotebookConfigurationError("The notebook Workflow selected scope is invalid.")
    selected_ids = cast(list[int], selected_values)
    agent = payload["agent"]
    if agent is None:
        agent_values: tuple[object, ...] = (None, None, None, None, None, None)
    elif isinstance(agent, Mapping):
        agent_mapping = cast(Mapping[str, object], agent)
        if set(agent_mapping) != {
            "sdk_code",
            "provider_code",
            "model_code",
            "reasoning_effort_code",
            "max_turns",
            "validation_retry_count",
        }:
            raise NotebookConfigurationError("The notebook Workflow agent input is invalid.")
        agent_values = (
            agent_mapping["sdk_code"],
            agent_mapping["provider_code"],
            agent_mapping["model_code"],
            agent_mapping["reasoning_effort_code"],
            agent_mapping["max_turns"],
            agent_mapping["validation_retry_count"],
        )
    else:
        raise NotebookConfigurationError("The notebook Workflow agent input is invalid.")
    prompt_overrides = payload["prompt_overrides"]
    if not isinstance(prompt_overrides, Mapping):
        raise NotebookConfigurationError("The notebook Workflow prompt overrides are invalid.")
    prompt_override_mapping = cast(Mapping[str, object], prompt_overrides)
    return (
        request.tenant_id,
        request.model_id,
        request.expected_model_revision,
        request.workflow,
        payload["workflow_execution_mode"],
        *agent_values,
        selected_ids,
        payload["modeled_entity_type"],
        payload["requested_batch_id"],
        request.idempotency_key,
        json.dumps(prompt_override_mapping, sort_keys=True, separators=(",", ":")),
        payload["mapping_operation"],
        payload["mapping_coverage_mode"],
        payload["mapping_artifact_type"],
        payload["mapping_source_system_id"],
        payload["mapping_object_output_template_id"],
        payload["mapping_attribute_output_template_id"],
        payload["code_generation_coverage_mode"],
        payload["sql_generation_guide_version_id"],
    )


def _required_row(
    row: Mapping[str, Any] | None,
    *,
    operation: str,
) -> Mapping[str, Any]:
    if row is None:
        raise NotebookDatabaseError(
            f"The notebook Workflow {operation} operation returned no result."
        )
    return row


def _required_text(value: Any, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or re.search(r"[\x00-\x1f\x7f]", value)
    ):
        raise NotebookDatabaseError("The notebook database returned invalid bounded text.")
    return value


def _optional_code(value: Any, *, maximum: int) -> str | None:
    if value is None:
        return None
    code = _required_text(value, maximum=maximum)
    if re.fullmatch(r"[a-z][a-z0-9_.-]*", code) is None:
        raise NotebookDatabaseError("The notebook database returned an invalid code.")
    return code


def _positive_integer(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise NotebookDatabaseError("The notebook database returned an invalid integer.")
    return value


def _optional_positive_integer(value: Any) -> int | None:
    if value is None:
        return None
    return _positive_integer(value)


def _nonnegative_integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise NotebookDatabaseError("The notebook database returned an invalid integer.")
    return value


def _bounded_integer(value: Any, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise NotebookDatabaseError("The notebook database returned an invalid integer.")
    return value


def _required_uuid(value: Any) -> UUID:
    if not isinstance(value, UUID) or value.int == 0:
        raise NotebookDatabaseError("The notebook database returned an invalid UUID.")
    return value


def _required_timestamp(value: Any) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise NotebookDatabaseError("The notebook database returned an invalid timestamp.")
    return value


def _validate_lease_duration(value: int) -> None:
    if type(value) is not int or not 1 <= value <= 300:
        raise NotebookConfigurationError(
            "Workflow lease duration must be from 1 through 300 seconds."
        )


__all__ = [
    "NotebookPrincipal",
    "NotebookWorkflowControlClient",
    "WorkflowClaimResult",
    "WorkflowCreateResult",
    "WorkflowLeaseResult",
]
