"""Bounded Azure App Service Easy Auth identity parsing."""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

_CLIENT_PRINCIPAL_HEADER = "x-ms-client-principal"
_MAX_DECODED_BYTES = 64 * 1024
_MAX_ENCODED_BYTES = 90 * 1024
_MAX_CLAIMS = 256
_MAX_CLAIM_VALUE_CHARS = 4096

_TENANT_CLAIMS = frozenset({"tid", "http://schemas.microsoft.com/identity/claims/tenantid"})
_OBJECT_CLAIMS = frozenset({"oid", "http://schemas.microsoft.com/identity/claims/objectidentifier"})
_IDENTITY_TYPE_CLAIMS = frozenset({"idtyp"})
_SCOPE_CLAIMS = frozenset({"scp", "http://schemas.microsoft.com/identity/claims/scope"})
_ROLE_CLAIMS = frozenset({"roles", "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"})


@dataclass(frozen=True, slots=True)
class AuthenticationError(Exception):
    public_code: str
    message: str
    http_status: int

    def __str__(self) -> str:
        return self.message


class IdentityProvider:
    """Resolve a request identity from either dev mode or trusted Easy Auth claims."""

    def __init__(
        self,
        auth_mode: AuthMode,
        *,
        local_tenant_id: UUID | None = None,
        local_principal_object_id: UUID | None = None,
    ) -> None:
        self._auth_mode = auth_mode
        self._local_tenant_id = local_tenant_id
        self._local_principal_object_id = local_principal_object_id

    def authenticate(self, headers: Mapping[str, str] | None) -> RequestPrincipal:
        if self._auth_mode is AuthMode.DEV:
            if self._local_tenant_id is not None and self._local_principal_object_id is not None:
                return RequestPrincipal(
                    actor_kind=ActorKind.HUMAN,
                    entra_tenant_id=self._local_tenant_id,
                    entra_object_id=self._local_principal_object_id,
                )
            return RequestPrincipal.development()

        normalized_headers = {key.lower(): value for key, value in (headers or {}).items()}
        encoded = normalized_headers.get(_CLIENT_PRINCIPAL_HEADER, "")
        if not encoded:
            raise AuthenticationError(
                public_code="authentication_required",
                message="Authentication is required.",
                http_status=401,
            )
        if len(encoded) > _MAX_ENCODED_BYTES:
            raise _invalid_identity()

        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise _invalid_identity() from exc
        if not decoded or len(decoded) > _MAX_DECODED_BYTES:
            raise _invalid_identity()

        try:
            payload: object = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _invalid_identity() from exc
        if not isinstance(payload, dict):
            raise _invalid_identity()
        payload_object = cast(dict[str, object], payload)
        if payload_object.get("auth_typ") != "aad":
            raise _invalid_identity()

        raw_claims = payload_object.get("claims")
        if not isinstance(raw_claims, list):
            raise _invalid_identity()
        claims = cast(list[object], raw_claims)
        if not 1 <= len(claims) <= _MAX_CLAIMS:
            raise _invalid_identity()

        claim_values: dict[str, list[str]] = {}
        for claim in claims:
            if not isinstance(claim, dict):
                raise _invalid_identity()
            claim_object = cast(dict[str, object], claim)
            claim_type = claim_object.get("typ")
            claim_value = claim_object.get("val")
            if not isinstance(claim_type, str) or not isinstance(claim_value, str):
                raise _invalid_identity()
            if not claim_type or len(claim_type) > _MAX_CLAIM_VALUE_CHARS:
                raise _invalid_identity()
            if not claim_value or len(claim_value) > _MAX_CLAIM_VALUE_CHARS:
                raise _invalid_identity()
            claim_values.setdefault(claim_type, []).append(claim_value)

        tenant_id = _one_uuid_claim(claim_values, _TENANT_CLAIMS)
        object_id = _one_uuid_claim(claim_values, _OBJECT_CLAIMS)
        identity_type = _one_text_claim(claim_values, _IDENTITY_TYPE_CLAIMS)
        if identity_type == "user":
            scopes = {
                scope
                for claim_type in _SCOPE_CLAIMS
                for value in claim_values.get(claim_type, [])
                for scope in value.split()
            }
            if "workbench.access" not in scopes:
                raise AuthenticationError(
                    public_code="authorization_denied",
                    message="Required application scope is missing.",
                    http_status=403,
                )
            actor_kind = ActorKind.HUMAN
        elif identity_type == "app":
            roles = {
                role for claim_type in _ROLE_CLAIMS for role in claim_values.get(claim_type, [])
            }
            if "workbench.workflow" not in roles:
                raise AuthenticationError(
                    public_code="authorization_denied",
                    message="Required application permission is missing.",
                    http_status=403,
                )
            actor_kind = ActorKind.WORKLOAD
        else:
            raise AuthenticationError(
                public_code="authorization_denied",
                message="This operation is not available to this actor.",
                http_status=403,
            )

        return RequestPrincipal(
            actor_kind=actor_kind,
            entra_tenant_id=tenant_id,
            entra_object_id=object_id,
        )

    def request_principal(self, request: object | None) -> RequestPrincipal:
        """Read middleware-authenticated state; only local dev may lack HTTP state."""
        state = getattr(request, "state", None)
        principal = getattr(state, "request_principal", None)
        if isinstance(principal, RequestPrincipal):
            return principal
        if self._auth_mode is AuthMode.DEV:
            return RequestPrincipal.development()
        raise AuthenticationError(
            public_code="authentication_required",
            message="Authentication is required.",
            http_status=401,
        )


def _one_uuid_claim(claims: Mapping[str, list[str]], aliases: frozenset[str]) -> UUID:
    raw = _one_text_claim(claims, aliases)
    try:
        return UUID(raw)
    except ValueError as exc:
        raise _invalid_identity() from exc


def _one_text_claim(claims: Mapping[str, list[str]], aliases: frozenset[str]) -> str:
    values = {value for alias in aliases for value in claims.get(alias, [])}
    if len(values) != 1:
        raise _invalid_identity()
    return next(iter(values))


def _invalid_identity() -> AuthenticationError:
    return AuthenticationError(
        public_code="authentication_required",
        message="Authenticated identity is invalid.",
        http_status=401,
    )
