"""Validated Databricks Model Serving configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Self, cast

from gds_etl_workbench.configuration import ConfigurationError
from pydantic import BaseModel, ConfigDict, Field


class AgentProviderConnection(BaseModel):
    """Non-secret logical provider to physical serving-endpoint mapping."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_code: Literal["databricks"]
    model_endpoint: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$",
    )
    timeout_seconds: int = Field(ge=1, le=600)


class AgentRuntimeConfiguration(BaseModel):
    """Select deterministic local fakes or one Databricks endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: Literal["fake", "remote"]
    timeout_seconds: int = Field(ge=1, le=600)
    connections: tuple[AgentProviderConnection, ...]

    @classmethod
    def from_environment(
        cls,
        source: Mapping[str, str],
        *,
        production: bool,
    ) -> Self:
        raw_mode = source.get(
            "GDS_WEB_AGENT_EXECUTION_MODE",
            "remote" if production else "fake",
        ).strip()
        if raw_mode not in {"fake", "remote"}:
            raise ConfigurationError("GDS_WEB_AGENT_EXECUTION_MODE must be fake or remote")
        if production and raw_mode == "fake":
            raise ConfigurationError("fake agent execution is available only locally")

        raw_timeout = source.get("GDS_WEB_AGENT_TIMEOUT_SECONDS", "120").strip()
        try:
            timeout_seconds = int(raw_timeout)
        except ValueError as exc:
            raise ConfigurationError("GDS_WEB_AGENT_TIMEOUT_SECONDS must be an integer") from exc
        if not 1 <= timeout_seconds <= 600:
            raise ConfigurationError("GDS_WEB_AGENT_TIMEOUT_SECONDS must be between 1 and 600")

        endpoint = source.get("GDS_WEB_DATABRICKS_MODEL_ENDPOINT", "").strip()
        if raw_mode == "fake" and endpoint:
            raise ConfigurationError("fake agent execution does not accept a model endpoint")
        if raw_mode == "remote" and not endpoint:
            raise ConfigurationError(
                "remote agent execution requires GDS_WEB_DATABRICKS_MODEL_ENDPOINT"
            )
        try:
            connections = (
                (
                    AgentProviderConnection(
                        provider_code="databricks",
                        model_endpoint=endpoint,
                        timeout_seconds=timeout_seconds,
                    ),
                )
                if endpoint
                else ()
            )
        except ValueError as exc:
            raise ConfigurationError("GDS_WEB_DATABRICKS_MODEL_ENDPOINT is invalid") from exc
        return cls(
            mode=cast(Literal["fake", "remote"], raw_mode),
            timeout_seconds=timeout_seconds,
            connections=connections,
        )
