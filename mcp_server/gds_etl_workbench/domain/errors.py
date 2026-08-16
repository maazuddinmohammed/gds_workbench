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


class MetadataChangeSetNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="metadata_change_set_not_found",
            message="Metadata Change Set was not found for the current Principal and Tenant.",
        )


class MetadataChangeSetNotActiveError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="metadata_change_set_not_active",
            message="Metadata Change Set is no longer active.",
        )


class MetadataChangeSetNotValidatedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="metadata_change_set_not_validated",
            message="Metadata Change Set must pass validation before it can be applied.",
        )


class ObjectLockedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="object_locked",
            message="Object is locked; neither it nor its Attributes can be changed.",
        )


class CandidateDigestConflictError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="candidate_digest_conflict",
            message="Validated Metadata Change Set content changed before apply.",
        )


class ModelChangeSetNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_change_set_not_found",
            message="Model Change Set was not found for the current Principal and Model.",
        )


class ModelChangeSetNotActiveError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_change_set_not_active",
            message="Model Change Set is no longer active.",
        )


class ModelChangeSetNotValidatedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_change_set_not_validated",
            message="Model Change Set must pass validation before it can be applied.",
        )


class DraftRevisionConflictError(WorkbenchError):
    def __init__(self, current_revision: int) -> None:
        super().__init__(
            code="draft_revision_conflict",
            message=f"Draft revision changed; current revision is {current_revision}.",
        )


class DependencyUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="dependency_unavailable",
            message="A required dependency is unavailable.",
        )


class DatabricksConnectionNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="databricks_connection_not_found",
            message="An active global Databricks Connection was not found.",
        )


class DatabricksConnectionConfigurationError(WorkbenchError):
    def __init__(self, reason: str) -> None:
        messages = {
            "missing": (
                "The Connection is missing a complete Databricks host, HTTP path, "
                "and token configuration."
            ),
            "ambiguous": (
                "The Connection has complete Databricks values for more than one Environment."
            ),
            "invalid": "The Connection has invalid Databricks configuration values.",
        }
        super().__init__(
            code=f"databricks_connection_configuration_{reason}",
            message=messages.get(reason, messages["invalid"]),
        )


class DatabricksConnectionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="databricks_connection_failed",
            message=(
                "The Databricks SQL Warehouse connection failed. Check the configured "
                "host, HTTP path, token, Warehouse state, and network access."
            ),
        )


class DatabricksStatementFailedError(WorkbenchError):
    def __init__(self, statement_index: int) -> None:
        super().__init__(
            code="databricks_statement_failed",
            message=(
                f"Databricks rejected statement {statement_index}. Check its syntax, "
                "object names, permissions, and temporary-object support."
            ),
        )


class DatabricksResultTooLargeError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="databricks_result_too_large",
            message="The bounded Databricks result is too large to return safely.",
        )
