"""Stable, non-disclosing HTTP error responses."""

from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from gds_etl_workbench.adapters.auth.identity import AuthenticationError
from gds_etl_workbench.domain.errors import WorkbenchError


async def authentication_error_response(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    if not isinstance(error, AuthenticationError):
        raise error

    return _safe_error_response(
        code=error.public_code,
        message=error.message,
        status_code=error.http_status,
        retryable=False,
    )


async def workbench_error_response(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    if not isinstance(error, WorkbenchError):
        raise error
    status_code = 400
    if error.code == "authorization_denied":
        status_code = 403
    elif error.code.endswith("_not_found"):
        status_code = 404
    elif error.code == "invalid_request":
        status_code = 422
    elif error.code == "dependency_unavailable":
        status_code = 503
    elif (
        "conflict" in error.code
        or error.code in {"tenant_locked", "tenant_lock_required"}
        or error.code.endswith("_not_active")
    ):
        status_code = 409
    return _safe_error_response(
        code=error.code,
        message=error.message,
        status_code=status_code,
        retryable=error.code == "dependency_unavailable",
    )


def _safe_error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    retryable: bool,
) -> JSONResponse:
    correlation_id = str(uuid4())
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "correlation_id": correlation_id,
            }
        },
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "X-Correlation-ID": correlation_id,
        },
    )
