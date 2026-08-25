"""Tenant entry HTTP contracts."""

from datetime import datetime
from typing import Literal

from gds_etl_workbench.domain.authorization import TenantRole
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TenantRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_name: str = Field(min_length=1, max_length=200)
    tenant_description: str | None = Field(default=None, max_length=2000)
    tenant_visibility: Literal["global", "private"]
    effective_role: TenantRole


class TenantCollection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[TenantRecord, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class TenantSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant_id: int = Field(gt=0)


class TenantLockState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    is_locked: bool
    owner_display_name: str | None = Field(default=None, min_length=1, max_length=200)
    owned_by_current_principal: bool | None = None
    purpose: str | None = Field(default=None, max_length=500)
    acquired_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> TenantLockState:
        details = (
            self.owner_display_name,
            self.owned_by_current_principal,
            self.acquired_at,
            self.expires_at,
        )
        if self.is_locked != all(value is not None for value in details):
            raise ValueError("active Tenant Lock details must be complete")
        if not self.is_locked and self.purpose is not None:
            raise ValueError("unlocked Tenant cannot have a lock purpose")
        return self


class TenantLockActions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    can_acquire: bool
    can_renew: bool
    can_release: bool
    can_override: bool


class TenantSystemRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    system_type_name: str = Field(min_length=1, max_length=200)
    connection_count: int = Field(ge=0)
    registered_object_count: int = Field(ge=0)
    active_model_count: int = Field(ge=0)
    last_metadata_update_time: datetime | None = None


class TenantHome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenant: TenantRecord
    lock: TenantLockState
    lock_actions: TenantLockActions
    systems: tuple[TenantSystemRecord, ...]
