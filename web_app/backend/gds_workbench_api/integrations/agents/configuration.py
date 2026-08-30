"""Validated direct model-provider configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Self, cast
from urllib.parse import urlsplit
from uuid import UUID

from gds_etl_workbench.configuration import ConfigurationError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    load_default_agent_capabilities,
)


class FoundryClientCredentials(BaseModel):
    """Explicit Entra application credentials for a Databricks-hosted app."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    tenant_id: UUID
    client_id: UUID
    client_secret: SecretStr = Field(min_length=1, max_length=4096)


class AgentProviderConnection(BaseModel):
    """Validated provider connection with redacted credentials when required."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    provider_code: Literal["databricks", "microsoft_foundry"]
    model_code: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$",
    )
    model_endpoint: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,199}$",
    )
    timeout_seconds: int = Field(ge=1, le=600)
    openai_base_url: str | None = Field(default=None, max_length=2048)
    token_scope: str | None = Field(default=None, max_length=2048)
    foundry_client_credentials: FoundryClientCredentials | None = None
    foundry_api_key: SecretStr | None = None


class AgentRuntimeConfiguration(BaseModel):
    """Select deterministic local fakes or registered direct model providers."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    mode: Literal["fake", "remote"]
    timeout_seconds: int = Field(ge=1, le=600)
    connections: tuple[AgentProviderConnection, ...] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_connections(self) -> Self:
        keys = [
            (connection.provider_code, connection.model_code) for connection in self.connections
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("Agent model deployment connections must be unique")
        if self.mode == "fake" and self.connections:
            raise ValueError("fake Agent execution cannot have model deployments")
        if self.mode == "remote" and not self.connections:
            raise ValueError("remote Agent execution requires a model deployment")
        return self

    @classmethod
    def from_environment(
        cls,
        source: Mapping[str, str],
        *,
        production: bool,
        capabilities: AgentCapabilityRegistry | None = None,
    ) -> Self:
        registry = capabilities or load_default_agent_capabilities()
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

        databricks_models = tuple(
            model for model in registry.models if model.provider_code == "databricks"
        )
        foundry_models = tuple(
            model for model in registry.models if model.provider_code == "microsoft_foundry"
        )
        foundry_base_url = source.get("GDS_WEB_FOUNDRY_OPENAI_BASE_URL", "").strip()
        foundry_scope = "https://cognitiveservices.azure.com/.default"
        foundry_tenant_id = _optional_uuid(source, "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID")
        foundry_client_id = _optional_uuid(source, "GDS_WEB_FOUNDRY_CLIENT_ID")
        foundry_client_secret = source.get("GDS_WEB_FOUNDRY_CLIENT_SECRET", "")
        foundry_api_key = source.get("GDS_WEB_FOUNDRY_API_KEY", "")

        supplied_foundry_values = any(
            (
                foundry_base_url,
                foundry_tenant_id,
                foundry_client_id,
                foundry_client_secret,
                foundry_api_key,
            )
        )
        if raw_mode == "fake" and supplied_foundry_values:
            raise ConfigurationError("fake agent execution does not accept provider settings")

        try:
            connections: tuple[AgentProviderConnection, ...] = ()
            if raw_mode == "remote":
                connections = tuple(
                    AgentProviderConnection(
                        provider_code="databricks",
                        model_code=model.code,
                        model_endpoint=model.deployment_name,
                        timeout_seconds=timeout_seconds,
                    )
                    for model in databricks_models
                )
            if raw_mode == "remote" and supplied_foundry_values:
                if not foundry_models:
                    raise ConfigurationError(
                        "The Agent registry has no Microsoft Foundry model deployments"
                    )
                if not foundry_base_url:
                    raise ConfigurationError("Foundry agent execution requires its OpenAI base URL")
                foundry_entra_supplied = (
                    foundry_tenant_id is not None
                    or foundry_client_id is not None
                    or bool(foundry_client_secret)
                )
                if foundry_api_key.strip() and foundry_entra_supplied:
                    raise ConfigurationError(
                        "Foundry agent execution accepts exactly one authentication method: "
                        "API key or complete Entra client credentials"
                    )
                if not foundry_api_key.strip() and (
                    foundry_tenant_id is None
                    or foundry_client_id is None
                    or not foundry_client_secret.strip()
                ):
                    raise ConfigurationError(
                        "Foundry agent execution requires either an API key or complete Entra "
                        "tenant, client ID, and client secret"
                    )
                if len(foundry_client_secret.encode()) > 4096:
                    raise ConfigurationError(
                        "GDS_WEB_FOUNDRY_CLIENT_SECRET must be at most 4096 UTF-8 bytes"
                    )
                if len(foundry_api_key.encode()) > 4096:
                    raise ConfigurationError(
                        "GDS_WEB_FOUNDRY_API_KEY must be at most 4096 UTF-8 bytes"
                    )
                _validate_foundry_base_url(
                    foundry_base_url,
                    allow_services_host=bool(foundry_api_key.strip()),
                )
                _validate_foundry_scope(foundry_scope)
                connections += tuple(
                    AgentProviderConnection(
                        provider_code="microsoft_foundry",
                        model_code=model.code,
                        model_endpoint=model.deployment_name,
                        timeout_seconds=timeout_seconds,
                        openai_base_url=foundry_base_url,
                        token_scope=None if foundry_api_key.strip() else foundry_scope,
                        foundry_client_credentials=(
                            None
                            if foundry_api_key.strip()
                            else FoundryClientCredentials(
                                tenant_id=cast(UUID, foundry_tenant_id),
                                client_id=cast(UUID, foundry_client_id),
                                client_secret=SecretStr(foundry_client_secret),
                            )
                        ),
                        foundry_api_key=(
                            SecretStr(foundry_api_key.strip()) if foundry_api_key.strip() else None
                        ),
                    )
                    for model in foundry_models
                )
            if raw_mode == "remote" and not connections:
                raise ConfigurationError("The Agent registry has no available model deployments")
        except ConfigurationError:
            raise
        except ValueError as exc:
            raise ConfigurationError(
                "The selected model provider configuration is invalid"
            ) from exc
        return cls(
            mode=cast(Literal["fake", "remote"], raw_mode),
            timeout_seconds=timeout_seconds,
            connections=connections,
        )


def _optional_uuid(source: Mapping[str, str], key: str) -> UUID | None:
    raw = source.get(key, "").strip()
    if not raw:
        return None
    try:
        value = UUID(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{key} must be a UUID") from exc
    if value.int == 0:
        raise ConfigurationError(f"{key} must be a nonzero UUID")
    return value


def _validate_foundry_base_url(
    value: str,
    *,
    allow_services_host: bool,
) -> None:
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    is_resource_route = hostname.endswith(".openai.azure.com") and path == "/openai/v1"
    is_api_key_services_route = (
        allow_services_host and hostname.endswith(".services.ai.azure.com") and path == "/openai/v1"
    )
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (
        parsed.scheme != "https"
        or not hostname
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not (is_resource_route or is_api_key_services_route)
    ):
        raise ConfigurationError(
            "GDS_WEB_FOUNDRY_OPENAI_BASE_URL must be an Azure resource HTTPS /openai/v1 endpoint"
        )


def _validate_foundry_scope(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith("/.default")
    ):
        raise ConfigurationError("GDS_WEB_FOUNDRY_TOKEN_SCOPE must be an HTTPS /.default scope")
