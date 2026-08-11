"""Stable, non-disclosing application failures."""

from dataclasses import dataclass


@dataclass(slots=True)
class WorkbenchError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class InvalidRequestError(WorkbenchError):
    def __init__(self, message: str = "The request is invalid.") -> None:
        super().__init__(code="invalid_request", message=message)


class AuthorizationDeniedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="authorization_denied",
            message="The current Principal is not authorized for this operation.",
        )


class TenantNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(code="tenant_not_found", message="Tenant was not found.")


class TenantLockRequiredError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="tenant_lock_required",
            message="An active Tenant Lock owned by the current Principal is required.",
        )


class TenantLockedError(WorkbenchError):
    def __init__(self, owner_display_name: str) -> None:
        super().__init__(
            code="tenant_locked",
            message=f"Tenant is locked by {owner_display_name}.",
        )


class DependencyUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dependency_unavailable",
            message="A required dependency is unavailable.",
        )
