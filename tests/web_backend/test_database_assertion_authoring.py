"""Manual requirements retain authorization, revisions, idempotency and locks."""

# pyright: reportPrivateUsage=false
from typing import cast
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.assertions.authoring import (
    AssertionDetails,
    SaveAssertionRequest,
)
from gds_workbench_api.features.model_change_sets.contracts import (
    ReviewModelRecordsRequest,
)
from gds_workbench_api.features.model_change_sets.review import RecordReviewAction
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from gds_workbench_api.features.models import ModelRevisionConflictError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _seed_model_foundation,
)


async def test_manual_requirement_round_trip(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    prefix = f"REQ_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    principal = StaticIdentityProvider().request_principal(None)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseModelChangeSetService(
        database=database, authorizer=AuthorizationService()
    )
    command = SaveAssertionRequest(
        expected_model_revision=1,
        document_name="Finance and customer requirements",
        document_type="business_context",
        record_key="monthly_sales",
        record_type="reporting_requirement",
        text="Report monthly net sales by customer segment.",
        details=AssertionDetails(
            notes="Sales less refunds, grouped by month and segment."
        ),
        source_reference="Finance requirements, section 2",
    )

    async def save(value: SaveAssertionRequest = command, key: UUID | None = None):
        return await service.save_assertion(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=value,
            idempotency_key=key or uuid4(),
        )

    await database.open()
    try:
        with pytest.raises(WorkbenchError):
            await save()
        _acquire_tenant_lock(fixture, tenant_id)
        key = uuid4()
        result = await save(key=key)
        assert result.model_revision == 2 and result.action_count == 2
        assert await save(key=key) == result
        with pytest.raises(ModelRevisionConflictError):
            await save()
        with pytest.raises(InvalidRequestError):
            await save(command.model_copy(update={"expected_model_revision": 2}))
        with fixture.connect_owner() as connection:
            row = connection.execute(
                "SELECT modeling_assertion_record_id AS id, modeling_assertion_details AS details "
                "FROM model.modeling_assertion_record WHERE model_id=%s",
                (model_id,),
            ).fetchone()
        assert (
            row is not None
            and row["details"]["notes"]
            == "Sales less refunds, grouped by month and segment."
        )
        updated = command.model_copy(
            update={
                "record_id": row["id"],
                "expected_model_revision": 2,
                "text": "Report net sales by month and segment.",
            }
        )
        assert (await save(updated)).model_revision == 3
        for action, revision in (
            ("lock", 3),
            ("unlock", 4),
            ("deactivate", 5),
            ("reactivate", 6),
        ):
            result = await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=ReviewModelRecordsRequest(
                    dataset="modeling_assertion_record",
                    record_ids=[row["id"]],
                    action=cast(RecordReviewAction, action),
                    expected_model_revision=revision,
                ),
                idempotency_key=uuid4(),
            )
            assert result.model_revision == revision + 1
            if action == "lock":
                with pytest.raises(InvalidRequestError):
                    await save(
                        updated.model_copy(update={"expected_model_revision": 4})
                    )
        with pytest.raises(InvalidRequestError):
            await save(
                command.model_copy(
                    update={
                        "expected_model_revision": 7,
                        "document_name": "System context",
                        "record_key": "system.identity",
                        "source_system_code": "MISSING_SYSTEM",
                    }
                )
            )
        assert (
            await save(
                command.model_copy(
                    update={
                        "expected_model_revision": 7,
                        "document_name": "System context",
                        "record_key": "system.identity",
                        "source_system_code": f"{prefix}_ERP",
                    }
                )
            )
        ).model_revision == 8
        # More records share the named Document without changing its metadata or scope.
        second = command.model_copy(
            update={
                "expected_model_revision": 8,
                "record_key": "customer.identity",
                "record_type": "identity_rule",
                "text": "Customer identity is stable across orders.",
            }
        )
        assert (await save(second)).model_revision == 9
        with fixture.connect_owner() as connection:
            documents = connection.execute(
                "SELECT modeling_assertion_document_name AS name, count(*) OVER () AS total "
                "FROM model.modeling_assertion_document WHERE model_id=%s",
                (model_id,),
            ).fetchall()
        assert len(documents) == 2
        assert {d["name"] for d in documents} == {
            command.document_name,
            "System context",
        }
        async with database.read_transaction() as transaction:
            snapshot = await build_model_snapshot(
                transaction,
                ModelReadContext(
                    model_id=model_id,
                    tenant_id=tenant_id,
                    model_name="Requirement Model",
                    model_revision=9,
                ),
                enforce_row_limits=False,
            )
            assert snapshot.model_tenant_code
            scoped = next(d for d in snapshot.assertion.documents if d.system_code)
            assert scoped.tenant_code == snapshot.model_tenant_code
    finally:
        await database.close()
