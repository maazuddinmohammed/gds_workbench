"""Authenticated Databricks notebook client for the Workbench App API."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlparse
from uuid import UUID

_MAX_RESPONSE_BYTES = 1024 * 1024
_INITIAL_POLL_INTERVAL_SECONDS = 2.0
_MAX_POLL_INTERVAL_SECONDS = 30.0
_TERMINAL_STATES = {"completed", "completed_with_repair", "failed"}
_EXECUTION_ROUTES: Mapping[tuple[str, str | None], str] = {
    ("profiling", None): "profiling/runs",
    ("analysis", "inference"): "analysis/inference-runs",
    ("analysis", "validation"): "analysis/validation-runs",
    ("conceptual", None): "conceptual/runs",
    ("logical", None): "logical/runs",
    ("dimensional", None): "dimensional/runs",
    ("mapping", None): "mapping/runs",
    ("code_generation", None): "code-generation/runs",
}


class NotebookConfigurationError(ValueError):
    """A notebook input or Databricks runtime value is invalid."""


class NotebookApiError(RuntimeError):
    """The Workbench App API returned a safe, bounded failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.correlation_id = correlation_id


class NotebookTenantWorkflowConflictError(NotebookApiError):
    """A different Workflow Run already owns the Tenant-wide execution slot."""

    def __init__(self, workflow_run_id: int, *, correlation_id: str | None = None) -> None:
        super().__init__(
            "Another Workflow Run is already active for this Tenant. "
            f"Workflow Run {workflow_run_id} remains queued. After the active Run "
            "finishes, rerun this notebook with the same IdempotencyKey.",
            status_code=409,
            error_code="tenant_workflow_conflict",
            correlation_id=correlation_id,
        )
        self.workflow_run_id = workflow_run_id


@dataclass(frozen=True)
class WorkflowLaunchResult:
    """Small, non-secret result suitable for a notebook output cell."""

    workflow_run_id: int
    workflow: str
    state: str
    created: bool
    failure_code: str | None = None
    failure_message: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "workflow_run_id": self.workflow_run_id,
            "workflow": self.workflow,
            "state": self.state,
            "created": self.created,
        }
        if self.failure_code is not None:
            result["failure_code"] = self.failure_code
        if self.failure_message is not None:
            result["failure_message"] = self.failure_message
        return result


class DatabricksAppApiClient:
    """Call the Databricks App as the interactive notebook user."""

    def __init__(
        self,
        *,
        app_url: str,
        workspace_url: str,
        app_client_id: str,
        notebook_token_provider: Callable[[], str],
        session: Any,
        request_timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._app_url = _validated_https_origin(
            app_url,
            label="Databricks App URL",
            required_host_suffix=".databricksapps.com",
        )
        self._workspace_url = _validated_https_origin(
            workspace_url,
            label="Databricks workspace URL",
        )
        if not _is_safe_text(app_client_id, maximum=200):
            raise NotebookConfigurationError("The Databricks App OAuth client ID is unavailable.")
        if request_timeout_seconds <= 0 or request_timeout_seconds > 120:
            raise NotebookConfigurationError(
                "The request timeout must be between 0 and 120 seconds."
            )
        self._app_client_id = app_client_id
        self._notebook_token_provider = notebook_token_provider
        self._session = session
        self._request_timeout_seconds = request_timeout_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._audience_token: str | None = None

    @classmethod
    def from_notebook(
        cls,
        *,
        app_name: str,
        dbutils: Any,
        workspace_client: Any | None = None,
        session: Any | None = None,
        request_timeout_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> DatabricksAppApiClient:
        """Resolve the App and prepare the documented notebook token exchange."""
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,99}", app_name):
            raise NotebookConfigurationError("AppName must be a Databricks App name.")

        if workspace_client is None:
            try:
                from databricks.sdk import WorkspaceClient

                workspace_client = WorkspaceClient()
            except Exception:
                raise NotebookConfigurationError(
                    "Databricks unified authentication is unavailable in this notebook."
                ) from None
        if session is None:
            try:
                import requests

                session = requests.Session()
            except Exception:
                raise NotebookConfigurationError(
                    "The requests dependency is unavailable in this notebook."
                ) from None

        try:
            app = workspace_client.apps.get(app_name)
            workspace_url = workspace_client.config.host
            app_url = app.url
            app_client_id = app.oauth2_app_client_id
        except Exception:
            raise NotebookConfigurationError(
                "The Databricks App could not be resolved. Verify AppName and CAN USE access."
            ) from None

        def notebook_token_provider() -> str:
            try:
                token = (
                    dbutils.notebook.entry_point.getDbutils()
                    .notebook()
                    .getContext()
                    .apiToken()
                    .get()
                )
            except Exception:
                raise NotebookConfigurationError(
                    "The notebook user token is unavailable on this compute."
                ) from None
            if not isinstance(token, str) or not token:
                raise NotebookConfigurationError(
                    "The notebook user token is unavailable on this compute."
                )
            return token

        return cls(
            app_url=app_url,
            workspace_url=workspace_url,
            app_client_id=app_client_id,
            notebook_token_provider=notebook_token_provider,
            session=session,
            request_timeout_seconds=request_timeout_seconds,
            sleep=sleep,
            monotonic=monotonic,
        )

    def __repr__(self) -> str:
        return (
            f"DatabricksAppApiClient(app_url={self._app_url!r}, "
            f"request_timeout_seconds={self._request_timeout_seconds!r})"
        )

    def launch_workflow(
        self,
        *,
        tenant_id: int,
        model_id: int,
        workflow: str,
        analysis_operation: str | None,
        expected_model_revision: int,
        idempotency_key: UUID,
        create_payload: Mapping[str, object],
        wait_timeout_seconds: int,
    ) -> WorkflowLaunchResult:
        """Create idempotently, request execution, then optionally poll."""
        if type(tenant_id) is not int or tenant_id <= 0:
            raise NotebookConfigurationError("TenantID must be a positive integer.")
        if type(model_id) is not int or model_id <= 0:
            raise NotebookConfigurationError("ModelID must be a positive integer.")
        if type(expected_model_revision) is not int or expected_model_revision <= 0:
            raise NotebookConfigurationError("ExpectedModelRevision must be a positive integer.")
        if type(wait_timeout_seconds) is not int or not 0 <= wait_timeout_seconds <= 86_400:
            raise NotebookConfigurationError("WaitTimeoutSeconds must be from 0 through 86400.")
        route = _EXECUTION_ROUTES.get((workflow, analysis_operation))
        if route is None:
            raise NotebookConfigurationError("The requested Workflow is unavailable.")

        run_base_path = f"/api/v1/tenants/{tenant_id}/models/{model_id}/runs"
        created_run = self._app_request(
            "POST",
            run_base_path,
            headers={"Idempotency-Key": str(idempotency_key)},
            json_body=dict(create_payload),
        )
        workflow_run_id = _required_positive_int(created_run, "workflow_run_id")
        created = created_run.get("created")
        if type(created) is not bool:
            raise NotebookApiError("The Workbench App returned an invalid create response.")

        try:
            started_run = self._app_request(
                "POST",
                f"/api/v1/tenants/{tenant_id}/models/{model_id}/{route}/{workflow_run_id}/execute",
                json_body=_execute_payload(workflow, expected_model_revision, create_payload),
            )
        except NotebookApiError as error:
            if error.status_code == 409 and error.error_code == "tenant_workflow_conflict":
                raise NotebookTenantWorkflowConflictError(
                    workflow_run_id,
                    correlation_id=error.correlation_id,
                ) from None
            raise

        state = _required_run_state(started_run)
        workflow_label = f"analysis_{analysis_operation}" if workflow == "analysis" else workflow
        if wait_timeout_seconds == 0 or state in _TERMINAL_STATES:
            return WorkflowLaunchResult(
                workflow_run_id=workflow_run_id,
                workflow=workflow_label,
                state=state,
                created=created,
                failure_code=_optional_safe_text(started_run, "failure_code", maximum=100),
                failure_message=_optional_safe_text(started_run, "failure_message", maximum=2000),
            )

        deadline = self._monotonic() + wait_timeout_seconds
        poll_interval_seconds = _INITIAL_POLL_INTERVAL_SECONDS
        while state not in _TERMINAL_STATES:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                break
            self._sleep(min(poll_interval_seconds, remaining))
            run = self._app_request("GET", f"{run_base_path}/{workflow_run_id}")
            state = _required_run_state(run)
            if state in _TERMINAL_STATES:
                return WorkflowLaunchResult(
                    workflow_run_id=workflow_run_id,
                    workflow=workflow_label,
                    state=state,
                    created=created,
                    failure_code=_optional_safe_text(run, "failure_code", maximum=100),
                    failure_message=_optional_safe_text(run, "failure_message", maximum=2000),
                )
            poll_interval_seconds = min(
                poll_interval_seconds * 2,
                _MAX_POLL_INTERVAL_SECONDS,
            )

        return WorkflowLaunchResult(
            workflow_run_id=workflow_run_id,
            workflow=workflow_label,
            state=state,
            created=created,
        )

    def _app_request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> dict[str, Any]:
        if not path.startswith("/api/") or ".." in path or "?" in path or "#" in path:
            raise NotebookConfigurationError("The Workbench App API path is invalid.")
        for attempt in range(2):
            token = self._audience_token or self._exchange_audience_token()
            request_headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
            if json_body is not None:
                request_headers["Content-Type"] = "application/json"
            if headers is not None:
                request_headers.update(headers)
            status_code, payload = self._request_json(
                method,
                f"{self._app_url}{path}",
                headers=request_headers,
                json_body=json_body,
            )
            if status_code == 401 and attempt == 0:
                self._audience_token = None
                continue
            if not 200 <= status_code < 300:
                raise _api_error(status_code, payload)
            return payload
        raise NotebookApiError(
            "The Workbench App rejected notebook authentication.", status_code=401
        )

    def _exchange_audience_token(self) -> str:
        notebook_token = self._notebook_token_provider()
        status_code, payload = self._request_json(
            "POST",
            f"{self._workspace_url}/oidc/v1/token",
            headers={"Accept": "application/json"},
            form_body={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": notebook_token,
                "subject_token_type": (
                    "urn:databricks:params:oauth:token-type:personal-access-token"
                ),
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "scope": "all-apis",
                "audience": self._app_client_id,
            },
        )
        del notebook_token
        if not 200 <= status_code < 300:
            raise NotebookApiError(
                "Databricks could not exchange the notebook identity for an App token.",
                status_code=status_code,
                error_code="notebook_token_exchange_failed",
            )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token or len(token) > 16_384:
            raise NotebookApiError("Databricks returned an invalid App token response.")
        self._audience_token = token
        return token

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json_body: Mapping[str, object] | None = None,
        form_body: Mapping[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            response = self._session.request(
                method,
                url,
                headers=dict(headers),
                json=None if json_body is None else dict(json_body),
                data=None if form_body is None else dict(form_body),
                timeout=self._request_timeout_seconds,
                allow_redirects=False,
                stream=True,
            )
        except Exception:
            raise NotebookApiError("The Databricks endpoint could not be reached.") from None

        try:
            raw = bytearray()
            for chunk in response.iter_content(chunk_size=64 * 1024):
                raw.extend(chunk)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise NotebookApiError("The Databricks endpoint response was too large.")
            try:
                decoded: object = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                decoded = {}
            payload = cast(dict[str, Any], decoded) if isinstance(decoded, dict) else {}
            return int(response.status_code), payload
        except NotebookApiError:
            raise
        except Exception:
            raise NotebookApiError("The Databricks endpoint response could not be read.") from None
        finally:
            with suppress(Exception):
                response.close()


def _execute_payload(
    workflow: str,
    expected_model_revision: int,
    create_payload: Mapping[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {"expected_model_revision": expected_model_revision}
    if workflow in {"conceptual", "logical", "dimensional", "mapping"}:
        payload["execution_mode"] = create_payload.get("workflow_execution_mode")
    return payload


def _validated_https_origin(
    value: object,
    *,
    label: str,
    required_host_suffix: str | None = None,
) -> str:
    if not isinstance(value, str):
        raise NotebookConfigurationError(f"{label} is unavailable.")
    parsed = urlparse(value)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise NotebookConfigurationError(f"{label} must be a secure HTTPS origin.")
    if required_host_suffix is not None and not host.endswith(required_host_suffix):
        raise NotebookConfigurationError(f"{label} is not a Databricks Apps URL.")
    try:
        port_number = parsed.port
    except ValueError:
        raise NotebookConfigurationError(f"{label} must be a secure HTTPS origin.") from None
    port = f":{port_number}" if port_number is not None else ""
    return f"https://{host}{port}{parsed.path.rstrip('/')}"


def _api_error(status_code: int, payload: Mapping[str, Any]) -> NotebookApiError:
    raw_error: object = payload.get("error")
    error = cast(dict[str, object], raw_error) if isinstance(raw_error, dict) else {}
    error_code = error.get("code")
    message = error.get("message")
    correlation_id = error.get("correlation_id")
    safe_code = error_code if isinstance(error_code, str) and _is_code(error_code) else None
    safe_message = (
        message
        if isinstance(message, str) and _is_safe_text(message, maximum=2000)
        else f"The Workbench App request failed with HTTP {status_code}."
    )
    safe_correlation_id = (
        correlation_id if isinstance(correlation_id, str) and _is_uuid(correlation_id) else None
    )
    return NotebookApiError(
        safe_message,
        status_code=status_code,
        error_code=safe_code,
        correlation_id=safe_correlation_id,
    )


def _required_positive_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value <= 0:
        raise NotebookApiError("The Workbench App returned an invalid workflow response.")
    return value


def _required_run_state(payload: Mapping[str, Any]) -> str:
    value = payload.get("workflow_run_state")
    if value not in {"queued", "running", *_TERMINAL_STATES}:
        raise NotebookApiError("The Workbench App returned an invalid workflow state.")
    return value


def _optional_safe_text(payload: Mapping[str, Any], key: str, *, maximum: int) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not _is_safe_text(value, maximum=maximum):
        raise NotebookApiError("The Workbench App returned invalid workflow failure metadata.")
    return value


def _is_code(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", value) is not None


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _is_safe_text(value: object, *, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value.encode("utf-8")) <= maximum
        and re.search(r"[\x00-\x1f\x7f]", value) is None
    )


__all__ = [
    "DatabricksAppApiClient",
    "NotebookApiError",
    "NotebookConfigurationError",
    "NotebookTenantWorkflowConflictError",
    "WorkflowLaunchResult",
]
