"""Explicit governed Tenant Lock HTTP contracts."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type LockAction = Literal["acquired", "renewed", "released", "overridden"]
type LockEventType = Literal[
    "acquired",
    "renewed",
    "released",
    "force_unlocked",
    "expired",
]


class LockContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TenantLockRecord(LockContract):
    owner_display_name: str = Field(min_length=1, max_length=200)
    owned_by_current_principal: bool
    purpose: str | None = Field(default=None, max_length=500)
    acquired_at: datetime
    expires_at: datetime


class TenantLockMutation(LockContract):
    tenant_id: int = Field(gt=0)
    action: LockAction
    lock: TenantLockRecord | None = None
    previous_lock: TenantLockRecord | None = None

    @model_validator(mode="after")
    def validate_action_shape(self) -> Self:
        if self.action in {"acquired", "renewed"}:
            valid = self.lock is not None and self.previous_lock is None
        elif self.action == "released":
            valid = self.lock is None and self.previous_lock is None
        else:
            valid = self.lock is None and self.previous_lock is not None
        if not valid:
            raise ValueError("Tenant Lock result does not match its action")
        return self


class LockHistoryEvent(LockContract):
    event_id: int = Field(gt=0)
    event_type: LockEventType
    owner_display_name: str = Field(min_length=1, max_length=200)
    actor_display_name: str | None = Field(default=None, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)
    acquired_at: datetime
    expires_at: datetime
    created_at: datetime


class LockHistoryPage(LockContract):
    tenant_id: int = Field(gt=0)
    items: tuple[LockHistoryEvent, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class AcquireLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_minutes: int = Field(default=60, ge=1, le=240)
    purpose: str | None = Field(default=None, max_length=500)

    @field_validator("purpose")
    @classmethod
    def normalize_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("purpose must be nonblank when provided")
        return normalized


class RenewLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    duration_minutes: int = Field(default=60, ge=1, le=240)


class OverrideLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("reason must be nonblank")
        return normalized
