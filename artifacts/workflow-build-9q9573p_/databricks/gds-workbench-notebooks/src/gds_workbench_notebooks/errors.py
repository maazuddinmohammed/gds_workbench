"""Bounded notebook errors that never include secrets or raw database output."""


class NotebookConfigurationError(ValueError):
    """A notebook input or runtime setting is invalid."""


class NotebookDatabaseError(RuntimeError):
    """A notebook database operation failed without exposing driver details."""


class NotebookAuthorizationError(RuntimeError):
    """The notebook database login has no active governed workload binding."""


__all__ = [
    "NotebookAuthorizationError",
    "NotebookConfigurationError",
    "NotebookDatabaseError",
]
