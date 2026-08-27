"""Transport-neutral Databricks connection values."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DatabricksSqlConnection:
    server_hostname: str = field(repr=False)
    http_path: str = field(repr=False)
    access_token: str = field(repr=False)


__all__ = ["DatabricksSqlConnection"]
