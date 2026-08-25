from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import psycopg
import pytest
from database_test_support import require_row
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from test_database_profiling_execution_context import (
    ProfilingExecutionSeed,
    _execution_parameters,
    _seed_profiling_execution,
)
from test_database_profiling_persistence import _create_run
from test_database_workflow_run_lifecycle import seed_workflow_context

if TYPE_CHECKING:
    from conftest import DisposablePostgres


GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL = """
    SELECT *
      FROM application.get_analysis_validation_execution_context(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR
      )
"""

GET_ANALYSIS_VALIDATION_CONNECTION_VALUES_SQL = """
    SELECT *
      FROM application.get_analysis_validation_connection_values(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR
      )
"""

PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL = """
    SELECT *
      FROM application.persist_analysis_validation_results(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR,
          %s::JSONB
      )
"""

ANALYSIS_VALIDATION_CONTEXT_SIGNATURE = (
    "application.get_analysis_validation_execution_context("
    "uuid,uuid,character varying,bigint,bigint,character varying)"
)
ANALYSIS_VALIDATION_VALUES_SIGNATURE = (
    "application.get_analysis_validation_connection_values("
    "uuid,uuid,character varying,bigint,bigint,character varying)"
)

SAFE_CONTEXT_COLUMNS = {
    "workflow_run_id",
    "model_id",
    "model_revision",
    "requested_batch_id",
    "analysis_result_id",
    "relationship_kind",
    "relationship_confidence",
    "relationship_basis",
    "analysis_result_status",
    "analysis_result_is_locked",
    "gds_connection_id",
    "source_context_digest",
    "from_relation_catalog",
    "from_relation_schema",
    "from_relation_object",
    "from_object_id",
    "from_attribute_id",
    "from_attribute_name",
    "from_attribute_data_type",
    "from_batch_attribute_name",
    "from_batch_attribute_data_type",
    "to_relation_catalog",
    "to_relation_schema",
    "to_relation_object",
    "to_object_id",
    "to_attribute_id",
    "to_attribute_name",
    "to_attribute_data_type",
    "to_batch_attribute_name",
    "to_batch_attribute_data_type",
}


@dataclass(frozen=True, slots=True)
class EndpointMetadata:
    object_id: int
    attribute_id: int
    relation_catalog: str
    relation_schema: str
    relation_object: str
    attribute_name: str
    attribute_data_type: str
    batch_attribute_name: str
    batch_attribute_data_type: str


@dataclass(frozen=True, slots=True)
class AnalysisValidationSeed:
    execution: ProfilingExecutionSeed
    endpoints: tuple[EndpointMetadata, ...]
    active_result_id: int
    locked_result_id: int
    inactive_result_id: int


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _analysis_execution_parameters(
    seed: ProfilingExecutionSeed,
) -> tuple[object, ...]:
    return (*_execution_parameters(seed), seed.environment_code)


def _seed_analysis_validation(
    postgres_database: DisposablePostgres,
) -> AnalysisValidationSeed:
    execution = _seed_profiling_execution(
        postgres_database,
        workflow="analysis",
    )
    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT object_record.object_id,
                   attribute.attribute_id,
                   discovery_tenant.tenant_catalog AS relation_catalog,
                   object_record.object_schema AS relation_schema,
                   object_record.object_name AS relation_object,
                   attribute.attribute_name,
                   attribute.attribute_data_type,
                   batch_attribute.attribute_name AS batch_attribute_name,
                   batch_attribute.attribute_data_type AS batch_attribute_data_type
              FROM core.object AS object_record
              JOIN core.attribute AS attribute
                ON attribute.object_id = object_record.object_id
               AND attribute.is_active
              JOIN core.connection AS gds_connection
                ON gds_connection.connection_id = object_record.connection_id
              JOIN core.tenant_metadata_discovery_scope AS discovery_scope
                ON discovery_scope.gds_connection_id = gds_connection.connection_id
               AND discovery_scope.zone_id = object_record.zone_id
               AND lower(btrim(discovery_scope.object_schema)) =
                   lower(btrim(object_record.object_schema))
               AND discovery_scope.is_active
              JOIN core.tenant AS discovery_tenant
                ON discovery_tenant.tenant_id = discovery_scope.tenant_id
               AND discovery_tenant.is_active
              JOIN core.attribute AS batch_attribute
                ON batch_attribute.object_id = object_record.object_id
               AND lower(btrim(batch_attribute.attribute_name)) =
                   lower(btrim(object_record.batch_attribute_name))
               AND batch_attribute.is_active
             WHERE object_record.object_id = ANY(%s::BIGINT[])
             ORDER BY object_record.object_id, attribute.attribute_id
            """,
            (list(execution.context.selected_object_ids),),
        ).fetchall()
        assert len(rows) == 3
        endpoints = tuple(
            EndpointMetadata(
                object_id=int(row["object_id"]),
                attribute_id=int(row["attribute_id"]),
                relation_catalog=str(row["relation_catalog"]),
                relation_schema=str(row["relation_schema"]),
                relation_object=str(row["relation_object"]),
                attribute_name=str(row["attribute_name"]),
                attribute_data_type=str(row["attribute_data_type"]),
                batch_attribute_name=str(row["batch_attribute_name"]),
                batch_attribute_data_type=str(row["batch_attribute_data_type"]),
            )
            for row in rows
        )

        result_ids: list[int] = []
        relationships = (
            (endpoints[0], endpoints[1], "reference", "active", False),
            (endpoints[1], endpoints[2], "lookup", "needs_review", True),
            (endpoints[0], endpoints[2], "inactive_test", "inactive", False),
        )
        for position, (source, target, kind, status, is_locked) in enumerate(
            relationships,
            start=1,
        ):
            result_id = require_row(
                connection.execute(
                    """
                    INSERT INTO workflow.analysis_result (
                        model_id,
                        from_object_id,
                        from_attribute_id,
                        to_object_id,
                        to_attribute_id,
                        relationship_kind,
                        relationship_confidence,
                        relationship_basis,
                        analysis_result_status,
                        analysis_result_is_locked
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'medium', %s, %s, %s)
                    RETURNING analysis_result_id
                    """,
                    (
                        execution.context.model_id,
                        source.object_id,
                        source.attribute_id,
                        target.object_id,
                        target.attribute_id,
                        kind,
                        f"Analysis validation relationship {position}.",
                        status,
                        is_locked,
                    ),
                ).fetchone()
            )["analysis_result_id"]
            result_ids.append(int(result_id))

    return AnalysisValidationSeed(
        execution=execution,
        endpoints=endpoints,
        active_result_id=result_ids[0],
        locked_result_id=result_ids[1],
        inactive_result_id=result_ids[2],
    )


def _expected_endpoint(prefix: str, endpoint: EndpointMetadata) -> dict[str, object]:
    return {
        f"{prefix}_relation_catalog": endpoint.relation_catalog,
        f"{prefix}_relation_schema": endpoint.relation_schema,
        f"{prefix}_relation_object": endpoint.relation_object,
        f"{prefix}_object_id": endpoint.object_id,
        f"{prefix}_attribute_id": endpoint.attribute_id,
        f"{prefix}_attribute_name": endpoint.attribute_name,
        f"{prefix}_attribute_data_type": endpoint.attribute_data_type,
        f"{prefix}_batch_attribute_name": endpoint.batch_attribute_name,
        f"{prefix}_batch_attribute_data_type": endpoint.batch_attribute_data_type,
    }


def _validation_result(
    analysis_result_id: int,
    *,
    source_context_digest: str,
    digest_character: str,
    count_base: int,
    validation_result: str = "supported",
) -> dict[str, Any]:
    source_non_null_count = count_base + 10
    source_distinct_count = count_base + 9
    target_non_null_count = count_base + 8
    target_distinct_count = target_non_null_count
    source_missing_target_count = 0
    duplicate_target_key_count = 0
    if validation_result == "inconclusive":
        source_non_null_count = 0
        source_distinct_count = 0
    elif validation_result == "unsupported":
        source_missing_target_count = 3
        target_distinct_count = target_non_null_count - 1
        duplicate_target_key_count = 1
    return {
        "analysis_result_id": analysis_result_id,
        "source_context_digest": source_context_digest,
        "validation_policy_version": "1.0.0",
        "validation_policy_digest": digest_character * 64,
        "validation_result": validation_result,
        "validation_source_non_null_count": source_non_null_count,
        "validation_source_distinct_count": source_distinct_count,
        "validation_target_non_null_count": target_non_null_count,
        "validation_target_distinct_count": target_distinct_count,
        "validation_source_missing_target_count": source_missing_target_count,
        "validation_unused_target_count": 2,
        "validation_duplicate_target_key_count": duplicate_target_key_count,
    }


def _source_context_digests(
    postgres_database: DisposablePostgres,
    seed: AnalysisValidationSeed,
) -> dict[int, str]:
    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        rows = connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            _analysis_execution_parameters(seed.execution),
        ).fetchall()
    return {
        int(row["analysis_result_id"]): str(row["source_context_digest"])
        for row in rows
    }


def _persist_validation_parameters(
    seed: AnalysisValidationSeed,
    results: list[dict[str, Any]],
    *,
    expected_model_revision: int | None = None,
    workflow_run_id: int | None = None,
    entra_tenant_id: object | None = None,
    entra_object_id: object | None = None,
) -> tuple[object, ...]:
    context = seed.execution.context
    return (
        context.entra_tenant_id if entra_tenant_id is None else entra_tenant_id,
        context.entra_object_id if entra_object_id is None else entra_object_id,
        (
            seed.execution.workflow_run_id
            if workflow_run_id is None
            else workflow_run_id
        ),
        (
            context.model_revision
            if expected_model_revision is None
            else expected_model_revision
        ),
        seed.execution.environment_code,
        Jsonb(results),
    )


def test_running_analysis_validation_context_is_safe_exact_and_lock_agnostic(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        context_rows = connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            _analysis_execution_parameters(seed.execution),
        ).fetchall()
        connection_rows = connection.execute(
            GET_ANALYSIS_VALIDATION_CONNECTION_VALUES_SQL,
            _analysis_execution_parameters(seed.execution),
        ).fetchall()

    assert [set(row) for row in context_rows] == [
        SAFE_CONTEXT_COLUMNS,
        SAFE_CONTEXT_COLUMNS,
    ]
    assert [row["analysis_result_id"] for row in context_rows] == [
        seed.active_result_id,
        seed.locked_result_id,
    ]
    expected_rows = (
        (
            seed.active_result_id,
            "reference",
            "active",
            False,
            seed.endpoints[0],
            seed.endpoints[1],
        ),
        (
            seed.locked_result_id,
            "lookup",
            "needs_review",
            True,
            seed.endpoints[1],
            seed.endpoints[2],
        ),
    )
    for row, (result_id, kind, status, is_locked, source, target) in zip(
        context_rows,
        expected_rows,
        strict=True,
    ):
        assert re.fullmatch(r"[0-9a-f]{64}", row["source_context_digest"])
        assert row == {
            "workflow_run_id": seed.execution.workflow_run_id,
            "model_id": seed.execution.context.model_id,
            "model_revision": seed.execution.context.model_revision,
            "requested_batch_id": None,
            "analysis_result_id": result_id,
            "relationship_kind": kind,
            "relationship_confidence": "medium",
            "relationship_basis": (
                "Analysis validation relationship "
                f"{1 if result_id == seed.active_result_id else 2}."
            ),
            "analysis_result_status": status,
            "analysis_result_is_locked": is_locked,
            "gds_connection_id": seed.execution.connection_id,
            "source_context_digest": row["source_context_digest"],
            **_expected_endpoint("from", source),
            **_expected_endpoint("to", target),
        }

    assert len(connection_rows) == 1
    connection_row = connection_rows[0]
    assert connection_row["failure_code"] is None
    assert connection_row["failure_message"] is None
    assert connection_row["gds_connection_id"] == seed.execution.connection_id
    assert connection_row["environment_code"] == seed.execution.environment_code
    assert _digest(connection_row["databricks_host_name"]) == _digest(
        seed.execution.server_hostname
    )
    assert _digest(connection_row["databricks_http_path"]) == _digest(
        seed.execution.http_path
    )
    assert _digest(connection_row["databricks_token"]) == _digest(
        seed.execution.access_token
    )


def test_analysis_validation_context_allows_zero_eligible_relationships(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database, workflow="analysis")

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        rows = connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            _analysis_execution_parameters(seed),
        ).fetchall()

    assert rows == []


def test_analysis_validation_context_requires_actor_revision_and_owned_lock(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    other = seed_workflow_context(postgres_database)

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(
            RaiseException,
            match="analysis_validation_execution_denied: authorization_denied",
        ),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            (
                other.entra_tenant_id,
                other.entra_object_id,
                seed.execution.workflow_run_id,
                seed.execution.context.model_revision,
                seed.execution.environment_code,
            ),
        ).fetchall()

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="stale_model_revision"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            (
                seed.execution.context.entra_tenant_id,
                seed.execution.context.entra_object_id,
                seed.execution.workflow_run_id,
                seed.execution.context.model_revision + 1,
                seed.execution.environment_code,
            ),
        ).fetchall()

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET tenant_lock_acquired_time =
                       CURRENT_TIMESTAMP - INTERVAL '2 minutes',
                   tenant_lock_expires_time =
                       CURRENT_TIMESTAMP - INTERVAL '1 minute'
             WHERE tenant_id = %s
            """,
            (seed.execution.context.tenant_id,),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(
            RaiseException,
            match="analysis_validation_execution_denied: tenant_lock_required",
        ),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            _analysis_execution_parameters(seed.execution),
        ).fetchall()


def test_analysis_validation_context_requires_exact_run_entra_identity(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    alternate_entra_tenant_id = uuid4()
    alternate_entra_object_id = uuid4()
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (
                seed.execution.context.principal_id,
                alternate_entra_tenant_id,
                alternate_entra_object_id,
            ),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="workflow_run_owner_mismatch"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            (
                alternate_entra_tenant_id,
                alternate_entra_object_id,
                seed.execution.workflow_run_id,
                seed.execution.context.model_revision,
                seed.execution.environment_code,
            ),
        ).fetchall()


def test_analysis_validation_context_rejects_one_unselected_endpoint(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    one_object_run_id = _create_run(
        postgres_database,
        seed.execution.context,
        workflow="analysis",
        selected_object_ids=(seed.endpoints[0].object_id,),
    )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(
            RaiseException,
            match="analysis_validation_endpoint_not_selected",
        ),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            (
                seed.execution.context.entra_tenant_id,
                seed.execution.context.entra_object_id,
                one_object_run_id,
                seed.execution.context.model_revision,
                seed.execution.environment_code,
            ),
        ).fetchall()


def test_analysis_validation_context_rejects_cross_connection_relationship(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    moved = seed.endpoints[1]
    with postgres_database.connect_owner() as connection:
        physical = require_row(
            connection.execute(
                """
                SELECT source_connection.tenant_id,
                       source_connection.system_id,
                       source_connection.connection_type_id,
                       object_record.zone_id,
                       object_record.object_schema
                  FROM core.object AS object_record
                  JOIN core.connection AS source_connection
                    ON source_connection.connection_id = object_record.connection_id
                 WHERE object_record.object_id = %s
                """,
                (moved.object_id,),
            ).fetchone()
        )
        second_connection_id = require_row(
            connection.execute(
                """
                INSERT INTO core.connection (
                    tenant_id,
                    system_id,
                    connection_code,
                    connection_name,
                    connection_type_id,
                    is_global_data_store
                ) VALUES (%s, %s, %s, %s, %s, TRUE)
                RETURNING connection_id
                """,
                (
                    physical["tenant_id"],
                    physical["system_id"],
                    f"analysis_validation_{uuid4().hex}",
                    f"Analysis Validation {uuid4().hex}",
                    physical["connection_type_id"],
                ),
            ).fetchone()
        )["connection_id"]
        connection.execute(
            "UPDATE core.object SET connection_id = %s WHERE object_id = %s",
            (second_connection_id, moved.object_id),
        )
        connection.execute(
            """
            INSERT INTO core.tenant_metadata_discovery_scope (
                tenant_id,
                gds_connection_id,
                zone_id,
                object_schema
            ) VALUES (%s, %s, %s, %s)
            """,
            (
                physical["tenant_id"],
                second_connection_id,
                physical["zone_id"],
                physical["object_schema"],
            ),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(
            RaiseException,
            match="analysis_validation_cross_connection",
        ),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            _analysis_execution_parameters(seed.execution),
        ).fetchall()


def test_analysis_validation_context_rejects_blank_discovery_tenant_catalog(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    with postgres_database.connect_owner() as connection:
        discovery_tenant_id = require_row(
            connection.execute(
                """
                SELECT DISTINCT discovery_scope.tenant_id
                  FROM core.tenant_metadata_discovery_scope AS discovery_scope
                 WHERE discovery_scope.gds_connection_id = %s
                   AND discovery_scope.is_active
                """,
                (seed.execution.connection_id,),
            ).fetchone()
        )["tenant_id"]
        connection.execute(
            """
            UPDATE core.tenant
               SET tenant_catalog = '   '
             WHERE tenant_id = %s
            """,
            (discovery_tenant_id,),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="analysis_validation_context_changed"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            _analysis_execution_parameters(seed.execution),
        ).fetchall()


def test_analysis_validation_context_rejects_blank_endpoint_data_type(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.attribute
               SET attribute_data_type = '   '
             WHERE attribute_id = %s
            """,
            (seed.endpoints[0].attribute_id,),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="analysis_validation_context_changed"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            _analysis_execution_parameters(seed.execution),
        ).fetchall()


def test_analysis_validation_partial_connection_values_return_no_secrets(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.connection_value AS connection_value
               SET connection_value = NULL
              FROM reference.connection_parameter AS parameter
             WHERE parameter.connection_parameter_id =
                   connection_value.connection_parameter_id
               AND connection_value.connection_id = %s
               AND lower(btrim(parameter.connection_parameter_code)) =
                   'databricks_token'
            """,
            (seed.execution.connection_id,),
        )

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        failure = require_row(
            connection.execute(
                GET_ANALYSIS_VALIDATION_CONNECTION_VALUES_SQL,
                _analysis_execution_parameters(seed.execution),
            ).fetchone()
        )

    assert failure == {
        "workflow_run_id": seed.execution.workflow_run_id,
        "model_id": seed.execution.context.model_id,
        "model_revision": seed.execution.context.model_revision,
        "gds_connection_id": None,
        "environment_code": seed.execution.environment_code,
        "failure_code": "connection_values_missing",
        "failure_message": (
            "Analysis validation GDS connection values are incomplete."
        ),
        "databricks_host_name": None,
        "databricks_http_path": None,
        "databricks_token": None,
    }


def test_analysis_validation_results_replace_only_validation_fields_and_replay(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    context = seed.execution.context
    source_context_digests = _source_context_digests(postgres_database, seed)
    results = [
        _validation_result(
            seed.active_result_id,
            source_context_digest=source_context_digests[seed.active_result_id],
            digest_character="a",
            count_base=100,
        ),
        _validation_result(
            seed.locked_result_id,
            source_context_digest=source_context_digests[seed.locked_result_id],
            digest_character="b",
            count_base=200,
            validation_result="inconclusive",
        ),
    ]

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        persisted = require_row(
            connection.execute(
                PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
                _persist_validation_parameters(seed, results),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        after_persist = connection.execute(
            """
            SELECT analysis_result_id,
                   agent_run_id,
                   inference_workflow_run_id,
                   validation_workflow_run_id,
                   validation_source_context_digest,
                   relationship_kind,
                   relationship_confidence,
                   relationship_basis,
                   validation_policy_version,
                   validation_policy_digest,
                   validation_result,
                   validation_source_non_null_count,
                   validation_source_distinct_count,
                   validation_target_non_null_count,
                   validation_target_distinct_count,
                   validation_source_missing_target_count,
                   validation_unused_target_count,
                   validation_duplicate_target_key_count,
                   analysis_result_status,
                   analysis_result_is_locked,
                   updated_time
              FROM workflow.analysis_result
             WHERE model_id = %s
             ORDER BY analysis_result_id
            """,
            (context.model_id,),
        ).fetchall()

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        replayed = require_row(
            connection.execute(
                PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
                _persist_validation_parameters(
                    seed,
                    results,
                    expected_model_revision=persisted["model_revision"],
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
                    seed.execution.workflow_run_id,
                    persisted["model_revision"],
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        after_replay = connection.execute(
            """
            SELECT analysis_result_id, updated_time
              FROM workflow.analysis_result
             WHERE model_id = %s
             ORDER BY analysis_result_id
            """,
            (context.model_id,),
        ).fetchall()
        revision_kinds = connection.execute(
            """
            SELECT change_kind
              FROM model.model_revision_transaction
             WHERE model_id = %s
               AND change_kind = 'web_analysis_validation_results_persist'
             ORDER BY changed_time
            """,
            (context.model_id,),
        ).fetchall()

    assert persisted == {
        "changed": True,
        "workflow_run_id": seed.execution.workflow_run_id,
        "model_id": context.model_id,
        "model_revision": context.model_revision + 1,
        "submitted_result_count": 2,
        "changed_result_count": 2,
    }
    assert replayed == {
        **persisted,
        "changed": False,
        "changed_result_count": 0,
    }
    assert completed["workflow_run_state"] == "completed"
    assert revision_kinds == [
        {"change_kind": "web_analysis_validation_results_persist"}
    ]
    assert after_replay == [
        {
            "analysis_result_id": row["analysis_result_id"],
            "updated_time": row["updated_time"],
        }
        for row in after_persist
    ]

    stored_by_id = {row["analysis_result_id"]: row for row in after_persist}
    for submitted in results:
        stored = stored_by_id[submitted["analysis_result_id"]]
        assert stored["agent_run_id"] is None
        assert stored["inference_workflow_run_id"] is None
        assert stored["validation_workflow_run_id"] == seed.execution.workflow_run_id
        for field, value in submitted.items():
            if field == "source_context_digest":
                assert stored["validation_source_context_digest"] == value
            else:
                assert stored[field] == value

    active = stored_by_id[seed.active_result_id]
    assert active["relationship_kind"] == "reference"
    assert active["relationship_confidence"] == "medium"
    assert active["relationship_basis"] == "Analysis validation relationship 1."
    assert active["analysis_result_status"] == "active"
    assert active["analysis_result_is_locked"] is False

    locked = stored_by_id[seed.locked_result_id]
    assert locked["relationship_kind"] == "lookup"
    assert locked["relationship_basis"] == "Analysis validation relationship 2."
    assert locked["analysis_result_status"] == "needs_review"
    assert locked["analysis_result_is_locked"] is True

    inactive = stored_by_id[seed.inactive_result_id]
    assert inactive["relationship_kind"] == "inactive_test"
    assert inactive["analysis_result_status"] == "inactive"
    assert inactive["validation_workflow_run_id"] is None
    assert inactive["validation_source_context_digest"] is None
    assert inactive["validation_policy_version"] is None
    assert inactive["validation_result"] is None


def test_analysis_validation_results_allow_empty_exact_context(
    postgres_database: DisposablePostgres,
) -> None:
    execution = _seed_profiling_execution(postgres_database, workflow="analysis")
    seed = AnalysisValidationSeed(
        execution=execution,
        endpoints=(),
        active_result_id=0,
        locked_result_id=0,
        inactive_result_id=0,
    )

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        result = require_row(
            connection.execute(
                PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
                _persist_validation_parameters(seed, []),
            ).fetchone()
        )

    assert result == {
        "changed": False,
        "workflow_run_id": execution.workflow_run_id,
        "model_id": execution.context.model_id,
        "model_revision": execution.context.model_revision,
        "submitted_result_count": 0,
        "changed_result_count": 0,
    }


def test_analysis_validation_persistence_rejects_stale_physical_context(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    context = seed.execution.context
    source_context_digests = _source_context_digests(postgres_database, seed)
    results = [
        _validation_result(
            seed.active_result_id,
            source_context_digest=source_context_digests[seed.active_result_id],
            digest_character="7",
            count_base=10,
        ),
        _validation_result(
            seed.locked_result_id,
            source_context_digest=source_context_digests[seed.locked_result_id],
            digest_character="8",
            count_base=20,
        ),
    ]

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.object
               SET object_name = %s
             WHERE object_id = %s
            """,
            (f"renamed_{uuid4().hex}", seed.endpoints[0].object_id),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="context digest"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
            _persist_validation_parameters(seed, results),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        unchanged = require_row(
            connection.execute(
                """
                SELECT count(*) FILTER (
                           WHERE validation_workflow_run_id IS NOT NULL
                       )::INTEGER AS validated_count,
                       target_model.model_revision
                  FROM workflow.analysis_result AS result
                  JOIN model.model AS target_model
                    ON target_model.model_id = result.model_id
                 WHERE result.model_id = %s
                 GROUP BY target_model.model_revision
                """,
                (context.model_id,),
            ).fetchone()
        )

    assert unchanged == {
        "validated_count": 0,
        "model_revision": context.model_revision,
    }


def test_analysis_validation_persistence_rejects_stale_connection_context(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    source_context_digests = _source_context_digests(postgres_database, seed)
    results = [
        _validation_result(
            seed.active_result_id,
            source_context_digest=source_context_digests[seed.active_result_id],
            digest_character="7",
            count_base=10,
        ),
        _validation_result(
            seed.locked_result_id,
            source_context_digest=source_context_digests[seed.locked_result_id],
            digest_character="8",
            count_base=20,
        ),
    ]

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.connection_value AS connection_value
               SET connection_value = connection_value.connection_value || '_rotated'
              FROM reference.connection_parameter AS parameter
             WHERE parameter.connection_parameter_id =
                   connection_value.connection_parameter_id
               AND connection_value.connection_id = %s
               AND lower(btrim(parameter.connection_parameter_code)) =
                   'databricks_token'
            """,
            (seed.execution.connection_id,),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="context digest"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
            _persist_validation_parameters(seed, results),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        validated_count = require_row(
            connection.execute(
                """
                SELECT count(*) FILTER (
                           WHERE validation_workflow_run_id IS NOT NULL
                       )::INTEGER AS validated_count
                  FROM workflow.analysis_result
                 WHERE model_id = %s
                """,
                (seed.execution.context.model_id,),
            ).fetchone()
        )["validated_count"]

    assert validated_count == 0


def test_analysis_validation_persistence_requires_running_deterministic_analysis(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    context = seed.execution.context
    source_context_digests = _source_context_digests(postgres_database, seed)
    results = [
        _validation_result(
            seed.active_result_id,
            source_context_digest=source_context_digests[seed.active_result_id],
            digest_character="1",
            count_base=10,
        ),
        _validation_result(
            seed.locked_result_id,
            source_context_digest=source_context_digests[seed.locked_result_id],
            digest_character="2",
            count_base=20,
        ),
    ]
    queued_run_id = _create_run(
        postgres_database,
        context,
        workflow="analysis",
        start=False,
    )
    profiling_run_id = _create_run(
        postgres_database,
        context,
        workflow="profiling",
    )
    with postgres_database.connect_owner() as connection:
        agentic_run_id = require_row(
            connection.execute(
                """
                INSERT INTO application.workflow_run (
                    model_id,
                    model_revision,
                    model_workflow,
                    workflow_execution_mode,
                    actor_principal_id,
                    actor_entra_principal_identity_id,
                    agent_sdk_code,
                    agent_provider_code,
                    agent_model_code,
                    reasoning_effort_code,
                    max_turns,
                    validation_retry_count,
                    selected_scope_digest,
                    selected_scope_count,
                    workflow_run_state,
                    correlation_id,
                    started_time
                )
                SELECT source_run.model_id,
                       source_run.model_revision,
                       'analysis',
                       'one_shot',
                       source_run.actor_principal_id,
                       source_run.actor_entra_principal_identity_id,
                       target_model.default_agent_sdk_code,
                       target_model.default_agent_provider_code,
                       target_model.default_agent_model_code,
                       target_model.default_reasoning_effort_code,
                       target_model.default_max_turns,
                       target_model.default_validation_retry_count,
                       source_run.selected_scope_digest,
                       source_run.selected_scope_count,
                       'running',
                       %s,
                       CURRENT_TIMESTAMP
                  FROM application.workflow_run AS source_run
                  JOIN model.model AS target_model
                    ON target_model.model_id = source_run.model_id
                 WHERE source_run.workflow_run_id = %s
                RETURNING workflow_run_id
                """,
                (uuid4(), seed.execution.workflow_run_id),
            ).fetchone()
        )["workflow_run_id"]
        connection.execute(
            """
            INSERT INTO application.workflow_run_object_selection (
                workflow_run_id,
                model_id,
                object_id,
                selection_order
            )
            SELECT %s,
                   selection.model_id,
                   selection.object_id,
                   selection.selection_order
              FROM application.workflow_run_object_selection AS selection
             WHERE selection.workflow_run_id = %s
            """,
            (agentic_run_id, seed.execution.workflow_run_id),
        )

    for run_id in (queued_run_id, profiling_run_id, agentic_run_id):
        with (
            psycopg.connect(
                postgres_database.web_runtime_dsn(),
                row_factory=dict_row,
            ) as connection,
            pytest.raises(
                RaiseException,
                match="running deterministic Analysis Workflow Run",
            ),
            connection.transaction(),
        ):
            connection.execute("SET ROLE gds_web_write")
            connection.execute(
                PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
                _persist_validation_parameters(
                    seed,
                    results,
                    workflow_run_id=run_id,
                ),
            ).fetchone()


def test_analysis_validation_payload_is_exact_strict_and_atomic(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    source_context_digests = _source_context_digests(postgres_database, seed)
    valid = [
        _validation_result(
            seed.active_result_id,
            source_context_digest=source_context_digests[seed.active_result_id],
            digest_character="c",
            count_base=10,
        ),
        _validation_result(
            seed.locked_result_id,
            source_context_digest=source_context_digests[seed.locked_result_id],
            digest_character="d",
            count_base=20,
        ),
    ]
    missing_field = {**valid[0]}
    missing_field.pop("validation_result")
    extra_field = {**valid[0], "unexpected": "value"}
    invalid_version = {**valid[0], "validation_policy_version": "v1"}
    invalid_digest = {**valid[0], "validation_policy_digest": "A" * 64}
    invalid_source_digest = {**valid[0], "source_context_digest": "A" * 64}
    boolean_count = {**valid[0], "validation_source_non_null_count": True}
    negative_count = {**valid[0], "validation_unused_target_count": -1}
    invalid_result = {**valid[0], "validation_result": "confirmed"}
    out_of_range_id = {
        **valid[0],
        "analysis_result_id": 9223372036854775808,
    }
    count_fields = (
        "validation_source_non_null_count",
        "validation_source_distinct_count",
        "validation_target_non_null_count",
        "validation_target_distinct_count",
        "validation_source_missing_target_count",
        "validation_unused_target_count",
        "validation_duplicate_target_key_count",
    )
    out_of_range_counts = tuple(
        {**valid[0], field_name: 9223372036854775808} for field_name in count_fields
    )
    source_zero_distinct = {
        **valid[0],
        "validation_source_distinct_count": 0,
    }
    target_zero_distinct = {
        **valid[0],
        "validation_target_distinct_count": 0,
        "validation_duplicate_target_key_count": (
            valid[0]["validation_target_non_null_count"]
        ),
    }
    source_distinct_too_large = {
        **valid[0],
        "validation_source_distinct_count": (
            valid[0]["validation_source_non_null_count"] + 1
        ),
    }
    missing_too_large = {
        **valid[0],
        "validation_source_missing_target_count": (
            valid[0]["validation_source_distinct_count"] + 1
        ),
    }
    unused_too_large = {
        **valid[0],
        "validation_unused_target_count": (
            valid[0]["validation_target_distinct_count"] + 1
        ),
    }
    duplicate_mismatch = {
        **valid[0],
        "validation_duplicate_target_key_count": 1,
    }
    outcome_mismatch = {**valid[0], "validation_result": "unsupported"}
    unknown = _validation_result(
        9223372036854775807,
        source_context_digest="e" * 64,
        digest_character="e",
        count_base=30,
    )
    invalid_payloads = (
        (valid[:1], "exactly cover"),
        ([valid[0], valid[0]], "IDs must be unique"),
        ([valid[0], unknown], "exactly cover"),
        ([missing_field, valid[1]], "payload shape is invalid"),
        ([extra_field, valid[1]], "payload shape is invalid"),
        ([invalid_version, valid[1]], "payload shape is invalid"),
        ([invalid_digest, valid[1]], "payload shape is invalid"),
        ([invalid_source_digest, valid[1]], "payload shape is invalid"),
        ([boolean_count, valid[1]], "payload shape is invalid"),
        ([negative_count, valid[1]], "payload shape is invalid"),
        ([invalid_result, valid[1]], "payload shape is invalid"),
        ([out_of_range_id, valid[1]], "payload shape is invalid"),
        *(
            ([out_of_range_count, valid[1]], "payload shape is invalid")
            for out_of_range_count in out_of_range_counts
        ),
        ([source_zero_distinct, valid[1]], "evidence is inconsistent"),
        ([target_zero_distinct, valid[1]], "evidence is inconsistent"),
        ([source_distinct_too_large, valid[1]], "evidence is inconsistent"),
        ([missing_too_large, valid[1]], "evidence is inconsistent"),
        ([unused_too_large, valid[1]], "evidence is inconsistent"),
        ([duplicate_mismatch, valid[1]], "evidence is inconsistent"),
        ([outcome_mismatch, valid[1]], "evidence is inconsistent"),
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
                PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
                _persist_validation_parameters(seed, payload),
            ).fetchone()

    with postgres_database.connect_owner() as connection:
        unchanged = require_row(
            connection.execute(
                """
                SELECT count(*) FILTER (
                           WHERE validation_policy_version IS NOT NULL
                              OR validation_workflow_run_id IS NOT NULL
                       )::INTEGER AS validated_count,
                       target_model.model_revision
                  FROM workflow.analysis_result AS result
                  JOIN model.model AS target_model
                    ON target_model.model_id = result.model_id
                 WHERE result.model_id = %s
                 GROUP BY target_model.model_revision
                """,
                (seed.execution.context.model_id,),
            ).fetchone()
        )

    assert unchanged == {
        "validated_count": 0,
        "model_revision": seed.execution.context.model_revision,
    }


def test_analysis_validation_persistence_revalidates_actor_lock_and_revision(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_analysis_validation(postgres_database)
    other = seed_workflow_context(postgres_database)
    source_context_digests = _source_context_digests(postgres_database, seed)
    results = [
        _validation_result(
            seed.active_result_id,
            source_context_digest=source_context_digests[seed.active_result_id],
            digest_character="f",
            count_base=10,
        ),
        _validation_result(
            seed.locked_result_id,
            source_context_digest=source_context_digests[seed.locked_result_id],
            digest_character="0",
            count_base=20,
        ),
    ]

    attempts = (
        (
            _persist_validation_parameters(
                seed,
                results,
                entra_tenant_id=other.entra_tenant_id,
                entra_object_id=other.entra_object_id,
            ),
            "authorization_denied",
        ),
        (
            _persist_validation_parameters(
                seed,
                results,
                expected_model_revision=seed.execution.context.model_revision + 1,
            ),
            "stale_model_revision",
        ),
    )
    for parameters, message in attempts:
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
                PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
                parameters,
            ).fetchone()

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET tenant_lock_acquired_time = CURRENT_TIMESTAMP - INTERVAL '2 minutes',
                   tenant_lock_expires_time = CURRENT_TIMESTAMP - INTERVAL '1 minute'
             WHERE tenant_id = %s
            """,
            (seed.execution.context.tenant_id,),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="tenant_lock_required"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            PERSIST_ANALYSIS_VALIDATION_RESULTS_SQL,
            _persist_validation_parameters(seed, results),
        ).fetchone()

    with postgres_database.connect_owner() as connection:
        unchanged = require_row(
            connection.execute(
                """
                SELECT count(*) FILTER (
                           WHERE validation_workflow_run_id IS NOT NULL
                       )::INTEGER AS validated_count,
                       target_model.model_revision
                  FROM workflow.analysis_result AS result
                  JOIN model.model AS target_model
                    ON target_model.model_id = result.model_id
                 WHERE result.model_id = %s
                 GROUP BY target_model.model_revision
                """,
                (seed.execution.context.model_id,),
            ).fetchone()
        )

    assert unchanged == {
        "validated_count": 0,
        "model_revision": seed.execution.context.model_revision,
    }


def test_web_role_has_function_only_analysis_validation_credential_surface(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        privileges = require_row(
            connection.execute(
                """
                SELECT has_function_privilege(
                           'gds_web_write',
                           %s,
                           'EXECUTE'
                       ) AS web_context_execute,
                       has_function_privilege(
                           'gds_web_write',
                           %s,
                           'EXECUTE'
                       ) AS web_values_execute,
                       has_function_privilege(
                           'gds_app_write',
                           %s,
                           'EXECUTE'
                       ) AS mcp_context_execute,
                       has_function_privilege(
                           'gds_app_write',
                           %s,
                           'EXECUTE'
                       ) AS mcp_values_execute,
                       has_table_privilege(
                           'gds_web_write',
                           'core.connection_value',
                           'SELECT'
                       ) AS web_connection_value_select
                """,
                (
                    ANALYSIS_VALIDATION_CONTEXT_SIGNATURE,
                    ANALYSIS_VALIDATION_VALUES_SIGNATURE,
                    ANALYSIS_VALIDATION_CONTEXT_SIGNATURE,
                    ANALYSIS_VALIDATION_VALUES_SIGNATURE,
                ),
            ).fetchone()
        )

    assert privileges == {
        "web_context_execute": True,
        "web_values_execute": True,
        "mcp_context_execute": False,
        "mcp_values_execute": False,
        "web_connection_value_select": False,
    }

    with (
        postgres_database.connect_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
        connection.transaction(),
    ):
        connection.execute(
            GET_ANALYSIS_VALIDATION_EXECUTION_CONTEXT_SQL,
            (uuid4(), uuid4(), 1, 1, "Production"),
        )
