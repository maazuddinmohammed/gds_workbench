"""Validated direct model-provider configuration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, Self, cast
from urllib.parse import urlsplit
from uuid import UUID

from gds_etl_workbench.configuration import ConfigurationError
from pydantic import BaseModel, ConfigDict, Field, SecretStr


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


class AgentRuntimeConfiguration(BaseModel):
    """Select deterministic local fakes or one direct model provider."""

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

        raw_provider = source.get("GDS_WEB_AGENT_PROVIDER", "databricks").strip()
        if raw_provider not in {"databricks", "microsoft_foundry"}:
            raise ConfigurationError(
                "GDS_WEB_AGENT_PROVIDER must be databricks or microsoft_foundry"
            )

        databricks_endpoint = source.get("GDS_WEB_DATABRICKS_MODEL_ENDPOINT", "").strip()
        foundry_endpoint = source.get("GDS_WEB_FOUNDRY_MODEL_DEPLOYMENT", "").strip()
        foundry_base_url = source.get("GDS_WEB_FOUNDRY_OPENAI_BASE_URL", "").strip()
        foundry_scope = "https://ai.azure.com/.default"
        foundry_tenant_id = _optional_uuid(source, "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID")
        foundry_client_id = _optional_uuid(source, "GDS_WEB_FOUNDRY_CLIENT_ID")
        foundry_client_secret = source.get("GDS_WEB_FOUNDRY_CLIENT_SECRET", "")

        supplied_remote_values = any(
            (
                databricks_endpoint,
                foundry_endpoint,
                foundry_base_url,
                foundry_tenant_id,
                foundry_client_id,
                foundry_client_secret,
            )
        )
        if raw_mode == "fake" and supplied_remote_values:
            raise ConfigurationError("fake agent execution does not accept provider settings")

        try:
            connection: AgentProviderConnection | None = None
            if raw_mode == "remote" and raw_provider == "databricks":
                if not databricks_endpoint:
                    raise ConfigurationError(
                        "Databricks agent execution requires GDS_WEB_DATABRICKS_MODEL_ENDPOINT"
                    )
                if (
                    foundry_endpoint
                    or foundry_base_url
                    or foundry_tenant_id is not None
                    or foundry_client_id is not None
                    or foundry_client_secret
                ):
                    raise ConfigurationError(
                        "Databricks agent execution does not accept Foundry settings"
                    )
                connection = AgentProviderConnection(
                    provider_code="databricks",
                    model_code="databricks-primary",
                    model_endpoint=databricks_endpoint,
                    timeout_seconds=timeout_seconds,
                )
            elif raw_mode == "remote":
                if databricks_endpoint:
                    raise ConfigurationError(
                        "Foundry agent execution does not accept a Databricks model endpoint"
                    )
                if not foundry_endpoint or not foundry_base_url:
                    raise ConfigurationError(
                        "Foundry agent execution requires its OpenAI base URL and model deployment"
                    )
                if (
                    foundry_tenant_id is None
                    or foundry_client_id is None
                    or not foundry_client_secret.strip()
                ):
                    raise ConfigurationError(
                        "Foundry agent execution requires explicit Entra tenant, client ID, "
                        "and client secret"
                    )
                if len(foundry_client_secret.encode()) > 4096:
                    raise ConfigurationError(
                        "GDS_WEB_FOUNDRY_CLIENT_SECRET must be at most 4096 UTF-8 bytes"
                    )
                _validate_foundry_base_url(foundry_base_url)
                _validate_foundry_scope(foundry_scope)
                connection = AgentProviderConnection(
                    provider_code="microsoft_foundry",
                    model_code="foundry-primary",
                    model_endpoint=foundry_endpoint,
                    timeout_seconds=timeout_seconds,
                    openai_base_url=foundry_base_url,
                    token_scope=foundry_scope,
                    foundry_client_credentials=FoundryClientCredentials(
                        tenant_id=foundry_tenant_id,
                        client_id=foundry_client_id,
                        client_secret=SecretStr(foundry_client_secret),
                    ),
                )
            connections = () if connection is None else (connection,)
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


def _validate_foundry_base_url(value: str) -> None:
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    project_segments = path.split("/")
    is_resource_route = hostname.endswith(".openai.azure.com") and path == "/openai/v1"
    is_project_route = (
        hostname.endswith(".services.ai.azure.com")
        and len(project_segments) == 6
        and project_segments[:3] == ["", "api", "projects"]
        and bool(project_segments[3])
        and project_segments[4:] == ["openai", "v1"]
    )
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not (is_resource_route or is_project_route)
    ):
        raise ConfigurationError(
            "GDS_WEB_FOUNDRY_OPENAI_BASE_URL must be an Azure HTTPS /openai/v1 endpoint"
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
