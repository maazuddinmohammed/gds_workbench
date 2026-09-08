"""Physical lifecycle HTTP contracts and safe governed result handling."""

# pyright: reportPrivateUsage=false
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, LiteralString, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import AuthorizationDeniedError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_workbench_api.features.metadata.review import (
    DatabaseMetadataReviewService,
    MetadataReviewRecord,
    ReviewedMetadataRecord,
    ReviewMetadataRecordsRequest,
    ReviewMetadataRecordsResult,
)
from gds_workbench_api.main import create_app
from psycopg.types.json import Jsonb

from tests.web_backend.test_model_change_sets_api import _identity_provider


class RecordingReviewService:
    def __init__(self) -> None:
        self.calls: list[
            tuple[RequestPrincipal, int, ReviewMetadataRecordsRequest, UUID]
        ] = []

    async def review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        command: ReviewMetadataRecordsRequest,
        idempotency_key: UUID,
    ) -> ReviewMetadataRecordsResult:
        self.calls.append((principal, tenant_id, command, idempotency_key))
        return ReviewMetadataRecordsResult(
            review_event_id=9,
            action_count=1,
            records=[
                ReviewedMetadataRecord(
                    record_id=81,
                    review_revision="b" * 64,
                    is_active=True,
                    is_locked=True,
                )
            ],
        )


@pytest.mark.parametrize("record_type", ["object", "attribute"])
@pytest.mark.parametrize(
    "action", ["lock", "unlock", "deactivate", "reactivate", "describe"]
)
def test_physical_review_route_preserves_intent_and_server_identity(
    record_type: str, action: str
) -> None:
    service = RecordingReviewService()
    key = uuid4()
    with TestClient(
        create_app(
            identity_provider=_identity_provider(), metadata_review_service=service
        )
    ) as client:
        response = client.post(
            "/api/v1/tenants/7/metadata/review",
            headers={"Idempotency-Key": str(key)},
            json={
                "record_type": record_type,
                "action": action,
                "records": [
                    {
                        "record_id": 81,
                        "expected_revision": "a" * 64,
                        **(
                            {"description": "Order identifier."}
                            if action == "describe"
                            else {}
                        ),
                    }
                ],
            },
        )
    assert response.status_code == 200
    assert response.json() == {
        "review_event_id": 9,
        "action_count": 1,
        "records": [
            {
                "record_id": 81,
                "review_revision": "b" * 64,
                "is_active": True,
                "is_locked": True,
            }
        ],
    }
    assert len(service.calls) == 1
    principal, tenant_id, command, idempotency = service.calls[0]
    assert principal.actor_kind is ActorKind.HUMAN and tenant_id == 7
    assert (
        command.record_type == record_type
        and command.action == action
        and idempotency == key
    )


@pytest.mark.parametrize(
    "override",
    [
        {"records": []},
        {"records": [{"record_id": 0, "expected_revision": "a" * 64}]},
        {"records": [{"record_id": True, "expected_revision": "a" * 64}]},
        {"records": [{"record_id": 2**63, "expected_revision": "a" * 64}]},
        {"records": [{"record_id": 81, "expected_revision": "A" * 64}]},
        {"records": [{"record_id": 81, "expected_revision": "a" * 64}] * 2},
        {
            "records": [
                {"record_id": i, "expected_revision": "a" * 64} for i in range(1, 202)
            ]
        },
        {
            "records": [
                {
                    "record_id": 81,
                    "expected_revision": "a" * 64,
                    "attribute_description": "Private caller text",
                }
            ]
        },
        {"action": "delete"},
        {"action": "describe"},
        {
            "records": [
                {"record_id": 81, "expected_revision": "a" * 64, "description": None}
            ]
        },
        {"record_type": "core.object"},
        {"actor_principal_id": 1},
        {"model_id": 9},
    ],
)
def test_physical_review_route_rejects_unbounded_or_caller_authored_fields(
    override: dict[str, object],
) -> None:
    service = RecordingReviewService()
    body = {
        "record_type": "attribute",
        "action": "lock",
        "records": [{"record_id": 81, "expected_revision": "a" * 64}],
        **override,
    }
    with TestClient(
        create_app(
            identity_provider=_identity_provider(), metadata_review_service=service
        )
    ) as client:
        response = client.post(
            "/api/v1/tenants/7/metadata/review",
            headers={"Idempotency-Key": str(uuid4())},
            json=body,
        )
    assert response.status_code == 422 and not service.calls


@pytest.mark.parametrize("headers", [{}, {"Idempotency-Key": "invalid"}])
def test_physical_review_requires_idempotency_key(headers: dict[str, str]) -> None:
    service = RecordingReviewService()
    with TestClient(
        create_app(
            identity_provider=_identity_provider(), metadata_review_service=service
        )
    ) as client:
        response = client.post(
            "/api/v1/tenants/7/metadata/review",
            headers=headers,
            json={
                "record_type": "attribute",
                "action": "lock",
                "records": [{"record_id": 81, "expected_revision": "a" * 64}],
            },
        )
    assert response.status_code == 422 and not service.calls


class ReviewDatabase:
    def __init__(self, denial: str | None = None) -> None:
        self.denial = denial
        self.calls: list[tuple[LiteralString, tuple[Any, ...]]] = []

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction, None]:
        yield cast(WriteTransaction, self)

    async def fetch_one(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> dict[str, Any]:
        self.calls.append((query, parameters))
        return {
            "denial_code": self.denial,
            "review_event_id": 9,
            "action_count": 2,
            "records": [
                {
                    "record_id": record_id,
                    "review_revision": "b" * 64,
                    "is_active": True,
                    "is_locked": True,
                }
                for record_id in (81, 82)
            ],
        }


def _principal(kind: ActorKind = ActorKind.HUMAN) -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=kind, entra_tenant_id=uuid4(), entra_object_id=uuid4()
    )


def _command() -> ReviewMetadataRecordsRequest:
    return ReviewMetadataRecordsRequest(
        record_type="attribute",
        action="lock",
        records=[
            MetadataReviewRecord(record_id=record_id, expected_revision="a" * 64)
            for record_id in (82, 81)
        ],
    )


async def test_review_service_uses_only_fixed_governed_sql_and_authenticated_actor() -> (
    None
):
    database = ReviewDatabase()
    principal, key = _principal(), uuid4()
    result = await DatabaseMetadataReviewService(database=database).review_records(
        principal, tenant_id=7, command=_command(), idempotency_key=key
    )
    assert result.action_count == 2 and len(database.calls) == 1
    query, parameters = database.calls[0]
    assert "application.review_metadata_records(" in query
    assert parameters[:6] == (
        principal.entra_tenant_id,
        principal.entra_object_id,
        "user",
        7,
        "attribute",
        "lock",
    )
    assert isinstance(parameters[6], Jsonb)
    assert parameters[6].obj == [
        {"record_id": record_id, "expected_revision": "a" * 64}
        for record_id in (81, 82)
    ]
    assert parameters[7] == key


@pytest.mark.parametrize("kind", [ActorKind.WORKLOAD, ActorKind.DEVELOPMENT])
async def test_physical_review_rejects_nonhuman_execution_before_sql(
    kind: ActorKind,
) -> None:
    database = ReviewDatabase()
    with pytest.raises(AuthorizationDeniedError):
        await DatabaseMetadataReviewService(database=database).review_records(
            _principal(kind), tenant_id=7, command=_command(), idempotency_key=uuid4()
        )
    assert not database.calls


@pytest.mark.parametrize(
    "denial, expected",
    [
        ("metadata_revision_conflict", "metadata_revision_conflict"),
        ("metadata_selection_conflict", "metadata_selection_conflict"),
        ("metadata_review_conflict", "metadata_review_conflict"),
        ("tenant_locked", "tenant_lock_required"),
        ("object_locked", "object_locked"),
        ("attribute_locked", "attribute_locked"),
        ("Private unexpected database message", "dependency_unavailable"),
    ],
)
async def test_review_denials_are_actionable_without_raw_database_details(
    denial: str, expected: str
) -> None:
    with pytest.raises(WorkbenchError) as caught:
        await DatabaseMetadataReviewService(
            database=ReviewDatabase(denial)
        ).review_records(
            _principal(), tenant_id=7, command=_command(), idempotency_key=uuid4()
        )
    assert caught.value.code == expected and "Private" not in str(caught.value)
