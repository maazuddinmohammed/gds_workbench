"""Interactive Entra authentication with platform-protected token caching."""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from anyio import Lock
from anyio.to_thread import run_sync
from azure.core.credentials import AccessToken
from azure.identity import (
    AuthenticationRecord,
    InteractiveBrowserCredential,
    TokenCachePersistenceOptions,
)

from .configuration import BridgeConfigurationError, BridgeSettings
from .remote import OAuthMetadata


class InteractiveCredential(Protocol):
    def authenticate(
        self,
        *,
        scopes: Iterable[str] | None = None,
    ) -> AuthenticationRecord: ...

    def get_token(self, *scopes: str) -> AccessToken: ...

    def close(self) -> None: ...


CredentialFactory = Callable[
    [OAuthMetadata, AuthenticationRecord | None],
    InteractiveCredential,
]


class EntraAccessTokenProvider:
    """Acquire delegated user tokens without exposing authentication to MCP."""

    def __init__(
        self,
        settings: BridgeSettings,
        *,
        state_directory: Path | None = None,
        credential_factory: CredentialFactory | None = None,
    ) -> None:
        self._settings = settings
        self._state_directory = state_directory or _default_state_directory()
        self._credential_factory = credential_factory or self._create_credential
        self._credential: InteractiveCredential | None = None
        self._credential_tenant_id: str | None = None
        self._lock = Lock()

    async def get_token(self, metadata: OAuthMetadata) -> str:
        async with self._lock:
            return await run_sync(self._get_token_sync, metadata)

    async def close(self) -> None:
        async with self._lock:
            credential = self._credential
            self._credential = None
            self._credential_tenant_id = None
            if credential is not None:
                await run_sync(credential.close)

    def _get_token_sync(self, metadata: OAuthMetadata) -> str:
        tenant_id = str(metadata.tenant_id)
        if self._credential_tenant_id not in {None, tenant_id}:
            raise BridgeConfigurationError("remote OAuth tenant changed during this session")

        if self._credential is None:
            record = self._load_authentication_record(metadata)
            self._credential = self._credential_factory(metadata, record)
            self._credential_tenant_id = tenant_id
            if record is None:
                record = self._credential.authenticate(scopes=[metadata.scope])
                self._validate_authentication_record(record, metadata)
                self._save_authentication_record(record, metadata)

        access_token = self._credential.get_token(metadata.scope)
        if not access_token.token:
            raise BridgeConfigurationError("Entra returned an empty access token")
        return access_token.token

    def _create_credential(
        self,
        metadata: OAuthMetadata,
        record: AuthenticationRecord | None,
    ) -> InteractiveCredential:
        cache_name = (
            f"gds-workbench-bridge-{metadata.tenant_id}-{self._settings.entra_client_id}"
        )
        return InteractiveBrowserCredential(
            tenant_id=str(metadata.tenant_id),
            client_id=str(self._settings.entra_client_id),
            redirect_uri=self._settings.redirect_uri,
            authentication_record=record,
            cache_persistence_options=TokenCachePersistenceOptions(name=cache_name),
            timeout=300,
        )

    def _authentication_record_path(self, metadata: OAuthMetadata) -> Path:
        return self._state_directory / (
            f"account-{metadata.tenant_id}-{self._settings.entra_client_id}.json"
        )

    def _load_authentication_record(
        self,
        metadata: OAuthMetadata,
    ) -> AuthenticationRecord | None:
        path = self._authentication_record_path(metadata)
        if not path.exists():
            return None
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 16_384:
            raise BridgeConfigurationError("local Entra account record is invalid")
        try:
            record = AuthenticationRecord.deserialize(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise BridgeConfigurationError("local Entra account record is invalid") from exc
        self._validate_authentication_record(record, metadata)
        return record

    def _validate_authentication_record(
        self,
        record: AuthenticationRecord,
        metadata: OAuthMetadata,
    ) -> None:
        if (
            record.tenant_id != str(metadata.tenant_id)
            or record.client_id != str(self._settings.entra_client_id)
            or record.authority != "login.microsoftonline.com"
        ):
            raise BridgeConfigurationError("local Entra account record is incompatible")

    def _save_authentication_record(
        self,
        record: AuthenticationRecord,
        metadata: OAuthMetadata,
    ) -> None:
        path = self._authentication_record_path(metadata)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or not path.parent.is_dir():
            raise BridgeConfigurationError("local Entra state directory is invalid")
        path.parent.chmod(0o700)

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix="account-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary_path.chmod(0o600)
                temporary.write(record.serialize())
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, path)
            path.chmod(0o600)
        except OSError as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise BridgeConfigurationError("could not save local Entra account record") from exc


def _default_state_directory() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "gds-workbench-bridge"
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        root = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return root / "gds-workbench-bridge"
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg_state_home) if xdg_state_home else Path.home() / ".local" / "state"
    return root / "gds-workbench-bridge"
