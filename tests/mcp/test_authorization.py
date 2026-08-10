import pytest

from gds_etl_workbench.domain.authorization import (
    Capability,
    POLICY_REQUIREMENTS,
    TenantRole,
    ToolPolicy,
    has_capability,
)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (TenantRole.VIEWER, {Capability.READ_TENANT}),
        (TenantRole.DEVELOPER, {Capability.READ_TENANT, Capability.DEVELOP}),
        (
            TenantRole.ARCHITECT,
            {Capability.READ_TENANT, Capability.DEVELOP, Capability.ARCHITECT},
        ),
        (
            TenantRole.TENANT_ADMIN,
            {
                Capability.READ_TENANT,
                Capability.DEVELOP,
                Capability.ARCHITECT,
                Capability.ADMINISTER,
            },
        ),
        (
            TenantRole.SUPER_ADMIN,
            {
                Capability.READ_TENANT,
                Capability.DEVELOP,
                Capability.ARCHITECT,
                Capability.ADMINISTER,
            },
        ),
    ],
)
def test_role_capability_matrix(role: TenantRole, expected: set[Capability]) -> None:
    actual = {
        capability for capability in Capability if has_capability(role, capability)
    }
    assert actual == expected


def test_tool_policy_requirements_are_centralized() -> None:
    assert {
        policy: (
            requirement.minimum_role,
            requirement.requires_tenant_lock,
            requirement.requires_super_admin,
        )
        for policy, requirement in POLICY_REQUIREMENTS.items()
    } == {
        ToolPolicy.TENANT_READ: (TenantRole.VIEWER, False, False),
        ToolPolicy.TENANT_METADATA_WRITE: (TenantRole.DEVELOPER, True, False),
        ToolPolicy.TENANT_MODEL_WRITE: (TenantRole.ARCHITECT, True, False),
        ToolPolicy.TENANT_LOCK_MANAGE: (TenantRole.DEVELOPER, False, False),
        ToolPolicy.SUPER_ADMIN_ONLY: (TenantRole.SUPER_ADMIN, False, True),
    }
