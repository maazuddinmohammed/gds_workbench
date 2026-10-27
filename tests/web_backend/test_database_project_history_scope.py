"""Physical deactivation retains owned history without authorizing new evidence."""

from typing import Literal

import pytest
from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.database import WebPostgresDatabase

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_project_change_sets import (
    _seed_profile_project,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.parametrize("record_type", ["object", "attribute"])
async def test_owned_inactive_profile_history_survives_but_new_metrics_are_ineligible(
    web_postgres_database: DisposablePostgres,
    record_type: Literal["object", "attribute"],
) -> None:
    project_id, tenant_id, attribute_id, *_ = _seed_profile_project(
        web_postgres_database
    )
    with web_postgres_database.connect_owner() as connection:
        row = connection.execute(
            "SELECT object_id FROM core.attribute WHERE attribute_id=%s",
            (attribute_id,),
        ).fetchone()
        assert row is not None
        object_id = row["object_id"]
        second = connection.execute(
            """INSERT INTO core.attribute (
                object_id, attribute_name, attribute_ordinal_position, attribute_data_type
            ) VALUES (%s,'parent_id',2,'BIGINT') RETURNING attribute_id""",
            (object_id,),
        ).fetchone()
        assert second is not None
        connection.execute(
            """INSERT INTO workflow.analysis_result (
                project_id, from_object_id, from_attribute_id, to_object_id, to_attribute_id,
                relationship_kind,
                analysis_result_is_locked
            ) VALUES (%s,%s,%s,%s,%s,'reference',TRUE)""",
            (project_id, object_id, attribute_id, object_id, second["attribute_id"]),
        )
        connection.execute(
            """INSERT INTO workflow.attribute_profile (
                project_id, object_id, attribute_id, source_context_digest,
                row_count, non_null_count, null_count
            ) VALUES (%s,%s,%s,%s,2,2,0)""",
            (project_id, object_id, attribute_id, "a" * 64),
        )
        project_row = connection.execute(
            "SELECT project_name FROM project.project WHERE project_id=%s",
            (project_id,),
        ).fetchone()
        assert project_row is not None
    project = ProjectReadContext(
        project_id=project_id,
        tenant_id=tenant_id,
        project_name=project_row["project_name"],
        project_revision=1,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            baseline = await build_project_snapshot(transaction, project)
            current = await load_project_physical_scope(transaction, project)
        assert validate_future_graph(
            snapshot=baseline, staged_documents={}, physical_scope=current
        ).valid
        assert len(baseline.profiling.profiles) == 1
        assert len(baseline.analysis.relationships) == 1
        with web_postgres_database.connect_owner() as connection:
            if record_type == "object":
                connection.execute(
                    "UPDATE core.object SET is_active=FALSE WHERE object_id=%s",
                    (object_id,),
                )
            else:
                connection.execute(
                    "UPDATE core.attribute SET is_active=FALSE WHERE attribute_id=%s",
                    (attribute_id,),
                )
        async with database.read_transaction() as transaction:
            retained = await build_project_snapshot(transaction, project)
            history = await load_project_physical_scope(transaction, project)
        assert retained.profiling == baseline.profiling
        assert retained.analysis == baseline.analysis
        assert history.objects == current.objects
        assert history.attributes == current.attributes
        assert len(history.project_input_attributes) == (
            1 if record_type == "attribute" else 0
        )
        assert bool(history.project_input_objects) == (record_type == "attribute")
        assert validate_future_graph(
            snapshot=retained, staged_documents={}, physical_scope=history
        ).valid

        details = retained.project_input_scope.details.model_dump(mode="json")
        details["project_description"] = (
            "Updated description while retaining prior profile evidence."
        )
        scope = retained.project_input_scope.objects[0].model_dump(mode="json")
        scope["project_input_scope_is_locked"] = True
        assert validate_future_graph(
            snapshot=retained,
            staged_documents={
                "project_details": [details],
                "project_input_scope": [scope],
            },
            physical_scope=history,
        ).valid
        async with database.write_transaction() as transaction:
            materializer = ProjectMaterializer(
                transaction=transaction,
                project_id=project_id,
                source_context_digest="a" * 64,
            )
            resolved_object = await materializer.resolve_object(
                retained.project_input_scope.objects[0]
            )
            assert resolved_object[0] == object_id
            resolved = await materializer.resolve_attribute(
                retained.profiling.profiles[0]
            )
            assert resolved[:2] == (object_id, attribute_id)
        changed_profile = retained.profiling.profiles[0].model_dump(mode="json")
        changed_profile.update(row_count=3, non_null_count=3)
        rejected = validate_future_graph(
            snapshot=retained,
            staged_documents={"profiling_profile": [changed_profile]},
            physical_scope=history,
        )
        assert not rejected.valid
        assert any(issue.dataset == "profiling_profile" for issue in rejected.issues)

        # Retained references cannot survive an ownership transfer as authorized history.
        _, foreign_tenant, *_ = _seed_profile_project(web_postgres_database)
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.object SET source_tenant_id=%s WHERE object_id=%s",
                (foreign_tenant, object_id),
            )
        async with database.read_transaction() as transaction:
            foreign_scope = await load_project_physical_scope(transaction, project)
        assert not foreign_scope.objects
        assert not foreign_scope.attributes
        assert not validate_future_graph(
            snapshot=retained, staged_documents={}, physical_scope=foreign_scope
        ).valid
        async with database.write_transaction() as transaction:
            materializer = ProjectMaterializer(
                transaction=transaction,
                project_id=project_id,
                source_context_digest="a" * 64,
            )
            with pytest.raises(InvalidRequestError):
                await materializer.resolve_object(
                    retained.project_input_scope.objects[0]
                )
            with pytest.raises(InvalidRequestError):
                await materializer.resolve_attribute(retained.profiling.profiles[0])
    finally:
        await database.close()
