"""Tenant capability policy derived from the database role vocabulary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
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


class Capability(StrEnum):
    READ_TENANT = "read_tenant"
    DEVELOP = "develop"
    ARCHITECT = "architect"
    ADMINISTER = "administer"


class ToolPolicy(StrEnum):
    TENANT_READ = "tenant_read"
    TENANT_METADATA_WRITE = "tenant_metadata_write"
    TENANT_MODEL_WRITE = "tenant_model_write"
    TENANT_LOCK_MANAGE = "tenant_lock_manage"
    SUPER_ADMIN_ONLY = "super_admin_only"


@dataclass(frozen=True, slots=True)
class PolicyRequirement:
    minimum_role: TenantRole
    requires_tenant_lock: bool
    requires_super_admin: bool = False


_READ = frozenset({Capability.READ_TENANT})
_DEVELOP = _READ | {Capability.DEVELOP}
_ARCHITECT = _DEVELOP | {Capability.ARCHITECT}
_ADMINISTER = _ARCHITECT | {Capability.ADMINISTER}

CAPABILITIES_BY_ROLE = MappingProxyType(
    {
        TenantRole.VIEWER: _READ,
        TenantRole.DEVELOPER: _DEVELOP,
        TenantRole.ARCHITECT: _ARCHITECT,
        TenantRole.TENANT_ADMIN: _ADMINISTER,
        TenantRole.SUPER_ADMIN: _ADMINISTER,
        TenantRole.DEVELOPMENT: _ADMINISTER,
    }
)

POLICY_REQUIREMENTS: Mapping[ToolPolicy, PolicyRequirement] = MappingProxyType(
    {
        ToolPolicy.TENANT_READ: PolicyRequirement(TenantRole.VIEWER, False),
        ToolPolicy.TENANT_METADATA_WRITE: PolicyRequirement(
            TenantRole.DEVELOPER,
            True,
        ),
        ToolPolicy.TENANT_MODEL_WRITE: PolicyRequirement(
            TenantRole.ARCHITECT,
            True,
        ),
        ToolPolicy.TENANT_LOCK_MANAGE: PolicyRequirement(
            TenantRole.DEVELOPER,
            False,
        ),
        ToolPolicy.SUPER_ADMIN_ONLY: PolicyRequirement(
            TenantRole.SUPER_ADMIN,
            False,
            requires_super_admin=True,
        ),
    }
)


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


def has_capability(role: TenantRole, capability: Capability) -> bool:
    return capability in CAPABILITIES_BY_ROLE[role]
