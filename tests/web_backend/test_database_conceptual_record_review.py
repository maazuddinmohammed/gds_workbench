"""Conceptual review previews exact dependencies without changing stored records."""

# pyright: reportPrivateUsage=false
from typing import Any
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.features.model_change_sets.contracts import (
    PreviewModelRecordsRequest,
    ReviewModelRecordsRequest,
)
from gds_workbench_api.features.model_change_sets.service import DatabaseModelChangeSetService

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_model_review_governance import _setup


@pytest.mark.parametrize(("relationship_count", "locked"), [(1, False), (1, True), (205, False)])
async def test_conceptual_preview_is_complete_paged_and_preserves_stored_state(
    web_postgres_database: DisposablePostgres,
    relationship_count: int,
    locked: bool,
) -> None:
    database = web_postgres_database
    context, _, other, _, runtime = _setup(database)
    with database.connect_owner() as connection:
        objects = connection.execute(
            "INSERT INTO workflow.conceptual_object (model_id,conceptual_object_name,"
            "conceptual_object_definition,conceptual_object_type,conceptual_object_grain) "
            "VALUES (%s,'Customer','Customer identity.','entity','One customer.'),"
            "(%s,'Order','An order.','event','One order.') RETURNING conceptual_object_id",
            (context.model_id, context.model_id),
        ).fetchall()
        object_id, endpoint_id = [row["conceptual_object_id"] for row in objects]
        relationships = connection.execute(
            "INSERT INTO workflow.conceptual_relationship (model_id,from_conceptual_object_id,"
            "to_conceptual_object_id,conceptual_relationship_name,conceptual_relationship_type,"
            "conceptual_relationship_definition,conceptual_relationship_cardinality,"
            "conceptual_relationship_basis,conceptual_relationship_cardinality_basis,"
            "conceptual_relationship_is_locked) "
            "SELECT %s,%s,%s,'Relationship '||number,'association','Recorded relationship.',"
            "'one_to_many','Recorded support.','One customer can order many times.',%s "
            "FROM generate_series(1,%s) number RETURNING conceptual_relationship_id",
            (context.model_id, object_id, endpoint_id, locked, relationship_count),
        ).fetchall()

    def stored() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with database.connect_owner() as connection:
            return (
                connection.execute(
                    "SELECT * FROM workflow.conceptual_object WHERE model_id=%s "
                    "ORDER BY conceptual_object_id",
                    (context.model_id,),
                ).fetchall(),
                connection.execute(
                    "SELECT * FROM workflow.conceptual_relationship WHERE model_id=%s "
                    "ORDER BY conceptual_relationship_id",
                    (context.model_id,),
                ).fetchall(),
            )

    before = stored()
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    service = DatabaseModelChangeSetService(database=runtime, authorizer=AuthorizationService())
    command = PreviewModelRecordsRequest(
        dataset="conceptual_object",
        record_ids=[object_id],
        action="deactivate",
        expected_model_revision=context.model_revision,
    )
    await runtime.open()
    try:
        first = await service.preview_record_review(
            principal, tenant_id=context.tenant_id, model_id=context.model_id, command=command
        )
        assert first.can_apply is not locked
        assert first.action_count == relationship_count + 1
        assert first.additional_change_count == relationship_count
        assert first.total_record_count == relationship_count + 1
        all_items = list(first.items)
        if first.next_page is not None:
            second = await service.preview_record_review(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=command.model_copy(update={"expected_plan_digest": first.plan_digest}),
                page=first.next_page,
            )
            assert second.plan_digest == first.plan_digest and second.next_page is None
            all_items.extend(second.items)
        assert {(item.dataset, item.record_id) for item in all_items} == {
            ("conceptual_object", object_id),
            *(
                ("conceptual_relationship", row["conceptual_relationship_id"])
                for row in relationships
            ),
        }
        assert all(item.desired_status == "inactive" for item in all_items)
        assert stored() == before
        assert bool(first.issues) == locked
        if locked:
            assert any(issue.code == "record_locked" for issue in first.issues)
        with pytest.raises(WorkbenchError) as missing:
            await service.preview_record_review(
                principal,
                tenant_id=context.tenant_id,
                model_id=other.model_id,
                command=command.model_copy(
                    update={"expected_model_revision": other.model_revision}
                ),
            )
        assert missing.value.code == "model_record_not_found"
        with pytest.raises(WorkbenchError) as stale:
            await service.preview_record_review(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=command.model_copy(update={"expected_plan_digest": "f" * 64}),
            )
        assert stale.value.code == "review_conflict"
        assert stored() == before
        apply_command = ReviewModelRecordsRequest.model_validate(command.model_dump(), strict=False)
        with pytest.raises(WorkbenchError) as denied:
            await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=apply_command,
                idempotency_key=uuid4(),
            )
        assert denied.value.code == ("record_locked" if locked else "review_confirmation_required")
        assert stored() == before
        if locked:
            return
        apply_command = apply_command.model_copy(update={"expected_plan_digest": first.plan_digest})
        request_key = uuid4()
        applied = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            command=apply_command,
            idempotency_key=request_key,
        )
        assert applied.action_count == first.action_count
        assert applied.model_revision == context.model_revision + 1
        after = stored()
        assert after[0][0]["conceptual_object_status"] == "inactive"
        assert after[0][1] == before[0][1]
        assert all(row["conceptual_relationship_status"] == "inactive" for row in after[1])
        for dataset_index, dataset in enumerate(("conceptual_object", "conceptual_relationship")):
            for original, reviewed in zip(before[dataset_index], after[dataset_index], strict=True):
                for field in original.keys() - {
                    dataset + "_status",
                    dataset + "_is_locked",
                    "updated_time",
                    "updated_by",
                }:
                    assert original[field] == reviewed[field]
        replay = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            command=apply_command,
            idempotency_key=request_key,
        )
        assert replay == applied and stored() == after
        revision = applied.model_revision
        for action in ("lock", "unlock"):
            reviewed = await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                command=ReviewModelRecordsRequest(
                    dataset="conceptual_object",
                    record_ids=[object_id],
                    action=action,
                    expected_model_revision=revision,
                ),
                idempotency_key=uuid4(),
            )
            assert reviewed.action_count == 1
            revision = reviewed.model_revision
            if action == "lock":
                with pytest.raises(WorkbenchError) as locked_status:
                    await service.review_records(
                        principal,
                        tenant_id=context.tenant_id,
                        model_id=context.model_id,
                        command=ReviewModelRecordsRequest(
                            dataset="conceptual_object",
                            record_ids=[object_id],
                            action="reactivate",
                            expected_model_revision=revision,
                        ),
                        idempotency_key=uuid4(),
                    )
                assert locked_status.value.code == "record_locked"
        reactivate = PreviewModelRecordsRequest(
            dataset="conceptual_relationship",
            record_ids=[relationships[0]["conceptual_relationship_id"]],
            action="reactivate",
            expected_model_revision=revision,
        )
        reopen = await service.preview_record_review(
            principal, tenant_id=context.tenant_id, model_id=context.model_id, command=reactivate
        )
        assert reopen.can_apply and reopen.additional_change_count == 1
        applied = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            command=ReviewModelRecordsRequest.model_validate(
                {**reactivate.model_dump(), "expected_plan_digest": reopen.plan_digest},
                strict=False,
            ),
            idempotency_key=uuid4(),
        )
        assert applied.action_count == 2
        final_objects, final_relationships = stored()
        assert all(row["conceptual_object_status"] == "active" for row in final_objects)
        assert (
            sum(row["conceptual_relationship_status"] == "active" for row in final_relationships)
            == 1
        )
    finally:
        await runtime.close()
