"""Public contracts for the Tenant catalog tracer bullet."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.domain.authorization import TenantRole


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ListTenantsRequest(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    page_size: int = Field(default=50, ge=1, le=200)
    cursor: str | None = Field(default=None, max_length=2048)


class TenantSummary(ContractModel):
    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_name: str = Field(min_length=1, max_length=200)
    tenant_description: str | None = Field(default=None, max_length=2000)
    tenant_visibility: Literal["global", "private"]
    effective_role: TenantRole


class ListTenantsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenants: tuple[TenantSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)
