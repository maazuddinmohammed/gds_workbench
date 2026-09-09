"""Server-owned Principal, Tenant Role, and Tool Policy vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ActorKind(StrEnum):
    HUMAN = "human"
    WORKLOAD = "workload"
    DEVELOPMENT = "development"


class TenantRole(StrEnum):
    VIEWER = "viewer"
    DEVELOPER = "developer"
    ARCHITECT = "architect"
    TENANT_ADMIN = "tenant_admin"
    SUPER_ADMIN = "super_admin"
    DEVELOPMENT = "development"


class ToolPolicy(StrEnum):
    TENANT_READ = "tenant_read"
    TENANT_METADATA_WRITE = "tenant_metadata_write"
    TENANT_MODEL_WRITE = "tenant_model_write"
    TENANT_LOCK_MANAGE = "tenant_lock_manage"
    SUPER_ADMIN_ONLY = "super_admin_only"


@dataclass(frozen=True, slots=True)
class RequestPrincipal:
    actor_kind: ActorKind
    entra_tenant_id: UUID | None
    entra_object_id: UUID | None

    @classmethod
    def development(cls) -> RequestPrincipal:
        return cls(
            actor_kind=ActorKind.DEVELOPMENT,
            entra_tenant_id=None,
            entra_object_id=None,
        )
