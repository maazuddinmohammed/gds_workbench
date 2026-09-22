"""Exercise shared authentication through real FastAPI request handling."""

from uuid import UUID

from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_workbench_api.features.session import SessionRecord
from gds_workbench_api.main import create_app


class RecordingSessionService:
    def __init__(self) -> None:
        self.principals: list[RequestPrincipal] = []

    async def read_session(self, principal: RequestPrincipal) -> SessionRecord:
        self.principals.append(principal)
        return SessionRecord(
            display_name="Fixture Principal",
            actor_kind=principal.actor_kind,
            is_super_admin=False,
            last_tenant_id=None,
        )


def test_authentication_dependencies_are_isolated_between_apps_and_ignore_query_identity() -> None:
    first_service = RecordingSessionService()
    second_service = RecordingSessionService()
    first = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID(int=1),
            local_principal_object_id=UUID(int=2),
        ),
        session_service=first_service,
    )
    second = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID(int=3),
            local_principal_object_id=UUID(int=4),
        ),
        session_service=second_service,
    )
    with TestClient(first) as first_client, TestClient(second) as second_client:
        for client in (first_client, second_client, first_client):
            assert (
                client.get("/api/v1/session?principal=forged&actor_kind=service").status_code == 200
            )
    assert [p.entra_object_id for p in first_service.principals] == [
        UUID(int=2),
        UUID(int=2),
    ]
    assert [p.entra_object_id for p in second_service.principals] == [UUID(int=4)]
    assert "parameters" not in first.openapi()["paths"]["/api/v1/session"]["get"]


def test_failed_authentication_never_calls_service_and_leaves_health_public() -> None:
    service = RecordingSessionService()
    app = create_app(
        identity_provider=IdentityProvider(AuthMode.AZURE_EASY_AUTH),
        session_service=service,
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/session?principal=forged")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_required"
        assert client.get("/healthz").status_code == 200
    assert service.principals == []
