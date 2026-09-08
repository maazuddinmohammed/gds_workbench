"""Governed physical enrichment, using fixture-only disposable PostgreSQL."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_metadata_enrichment_registration import _context, _create
from tests.mcp.test_database_notebook_workflows import (
    NotebookActor,
    notebook_actor as notebook_actor,
)
from tests.mcp.test_database_profiling_persistence import _seed_attributes
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    _claim_specific_workflow_run,
)

CONTEXT_SQL = "SELECT application.get_metadata_enrichment_execution_context(%s,%s,'user',%s,%s) AS result"
COMPLETE_SQL = "SELECT application.complete_metadata_enrichment(%s,%s,'user',%s,%s,%s,%s,%s) AS result"
READ_SQL = "SELECT application.get_metadata_enrichment_results(%s,%s,'user',%s,%s,%s) AS result"


def _start(
    actor: NotebookActor,
) -> tuple[WorkflowContext, int, UUID, tuple[tuple[int, int], ...]]:
    context = _context(actor)
    attributes = _seed_attributes(actor.database, context)
    run_id = _create(actor, context, correlation_id=uuid4())["workflow_run_id"]
    with actor.database.connect_owner() as connection:
        connection.execute(
            "SELECT application.start_workflow_run(%s,%s,'user',%s,%s)",
            (
                context.entra_tenant_id,
                context.entra_object_id,
                run_id,
                context.model_revision,
            ),
        )
    claim = _claim_specific_workflow_run(actor.database, run_id)
    return context, run_id, UUID(str(claim["workflow_run_claim_token"])), attributes


def _load(
    actor: NotebookActor, context: WorkflowContext, run_id: int
) -> dict[str, Any]:
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        return require_row(
            connection.execute(
                CONTEXT_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    context.model_revision,
                ),
            ).fetchone()
        )["result"]


def _complete(
    actor: NotebookActor,
    context: WorkflowContext,
    run_id: int,
    claim: UUID,
    baseline: str,
    results: list[dict[str, Any]],
    *,
    full: bool = True,
) -> dict[str, Any]:
    if full:
        results = _full_results(actor, run_id, results)
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        return require_row(
            connection.execute(
                COMPLETE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    context.model_revision,
                    claim,
                    baseline,
                    Jsonb(results),
                ),
            ).fetchone()
        )["result"]


def _full_results(
    actor: NotebookActor, run_id: int, results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    keyed = {
        (row["object_id"], row["attribute_id"], row["field_name"]): row
        for row in results
    }
    with actor.database.connect_owner() as connection:
        objects = connection.execute(
            "SELECT object_id FROM application.workflow_run_object_selection WHERE workflow_run_id=%s ORDER BY object_id",
            (run_id,),
        ).fetchall()
        attributes = connection.execute(
            "SELECT attribute.object_id, attribute_id FROM core.attribute AS attribute JOIN application.workflow_run_object_selection USING(object_id) WHERE workflow_run_id=%s ORDER BY attribute_id",
            (run_id,),
        ).fetchall()
    keys = [(row["object_id"], None, "object_description") for row in objects]
    keys += [
        (row["object_id"], row["attribute_id"], field)
        for row in attributes
        for field in ("attribute_description", "attribute_inferred_data_type")
    ]
    return [
        keyed.get(key, _field(*key, None, status="inconclusive", method="none"))
        for key in keys
    ]


def _field(
    object_id: int,
    attribute_id: int | None,
    field: str,
    value: str | None,
    *,
    status: str = "applied",
    method: str = "agent_description",
    count: int = 0,
) -> dict[str, Any]:
    return dict(
        object_id=object_id,
        attribute_id=attribute_id,
        field_name=field,
        applied_value=value,
        status=status,
        evidence_method=method,
        sample_count=count,
    )


def test_context_missing_relations_and_atomic_completion_replay(
    notebook_actor: NotebookActor,
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    snapshot = _load(actor, context, run_id)
    object_id, attribute_id = attributes[0]
    assert len(snapshot["baseline_digest"]) == 64
    assert snapshot["objects"][0]["relation"] is None
    assert snapshot["objects"][0]["attributes"][0]["source"] is None
    fields = [
        _field(object_id, None, "object_description", "Customer records."),
        _field(
            object_id, attribute_id, "attribute_description", "Customer identifier."
        ),
        _field(
            object_id,
            attribute_id,
            "attribute_inferred_data_type",
            "BIGINT",
            method="registered_type",
        ),
    ]
    result = _complete(
        actor, context, run_id, claim, snapshot["baseline_digest"], fields
    )
    assert result["counts"]["applied"] == 3
    assert result["workflow_run_state"] == "completed"
    assert "applied_field_counts" not in result
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        for offset in (0, 1, 2, 10200):
            page = require_row(
                connection.execute(
                    READ_SQL,
                    (
                        context.entra_tenant_id,
                        context.entra_object_id,
                        run_id,
                        1,
                        offset,
                    ),
                ).fetchone()
            )["result"]
            assert page["applied_field_counts"] == {
                "object_description": 1,
                "attribute_description": 1,
                "attribute_inferred_data_type": 1,
            }
    assert (
        _complete(actor, context, run_id, claim, snapshot["baseline_digest"], fields)
        == result
    )
    with pytest.raises(RaiseException, match="conflict"):
        _complete(
            actor, context, run_id, claim, snapshot["baseline_digest"], fields[:1]
        )
    with actor.database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                "SELECT attribute_data_type, attribute_inferred_data_type, attribute_description, is_locked FROM core.attribute WHERE attribute_id=%s",
                (attribute_id,),
            ).fetchone()
        )
        assert row == dict(
            attribute_data_type="string",
            attribute_inferred_data_type="BIGINT",
            attribute_description="Customer identifier.",
            is_locked=False,
        )
        assert (
            require_row(
                connection.execute(
                    "SELECT model_revision FROM model.model WHERE model_id=%s",
                    (context.model_id,),
                ).fetchone()
            )["model_revision"]
            == context.model_revision
        )
        assert require_row(
            connection.execute(
                "SELECT count(*) AS count FROM application.metadata_enrichment_result WHERE workflow_run_id=%s",
                (run_id,),
            ).fetchone()
        )["count"] == len(_full_results(actor, run_id, fields))
        with pytest.raises(RaiseException, match="durable"):
            connection.execute(
                "SELECT application.fail_workflow_run(%s,%s,'user',%s,%s,'failure','Safe failure.')",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    context.model_revision,
                ),
            )


def test_completion_replaces_unlocked_descriptions_and_preserves_locked_inactive_fields(
    notebook_actor: NotebookActor,
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    first, second = attributes[:2]
    with actor.database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET object_description='Existing object.' WHERE object_id=%s",
            (first[0],),
        )

        connection.execute(
            "UPDATE core.attribute SET is_locked=TRUE WHERE attribute_id=%s",
            (first[1],),
        )
        connection.execute(
            "UPDATE core.attribute SET is_active=FALSE WHERE attribute_id=%s",
            (second[1],),
        )
    snapshot = _load(actor, context, run_id)
    results = [
        _field(first[0], None, "object_description", "Replacement."),
        _field(*first, "attribute_description", "Replacement."),
        _field(*second, "attribute_description", "Replacement."),
    ]
    result = _complete(
        actor, context, run_id, claim, snapshot["baseline_digest"], results
    )
    assert result["counts"] == {
        "applied": 1,
        "locked": 2,
        "inactive": 2,
        "inconclusive": len(_full_results(actor, run_id, [])) - 5,
    }
    with actor.database.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT applied_value FROM application.metadata_enrichment_result WHERE workflow_run_id=%s AND applied_value IS NOT NULL",
                (run_id,),
            ).fetchone()
            is not None
        )


def test_generated_null_clears_unlocked_description_but_not_inferred_type(
    notebook_actor: NotebookActor,
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    first = attributes[0]
    with actor.database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET object_description='Existing description.' WHERE object_id=%s",
            (first[0],),
        )
        connection.execute(
            "UPDATE core.attribute SET attribute_description='Existing meaning.', attribute_inferred_data_type='BIGINT' WHERE attribute_id=%s",
            (first[1],),
        )
    snapshot = _load(actor, context, run_id)
    _complete(
        actor,
        context,
        run_id,
        claim,
        snapshot["baseline_digest"],
        [
            _field(first[0], None, "object_description", None),
            _field(*first, "attribute_description", None),
            _field(
                *first,
                "attribute_inferred_data_type",
                "STRING",
                method="registered_type",
            ),
        ],
    )
    with actor.database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                "SELECT object_description, attribute_description, attribute_inferred_data_type FROM core.object JOIN core.attribute USING(object_id) WHERE attribute_id=%s",
                (first[1],),
            ).fetchone()
        )
        assert row == {
            "object_description": None,
            "attribute_description": None,
            "attribute_inferred_data_type": "BIGINT",
        }


@pytest.mark.parametrize("drift", ["description", "lock", "attribute", "mapping"])
def test_baseline_drift_completes_changed_without_writes(
    notebook_actor: NotebookActor, drift: str
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    snapshot = _load(actor, context, run_id)
    first, second = attributes[:2]
    with actor.database.connect_owner() as connection:
        if drift == "description":
            connection.execute(
                "UPDATE core.object SET object_description='Changed.' WHERE object_id=%s",
                (second[0],),
            )
        elif drift == "lock":
            connection.execute(
                "UPDATE core.object SET is_locked=TRUE WHERE object_id=%s", (second[0],)
            )
        elif drift == "attribute":
            connection.execute(
                "UPDATE core.attribute SET attribute_data_type='int' WHERE attribute_id=%s",
                (second[1],),
            )
        else:
            connection.execute(
                "INSERT INTO core.ingestion_object_mapping(source_object_id,target_object_id) VALUES (%s,%s)",
                (second[0], first[0]),
            )
    result = _complete(
        actor,
        context,
        run_id,
        claim,
        snapshot["baseline_digest"],
        [_field(*first, "attribute_description", "Candidate.")],
    )
    assert result["counts"] == {"changed": len(_full_results(actor, run_id, []))}
    assert result["warning_count"] == len(_full_results(actor, run_id, []))
    with actor.database.connect_owner() as connection:
        assert (
            require_row(
                connection.execute(
                    "SELECT attribute_description FROM core.attribute WHERE attribute_id=%s",
                    (first[1],),
                ).fetchone()
            )["attribute_description"]
            is None
        )


@pytest.mark.parametrize(
    "fence", ["claim", "revision", "identity", "scope", "role", "lock", "object_owner"]
)
def test_completion_denials_leave_no_receipt_or_writes(
    notebook_actor: NotebookActor, fence: str
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    snapshot = _load(actor, context, run_id)
    first = attributes[0]
    if fence == "claim":
        claim = uuid4()
    elif fence == "revision":
        context = replace(context, model_revision=context.model_revision + 1)
    elif fence == "identity":
        context = replace(context, entra_object_id=uuid4())
    else:
        with actor.database.connect_owner() as connection:
            if fence == "scope":
                connection.execute(
                    "UPDATE model.model_input_scope SET is_active=FALSE WHERE model_id=%s AND object_id=%s",
                    (context.model_id, first[0]),
                )
            elif fence == "role":
                connection.execute(
                    "UPDATE security.tenant_principal_access SET tenant_role='developer' WHERE tenant_id=%s AND principal_id=%s",
                    (context.tenant_id, context.principal_id),
                )
            elif fence == "lock":
                connection.execute(
                    "UPDATE security.tenant_lock SET tenant_lock_expires_time=clock_timestamp()-INTERVAL '1 second', tenant_lock_acquired_time=clock_timestamp()-INTERVAL '1 hour' WHERE tenant_id=%s",
                    (context.tenant_id,),
                )
            else:
                connection.execute(
                    "UPDATE core.object SET is_active=FALSE WHERE object_id=%s",
                    (first[0],),
                )
    with pytest.raises(RaiseException):
        _complete(
            actor,
            context,
            run_id,
            claim,
            snapshot["baseline_digest"],
            [_field(*first, "attribute_description", "Candidate.")],
        )
    with actor.database.connect_owner() as connection:
        assert (
            require_row(
                connection.execute(
                    "SELECT metadata_enrichment_receipt_digest FROM application.workflow_run WHERE workflow_run_id=%s",
                    (run_id,),
                ).fetchone()
            )["metadata_enrichment_receipt_digest"]
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM application.metadata_enrichment_result WHERE workflow_run_id=%s",
                (run_id,),
            ).fetchone()
            is None
        )


def test_generic_completion_denied_and_paginated_read_needs_no_lock(
    notebook_actor: NotebookActor,
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    with actor.database.connect_owner() as connection:
        with pytest.raises(RaiseException, match="receipt"):
            connection.execute(
                "SELECT application.complete_workflow_run(%s,%s,'user',%s,%s,0)",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    context.model_revision,
                ),
            )
    snapshot = _load(actor, context, run_id)
    _complete(
        actor,
        context,
        run_id,
        claim,
        snapshot["baseline_digest"],
        [_field(*attributes[0], "attribute_description", "Candidate.")],
    )
    with actor.database.connect_owner() as connection:
        connection.execute(
            "UPDATE security.tenant_lock SET tenant_lock_expires_time=clock_timestamp()-INTERVAL '1 second', tenant_lock_acquired_time=clock_timestamp()-INTERVAL '1 hour' WHERE tenant_id=%s",
            (context.tenant_id,),
        )
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        page = require_row(
            connection.execute(
                READ_SQL,
                (context.entra_tenant_id, context.entra_object_id, run_id, 1, 0),
            ).fetchone()
        )["result"]
        assert page["tenant_id"] == context.tenant_id
        assert page["model_id"] == context.model_id
        assert len(page["results"]) == 1
        assert page["total_count"] == len(_full_results(actor, run_id, []))
        with pytest.raises(InsufficientPrivilege):
            connection.execute("SELECT * FROM application.metadata_enrichment_result")


@pytest.mark.parametrize(
    "invalid",
    [
        "empty",
        "partial",
        "duplicate",
        "extra_key",
        "null_status",
        "object_attribute",
        "description_bytes",
        "type_length",
        "sample_count",
        "masked_sample",
    ],
)
def test_completion_rejects_incomplete_or_invalid_ledger(
    notebook_actor: NotebookActor, invalid: str
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    first = attributes[0]
    if invalid == "masked_sample":
        with actor.database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.attribute SET is_masking_required=TRUE WHERE attribute_id=%s",
                (first[1],),
            )
    snapshot = _load(actor, context, run_id)
    fields = _full_results(
        actor, run_id, [_field(*first, "attribute_description", "Candidate.")]
    )
    target = next(
        row
        for row in fields
        if row["attribute_id"] == first[1]
        and row["field_name"] == "attribute_description"
    )
    if invalid == "empty":
        fields = []
    elif invalid == "partial":
        fields.pop()
    elif invalid == "duplicate":
        fields.append(target.copy())
    elif invalid == "extra_key":
        target["raw_sample"] = "must not persist"
    elif invalid == "null_status":
        target["status"] = None
    elif invalid == "object_attribute":
        fields[0]["attribute_id"] = first[1]
    elif invalid == "description_bytes":
        target["applied_value"] = "é" * 1001
    elif invalid == "type_length":
        target = next(
            row
            for row in fields
            if row["attribute_id"] == first[1]
            and row["field_name"] == "attribute_inferred_data_type"
        )
        target.update(
            status="applied", applied_value="x" * 101, evidence_method="registered_type"
        )
    elif invalid == "sample_count":
        target.update(sample_count=51, evidence_method="source_sample")
    else:
        target = next(
            row
            for row in fields
            if row["attribute_id"] == first[1]
            and row["field_name"] == "attribute_inferred_data_type"
        )
        target.update(
            status="applied",
            applied_value="BIGINT",
            evidence_method="bronze_sample",
            sample_count=1,
        )
    with pytest.raises(RaiseException):
        _complete(
            actor,
            context,
            run_id,
            claim,
            snapshot["baseline_digest"],
            fields,
            full=False,
        )
    with actor.database.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM application.metadata_enrichment_result WHERE workflow_run_id=%s",
                (run_id,),
            ).fetchone()
            is None
        )
        assert (
            require_row(
                connection.execute(
                    "SELECT attribute_description FROM core.attribute WHERE attribute_id=%s",
                    (first[1],),
                ).fetchone()
            )["attribute_description"]
            is None
        )


@pytest.mark.parametrize(
    "mapping",
    [
        "none",
        "one",
        "ambiguous",
        "inactive_object_mapping",
        "inactive_attribute_mapping",
        "inactive_source",
        "foreign_source",
    ],
)
def test_source_evidence_requires_exact_active_unambiguous_ingestion(
    notebook_actor: NotebookActor, mapping: str
) -> None:
    from tests.mcp.test_database_workflow_run_lifecycle import (
        _seed_model_input_scope_object_in_zone,
        seed_workflow_context,
    )

    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    target_object, target_attribute = attributes[0]
    source_ids: list[int] = []
    for _ in range(2 if mapping == "ambiguous" else 1):
        source_object = _seed_model_input_scope_object_in_zone(
            actor.database, context, zone_code="source"
        )
        with actor.database.connect_owner() as connection:
            source_attribute = require_row(
                connection.execute(
                    "INSERT INTO core.attribute(object_id,attribute_name,attribute_ordinal_position,attribute_data_type,attribute_description) VALUES (%s,'registered_id',1,'bigint','Registered source identifier.') RETURNING attribute_id",
                    (source_object,),
                ).fetchone()
            )["attribute_id"]
            source_ids.append(source_attribute)
            if mapping != "none":
                object_mapping = require_row(
                    connection.execute(
                        "INSERT INTO core.ingestion_object_mapping(source_object_id,target_object_id,is_active) VALUES (%s,%s,%s) RETURNING ingestion_object_mapping_id",
                        (
                            source_object,
                            target_object,
                            mapping != "inactive_object_mapping",
                        ),
                    ).fetchone()
                )["ingestion_object_mapping_id"]
                connection.execute(
                    "INSERT INTO core.ingestion_attribute_mapping(ingestion_object_mapping_id,source_object_id,target_object_id,source_attribute_id,target_attribute_id,is_active) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        object_mapping,
                        source_object,
                        target_object,
                        source_attribute,
                        target_attribute,
                        mapping != "inactive_attribute_mapping",
                    ),
                )
            if mapping == "inactive_source":
                connection.execute(
                    "UPDATE core.attribute SET is_active=FALSE WHERE attribute_id=%s",
                    (source_attribute,),
                )
        if mapping == "foreign_source":
            foreign = seed_workflow_context(actor.database)
            with actor.database.connect_owner() as connection:
                connection.execute(
                    "UPDATE core.object SET source_tenant_id=%s WHERE object_id=%s",
                    (foreign.tenant_id, source_object),
                )
    snapshot = _load(actor, context, run_id)
    target = next(
        row for row in snapshot["objects"] if row["object_id"] == target_object
    )["attributes"][0]
    assert target["source_candidate_count"] == (
        2 if mapping == "ambiguous" else 1 if mapping == "one" else 0
    )
    if mapping == "one":
        assert target["source"]["attribute_id"] == source_ids[0]
        assert target["source"]["attribute_data_type"] == "bigint"
        assert target["source"]["relation"] is None
        with actor.database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.attribute SET attribute_description='Changed source.' WHERE attribute_id=%s",
                (source_ids[0],),
            )
        result = _complete(
            actor,
            context,
            run_id,
            claim,
            snapshot["baseline_digest"],
            [
                _field(
                    target_object,
                    target_attribute,
                    "attribute_description",
                    "Candidate.",
                )
            ],
        )
        assert set(result["counts"]) == {"changed"}
    else:
        assert target["source"] is None


def test_source_relation_uses_gds_execution_connection_and_credentials_are_exact(
    notebook_actor: NotebookActor,
) -> None:
    from tests.mcp.test_database_workflow_run_lifecycle import (
        _seed_model_input_scope_object_in_zone,
    )

    actor = notebook_actor
    context = _context(actor)
    source_object = _seed_model_input_scope_object_in_zone(
        actor.database, context, zone_code="source"
    )
    with actor.database.connect_owner() as connection:
        source_connection = require_row(
            connection.execute(
                "SELECT connection_id FROM core.object WHERE object_id=%s",
                (source_object,),
            ).fetchone()
        )["connection_id"]
        gds_connection = require_row(
            connection.execute(
                "INSERT INTO core.connection(tenant_id,system_id,connection_code,connection_name,connection_type_id,is_global_data_store) SELECT tenant_id,system_id,%s,'Execution connection',connection_type_id,TRUE FROM core.connection WHERE connection_id=%s RETURNING connection_id",
                (uuid4().hex, source_connection),
            ).fetchone()
        )["connection_id"]
        connection.execute(
            "UPDATE core.tenant SET gds_connection_id=%s WHERE tenant_id=%s",
            (gds_connection, context.tenant_id),
        )
        connection.execute(
            "UPDATE core.connection SET has_foreign_catalog=TRUE,foreign_catalog='foreign_fixture' WHERE connection_id=%s",
            (source_connection,),
        )
        connection.execute(
            "UPDATE core.object SET fc_object_schema='fixture_schema',fc_object_name='fixture_table' WHERE object_id=%s",
            (source_object,),
        )
        source_attribute = require_row(
            connection.execute(
                "INSERT INTO core.attribute(object_id,attribute_name,fc_attribute_name,attribute_ordinal_position,attribute_data_type) VALUES (%s,'identifier','remote_identifier',1,'string') RETURNING attribute_id",
                (source_object,),
            ).fetchone()
        )["attribute_id"]
        environment = f"enrichment_{uuid4().hex}"
        environment_id = require_row(
            connection.execute(
                "INSERT INTO reference.environment(environment_code,environment_name) VALUES (%s,'Fixture environment') RETURNING environment_id",
                (environment,),
            ).fetchone()
        )["environment_id"]
        for parameter in ("databricks_host_name", "databricks_http_path"):
            connection.execute(
                "INSERT INTO reference.connection_parameter(connection_parameter_code,connection_parameter_name) SELECT %s,%s WHERE NOT EXISTS (SELECT 1 FROM reference.connection_parameter WHERE lower(connection_parameter_code)=%s)",
                (parameter, parameter, parameter),
            )
            parameter_id = require_row(
                connection.execute(
                    "SELECT connection_parameter_id FROM reference.connection_parameter WHERE lower(connection_parameter_code)=%s",
                    (parameter,),
                ).fetchone()
            )["connection_parameter_id"]
            connection.execute(
                "INSERT INTO core.connection_value(connection_id,environment_id,connection_parameter_id,connection_value) VALUES (%s,%s,%s,%s)",
                (gds_connection, environment_id, parameter_id, uuid4().hex),
            )
    run_id = _create(
        actor, context, correlation_id=uuid4(), selected_object_ids=[source_object]
    )["workflow_run_id"]
    with actor.database.connect_owner() as connection:
        connection.execute(
            "SELECT application.start_workflow_run(%s,%s,'user',%s,%s)",
            (
                context.entra_tenant_id,
                context.entra_object_id,
                run_id,
                context.model_revision,
            ),
        )
    snapshot = _load(actor, context, run_id)
    obj = snapshot["objects"][0]
    assert obj["connection_id"] == source_connection
    assert obj["relation"] == dict(
        connection_id=gds_connection,
        catalog="foreign_fixture",
        schema="fixture_schema",
        table="fixture_table",
    )
    assert obj["attributes"][0]["source"]["attribute_id"] == source_attribute
    assert obj["attributes"][0]["source"]["relation"]["connection_id"] == gds_connection
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        values = require_row(
            connection.execute(
                "SELECT * FROM application.get_metadata_enrichment_connection_values(%s,%s,'user',%s,%s,%s,%s)",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    context.model_revision,
                    gds_connection,
                    environment,
                ),
            ).fetchone()
        )
        assert values["failure_code"] == "connection_values_missing"
        assert all(
            values[key] is None
            for key in (
                "databricks_host_name",
                "databricks_http_path",
                "databricks_token",
            )
        )
        with pytest.raises(RaiseException, match="connection_denied"):
            connection.execute(
                "SELECT * FROM application.get_metadata_enrichment_connection_values(%s,%s,'user',%s,%s,%s,%s)",
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    run_id,
                    context.model_revision,
                    source_connection,
                    environment,
                ),
            )


def test_new_attribute_baseline_drift_completes_all_current_fields_changed(
    notebook_actor: NotebookActor,
) -> None:
    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    snapshot = _load(actor, context, run_id)
    fields = _full_results(
        actor, run_id, [_field(*attributes[0], "attribute_description", "Candidate.")]
    )
    with actor.database.connect_owner() as connection:
        connection.execute(
            "INSERT INTO core.attribute(object_id,attribute_name,attribute_ordinal_position,attribute_data_type) VALUES (%s,'new_registered',2,'string')",
            (attributes[0][0],),
        )
    result = _complete(
        actor, context, run_id, claim, snapshot["baseline_digest"], fields, full=False
    )
    assert result["counts"] == {"changed": len(fields) + 2}
    assert result["warning_count"] == len(fields) + 2
    assert (
        _complete(
            actor,
            context,
            run_id,
            claim,
            snapshot["baseline_digest"],
            fields,
            full=False,
        )
        == result
    )


def test_multiline_description_and_result_labels_hide_reowned_metadata(
    notebook_actor: NotebookActor,
) -> None:
    from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context

    actor = notebook_actor
    context, run_id, claim, attributes = _start(actor)
    snapshot = _load(actor, context, run_id)
    first = attributes[0]
    description = "First line.\n\tSecond line.\r\nThird line."
    _complete(
        actor,
        context,
        run_id,
        claim,
        snapshot["baseline_digest"],
        [_field(*first, "attribute_description", description)],
    )
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        page = require_row(
            connection.execute(
                READ_SQL,
                (context.entra_tenant_id, context.entra_object_id, run_id, 200, 0),
            ).fetchone()
        )["result"]
        result = next(
            row
            for row in page["results"]
            if row["attribute_id"] == first[1]
            and row["field_name"] == "attribute_description"
        )
        assert result["applied_value"] == description
        assert result["storage_type"] == "string"
        assert result["object_name"] and result["attribute_name"]
    foreign = seed_workflow_context(actor.database)
    with actor.database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET source_tenant_id=%s,object_name='New owner name' WHERE object_id=%s",
            (foreign.tenant_id, first[0]),
        )
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        page = require_row(
            connection.execute(
                READ_SQL,
                (context.entra_tenant_id, context.entra_object_id, run_id, 200, 0),
            ).fetchone()
        )["result"]
        for result in page["results"]:
            if result["object_id"] == first[0]:
                assert all(
                    result[key] is None
                    for key in (
                        "object_name",
                        "object_schema",
                        "attribute_name",
                        "storage_type",
                    )
                )
