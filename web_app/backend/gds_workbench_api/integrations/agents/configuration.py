"""Validated deployment configuration for agent-provider boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Self, cast

from gds_etl_workbench.configuration import ConfigurationError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class AgentProviderConnection(BaseModel):
    """Process-local provider values that must never be serialized or logged."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    api_key: SecretStr = Field(repr=False)
    base_url: str = Field(min_length=1, max_length=2000, repr=False)
    timeout_seconds: int = Field(ge=1, le=600)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not value.startswith("https://") or "\x00" in value:
            raise ValueError("Agent provider base URL must use HTTPS")
        return value


class AgentRuntimeConfiguration(BaseModel):
    """Select safe local fakes or explicitly configured remote providers."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: Literal["fake", "remote"]
    timeout_seconds: int = Field(ge=1, le=600)
    connections: tuple[AgentProviderConnection, ...] = Field(repr=False)

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

        connections = tuple(
            connection
            for provider_code, url_key, api_key_key in (
                (
                    "microsoft_foundry",
                    "GDS_WEB_FOUNDRY_BASE_URL",
                    "GDS_WEB_FOUNDRY_API_KEY",
                ),
                ("openai", "GDS_WEB_OPENAI_BASE_URL", "GDS_WEB_OPENAI_API_KEY"),
            )
            if (
                connection := _provider_connection(
                    source,
                    provider_code=provider_code,
                    url_key=url_key,
                    api_key_key=api_key_key,
                    timeout_seconds=timeout_seconds,
                )
            )
            is not None
        )
        if raw_mode == "fake" and connections:
            raise ConfigurationError("fake agent execution does not accept provider settings")
        if raw_mode == "remote" and not connections:
            raise ConfigurationError("remote agent execution requires at least one provider")
        return cls(
            mode=cast(Literal["fake", "remote"], raw_mode),
            timeout_seconds=timeout_seconds,
            connections=connections,
        )


def _provider_connection(
    source: Mapping[str, str],
    *,
    provider_code: str,
    url_key: str,
    api_key_key: str,
    timeout_seconds: int,
) -> AgentProviderConnection | None:
    base_url = source.get(url_key, "").strip()
    api_key = source.get(api_key_key, "").strip()
    if bool(base_url) != bool(api_key):
        raise ConfigurationError(f"{provider_code} agent provider requires both URL and API key")
    if not base_url:
        return None
    try:
        return AgentProviderConnection(
            provider_code=provider_code,
            api_key=SecretStr(api_key),
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        raise ConfigurationError(
            f"{provider_code} agent provider configuration is invalid"
        ) from exc
