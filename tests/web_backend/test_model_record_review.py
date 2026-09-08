from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, LiteralString, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import TenantLockRequiredError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.model_change_sets.contracts import (
    CreateModelChangeSetRequest,
    ReviewModelRecordsRequest,
)
from gds_workbench_api.features.model_change_sets.router import ModelChangeSetService
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
    ModelChangeSetDatabase,
)
from gds_workbench_api.features.models import ModelRevisionConflictError
from gds_workbench_api.main import create_app

from tests.web_backend.test_database_model_change_sets import (
    DisposablePostgresFixture,
    _seed_profile_model,  # pyright: ignore[reportPrivateUsage]
)
from tests.web_backend.test_model_change_sets_api import (
    StaticModelChangeSetService,
    _identity_provider,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.parametrize(
    ("denial", "expected_code"),
    [
        ("invalid_request", "invalid_request"),
        ("authorization_denied", "authorization_denied"),
        ("model_not_found", "model_not_found"),
        ("tenant_not_found", "model_not_found"),
        ("tenant_lock_required", "tenant_lock_required"),
        ("tenant_locked", "tenant_lock_required"),
        ("unexpected_private_marker", "dependency_unavailable"),
    ],
)
async def test_review_uses_governed_fence_before_authorization_and_maps_safe_denials(
    denial: str, expected_code: str
) -> None:
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN, entra_tenant_id=uuid4(), entra_object_id=uuid4()
    )
    calls = 0

    class Transaction:
        async def fetch_one(
            self, query: LiteralString, parameters: tuple[object, ...] = ()
        ) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            assert "application.authorize_model_record_review" in query
            assert parameters == (principal.entra_tenant_id, principal.entra_object_id, 7, 18)
            return {"denial_code": denial}

    class Database:
        @asynccontextmanager
        async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
            yield cast(WriteTransaction, Transaction())

    service = DatabaseModelChangeSetService(
        database=cast(ModelChangeSetDatabase, Database()), authorizer=AuthorizationService()
    )
    with pytest.raises(WorkbenchError) as raised:
        await service.review_records(
            principal,
            tenant_id=7,
            model_id=18,
            command=ReviewModelRecordsRequest(
                dataset="analysis_result",
                record_ids=[81],
                action="lock",
                expected_model_revision=4,
            ),
            idempotency_key=uuid4(),
        )
    assert raised.value.code == expected_code
    assert "unexpected_private_marker" not in str(raised.value)
    assert calls == 1


def test_analysis_review_route_accepts_only_bounded_selected_ids() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        model_change_set_service=cast(ModelChangeSetService, StaticModelChangeSetService()),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/change-sets/review",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "dataset": "analysis_result",
                "record_ids": [81],
                "action": "unlock",
                "expected_model_revision": 4,
                "records": [{"relationship_basis": "Caller must not author rows."}],
            },
        )
    assert response.status_code == 422


@pytest.mark.parametrize("record_ids", [[], [0], [True], [81, 81], list(range(1, 202))])
def test_analysis_review_route_rejects_invalid_selection(record_ids: list[int]) -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        model_change_set_service=cast(ModelChangeSetService, StaticModelChangeSetService()),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/change-sets/review",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "dataset": "analysis_result",
                "record_ids": record_ids,
                "action": "unlock",
                "expected_model_revision": 4,
            },
        )
    assert response.status_code == 422


async def test_analysis_review_round_trip_preserves_evidence_and_fences_writes(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    model_id, tenant_id, attribute_id, entra_tenant, entra_object, _ = _seed_profile_model(
        web_postgres_database
    )
    with web_postgres_database.connect_owner() as connection:
        second = connection.execute(
            """INSERT INTO core.attribute (
                object_id, attribute_name, attribute_ordinal_position, attribute_data_type
            ) SELECT object_id, 'review_parent_id', 2, 'bigint'
                FROM core.attribute WHERE attribute_id = %s
            RETURNING object_id, attribute_id""",
            (attribute_id,),
        ).fetchone()
        assert second is not None
        result = connection.execute(
            """INSERT INTO workflow.analysis_result (
                model_id, agent_run_id, from_object_id, from_attribute_id,
                to_object_id, to_attribute_id, relationship_kind,
                relationship_confidence, relationship_basis, validation_policy_version,
                validation_policy_digest, validation_result,
                validation_source_non_null_count, validation_source_distinct_count,
                validation_target_non_null_count, validation_target_distinct_count,
                validation_source_missing_target_count, validation_unused_target_count,
                validation_duplicate_target_key_count
            ) VALUES (%s, 'review-fixture-agent', %s, %s, %s, %s, 'reference', 'high',
                'Fixture relationship.', '1.0.0', %s, 'supported', 2, 2, 2, 2, 0, 0, 0)
            RETURNING *""",
            (
                model_id,
                second["object_id"],
                attribute_id,
                second["object_id"],
                second["attribute_id"],
                "b" * 64,
            ),
        ).fetchone()
        assert result is not None
        record_id = cast(int, result["analysis_result_id"])
        acquired = connection.execute(
            "SELECT acquired FROM security.acquire_tenant_lock(%s, %s, 'user', %s, 60, %s)",
            (entra_tenant, entra_object, tenant_id, "Review fixture"),
        ).fetchone()
        assert acquired == {"acquired": True}
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant,
        entra_object_id=entra_object,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseModelChangeSetService(database=database, authorizer=AuthorizationService())
    await database.open()
    try:
        existing_draft = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=CreateModelChangeSetRequest(expected_model_revision=1),
            idempotency_key=uuid4(),
        )
        command = ReviewModelRecordsRequest(
            dataset="analysis_result",
            record_ids=[record_id],
            action="lock",
            expected_model_revision=1,
        )
        key = uuid4()
        locked = await service.review_records(
            principal, tenant_id=tenant_id, model_id=model_id, command=command, idempotency_key=key
        )
        assert (locked.action_count, locked.model_revision) == (1, 2)
        assert (
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command,
                idempotency_key=key,
            )
            == locked
        )
        with pytest.raises(WorkbenchError, match="already used"):
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command.model_copy(update={"action": "unlock"}),
                idempotency_key=key,
            )
        with pytest.raises(ModelRevisionConflictError):
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command,
                idempotency_key=uuid4(),
            )
        with pytest.raises(WorkbenchError, match="Unlock selected"):
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command.model_copy(
                    update={"action": "deactivate", "expected_model_revision": 2}
                ),
                idempotency_key=uuid4(),
            )
        with pytest.raises(WorkbenchError, match="unavailable"):
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command.model_copy(
                    update={"record_ids": [record_id, 2**62], "expected_model_revision": 2}
                ),
                idempotency_key=uuid4(),
            )
        revision = 2
        for action, expected_locked, expected_status in (
            ("unlock", False, "active"),
            ("deactivate", False, "inactive"),
            ("reactivate", False, "active"),
            ("lock", True, "active"),
        ):
            reviewed = await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=ReviewModelRecordsRequest.model_validate(
                    {
                        "dataset": "analysis_result",
                        "record_ids": [record_id],
                        "action": action,
                        "expected_model_revision": revision,
                    }
                ),
                idempotency_key=uuid4(),
            )
            revision += 1
            assert reviewed.model_revision == revision
            with web_postgres_database.connect_owner() as connection:
                current = connection.execute(
                    "SELECT * FROM workflow.analysis_result WHERE analysis_result_id = %s",
                    (record_id,),
                ).fetchone()
                assert current is not None
                assert current["analysis_result_is_locked"] is expected_locked
                assert current["analysis_result_status"] == expected_status
                assert all(
                    current[field] == value
                    for field, value in result.items()
                    if field
                    not in {
                        "analysis_result_is_locked",
                        "analysis_result_status",
                        "updated_time",
                        "updated_by",
                    }
                )
                events = connection.execute(
                    """SELECT count(*) AS count FROM mcp.model_change_set_event
                        WHERE model_change_set_id = %s""",
                    (reviewed.model_change_set_id,),
                ).fetchone()
                assert events == {"count": 4}
                if action == "unlock":
                    audit = connection.execute(
                        """SELECT validation_outcome FROM mcp.model_change_set
                            WHERE model_change_set_id = %s""",
                        (reviewed.model_change_set_id,),
                    ).fetchone()
                    assert audit is not None
                    outcome = cast(dict[str, object], audit["validation_outcome"])
                    summaries = cast(list[dict[str, object]], outcome["action_review"])
                    assert summaries[0]["update_count"] == 1
        no_change = await service.review_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=command.model_copy(update={"expected_model_revision": revision}),
            idempotency_key=uuid4(),
        )
        assert (no_change.action_count, no_change.model_revision) == (0, revision)
        with web_postgres_database.connect_owner() as connection:
            draft = connection.execute(
                """SELECT model_change_set_status, draft_revision, analysis_document
                     FROM mcp.model_change_set WHERE model_change_set_id = %s""",
                (existing_draft.model_change_set_id,),
            ).fetchone()
            assert draft == {
                "model_change_set_status": "active",
                "draft_revision": 1,
                "analysis_document": {},
            }
            connection.execute(
                "SELECT released FROM security.release_tenant_lock(%s, %s, 'user', %s)",
                (entra_tenant, entra_object, tenant_id),
            )
        with pytest.raises(TenantLockRequiredError):
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command.model_copy(update={"expected_model_revision": revision}),
                idempotency_key=uuid4(),
            )
    finally:
        await database.close()
