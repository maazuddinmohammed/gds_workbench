"""Validated, non-secret agent SDK/provider/model capability registry."""

from importlib.resources import files
from pathlib import Path
from typing import Literal, Self

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import BaseModel, ConfigDict, Field, model_validator

_CODE_PATTERN = r"^[a-z][a-z0-9_.-]{0,99}$"
_MODEL_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$"
_MAX_CONFIGURATION_BYTES = 1024 * 1024


class CapabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AgentSdkCapability(CapabilityModel):
    code: str = Field(pattern=_CODE_PATTERN, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    provider_codes: tuple[str, ...] = Field(min_length=1, max_length=20)


class AgentProviderCapability(CapabilityModel):
    code: str = Field(pattern=_CODE_PATTERN, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class AgentModelCapability(CapabilityModel):
    code: str = Field(pattern=_MODEL_CODE_PATTERN, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    provider_code: str = Field(pattern=_CODE_PATTERN, max_length=100)
    sdk_codes: tuple[str, ...] = Field(min_length=1, max_length=20)
    reasoning_effort_codes: tuple[str, ...] = Field(min_length=1, max_length=20)


class ReasoningEffortCapability(CapabilityModel):
    code: str = Field(pattern=_CODE_PATTERN, max_length=50)
    name: str = Field(min_length=1, max_length=100)


class BoundedDefault(CapabilityModel):
    minimum: int
    default: int
    maximum: int

    @model_validator(mode="after")
    def validate_bounds(self) -> Self:
        if not self.minimum <= self.default <= self.maximum:
            raise ValueError("default must be within the configured bounds")
        return self


class AgentRunSelection(CapabilityModel):
    sdk_code: str = Field(pattern=_CODE_PATTERN, max_length=100)
    provider_code: str = Field(pattern=_CODE_PATTERN, max_length=100)
    model_code: str = Field(pattern=_MODEL_CODE_PATTERN, max_length=200)
    reasoning_effort_code: str = Field(pattern=_CODE_PATTERN, max_length=50)
    max_turns: int = Field(ge=1, le=50)
    validation_retry_count: int = Field(ge=0, le=5)


class AgentCapabilityRegistry(CapabilityModel):
    schema_version: Literal["1.0"]
    sdks: tuple[AgentSdkCapability, ...] = Field(min_length=1, max_length=20)
    providers: tuple[AgentProviderCapability, ...] = Field(min_length=1, max_length=20)
    models: tuple[AgentModelCapability, ...] = Field(min_length=1, max_length=200)
    reasoning_efforts: tuple[ReasoningEffortCapability, ...] = Field(
        min_length=1,
        max_length=20,
    )
    max_turns: BoundedDefault
    validation_retries: BoundedDefault

    @model_validator(mode="after")
    def validate_registry(self) -> Self:
        sdk_codes = _unique_codes("SDK", self.sdks)
        provider_codes = _unique_codes("provider", self.providers)
        model_codes = _unique_codes("model", self.models)
        reasoning_codes = _unique_codes("reasoning effort", self.reasoning_efforts)
        del model_codes

        for sdk in self.sdks:
            if not set(sdk.provider_codes) <= provider_codes:
                raise ValueError(f"SDK {sdk.code} references an unknown provider")
            if len(set(sdk.provider_codes)) != len(sdk.provider_codes):
                raise ValueError(f"SDK {sdk.code} repeats a provider")
        for model in self.models:
            if model.provider_code not in provider_codes:
                raise ValueError(f"Model {model.code} references an unknown provider")
            if not set(model.sdk_codes) <= sdk_codes:
                raise ValueError(f"Model {model.code} references an unknown SDK")
            if not set(model.reasoning_effort_codes) <= reasoning_codes:
                raise ValueError(f"Model {model.code} references an unknown reasoning effort")
            if any(
                model.provider_code
                not in next(sdk.provider_codes for sdk in self.sdks if sdk.code == sdk_code)
                for sdk_code in model.sdk_codes
            ):
                raise ValueError(f"Model {model.code} uses an SDK incompatible with its provider")
        if (self.max_turns.minimum, self.max_turns.maximum) != (1, 50):
            raise ValueError("max_turns bounds must remain 1 through 50")
        if (self.validation_retries.minimum, self.validation_retries.maximum) != (
            0,
            5,
        ):
            raise ValueError("validation retry bounds must remain 0 through 5")
        return self

    @classmethod
    def from_path(cls, path: Path) -> AgentCapabilityRegistry:
        raw = path.read_bytes()
        if len(raw) > _MAX_CONFIGURATION_BYTES:
            raise ValueError("agent capability configuration is too large")
        return cls.model_validate_json(raw, strict=True)

    def validate_selection(self, selection: AgentRunSelection) -> None:
        sdk = next((item for item in self.sdks if item.code == selection.sdk_code), None)
        provider = next(
            (item for item in self.providers if item.code == selection.provider_code),
            None,
        )
        model = next(
            (item for item in self.models if item.code == selection.model_code),
            None,
        )
        reasoning = next(
            (
                item
                for item in self.reasoning_efforts
                if item.code == selection.reasoning_effort_code
            ),
            None,
        )
        if sdk is None or provider is None or model is None or reasoning is None:
            raise InvalidRequestError("The selected agent configuration is unavailable.")
        if (
            provider.code not in sdk.provider_codes
            or model.provider_code != provider.code
            or sdk.code not in model.sdk_codes
            or reasoning.code not in model.reasoning_effort_codes
            or not self.max_turns.minimum <= selection.max_turns <= self.max_turns.maximum
            or not self.validation_retries.minimum
            <= selection.validation_retry_count
            <= self.validation_retries.maximum
        ):
            raise InvalidRequestError("The selected agent configuration is incompatible.")


def load_default_agent_capabilities() -> AgentCapabilityRegistry:
    resource = files("gds_workbench_api").joinpath("config/agent_capabilities.json")
    raw = resource.read_bytes()
    if len(raw) > _MAX_CONFIGURATION_BYTES:
        raise ValueError("agent capability configuration is too large")
    return AgentCapabilityRegistry.model_validate_json(raw, strict=True)


def _unique_codes(
    label: str,
    items: tuple[
        AgentSdkCapability
        | AgentProviderCapability
        | AgentModelCapability
        | ReasoningEffortCapability,
        ...,
    ],
) -> set[str]:
    codes = [item.code for item in items]
    if len(set(codes)) != len(codes):
        raise ValueError(f"{label} codes must be unique")
    return set(codes)
