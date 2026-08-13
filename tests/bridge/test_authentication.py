from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from time import time
from uuid import UUID

from anyio.to_thread import run_sync
from azure.core.credentials import AccessToken
from azure.identity import AuthenticationRecord

from gds_workbench_bridge.authentication import EntraAccessTokenProvider
from gds_workbench_bridge.configuration import BridgeSettings
from gds_workbench_bridge.remote import OAuthMetadata


class FakeInteractiveCredential:
    def __init__(
        self,
        record: AuthenticationRecord | None,
        authenticated_record: AuthenticationRecord,
    ) -> None:
        self.record = record
        self.authenticated_record = authenticated_record
        self.authenticate_calls = 0
        self.token_calls = 0
        self.closed = False

    def authenticate(
        self,
        *,
        scopes: Iterable[str] | None = None,
    ) -> AuthenticationRecord:
        assert list(scopes or []) == [
            "https://testserver/mcp/workbench.access"
        ]
        self.authenticate_calls += 1
        return self.authenticated_record

    def get_token(self, *scopes: str) -> AccessToken:
        assert scopes == ("https://testserver/mcp/workbench.access",)
        self.token_calls += 1
        return AccessToken("test-access-token", int(time()) + 3600)

    def close(self) -> None:
        self.closed = True


def settings() -> BridgeSettings:
    return BridgeSettings(
        remote_url="https://testserver/mcp",
        entra_client_id=UUID("22222222-2222-2222-2222-222222222222"),
        redirect_uri="http://localhost:8400",
    )


def metadata() -> OAuthMetadata:
    return OAuthMetadata(
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        scope="https://testserver/mcp/workbench.access",
    )


def account_record() -> AuthenticationRecord:
    return AuthenticationRecord(
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        authority="login.microsoftonline.com",
        home_account_id="account-id",
        username="user@example.com",
    )


async def test_first_use_authenticates_and_saves_only_account_record(tmp_path: Path) -> None:
    credentials: list[FakeInteractiveCredential] = []

    def factory(
        _metadata: OAuthMetadata,
        record: AuthenticationRecord | None,
    ) -> FakeInteractiveCredential:
        credential = FakeInteractiveCredential(record, account_record())
        credentials.append(credential)
        return credential

    provider = EntraAccessTokenProvider(
        settings(),
        state_directory=tmp_path,
        credential_factory=factory,
    )

    token = await provider.get_token(metadata())
    await provider.close()

    assert token == "test-access-token"
    assert credentials[0].record is None
    assert credentials[0].authenticate_calls == 1
    assert credentials[0].token_calls == 1
    assert credentials[0].closed is True
    account_files = await run_sync(lambda: list(tmp_path.glob("account-*.json")))
    assert len(account_files) == 1
    assert "test-access-token" not in account_files[0].read_text(encoding="utf-8")
    assert account_files[0].stat().st_mode & 0o777 == 0o600


async def test_later_use_loads_account_record_without_interactive_login(
    tmp_path: Path,
) -> None:
    record_path = tmp_path / (
        "account-11111111-1111-1111-1111-111111111111-"
        "22222222-2222-2222-2222-222222222222.json"
    )
    record_path.write_text(account_record().serialize(), encoding="utf-8")
    record_path.chmod(0o600)
    credentials: list[FakeInteractiveCredential] = []

    def factory(
        _metadata: OAuthMetadata,
        record: AuthenticationRecord | None,
    ) -> FakeInteractiveCredential:
        credential = FakeInteractiveCredential(record, account_record())
        credentials.append(credential)
        return credential

    provider = EntraAccessTokenProvider(
        settings(),
        state_directory=tmp_path,
        credential_factory=factory,
    )

    token = await provider.get_token(metadata())
    await provider.close()

    assert token == "test-access-token"
    assert credentials[0].record is not None
    assert credentials[0].authenticate_calls == 0
    assert credentials[0].token_calls == 1
