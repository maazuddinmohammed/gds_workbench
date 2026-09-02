from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import psycopg
import pytest
from tests.mcp.database_test_support import require_row
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from tests.mcp.test_database_workflow_run_lifecycle import (
    CREATE_WORKFLOW_RUN_SQL,
    WorkflowContext,
    create_workflow_run_parameters,
    seed_workflow_context,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


PERSIST_PROFILING_RESULTS_SQL = """
    SELECT *
      FROM application.persist_profiling_results(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::JSONB
      )
"""


def _seed_attributes(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
) -> tuple[tuple[int, int], ...]:
    attributes: list[tuple[int, int]] = []
    with postgres_database.connect_owner() as connection:
        for position, object_id in enumerate(context.selected_object_ids, start=1):
            attribute_id = require_row(
                connection.execute(
                    """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type
                ) VALUES (%s, %s, 1, 'string')
                RETURNING attribute_id
                """,
                    (object_id, f"profile_attribute_{position}_{uuid4().hex}"),
                ).fetchone()
            )["attribute_id"]
            attributes.append((object_id, attribute_id))
    return tuple(attributes)


def _create_run(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
    *,
    workflow: str = "profiling",
    selected_object_ids: tuple[int, ...] | None = None,
    start: bool = True,
) -> int:
    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    selected_object_ids=(
                        context.selected_object_ids
                        if selected_object_ids is None
                        else selected_object_ids
                    ),
                    workflow=workflow,
                    execution_mode=None,
                ),
            ).fetchone()
        )
        if start:
            connection.execute(
                """
                SELECT *
                  FROM application.start_workflow_run(
                      %s::UUID,
                      %s::UUID,
                      'user'::VARCHAR,
                      %s::BIGINT,
                      %s::BIGINT
                  )
                """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["workflow_run_id"],
                    context.model_revision,
                ),
            ).fetchone()
    return created["workflow_run_id"]


def _profile(
    object_id: int,
    attribute_id: int,
    *,
    row_count: int = 10,
    non_null_count: int = 8,
    null_count: int = 2,
    digest_character: str = "a",
    source_context_digest: str | None = None,
) -> dict[str, Any]:
    return {
        "object_id": object_id,
        "attribute_id": attribute_id,
        "source_context_digest": (
            digest_character * 64
            if source_context_digest is None
            else source_context_digest
        ),
        "row_count": row_count,
        "non_null_count": non_null_count,
        "null_count": null_count,
        "blank_count": 1,
        "distinct_count": 6,
        "min_data_length": 1,
        "max_data_length": 8,
        "avg_data_length": 4.5,
        "percent_populated": 80,
        "percent_duplicates": 25,
        "percent_null": 20,
        "percent_blank": 12.5,
        "percent_distinct": 75,
    }


def _source_context_digests(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
    workflow_run_id: int,
) -> dict[int, str]:
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT attribute.attribute_id,
                   attribute.attribute_name,
                   attribute.attribute_data_type,
                   object_record.object_id,
                   object_record.object_name,
                   object_record.object_schema,
                   object_record.batch_attribute_name,
                   source_tenant.tenant_catalog,
                   run.requested_batch_id
              FROM application.workflow_run AS run
              JOIN application.workflow_run_object_selection AS selection
                ON selection.workflow_run_id = run.workflow_run_id
               AND selection.model_id = run.model_id
              JOIN workflow.list_model_attribute_eligibility(run.model_id)
                   AS eligible
                ON eligible.model_id = selection.model_id
               AND eligible.object_id = selection.object_id
               AND eligible.is_model_input_eligible
              JOIN core.attribute AS attribute
                ON attribute.attribute_id = eligible.attribute_id
               AND attribute.object_id = eligible.object_id
               AND attribute.is_active
              JOIN core.object AS object_record
                ON object_record.object_id = selection.object_id
               AND object_record.is_active
              JOIN core.tenant AS source_tenant
                ON source_tenant.tenant_id = object_record.source_tenant_id
               AND source_tenant.is_active
             WHERE run.workflow_run_id = %s
             ORDER BY attribute.attribute_id
            """,
            (workflow_run_id,),
        ).fetchall()

    return {
        int(row["attribute_id"]): hashlib.sha256(
            json.dumps(
                {
                    "attribute_data_type": row["attribute_data_type"],
                    "attribute_id": row["attribute_id"],
                    "attribute_name": row["attribute_name"],
                    "batch_attribute_name": row["batch_attribute_name"],
                    "catalog": row["tenant_catalog"],
                    "object_id": row["object_id"],
                    "requested_batch_id": row["requested_batch_id"],
                    "schema": row["object_schema"],
                    "table": row["object_name"],
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        for row in rows
    }


def _persist_parameters(
    context: WorkflowContext,
    workflow_run_id: int,
    profiles: list[dict[str, Any]],
    *,
    expected_model_revision: int | None = None,
) -> tuple[object, ...]:
    return (
        context.entra_tenant_id,
        context.entra_object_id,
        workflow_run_id,
        (
            context.model_revision
            if expected_model_revision is None
            else expected_model_revision
        ),
        Jsonb(profiles),
    )


def test_running_profiling_results_replace_selected_profiles_and_complete(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    selected_objects = context.selected_object_ids[:2]
    selected_attributes = attributes[:2]
    outside_object_id, outside_attribute_id = attributes[2]
    workflow_run_id = _create_run(
        postgres_database,
        context,
        selected_object_ids=selected_objects,
    )

    with postgres_database.connect_owner() as connection:
        inactive_attribute_id = require_row(
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    is_active
                ) VALUES (%s, %s, 2, 'string', FALSE)
                RETURNING attribute_id
                """,
                (selected_objects[0], f"inactive_profile_{uuid4().hex}"),
            ).fetchone()
        )["attribute_id"]
        connection.execute(
            """
            INSERT INTO workflow.attribute_profile (
                model_id,
                attribute_id,
                object_id,
                agent_run_id,
                workflow_run_id,
                source_context_digest,
                row_count,
                non_null_count,
                null_count
            ) VALUES
                (%s, %s, %s, 'manual-active', NULL, %s, 4, 4, 0),
                (%s, %s, %s, 'manual-stale', NULL, %s, 3, 3, 0),
                (%s, %s, %s, 'manual-outside', NULL, %s, 2, 2, 0)
            """,
            (
                context.model_id,
                selected_attributes[0][1],
                selected_attributes[0][0],
                "b" * 64,
                context.model_id,
                inactive_attribute_id,
                selected_objects[0],
                "c" * 64,
                context.model_id,
                outside_attribute_id,
                outside_object_id,
                "d" * 64,
            ),
        )

    source_context_digests = _source_context_digests(
        postgres_database,
        context,
        workflow_run_id,
    )
    profiles = [
        _profile(
            object_id,
            attribute_id,
            source_context_digest=source_context_digests[attribute_id],
        )
        for object_id, attribute_id in selected_attributes
    ]
    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        result = require_row(
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(context, workflow_run_id, profiles),
            ).fetchone()
        )
        replayed = require_row(
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(
                    context,
                    workflow_run_id,
                    profiles,
                    expected_model_revision=result["model_revision"],
                ),
            ).fetchone()
        )
        completed = require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.complete_workflow_run(
                      %s::UUID,
                      %s::UUID,
                      'user'::VARCHAR,
                      %s::BIGINT,
                      %s::BIGINT,
                      0::INTEGER
                  )
                """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    workflow_run_id,
                    result["model_revision"],
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT object_id,
                   attribute_id,
                   agent_run_id,
                   workflow_run_id,
                   source_context_digest,
                   row_count
              FROM workflow.attribute_profile
             WHERE model_id = %s
             ORDER BY attribute_id
            """,
            (context.model_id,),
        ).fetchall()
        revision_kinds = connection.execute(
            """
            SELECT change_kind
              FROM model.model_revision_transaction
             WHERE model_id = %s
             ORDER BY changed_time
            """,
            (context.model_id,),
        ).fetchall()

    assert result == {
        "changed": True,
        "workflow_run_id": workflow_run_id,
        "model_id": context.model_id,
        "model_revision": context.model_revision + 1,
        "submitted_profile_count": 2,
        "changed_profile_count": 3,
    }
    assert replayed == {
        **result,
        "changed": False,
        "changed_profile_count": 0,
    }
    assert completed["workflow_run_state"] == "completed"
    assert [row["attribute_id"] for row in stored] == [
        selected_attributes[0][1],
        selected_attributes[1][1],
        outside_attribute_id,
    ]
    assert stored[0]["agent_run_id"] is None
    assert stored[0]["workflow_run_id"] == workflow_run_id
    assert (
        stored[0]["source_context_digest"]
        == source_context_digests[selected_attributes[0][1]]
    )
    assert stored[0]["row_count"] == 10
    assert stored[1]["workflow_run_id"] == workflow_run_id
    assert stored[2]["agent_run_id"] == "manual-outside"
    assert stored[2]["workflow_run_id"] is None
    assert revision_kinds == [{"change_kind": "web_profiling_results_persist"}]


def test_gds_persistence_uses_discovery_assigned_tenant_not_connection_owner(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    with postgres_database.connect_owner() as connection:
        physical_owner_id = require_row(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                )
                SELECT project_id, %s, %s, %s, %s
                  FROM core.tenant
                 WHERE tenant_id = %s
                RETURNING tenant_id
                """,
                (
                    f"physical_gds_{uuid4().hex}",
                    "Inactive physical GDS owner",
                    f"physical_catalog_{uuid4().hex}",
                    f"physical_admin_{uuid4().hex}",
                    context.tenant_id,
                ),
            ).fetchone()
        )["tenant_id"]
        location = require_row(
            connection.execute(
                """
                SELECT DISTINCT object_record.connection_id,
                                object_record.zone_id,
                                object_record.object_schema
                  FROM core.object AS object_record
                 WHERE object_record.object_id = ANY(%s::BIGINT[])
                """,
                (list(context.selected_object_ids),),
            ).fetchone()
        )
        connection.execute(
            """
            UPDATE core.connection
               SET tenant_id = %s,
                   is_global_data_store = TRUE
             WHERE connection_id = %s
            """,
            (physical_owner_id, location["connection_id"]),
        )
        connection.execute(
            "UPDATE core.tenant SET is_active = FALSE WHERE tenant_id = %s",
            (physical_owner_id,),
        )

    workflow_run_id = _create_run(postgres_database, context)
    source_context_digests = _source_context_digests(
        postgres_database,
        context,
        workflow_run_id,
    )
    profiles = [
        _profile(
            object_id,
            attribute_id,
            source_context_digest=source_context_digests[attribute_id],
        )
        for object_id, attribute_id in attributes
    ]
    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        result = require_row(
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(context, workflow_run_id, profiles),
            ).fetchone()
        )

    assert result["changed"] is True
    assert result["submitted_profile_count"] == len(attributes)
    assert result["changed_profile_count"] == len(attributes)


def test_one_invalid_profile_rolls_back_every_profile_and_revision(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)[:2]
    workflow_run_id = _create_run(
        postgres_database,
        context,
        selected_object_ids=context.selected_object_ids[:2],
    )
    with postgres_database.connect_owner() as connection:
        inactive_attribute_id = require_row(
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    is_active
                ) VALUES (%s, %s, 2, 'string', FALSE)
                RETURNING attribute_id
                """,
                (attributes[0][0], f"rollback_inactive_{uuid4().hex}"),
            ).fetchone()
        )["attribute_id"]
        connection.execute(
            """
            INSERT INTO workflow.attribute_profile (
                model_id,
                attribute_id,
                object_id,
                source_context_digest,
                row_count,
                non_null_count,
                null_count
            ) VALUES
                (%s, %s, %s, %s, 4, 4, 0),
                (%s, %s, %s, %s, 3, 3, 0)
            """,
            (
                context.model_id,
                attributes[0][1],
                attributes[0][0],
                "1" * 64,
                context.model_id,
                inactive_attribute_id,
                attributes[0][0],
                "4" * 64,
            ),
        )

    invalid_profiles = [
        _profile(*attributes[0], digest_character="2"),
        _profile(
            *attributes[1],
            row_count=10,
            non_null_count=9,
            null_count=2,
            digest_character="3",
        ),
    ]
    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="metrics do not reconcile"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            PERSIST_PROFILING_RESULTS_SQL,
            _persist_parameters(context, workflow_run_id, invalid_profiles),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT attribute_id, source_context_digest, row_count
              FROM workflow.attribute_profile
             WHERE model_id = %s
             ORDER BY attribute_id
            """,
            (context.model_id,),
        ).fetchall()
        revision = require_row(
            connection.execute(
                """
                SELECT model_revision
                  FROM model.model
                 WHERE model_id = %s
                """,
                (context.model_id,),
            ).fetchone()
        )["model_revision"]

    assert stored == [
        {
            "attribute_id": attributes[0][1],
            "source_context_digest": "1" * 64,
            "row_count": 4,
        },
        {
            "attribute_id": inactive_attribute_id,
            "source_context_digest": "4" * 64,
            "row_count": 3,
        },
    ]
    assert revision == context.model_revision


def test_profiling_persistence_rejects_inconsistent_percentages(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    workflow_run_id = _create_run(postgres_database, context)
    profiles = [_profile(*attribute) for attribute in attributes]
    profiles[0] = {**profiles[0], "percent_null": 19}

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="metrics do not reconcile"),
    ):
        connection.execute(
            PERSIST_PROFILING_RESULTS_SQL,
            _persist_parameters(context, workflow_run_id, profiles),
        )


def test_profiling_persistence_recomputes_source_context_digests(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    workflow_run_id = _create_run(postgres_database, context)
    source_context_digests = _source_context_digests(
        postgres_database,
        context,
        workflow_run_id,
    )
    profiles = [
        _profile(
            object_id,
            attribute_id,
            source_context_digest=source_context_digests[attribute_id],
        )
        for object_id, attribute_id in attributes
    ]
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.attribute
               SET attribute_name = %s
             WHERE attribute_id = %s
            """,
            (f"changed_profile_attribute_{uuid4().hex}", attributes[0][1]),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="source context"),
    ):
        connection.execute(
            PERSIST_PROFILING_RESULTS_SQL,
            _persist_parameters(context, workflow_run_id, profiles),
        )


def test_profiling_payload_requires_exact_selected_attribute_coverage(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    workflow_run_id = _create_run(
        postgres_database,
        context,
        selected_object_ids=context.selected_object_ids[:2],
    )
    valid_profiles = [_profile(*attribute) for attribute in attributes[:2]]

    invalid_payloads = (
        (valid_profiles[:1], "exactly cover the eligible Selected Scope Attributes"),
        ([valid_profiles[0], valid_profiles[0]], "Attribute IDs must be unique"),
        (
            [*valid_profiles, _profile(*attributes[2])],
            "exactly cover the eligible Selected Scope Attributes",
        ),
    )
    for payload, message in invalid_payloads:
        with (
            psycopg.connect(
                postgres_database.web_runtime_dsn(),
                row_factory=dict_row,
            ) as connection,
            pytest.raises(RaiseException, match=message),
            connection.transaction(),
        ):
            connection.execute("SET ROLE gds_web_write")
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(context, workflow_run_id, payload),
            ).fetchone()

    with postgres_database.connect_owner() as connection:
        profile_count = require_row(
            connection.execute(
                """
                SELECT count(*)::INTEGER AS profile_count
                  FROM workflow.attribute_profile
                 WHERE model_id = %s
                """,
                (context.model_id,),
            ).fetchone()
        )["profile_count"]
    assert profile_count == 0


def test_profiling_payload_is_bounded_and_requires_complete_rows(
    postgres_database: DisposablePostgres,
) -> None:
    invalid_payloads = (
        ([{}] * 50001, "between 0 and 50000 Profiles"),
        ([{"object_id": 1}], "payload shape is invalid"),
    )
    for payload, message in invalid_payloads:
        with (
            postgres_database.connect_owner() as connection,
            pytest.raises(RaiseException, match=message),
            connection.transaction(),
        ):
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                (uuid4(), uuid4(), 1, 1, Jsonb(payload)),
            ).fetchone()


def test_profiling_persistence_denies_cross_tenant_actor(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    workflow_run_id = _create_run(postgres_database, context)
    other_context = seed_workflow_context(postgres_database)
    profiles = [_profile(*attribute) for attribute in attributes]

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="persistence denied: authorization_denied"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            PERSIST_PROFILING_RESULTS_SQL,
            (
                other_context.entra_tenant_id,
                other_context.entra_object_id,
                workflow_run_id,
                context.model_revision,
                Jsonb(profiles),
            ),
        ).fetchone()


def test_profiling_persistence_requires_running_profiling_workflow(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    profiles = [_profile(*attribute) for attribute in attributes]
    queued_run_id = _create_run(postgres_database, context, start=False)

    with postgres_database.connect_owner() as connection:
        with (
            pytest.raises(RaiseException, match="running Profiling Workflow Run"),
            connection.transaction(),
        ):
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(context, queued_run_id, profiles),
            ).fetchone()

        connection.execute(
            """
            SELECT *
              FROM application.start_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT, %s::BIGINT
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                queued_run_id,
                context.model_revision,
            ),
        ).fetchone()
        connection.execute(
            """
            SELECT *
              FROM application.complete_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT, 0::INTEGER
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                queued_run_id,
                context.model_revision,
            ),
        ).fetchone()
        with (
            pytest.raises(RaiseException, match="running Profiling Workflow Run"),
            connection.transaction(),
        ):
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(context, queued_run_id, profiles),
            ).fetchone()

    analysis_run_id = _create_run(
        postgres_database,
        context,
        workflow="analysis",
    )
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="running Profiling Workflow Run"),
    ):
        connection.execute(
            PERSIST_PROFILING_RESULTS_SQL,
            _persist_parameters(context, analysis_run_id, profiles),
        ).fetchone()


def test_profiling_persistence_requires_owned_lock_and_current_revision(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    attributes = _seed_attributes(postgres_database, context)
    workflow_run_id = _create_run(postgres_database, context)
    profiles = [_profile(*attribute) for attribute in attributes]

    with postgres_database.connect_owner() as connection:
        with connection.transaction():
            connection.execute(
                """
                SELECT *
                  FROM security.release_tenant_lock(
                      %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT
                  )
                """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    context.tenant_id,
                ),
            ).fetchone()
        with (
            pytest.raises(RaiseException, match="tenant_lock_required"),
            connection.transaction(),
        ):
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(context, workflow_run_id, profiles),
            ).fetchone()
        with connection.transaction():
            connection.execute(
                """
                SELECT *
                  FROM security.acquire_tenant_lock(
                      %s::UUID,
                      %s::UUID,
                      'user'::VARCHAR,
                      %s::BIGINT,
                      30::INTEGER,
                      'Profiling persistence test'::VARCHAR
                  )
                """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    context.tenant_id,
                ),
            ).fetchone()
        with (
            pytest.raises(RaiseException, match="stale_model_revision"),
            connection.transaction(),
        ):
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                _persist_parameters(
                    context,
                    workflow_run_id,
                    profiles,
                    expected_model_revision=context.model_revision + 1,
                ),
            ).fetchone()
        null_revision_parameters = list(
            _persist_parameters(context, workflow_run_id, profiles)
        )
        null_revision_parameters[3] = None
        with (
            pytest.raises(RaiseException, match="stale_model_revision"),
            connection.transaction(),
        ):
            connection.execute(
                PERSIST_PROFILING_RESULTS_SQL,
                null_revision_parameters,
            ).fetchone()


def test_web_role_has_function_only_profiling_write_surface(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        posture = require_row(
            connection.execute(
                """
            SELECT has_function_privilege(
                       'gds_web_write',
                       'application.persist_profiling_results('
                       'uuid,uuid,character varying,bigint,bigint,jsonb)',
                       'EXECUTE'
                   ) AS can_execute,
                   has_function_privilege(
                       'gds_app_write',
                       'application.persist_profiling_results('
                       'uuid,uuid,character varying,bigint,bigint,jsonb)',
                       'EXECUTE'
                   ) AS mcp_can_execute,
                   has_function_privilege(
                       'public',
                       'application.persist_profiling_results('
                       'uuid,uuid,character varying,bigint,bigint,jsonb)',
                       'EXECUTE'
                   ) AS public_can_execute,
                   has_table_privilege(
                       'gds_web_write',
                       'workflow.attribute_profile',
                       'INSERT'
                   ) AS can_insert,
                   has_table_privilege(
                       'gds_web_write',
                       'workflow.attribute_profile',
                       'UPDATE'
                   ) AS can_update,
                   has_table_privilege(
                       'gds_web_write',
                       'workflow.attribute_profile',
                       'DELETE'
                   ) AS can_delete,
                   (
                       SELECT is_nullable = 'YES'
                         FROM information_schema.columns
                        WHERE table_schema = 'workflow'
                          AND table_name = 'attribute_profile'
                          AND column_name = 'workflow_run_id'
                   ) AS workflow_provenance_is_nullable
                """
            ).fetchone()
        )

    assert posture == {
        "can_execute": True,
        "mcp_can_execute": False,
        "public_can_execute": False,
        "can_insert": False,
        "can_update": False,
        "can_delete": False,
        "workflow_provenance_is_nullable": True,
    }

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
            autocommit=True,
        ) as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            """
            INSERT INTO workflow.attribute_profile (
                model_id,
                attribute_id,
                object_id,
                source_context_digest,
                row_count,
                non_null_count,
                null_count
            ) VALUES (1, 1, 1, %s, 0, 0, 0)
            """,
            ("0" * 64,),
        )
