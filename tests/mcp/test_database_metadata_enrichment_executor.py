"""Actual shared executor, governed PostgreSQL writes, and synthetic agent responses."""

# Reuse fixture-only setup; never connect to an existing database.
# pyright: reportPrivateUsage=false
import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata_enrichment.contracts import (
    EnrichmentDescriptionTarget,
)
from gds_workbench_api.features.metadata_enrichment.repository import (
    MetadataEnrichmentRepository,
)
from gds_workbench_api.features.metadata_enrichment.service import (
    DatabaseMetadataEnrichmentExecutor,
)
from gds_workbench_api.features.model_input_scope.service import (
    DatabaseModelInputScopeService,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
)
from gds_workbench_api.integrations.agents.composition import LocalFakeAgentAdapter
from pydantic import JsonValue

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
)
from tests.mcp.test_database_notebook_workflows import (
    NotebookActor,
)
from tests.mcp.test_database_notebook_workflows import (
    notebook_actor as notebook_actor,
)
from tests.mcp.test_database_profiling_persistence import _seed_attributes
from tests.mcp.test_database_workflow_run_lifecycle import (
    _claim_specific_workflow_run,
    seed_workflow_context,
)


@pytest.fixture(scope="module")
def enrichment_seeded_actor(notebook_actor: NotebookActor) -> NotebookActor:
    database = notebook_actor.database
    _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
    _seed_super_admin(database)
    _apply_sql(database, _render_seed())
    return notebook_actor


class DescriptionAgent(LocalFakeAgentAdapter):
    def __init__(self, behavior: str) -> None:
        super().__init__(sdk_code="langchain_create_agent")
        self.behavior = behavior
        self.calls = 0
        self.requested_keys: list[tuple[str, ...]] = []

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.calls += 1
        assert request.workflow == "metadata_enrichment"
        assert not request.allowed_tool_names
        properties = request.output_schema["properties"]
        assert isinstance(properties, dict)
        descriptions_schema = properties["descriptions"]
        assert isinstance(descriptions_schema, dict)
        refs = descriptions_schema["required"]
        assert isinstance(refs, list) and refs
        keys = [json.loads(str(ref)) for ref in refs]
        assert all(
            len(key) in {5, 6} and all(isinstance(part, str) for part in key)
            for key in keys
        )
        assert len({tuple(key[:5]) for key in keys}) == 1
        assert len({len(key) for key in keys}) == 1, (
            "Objects and Attributes are separate calls."
        )
        self.requested_keys.extend(tuple(key) for key in keys)
        assert isinstance(request.context, dict)
        frozen = request.context["original_context"]
        assert isinstance(frozen, dict)
        inputs = frozen["prompt_inputs"]
        assert isinstance(inputs, dict)
        assert set(inputs) == {
            "source_context",
            "gds_context",
            "object_context",
            "object_attribute_context",
            "ingestion_mapping",
        }
        if self.behavior == "regenerate_attributes":
            assert len(refs) == 31, (
                "The selected Attribute set is never split into batches."
            )
        if self.behavior == "regenerate_null":
            nulls: dict[str, JsonValue] = {str(ref): None for ref in refs}
            return AgentExecutionResult(
                candidate={"descriptions": nulls}, turn_count=1, tool_call_count=0
            )
        assert "sample_rows" not in json.dumps(request.context)
        assert all(
            "{{" not in part
            for part in (
                request.system_prompt,
                request.instruction_prompt,
                request.tool_instruction or "",
            )
        )
        if self.behavior == "invalid" or (
            self.behavior == "repair" and self.calls == 1
        ):
            return AgentExecutionResult(
                candidate="unusable provider response", turn_count=1, tool_call_count=0
            )
        return await super().execute(request)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "behavior",
    [
        "normal",
        "repair",
        "invalid",
        "locked",
        "regenerate_object",
        "regenerate_attribute",
        "regenerate_changed",
        "regenerate_objects",
        "regenerate_attributes",
        "regenerate_bulk_attributes",
        "regenerate_existing_type",
        "regenerate_null",
    ],
)
async def test_shared_executor_completes_physical_enrichment(
    enrichment_seeded_actor: NotebookActor,
    behavior: str,
) -> None:
    actor = enrichment_seeded_actor
    context = seed_workflow_context(actor.database)
    attributes = _seed_attributes(actor.database, context)
    first_object, first_attribute = attributes[0]
    regeneration = None
    regenerations = None
    before_objects: dict[int, dict[str, Any]] = {}
    before_attributes: dict[int, dict[str, Any]] = {}
    with actor.database.connect_owner() as connection:
        connection.execute(
            "UPDATE model.model SET default_agent_sdk_code='langchain_create_agent', "
            "default_agent_provider_code='databricks',"
            "default_agent_model_code='databricks-primary' "
            "WHERE model_id=%s",
            (context.model_id,),
        )
        connection.execute(
            "INSERT INTO reference.zone(zone_code,zone_name) "
            "SELECT 'source','Source' WHERE NOT EXISTS "
            "(SELECT 1 FROM reference.zone WHERE lower(btrim(zone_code))='source')"
        )
        connection.execute(
            "UPDATE core.object SET zone_id=(SELECT zone_id FROM reference.zone "
            "WHERE lower(btrim(zone_code))='source') WHERE object_id=%s",
            (first_object,),
        )
        connection.execute(
            "UPDATE core.attribute SET attribute_data_type='DECIMAL(12,2)' WHERE attribute_id=%s",
            (first_attribute,),
        )
        if behavior.startswith("regenerate_"):
            connection.execute(
                "UPDATE core.object SET object_description='Original Object description.' "
                "WHERE object_id=%s",
                (first_object,),
            )
            row = require_row(
                connection.execute(
                    "UPDATE core.attribute SET "
                    "attribute_description='Original Attribute description.' "
                    "WHERE attribute_id=%s RETURNING attribute_id",
                    (first_attribute,),
                ).fetchone()
            )
            if behavior == "regenerate_existing_type":
                connection.execute(
                    "UPDATE core.attribute SET attribute_inferred_data_type='BIGINT' "
                    "WHERE attribute_id=%s",
                    (first_attribute,),
                )
            revisions = require_row(
                connection.execute(
                    "SELECT application.metadata_object_review_revision(object) "
                    "AS object_revision, "
                    "application.metadata_attribute_review_revision(attribute,object) "
                    "AS attribute_revision "
                    "FROM core.attribute AS attribute JOIN core.object AS object USING(object_id) "
                    "WHERE attribute.attribute_id=%s",
                    (row["attribute_id"],),
                ).fetchone()
            )
            regeneration = EnrichmentDescriptionTarget(
                object_id=first_object,
                attribute_id=None
                if behavior == "regenerate_object"
                else first_attribute,
                expected_revision=revisions[
                    "object_revision"
                    if behavior == "regenerate_object"
                    else "attribute_revision"
                ],
            )
        if regeneration:
            regenerations = [regeneration]
        if behavior in {"regenerate_objects", "regenerate_attributes"}:
            if behavior == "regenerate_attributes":
                connection.execute(
                    "INSERT INTO core.attribute(object_id, attribute_name, "
                    "attribute_ordinal_position, attribute_data_type, attribute_nullability) "
                    "SELECT %s, 'value_' || number, number + 1, 'BIGINT', TRUE "
                    "FROM generate_series(1,30) AS number",
                    (first_object,),
                )
                selected = connection.execute(
                    "SELECT attribute.attribute_id, object.object_id, "
                    "application.metadata_attribute_review_revision(attribute,object) AS revision "
                    "FROM core.attribute AS attribute JOIN core.object AS object USING(object_id) "
                    "WHERE object.object_id=%s ORDER BY attribute.attribute_id",
                    (first_object,),
                ).fetchall()
            else:
                selected = connection.execute(
                    "SELECT object_id, NULL::BIGINT AS attribute_id, "
                    "application.metadata_object_review_revision(object) AS revision "
                    "FROM core.object AS object WHERE object_id=ANY(%s) ORDER BY object_id",
                    (list(context.selected_object_ids),),
                ).fetchall()
            regenerations = [
                EnrichmentDescriptionTarget(
                    object_id=row["object_id"],
                    attribute_id=row["attribute_id"],
                    expected_revision=row["revision"],
                )
                for row in selected
            ]
        if behavior == "regenerate_bulk_attributes":
            selected_objects = list(context.selected_object_ids[:2])
            assert len(selected_objects) == 2
            connection.execute(
                "UPDATE core.object SET object_description='Original Object description.' "
                "WHERE object_id=ANY(%s)",
                (list(context.selected_object_ids),),
            )
            connection.execute(
                "INSERT INTO core.attribute(object_id,attribute_name,attribute_ordinal_position,"
                "attribute_data_type,attribute_description,is_locked,is_active) "
                "SELECT object_id, name, ordinal, 'BIGINT', "
                "'Preserve unless selected.', locked, active "
                "FROM unnest(%s::BIGINT[]) AS objects(object_id) CROSS JOIN (VALUES "
                "('bulk_selected',2,FALSE,TRUE), ('bulk_excluded',3,FALSE,TRUE), "
                "('bulk_locked',4,TRUE,TRUE), ('bulk_inactive',5,FALSE,FALSE)"
                ") AS attributes(name,ordinal,locked,active)",
                (selected_objects,),
            )
            connection.execute(
                "UPDATE core.attribute SET "
                "attribute_description='Original Attribute description.', "
                "attribute_data_type=CASE WHEN attribute_id=%s "
                "THEN 'DECIMAL(12,2)' ELSE 'BIGINT' END "
                "WHERE object_id=ANY(%s)",
                (first_attribute, list(context.selected_object_ids)),
            )
            selected = connection.execute(
                "SELECT attribute.attribute_id,object.object_id, "
                "application.metadata_attribute_review_revision(attribute,object) AS revision "
                "FROM core.attribute AS attribute JOIN core.object AS object USING(object_id) "
                "WHERE object.object_id=ANY(%s) AND attribute.is_active "
                "AND NOT attribute.is_locked AND attribute.attribute_name <> 'bulk_excluded' "
                "ORDER BY object.object_id,attribute.attribute_id",
                (selected_objects,),
            ).fetchall()
            regenerations = [
                EnrichmentDescriptionTarget(
                    object_id=row["object_id"],
                    attribute_id=row["attribute_id"],
                    expected_revision=row["revision"],
                )
                for row in selected
            ]
            before_objects = {
                row["object_id"]: row["record"]
                for row in connection.execute(
                    "SELECT object_id,to_jsonb(object) AS record FROM core.object AS object "
                    "WHERE object_id=ANY(%s)",
                    (list(context.selected_object_ids),),
                ).fetchall()
            }
            before_attributes = {
                row["attribute_id"]: row["record"]
                for row in connection.execute(
                    "SELECT attribute_id,to_jsonb(attribute) AS record "
                    "FROM core.attribute AS attribute "
                    "WHERE object_id=ANY(%s)",
                    (list(context.selected_object_ids),),
                ).fetchall()
            }
        if behavior == "locked":
            connection.execute(
                "UPDATE core.object SET is_locked=TRUE WHERE object_id=ANY(%s)",
                (list(context.selected_object_ids),),
            )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=actor.database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    agent = DescriptionAgent(behavior)
    try:
        if behavior == "regenerate_bulk_attributes":
            scope = DatabaseModelInputScopeService(
                database=database,
                authorizer=AuthorizationService(),
                cursor_signing_key=b"fixture-only-cursor-signing-key-32",
            )
            detail = await scope.read_input_scope_object(
                principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id,
                object_id=first_object,
            )
            assert detail.total_attribute_count == 5
            assert detail.attribute_count == len(detail.attributes) == 4
        created = await DatabaseWorkflowCommandService(
            database=database,
            authorizer=AuthorizationService(),
            agent_capability_registry=load_default_agent_capabilities(),
        ).create_run(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            correlation_id=uuid4(),
            command=CreateWorkflowRunRequest(
                expected_model_revision=context.model_revision,
                model_workflow="metadata_enrichment",
                workflow_execution_mode="one_shot",
                selected_object_ids=sorted(
                    {target.object_id for target in regenerations}
                )
                if regenerations
                else list(context.selected_object_ids),
                description_targets=regenerations,
            ),
        )
        run_id = created.workflow_run_id
        if behavior == "regenerate_changed":
            with actor.database.connect_owner() as connection:
                connection.execute(
                    "UPDATE core.attribute SET attribute_description='Concurrent edit.' "
                    "WHERE attribute_id=%s",
                    (first_attribute,),
                )
        lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
        service = DatabaseMetadataEnrichmentExecutor(
            repository=MetadataEnrichmentRepository(database, environment_code="test"),
            agent_executor=agent,
            lifecycle=lifecycle,
        )
        await service.start(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=run_id,
            expected_model_revision=context.model_revision,
        )
        claim = UUID(
            str(
                _claim_specific_workflow_run(actor.database, run_id)[
                    "workflow_run_claim_token"
                ]
            )
        )
        result = await service.execute_started(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=run_id,
            expected_model_revision=context.model_revision,
            workflow_run_claim_token=claim,
        )
    finally:
        await database.close()
    assert result.workflow_run_id == run_id
    assert result.workflow_run_state == (
        "completed_with_repair" if behavior == "repair" else "completed"
    )
    assert result.model_revision == context.model_revision
    with actor.database.connect_owner() as connection:
        attribute = require_row(
            connection.execute(
                "SELECT attribute_data_type,attribute_inferred_data_type,attribute_description "
                "FROM core.attribute WHERE attribute_id=%s",
                (first_attribute,),
            ).fetchone()
        )
        outcomes = connection.execute(
            "SELECT object_id,attribute_id,field_name,status,applied_value,evidence_method FROM "
            "application.metadata_enrichment_result WHERE workflow_run_id=%s",
            (run_id,),
        ).fetchall()
        state = require_row(
            connection.execute(
                "SELECT workflow_run_state,failure_code FROM application.workflow_run "
                "WHERE workflow_run_id=%s",
                (run_id,),
            ).fetchone()
        )
        if behavior == "regenerate_bulk_attributes":
            after_objects = {
                row["object_id"]: row["record"]
                for row in connection.execute(
                    "SELECT object_id,to_jsonb(object) AS record FROM core.object AS object "
                    "WHERE object_id=ANY(%s)",
                    (list(context.selected_object_ids),),
                ).fetchall()
            }
            after_attributes = {
                row["attribute_id"]: row["record"]
                for row in connection.execute(
                    "SELECT attribute_id,to_jsonb(attribute) AS record "
                    "FROM core.attribute AS attribute "
                    "WHERE object_id=ANY(%s)",
                    (list(context.selected_object_ids),),
                ).fetchall()
            }
            assert after_objects == before_objects
            selected_ids = {target.attribute_id for target in regenerations or ()}
            descriptions = [
                row for row in outcomes if row["field_name"] == "attribute_description"
            ]
            assert len(descriptions) == len(selected_ids) == 4
            assert {row["attribute_id"] for row in descriptions} == selected_ids
            assert all(row["status"] == "applied" for row in descriptions)
            assert not any(
                row["field_name"] == "object_description" for row in outcomes
            )
            assert len(agent.requested_keys) == 4
            assert all(len(key) == 6 for key in agent.requested_keys)
            assert len({key[:5] for key in agent.requested_keys}) == 2
            for attribute_id, before in before_attributes.items():
                after = after_attributes[attribute_id]
                if attribute_id not in selected_ids:
                    assert after == before
                else:
                    assert (
                        after["attribute_description"]
                        != before["attribute_description"]
                    )
                    permitted = {
                        "attribute_description",
                        "attribute_inferred_data_type",
                        "updated_time",
                        "updated_by",
                    }
                    assert {
                        key: value
                        for key, value in before.items()
                        if key not in permitted
                    } == {
                        key: value
                        for key, value in after.items()
                        if key not in permitted
                    }
    assert len(outcomes) == (
        sum(1 if target.attribute_id is None else 2 for target in regenerations)
        if regenerations
        else len(context.selected_object_ids) + 2 * len(attributes)
    )
    assert state["failure_code"] is None
    assert attribute["attribute_data_type"] == "DECIMAL(12,2)"
    if regeneration:
        assert attribute["attribute_inferred_data_type"] == (
            None
            if behavior
            in {"regenerate_object", "regenerate_objects", "regenerate_changed"}
            else "BIGINT"
            if behavior == "regenerate_existing_type"
            else "DECIMAL(12,2)"
        )
        assert result.counts == (
            {"changed": len(outcomes)}
            if behavior == "regenerate_changed"
            else {"applied": 1, "existing": 1}
            if behavior == "regenerate_existing_type"
            else {"applied": 6, "inconclusive": 2}
            if behavior == "regenerate_bulk_attributes"
            else {"applied": len(outcomes)}
        )
        assert agent.calls == (
            0
            if behavior == "regenerate_changed"
            else len({target.object_id for target in regenerations or ()})
        )
        if behavior in {"regenerate_object", "regenerate_objects"}:
            assert (
                attribute["attribute_description"] == "Original Attribute description."
            )
        elif behavior == "regenerate_changed":
            assert attribute["attribute_description"] == "Concurrent edit."
        else:
            assert (
                attribute["attribute_description"] != "Original Attribute description."
            )
        if behavior == "regenerate_null":
            assert attribute["attribute_description"] is None
    elif behavior == "locked":
        assert agent.calls == 0
        assert result.counts == {"locked": len(outcomes)}
        assert attribute["attribute_inferred_data_type"] is None
        assert attribute["attribute_description"] is None
    else:
        assert attribute["attribute_inferred_data_type"] == "DECIMAL(12,2)"
        if behavior == "invalid":
            assert attribute["attribute_description"] is None
            assert result.counts["unavailable"] > 0
            assert "unusable provider response" not in json.dumps(outcomes)
        else:
            assert attribute["attribute_description"] is not None
            assert result.counts["applied"] > 1
