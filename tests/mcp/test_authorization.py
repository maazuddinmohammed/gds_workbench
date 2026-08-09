import pytest

from gds_etl_workbench.domain.authorization import (
    Capability,
    TenantRole,
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
