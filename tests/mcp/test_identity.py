from __future__ import annotations

import base64
import json
from uuid import UUID

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from gds_etl_workbench.adapters.auth.identity import (
    AuthenticationError,
    IdentityProvider,
)
from gds_etl_workbench.adapters.auth.middleware import ProtectedMCPMiddleware
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
OBJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


def easy_auth_header(
    *,
    idtyp: str = "user",
    scopes: str = "workbench.access",
    roles: tuple[str, ...] = (),
) -> str:
    claims = [
        {
            "typ": "http://schemas.microsoft.com/identity/claims/tenantid",
            "val": str(TENANT_ID),
        },
        {
            "typ": "http://schemas.microsoft.com/identity/claims/objectidentifier",
            "val": str(OBJECT_ID),
        },
        {"typ": "idtyp", "val": idtyp},
    ]
    if scopes:
        claims.append({"typ": "scp", "val": scopes})
    claims.extend({"typ": "roles", "val": role} for role in roles)
    payload = {
        "auth_typ": "aad",
        "name_typ": "name",
        "role_typ": "roles",
        "claims": claims,
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def test_dev_mode_skips_authentication_and_authorization() -> None:
    principal = IdentityProvider(AuthMode.DEV).authenticate(None)

    assert principal.actor_kind is ActorKind.DEVELOPMENT
    assert principal.entra_tenant_id is None


def test_easy_auth_maps_only_the_bounded_principal_envelope() -> None:
    principal = IdentityProvider(AuthMode.AZURE_EASY_AUTH).authenticate(
        {
            "X-MS-CLIENT-PRINCIPAL": easy_auth_header(),
            "X-MS-CLIENT-PRINCIPAL-ID": "ignored-shortcut-header",
        }
    )

    assert principal.actor_kind is ActorKind.HUMAN
    assert principal.entra_tenant_id == TENANT_ID
    assert principal.entra_object_id == OBJECT_ID


def test_missing_principal_envelope_requires_authentication() -> None:
    with pytest.raises(AuthenticationError) as error:
        IdentityProvider(AuthMode.AZURE_EASY_AUTH).authenticate(
            {"X-MS-CLIENT-PRINCIPAL-ID": str(OBJECT_ID)}
        )

    assert error.value.public_code == "authentication_required"
    assert error.value.http_status == 401


def test_workload_application_permission_maps_workload_actor() -> None:
    principal = IdentityProvider(AuthMode.AZURE_EASY_AUTH).authenticate(
        {
            "X-MS-CLIENT-PRINCIPAL": easy_auth_header(
                idtyp="app",
                scopes="",
                roles=("workbench.workflow",),
            )
        }
    )

    assert principal.actor_kind is ActorKind.WORKLOAD
    assert principal.entra_tenant_id == TENANT_ID
    assert principal.entra_object_id == OBJECT_ID


def test_workload_without_application_permission_is_denied() -> None:
    with pytest.raises(AuthenticationError) as error:
        IdentityProvider(AuthMode.AZURE_EASY_AUTH).authenticate(
            {"X-MS-CLIENT-PRINCIPAL": easy_auth_header(idtyp="app", scopes="")}
        )

    assert error.value.public_code == "authorization_denied"
    assert error.value.http_status == 403


def test_missing_delegated_scope_is_denied() -> None:
    with pytest.raises(AuthenticationError) as error:
        IdentityProvider(AuthMode.AZURE_EASY_AUTH).authenticate(
            {"X-MS-CLIENT-PRINCIPAL": easy_auth_header(scopes="openid profile")}
        )

    assert error.value.public_code == "authorization_denied"


def test_ambiguous_tenant_claim_fails_closed() -> None:
    encoded = easy_auth_header()
    payload = json.loads(base64.b64decode(encoded))
    payload["claims"].append({"typ": "tid", "val": str(OBJECT_ID)})
    ambiguous = base64.b64encode(json.dumps(payload).encode()).decode()

    with pytest.raises(AuthenticationError) as error:
        IdentityProvider(AuthMode.AZURE_EASY_AUTH).authenticate(
            {"X-MS-CLIENT-PRINCIPAL": ambiguous}
        )

    assert error.value.public_code == "authentication_required"


def test_oversized_envelope_fails_before_decode() -> None:
    with pytest.raises(AuthenticationError):
        IdentityProvider(AuthMode.AZURE_EASY_AUTH).authenticate(
            {"X-MS-CLIENT-PRINCIPAL": "A" * (91 * 1024)}
        )


def test_middleware_propagates_the_authenticated_principal() -> None:
    async def current_actor(request: Request) -> Response:
        return JSONResponse(
            {"actor_kind": request.state.request_principal.actor_kind.value}
        )

    application = Starlette(routes=[Route("/mcp/actor", current_actor)])
    application.add_middleware(
        ProtectedMCPMiddleware,
        identity_provider=IdentityProvider(AuthMode.AZURE_EASY_AUTH),
        require_https=False,
    )

    with TestClient(application) as client:
        response = client.get(
            "/mcp/actor",
            headers={"X-MS-CLIENT-PRINCIPAL": easy_auth_header()},
        )

    assert response.status_code == 200
    assert response.json() == {"actor_kind": "human"}
