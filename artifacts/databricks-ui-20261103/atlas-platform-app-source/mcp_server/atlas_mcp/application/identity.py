"""Identity interface shared by transport adapters."""

from collections.abc import Mapping
from typing import Protocol

from atlas_mcp.domain.authorization import RequestPrincipal


class IdentityProvider(Protocol):
    def authenticate(self, headers: Mapping[str, str] | None) -> RequestPrincipal: ...

    def request_principal(self, request: object | None) -> RequestPrincipal: ...


__all__ = ["IdentityProvider"]
