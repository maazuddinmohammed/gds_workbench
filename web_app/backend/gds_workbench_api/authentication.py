"""Databricks Apps user authentication boundary for the web application only."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import PermissionDenied, Unauthenticated
from databricks.sdk.errors.base import DatabricksError
from databricks.sdk.service.iam import UserSchema
from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_FORWARDED_ACCESS_TOKEN = "x-forwarded-access-token"
_MAX_ACCESS_TOKEN_CHARS = 32 * 1024
_USER_SCHEMA = UserSchema.URN_IETF_PARAMS_SCIM_SCHEMAS_CORE_2_0_USER.value
_BOUND_PRINCIPAL: ContextVar[RequestPrincipal | None] = ContextVar(
    "gds_web_request_principal",
    default=None,
)


@dataclass(frozen=True, slots=True)
class DatabricksUserIdentity:
    active: bool | None
    external_id: str | None
    schemas: frozenset[str]
    user_name: str | None


class CurrentUserLookup(Protocol):
    def lookup(self, *, host: str, access_token: str) -> DatabricksUserIdentity: ...


class RequestIdentityResolver(Protocol):
    async def resolve(self, headers: Mapping[str, str]) -> RequestPrincipal: ...


class SdkCurrentUserLookup:
    """Call SCIM Me with the forwarded user token, never the app identity."""

    def lookup(self, *, host: str, access_token: str) -> DatabricksUserIdentity:
        client = WorkspaceClient(
            host=host,
            token=access_token,
            auth_type="pat",
            debug_headers=False,
            product="gds-workbench-web",
            product_version="0.1.0",
        )
        user = client.current_user.me(
            attributes="active,externalId,id,schemas,userName",
        )
        return DatabricksUserIdentity(
            active=user.active,
            external_id=user.external_id,
            schemas=frozenset(schema.value for schema in user.schemas or ()),
            user_name=user.user_name,
        )


class DatabricksUserResolver:
    def __init__(
        self,
        *,
        host: str,
        entra_tenant_id: UUID,
        lookup: CurrentUserLookup | None = None,
    ) -> None:
        self._host = host
        self._entra_tenant_id = entra_tenant_id
        self._lookup = lookup or SdkCurrentUserLookup()

    async def resolve(self, headers: Mapping[str, str]) -> RequestPrincipal:
        access_token = headers.get(_FORWARDED_ACCESS_TOKEN, "").strip()
        if (
            not access_token
            or len(access_token) > _MAX_ACCESS_TOKEN_CHARS
            or any(character.isspace() or ord(character) < 0x20 for character in access_token)
        ):
            raise _authentication_required()

        try:
            identity = await asyncio.to_thread(
                self._lookup.lookup,
                host=self._host,
                access_token=access_token,
            )
        except Unauthenticated:
            raise _authentication_required() from None
        except PermissionDenied:
            raise AuthenticationError(
                public_code="authorization_denied",
                message="Databricks user authorization is unavailable.",
                http_status=403,
            ) from None
        except DatabricksError, TimeoutError, OSError:
            raise AuthenticationError(
                public_code="dependency_unavailable",
                message="Databricks user authentication is temporarily unavailable.",
                http_status=503,
            ) from None

        if identity.active is not True or _USER_SCHEMA not in identity.schemas:
            raise AuthenticationError(
                public_code="authorization_denied",
                message="This Databricks user is not active.",
                http_status=403,
            )
        if not identity.user_name:
            raise _authentication_required()
        try:
            object_id = UUID(identity.external_id or "")
        except ValueError:
            raise _authentication_required() from None
        if object_id.int == 0:
            raise _authentication_required()
        return RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=self._entra_tenant_id,
            entra_object_id=object_id,
        )


class LocalUserResolver:
    def __init__(self, *, entra_tenant_id: UUID, entra_object_id: UUID) -> None:
        self._principal = RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
        )

    async def resolve(self, headers: Mapping[str, str]) -> RequestPrincipal:
        del headers
        return self._principal


class WebIdentityProvider(IdentityProvider):
    """Preserve existing route interfaces while requiring middleware state."""

    def __init__(self) -> None:
        super().__init__(AuthMode.AZURE_EASY_AUTH)

    def authenticate(self, headers: Mapping[str, str] | None) -> RequestPrincipal:
        del headers
        principal = _BOUND_PRINCIPAL.get()
        if principal is None:
            raise _authentication_required()
        return principal

    def request_principal(self, request: object | None) -> RequestPrincipal:
        del request
        return self.authenticate(None)

    @staticmethod
    def bind(principal: RequestPrincipal) -> Token[RequestPrincipal | None]:
        return _BOUND_PRINCIPAL.set(principal)

    @staticmethod
    def reset(token: Token[RequestPrincipal | None]) -> None:
        _BOUND_PRINCIPAL.reset(token)


class WebAuthenticationMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        identity_provider: WebIdentityProvider,
        resolver: RequestIdentityResolver,
    ) -> None:
        self._app = app
        self._identity_provider = identity_provider
        self._resolver = resolver

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not path.startswith("/api/"):
            await self._app(scope, receive, send)
            return

        try:
            principal = await self._resolver.resolve(Headers(scope=scope))
        except AuthenticationError as error:
            correlation_id = str(uuid4())
            response = JSONResponse(
                {
                    "error": {
                        "code": error.public_code,
                        "message": error.message,
                        "retryable": error.http_status == 503,
                        "correlation_id": correlation_id,
                    }
                },
                status_code=error.http_status,
                headers={
                    "Cache-Control": "no-store",
                    "X-Correlation-ID": correlation_id,
                },
            )
            await response(scope, receive, send)
            return

        scope.setdefault("state", {})["request_principal"] = principal
        context_token = self._identity_provider.bind(principal)
        try:
            await self._app(scope, receive, send)
        finally:
            self._identity_provider.reset(context_token)


def _authentication_required() -> AuthenticationError:
    return AuthenticationError(
        public_code="authentication_required",
        message="Authentication is required.",
        http_status=401,
    )


__all__ = [
    "CurrentUserLookup",
    "DatabricksUserIdentity",
    "DatabricksUserResolver",
    "LocalUserResolver",
    "RequestIdentityResolver",
    "SdkCurrentUserLookup",
    "WebAuthenticationMiddleware",
    "WebIdentityProvider",
]
