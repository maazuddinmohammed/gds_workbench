"""Numeric-only model usage; absent provider counts remain unknown."""

from decimal import Decimal
from typing import Annotated, Protocol, Self, runtime_checkable
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

type FoundryTokenRate = Annotated[
    Decimal, Field(ge=0, le=1_000_000, max_digits=15, decimal_places=8, allow_inf_nan=False)
]


class FoundryModelPricing(BaseModel):
    """Operator-supplied token rates; never a claim about actual invoice cost."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    basis: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$")
    input_usd_per_million: FoundryTokenRate
    cached_input_usd_per_million: FoundryTokenRate
    cache_write_input_usd_per_million: FoundryTokenRate
    output_usd_per_million: FoundryTokenRate
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    max_input_tokens: int | None = Field(default=None, ge=1, le=1_000_000_000_000)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_from >= self.valid_until
        ):
            raise ValueError("The pricing validity window must increase")
        return self


class ModelTokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    input_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    output_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    total_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    cached_input_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    cache_write_input_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    reasoning_output_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    other_token_types: bool = False

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.input_tokens is not None:
            if any(
                count is not None and count > self.input_tokens
                for count in (self.cached_input_tokens, self.cache_write_input_tokens)
            ):
                raise ValueError("Input token details exceed input tokens")
            if (
                self.cached_input_tokens is not None
                and self.cache_write_input_tokens is not None
                and self.cached_input_tokens + self.cache_write_input_tokens > self.input_tokens
            ):
                raise ValueError("Input token details exceed input tokens")
        if (
            self.reasoning_output_tokens is not None
            and self.output_tokens is not None
            and self.reasoning_output_tokens > self.output_tokens
        ):
            raise ValueError("Reasoning tokens exceed output tokens")
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.input_tokens + self.output_tokens != self.total_tokens
        ):
            raise ValueError("Total tokens disagree with input and output")
        return self


@runtime_checkable
class ModelRequestRecorder(Protocol):
    """One invocation's claim-bound recorder, never given prompts or responses."""

    async def begin_request(self, request_ordinal: int) -> UUID: ...

    async def complete_request(self, request_id: UUID, usage: ModelTokenUsage) -> None: ...


class AgentUsageRecorder(Protocol):
    def make_invocation_recorder(
        self,
        *,
        workflow_run_id: int,
        stage_code: str,
        invocation_id: UUID,
        authoring_attempt: int,
    ) -> ModelRequestRecorder: ...
