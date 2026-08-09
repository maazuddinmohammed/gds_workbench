"""Stable, non-disclosing application failures."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkbenchError(Exception):
    code: str
    message: str
    retryable: bool = False

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


class DependencyUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dependency_unavailable",
            message="A required dependency is unavailable.",
            retryable=True,
        )
