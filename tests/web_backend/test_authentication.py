from collections.abc import Mapping
from uuid import UUID

import pytest
from databricks.sdk.errors import InternalError, Unauthenticated
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import AuthenticationError
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.authentication import (
    CurrentUserLookup,
    DatabricksUserIdentity,
    DatabricksUserResolver,
    RequestIdentityResolver,
    WebAuthenticationMiddleware,
    WebIdentityProvider,
)

_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
_OBJECT_ID = UUID("22222222-2222-2222-2222-222222222222")
_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"


class RecordingLookup(CurrentUserLookup):
    def __init__(
        self,
        result: DatabricksUserIdentity | Exception,
    ) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    def lookup(self, *, host: str, access_token: str) -> DatabricksUserIdentity:
        self.calls.append((host, access_token))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _active_user(**overrides: object) -> DatabricksUserIdentity:
    values: dict[str, object] = {
        "active": True,
        "external_id": str(_OBJECT_ID),
        "schemas": frozenset({_USER_SCHEMA}),
        "user_name": "user@example.test",
    }
    values.update(overrides)
    return DatabricksUserIdentity(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_databricks_user_resolver_derives_existing_entra_identity() -> None:
    lookup = RecordingLookup(_active_user())
    resolver = DatabricksUserResolver(
        host="https://fixture.azuredatabricks.net",
        entra_tenant_id=_TENANT_ID,
        lookup=lookup,
    )

    principal = await resolver.resolve(
        {"x-forwarded-access-token": "bounded-user-token"}
    )

    assert principal == RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=_TENANT_ID,
        entra_object_id=_OBJECT_ID,
    )
    assert lookup.calls == [
        ("https://fixture.azuredatabricks.net", "bounded-user-token")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"x-forwarded-access-token": "contains whitespace"},
        {"x-forwarded-access-token": "x" * (32 * 1024 + 1)},
    ],
)
async def test_databricks_user_resolver_rejects_missing_or_unbounded_tokens(
    headers: Mapping[str, str],
) -> None:
    lookup = RecordingLookup(_active_user())
    resolver = DatabricksUserResolver(
        host="https://fixture.azuredatabricks.net",
        entra_tenant_id=_TENANT_ID,
        lookup=lookup,
    )

    with pytest.raises(AuthenticationError) as captured:
        await resolver.resolve(headers)

    assert captured.value.http_status == 401
    assert lookup.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identity", "status_code"),
    [
        (_active_user(active=False), 403),
        (_active_user(schemas=frozenset[str]()), 403),
        (_active_user(external_id=None), 401),
        (_active_user(external_id=str(UUID(int=0))), 401),
        (_active_user(user_name=None), 401),
    ],
)
async def test_databricks_user_resolver_fails_closed_on_unusable_identity(
    identity: DatabricksUserIdentity,
    status_code: int,
) -> None:
    resolver = DatabricksUserResolver(
        host="https://fixture.azuredatabricks.net",
        entra_tenant_id=_TENANT_ID,
        lookup=RecordingLookup(identity),
    )

    with pytest.raises(AuthenticationError) as captured:
        await resolver.resolve({"x-forwarded-access-token": "bounded-user-token"})

    assert captured.value.http_status == status_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status_code"),
    [(Unauthenticated("expired"), 401), (InternalError("unavailable"), 503)],
)
async def test_databricks_user_resolver_maps_sdk_failures_safely(
    failure: Exception,
    status_code: int,
) -> None:
    resolver = DatabricksUserResolver(
        host="https://fixture.azuredatabricks.net",
        entra_tenant_id=_TENANT_ID,
        lookup=RecordingLookup(failure),
    )

    with pytest.raises(AuthenticationError) as captured:
        await resolver.resolve(
            {"x-forwarded-access-token": "never-disclose-this-token"}
        )

    assert captured.value.http_status == status_code
    assert "never-disclose" not in str(captured.value)


class CountingResolver(RequestIdentityResolver):
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, headers: Mapping[str, str]) -> RequestPrincipal:
        assert headers["x-forwarded-access-token"] == "bounded-user-token"
        self.calls += 1
        return RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=_TENANT_ID,
            entra_object_id=_OBJECT_ID,
        )


def test_web_middleware_resolves_once_and_does_not_protect_health() -> None:
    provider = WebIdentityProvider()
    resolver = CountingResolver()
    app = FastAPI()

    async def protected(request: Request) -> dict[str, str]:
        principal = provider.authenticate(request.headers)
        assert request.state.request_principal == principal
        return {"object_id": str(principal.entra_object_id)}

    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.add_api_route("/api/protected", protected, methods=["GET"])
    app.add_api_route("/healthz", health, methods=["GET"])
    app.add_middleware(
        WebAuthenticationMiddleware,
        identity_provider=provider,
        resolver=resolver,
    )

    with TestClient(app) as client:
        protected_response = client.get(
            "/api/protected",
            headers={"x-forwarded-access-token": "bounded-user-token"},
        )
        health_response = client.get("/healthz")

    assert protected_response.json() == {"object_id": str(_OBJECT_ID)}
    assert health_response.status_code == 200
    assert resolver.calls == 1
    with pytest.raises(AuthenticationError):
        provider.authenticate(None)
