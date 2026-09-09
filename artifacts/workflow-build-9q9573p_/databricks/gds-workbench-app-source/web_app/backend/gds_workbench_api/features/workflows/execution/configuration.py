"""Validated durable Workflow worker timing configuration."""

from collections.abc import Mapping
from importlib.resources import files
from typing import Literal, Self

from gds_etl_workbench.configuration import ConfigurationError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_MAX_CONFIGURATION_BYTES = 64 * 1024
_ENVIRONMENT_OVERRIDES = {
    "GDS_WEB_WORKFLOW_LEASE_SECONDS": ("lease_duration_seconds", int),
    "GDS_WEB_WORKFLOW_HEARTBEAT_SECONDS": ("heartbeat_interval_seconds", float),
    "GDS_WEB_WORKFLOW_IDLE_POLL_SECONDS": ("idle_poll_interval_seconds", float),
    "GDS_WEB_WORKFLOW_ERROR_POLL_SECONDS": ("error_poll_interval_seconds", float),
}


class WorkflowExecutionConfiguration(BaseModel):
    """Stable worker defaults with bounded deployment overrides."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"]
    lease_duration_seconds: int = Field(ge=1, le=300)
    heartbeat_interval_seconds: float = Field(gt=0, le=299)
    idle_poll_interval_seconds: float = Field(ge=0.05, le=60)
    error_poll_interval_seconds: float = Field(ge=0.05, le=300)

    @model_validator(mode="after")
    def validate_heartbeat(self) -> Self:
        if self.heartbeat_interval_seconds >= self.lease_duration_seconds:
            raise ValueError("Workflow heartbeat must be shorter than its lease")
        return self

    @classmethod
    def from_environment(cls, source: Mapping[str, str]) -> Self:
        configured = load_default_workflow_execution_configuration()
        values = configured.model_dump()
        for setting, (field_name, parser) in _ENVIRONMENT_OVERRIDES.items():
            raw = source.get(setting)
            if raw is None:
                continue
            try:
                values[field_name] = parser(raw.strip())
            except ValueError as exc:
                value_kind = "an integer" if parser is int else "a number"
                raise ConfigurationError(f"{setting} must be {value_kind}") from exc
        try:
            return cls.model_validate(values, strict=True)
        except ValidationError as exc:
            raise ConfigurationError("Workflow execution configuration is invalid") from exc


def load_default_workflow_execution_configuration() -> WorkflowExecutionConfiguration:
    resource = files("gds_workbench_api").joinpath("config/workflow_execution.json")
    raw = resource.read_bytes()
    if len(raw) > _MAX_CONFIGURATION_BYTES:
        raise ConfigurationError("Workflow execution configuration is invalid")
    try:
        return WorkflowExecutionConfiguration.model_validate_json(raw, strict=True)
    except ValidationError as exc:
        raise ConfigurationError("Workflow execution configuration is invalid") from exc


__all__ = [
    "WorkflowExecutionConfiguration",
    "load_default_workflow_execution_configuration",
]
