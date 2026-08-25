from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from psycopg import Connection
from psycopg.types.json import Jsonb

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.code_generation.candidate import GeneratedSqlArtifact
from gds_workbench_api.features.code_generation.context import (
    PostgresCodeGenerationContextRepository,
)
from gds_workbench_api.features.code_generation.storage import (
    DatabaseGeneratedSqlStorage,
    GeneratedSqlStorageError,
    SqlGeneratorIdentity,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...

    def web_runtime_dsn(self) -> str: ...


@dataclass(frozen=True, slots=True)
class SeededCodeGeneration:
    tenant_id: int
    model_id: int
    model_revision: int
    principal: RequestPrincipal
    principal_id: int
    object_ids: tuple[int, ...]
    workflow_run_id: int
    correlation_id: UUID
    guide_id: int
    guide_version_id: int
    guide_digest: str
    stage: FrozenAgentStage
    workflow_run_claim_token: UUID = field(repr=False)

    def plan(self) -> AgentRunPlan:
        return AgentRunPlan(
            workflow_run_id=self.workflow_run_id,
            model_id=self.model_id,
            correlation_id=self.correlation_id,
            model_revision=self.model_revision,
            model_workflow="code_generation",
            workflow_execution_mode=None,
            modeled_entity_type="logical_entity",
            code_generation_coverage_mode="selected_targets",
            sql_generation_guide_id=self.guide_id,
            sql_generation_guide_version_id=self.guide_version_id,
            sql_generation_guide_digest=self.guide_digest,
            selected_scope_digest=_selection_digest(self.object_ids),
            selected_object_ids=self.object_ids,
            selection=AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="test-model",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=1,
            ),
            stages=(self.stage,),
        )


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    value = None if row is None else row.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID {field}")
    return value


def _required_str(row: Mapping[str, object] | None, field: str) -> str:
    value = None if row is None else row.get(field)
    if not isinstance(value, str) or not value:
        raise AssertionError(f"expected database text field {field}")
    return value


def _selection_digest(object_ids: tuple[int, ...]) -> str:
    return hashlib.sha256(
        ",".join(str(value) for value in object_ids).encode()
    ).hexdigest()


def _ensure_default_guide(
    connection: Connection[dict[str, object]],
    *,
    principal_id: int,
    suffix: str,
) -> int:
    existing = connection.execute(
        """
        SELECT version.sql_generation_guide_version_id
          FROM application.sql_generation_guide AS guide
          JOIN application.sql_generation_guide_version AS version
            ON version.sql_generation_guide_id = guide.sql_generation_guide_id
           AND version.sql_generation_guide_version_status = 'published'
         WHERE guide.is_default
           AND guide.is_active
         ORDER BY version.sql_generation_guide_version_number DESC
         LIMIT 1
        """
    ).fetchone()
    if existing is not None:
        return _required_id(existing, "sql_generation_guide_version_id")

    content = "Generate one bounded Databricks SQL file for each selected target."
    guide_id = _required_id(
        connection.execute(
            """
            INSERT INTO application.sql_generation_guide (
                sql_generation_guide_code,
                sql_generation_guide_name,
                is_default,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, %s, TRUE, %s, %s)
            RETURNING sql_generation_guide_id
            """,
            (
                f"codegen_guide_{suffix}",
                f"Code Generation Guide {suffix}",
                principal_id,
                principal_id,
            ),
        ).fetchone(),
        "sql_generation_guide_id",
    )
    version_id = _required_id(
        connection.execute(
            """
            INSERT INTO application.sql_generation_guide_version (
                sql_generation_guide_id,
                sql_generation_guide_version_number,
                sql_generation_guide_content,
                sql_generation_guide_digest,
                created_by_principal_id,
                updated_by_principal_id
            ) VALUES (%s, 1, %s, %s, %s, %s)
            RETURNING sql_generation_guide_version_id
            """,
            (
                guide_id,
                content,
                hashlib.sha256(content.encode()).hexdigest(),
                principal_id,
                principal_id,
            ),
        ).fetchone(),
        "sql_generation_guide_version_id",
    )
    connection.execute(
        """
        UPDATE application.sql_generation_guide_version
           SET sql_generation_guide_version_status = 'published',
               published_time = CURRENT_TIMESTAMP,
               published_by_principal_id = %s,
               updated_by_principal_id = %s,
               updated_time = CURRENT_TIMESTAMP
         WHERE sql_generation_guide_version_id = %s
        """,
        (principal_id, principal_id, version_id),
    )
    return version_id


def _seed_code_generation(
    database: DisposablePostgresFixture,
    *,
    mappings_per_target: tuple[int, ...],
    seed_prior_artifact: bool = False,
) -> SeededCodeGeneration:
    suffix = uuid4().hex[:12]
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with database.connect_owner() as connection:
        system_type_id = _required_id(
            connection.execute(
                """
                INSERT INTO reference.system_type (system_type_code, system_type_name)
                VALUES (%s, %s)
                RETURNING system_type_id
                """,
                (f"codegen_system_{suffix}", f"Code Generation System {suffix}"),
            ).fetchone(),
            "system_type_id",
        )
        connection_type_id = _required_id(
            connection.execute(
                """
                INSERT INTO reference.connection_type (
                    connection_type_code,
                    connection_type_name
                ) VALUES (%s, %s)
                RETURNING connection_type_id
                """,
                (
                    f"codegen_connection_{suffix}",
                    f"Code Generation Connection {suffix}",
                ),
            ).fetchone(),
            "connection_type_id",
        )
        object_type_id = _required_id(
            connection.execute(
                """
                INSERT INTO reference.object_type (object_type_code, object_type_name)
                VALUES (%s, %s)
                RETURNING object_type_id
                """,
                (f"codegen_table_{suffix}", f"Code Generation Table {suffix}"),
            ).fetchone(),
            "object_type_id",
        )
        silver_zone = connection.execute(
            """
            SELECT zone_id
              FROM reference.zone
             WHERE lower(btrim(zone_code)) = 'silver'
               AND is_active
            """
        ).fetchone()
        if silver_zone is None:
            silver_zone = connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                VALUES ('silver', 'Silver')
                RETURNING zone_id
                """
            ).fetchone()
        silver_zone_id = _required_id(silver_zone, "zone_id")
        project_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"codegen_{suffix}", f"Code Generation Project {suffix}"),
            ).fetchone(),
            "project_id",
        )
        tenant_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    f"CODEGEN_{suffix}",
                    f"Code Generation Tenant {suffix}",
                    f"codegen_catalog_{suffix}",
                    f"codegen_admin_{suffix}",
                ),
            ).fetchone(),
            "tenant_id",
        )
        principal_id = _required_id(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email
                ) VALUES ('user', %s, %s)
                RETURNING principal_id
                """,
                (
                    f"Code Generation Architect {suffix}",
                    f"codegen_{suffix}@example.test",
                ),
            ).fetchone(),
            "principal_id",
        )
        identity_id = _required_id(
            connection.execute(
                """
                INSERT INTO security.entra_principal_identity (
                    principal_id,
                    principal_type,
                    entra_tenant_id,
                    entra_object_id
                ) VALUES (%s, 'user', %s, %s)
                RETURNING entra_principal_identity_id
                """,
                (principal_id, entra_tenant_id, entra_object_id),
            ).fetchone(),
            "entra_principal_identity_id",
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id,
                locked_by_principal_id,
                tenant_lock_purpose,
                tenant_lock_expires_time
            ) VALUES (
                %s,
                %s,
                'Code Generation database test',
                CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            )
            """,
            (tenant_id, principal_id),
        )
        system_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.system (system_code, system_name, system_type_id)
                VALUES (%s, %s, %s)
                RETURNING system_id
                """,
                (
                    f"CODEGEN_{suffix}",
                    f"Code Generation System {suffix}",
                    system_type_id,
                ),
            ).fetchone(),
            "system_id",
        )
        connection_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.connection (
                    tenant_id,
                    system_id,
                    connection_code,
                    connection_name,
                    connection_type_id
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING connection_id
                """,
                (
                    tenant_id,
                    system_id,
                    f"codegen_{suffix}",
                    f"Code Generation Connection {suffix}",
                    connection_type_id,
                ),
            ).fetchone(),
            "connection_id",
        )
        model_row = connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id, model_revision
            """,
            (tenant_id, f"Code Generation Model {suffix}"),
        ).fetchone()
        model_id = _required_id(model_row, "model_id")
        model_revision = _required_id(model_row, "model_revision")
        source_system_ids = [system_id]
        for source_number in range(2, max(mappings_per_target) + 1):
            source_system_ids.append(
                _required_id(
                    connection.execute(
                        """
                        INSERT INTO core.system (
                            system_code,
                            system_name,
                            system_type_id
                        ) VALUES (%s, %s, %s)
                        RETURNING system_id
                        """,
                        (
                            f"CODEGEN_SOURCE_{source_number}_{suffix}",
                            f"Code Generation Source {source_number} {suffix}",
                            system_type_id,
                        ),
                    ).fetchone(),
                    "system_id",
                )
            )
        for dependency_order, source_system_id in enumerate(source_system_ids, start=1):
            connection.execute(
                """
                INSERT INTO workflow.mapping_source_system_dependency (
                    model_id,
                    modeled_entity_type,
                    source_system_id,
                    source_system_dependency_order
                ) VALUES (%s, 'logical_entity', %s, %s)
                """,
                (model_id, source_system_id, dependency_order),
            )

        object_ids: list[int] = []
        for target_number, mapping_count in enumerate(mappings_per_target, start=1):
            object_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO core.object (
                        connection_id,
                        object_schema,
                        object_name,
                        object_type_id,
                        zone_id
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING object_id
                    """,
                    (
                        connection_id,
                        f"silver_{suffix}",
                        f"target_{target_number}_{suffix}",
                        object_type_id,
                        silver_zone_id,
                    ),
                ).fetchone(),
                "object_id",
            )
            connection.execute(
                "INSERT INTO model.model_scope (model_id, object_id) VALUES (%s, %s)",
                (model_id, object_id),
            )
            object_ids.append(object_id)
            mapping_digest = hashlib.sha256(
                f"mapping-package-{suffix}-{target_number}".encode()
            ).hexdigest()
            for entity_number in range(1, mapping_count + 1):
                logical_entity_id = _required_id(
                    connection.execute(
                        """
                        INSERT INTO workflow.logical_entity (
                            model_id,
                            logical_entity_name,
                            logical_entity_definition,
                            logical_entity_type,
                            logical_entity_grain
                        ) VALUES (%s, %s, %s, 'core', %s)
                        RETURNING logical_entity_id
                        """,
                        (
                            model_id,
                            f"entity_{target_number}_{entity_number}_{suffix}",
                            f"Entity {entity_number} contributing to target {target_number}.",
                            f"One entity {target_number}.{entity_number} row.",
                        ),
                    ).fetchone(),
                    "logical_entity_id",
                )
                connection.execute(
                    """
                    INSERT INTO workflow.mapping_object (
                        model_id,
                        object_id,
                        source_system_id,
                        modeled_entity_type,
                        logical_entity_id,
                        object_dependency_order,
                        artifact_type,
                        artifact_generation_instructions,
                        mapping_profile_key,
                        mapping_profile_version,
                        mapping_profile_schema_digest,
                        mapping_package_document,
                        mapping_package_digest,
                        object_mapping_transformation_document
                    ) VALUES (
                        %s, %s, %s, 'logical_entity', %s, %s,
                        'sql_file', %s, 'free_form', '1.0.0', %s, %s, %s, %s
                    )
                    """,
                    (
                        model_id,
                        object_id,
                        source_system_ids[entity_number - 1],
                        logical_entity_id,
                        entity_number,
                        "Generate the selected target SQL file.",
                        "d" * 64,
                        Jsonb(
                            {
                                "schema_version": "1.0",
                                "package": f"target_{target_number}",
                            }
                        ),
                        mapping_digest,
                        Jsonb(
                            {
                                "schema_version": "1.0",
                                "transformation_kind": "direct",
                                "entity": entity_number,
                            }
                        ),
                    ),
                )

        guide_version_id = _ensure_default_guide(
            connection,
            principal_id=principal_id,
            suffix=suffix,
        )
        guide_snapshot = connection.execute(
            """
            SELECT sql_generation_guide_id,
                   sql_generation_guide_digest
              FROM application.sql_generation_guide_version
             WHERE sql_generation_guide_version_id = %s
            """,
            (guide_version_id,),
        ).fetchone()
        guide_id = _required_id(guide_snapshot, "sql_generation_guide_id")
        guide_digest = _required_str(
            guide_snapshot,
            "sql_generation_guide_digest",
        )

        stage_row = connection.execute(
            """
            SELECT workflow_stage_id,
                   workflow_stage_code,
                   workflow_stage_order
              FROM application.workflow_stage
             WHERE model_workflow = 'code_generation'
               AND workflow_execution_mode IS NULL
               AND workflow_stage_is_agentic
               AND is_active
             ORDER BY workflow_stage_order, workflow_stage_id
             LIMIT 1
            """
        ).fetchone()
        if stage_row is None:
            stage_row = connection.execute(
                """
                INSERT INTO application.workflow_stage (
                    model_workflow,
                    workflow_execution_mode,
                    workflow_stage_code,
                    workflow_stage_name,
                    workflow_stage_order,
                    workflow_stage_is_agentic
                ) VALUES (
                    'code_generation', NULL, 'sql_generation',
                    'SQL Generation', 10, TRUE
                )
                RETURNING workflow_stage_id,
                          workflow_stage_code,
                          workflow_stage_order
                """
            ).fetchone()
        workflow_stage_id = _required_id(stage_row, "workflow_stage_id")
        stage_code = _required_str(stage_row, "workflow_stage_code")
        stage_order = _required_id(stage_row, "workflow_stage_order")
        system_prompt = "Generate SQL only."
        instruction_prompt = "Generate every selected target exactly once."
        prompt_digest = _required_str(
            connection.execute(
                """
                SELECT encode(
                           sha256(
                               convert_to(
                                   jsonb_build_object(
                                       'system_prompt_template', %s::TEXT,
                                       'instruction_prompt_template', %s::TEXT,
                                       'tool_instruction_prompt_template', NULL::TEXT
                                   )::TEXT,
                                   'UTF8'
                               )
                           ),
                           'hex'
                       ) AS prompt_digest
                """,
                (system_prompt, instruction_prompt),
            ).fetchone(),
            "prompt_digest",
        )
        prompt_template_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.prompt_template (
                    workflow_stage_id,
                    prompt_template_ownership_scope,
                    owner_tenant_id,
                    prompt_template_code,
                    prompt_template_name,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (%s, 'tenant', %s, %s, %s, %s, %s)
                RETURNING prompt_template_id
                """,
                (
                    workflow_stage_id,
                    tenant_id,
                    f"sql_generation_{suffix}",
                    f"SQL Generation Prompt {suffix}",
                    principal_id,
                    principal_id,
                ),
            ).fetchone(),
            "prompt_template_id",
        )
        prompt_version_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.prompt_template_version (
                    prompt_template_id,
                    workflow_stage_id,
                    prompt_template_version_number,
                    system_prompt_template,
                    instruction_prompt_template,
                    prompt_template_digest,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (%s, %s, 1, %s, %s, %s, %s, %s)
                RETURNING prompt_template_version_id
                """,
                (
                    prompt_template_id,
                    workflow_stage_id,
                    system_prompt,
                    instruction_prompt,
                    prompt_digest,
                    principal_id,
                    principal_id,
                ),
            ).fetchone(),
            "prompt_template_version_id",
        )
        connection.execute(
            """
            UPDATE application.prompt_template_version
               SET prompt_template_version_status = 'published',
                   published_time = CURRENT_TIMESTAMP,
                   published_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE prompt_template_version_id = %s
            """,
            (principal_id, principal_id, prompt_version_id),
        )

        selected_object_ids = tuple(object_ids)
        correlation_id = uuid4()
        workflow_run_claim_token = uuid4()
        workflow_run_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.workflow_run (
                    model_id,
                    model_revision,
                    model_workflow,
                    actor_principal_id,
                    actor_entra_principal_identity_id,
                    agent_sdk_code,
                    agent_provider_code,
                    agent_model_code,
                    reasoning_effort_code,
                    max_turns,
                    validation_retry_count,
                    modeled_entity_type,
                    code_generation_coverage_mode,
                    sql_generation_guide_id,
                    sql_generation_guide_version_id,
                    sql_generation_guide_digest,
                    selected_scope_digest,
                    selected_scope_count,
                    workflow_run_state,
                    correlation_id,
                    started_time,
                    workflow_run_claim_token_digest,
                    workflow_run_claimed_time,
                    workflow_run_claim_heartbeat_time,
                    workflow_run_claim_expires_time
                ) VALUES (
                    %s, %s, 'code_generation', %s, %s, 'openai_agents_sdk',
                    'microsoft_foundry', 'test-model', 'medium', 8, 1,
                    'logical_entity', 'selected_targets', %s, %s, %s,
                    %s, %s, 'running', %s, CURRENT_TIMESTAMP,
                    %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP + INTERVAL '30 minutes'
                )
                RETURNING workflow_run_id
                """,
                (
                    model_id,
                    model_revision,
                    principal_id,
                    identity_id,
                    guide_id,
                    guide_version_id,
                    guide_digest,
                    _selection_digest(selected_object_ids),
                    len(selected_object_ids),
                    correlation_id,
                    hashlib.sha256(str(workflow_run_claim_token).encode()).hexdigest(),
                ),
            ).fetchone(),
            "workflow_run_id",
        )
        for selection_order, object_id in enumerate(selected_object_ids, start=1):
            connection.execute(
                """
                INSERT INTO application.workflow_run_object_selection (
                    workflow_run_id,
                    model_id,
                    object_id,
                    selection_order
                ) VALUES (%s, %s, %s, %s)
                """,
                (workflow_run_id, model_id, object_id, selection_order),
            )
        connection.execute(
            """
            INSERT INTO application.workflow_run_prompt_snapshot (
                workflow_run_id,
                model_id,
                workflow_stage_id,
                prompt_template_version_id,
                prompt_resolution_source,
                prompt_template_digest
            ) VALUES (%s, %s, %s, %s, 'run_override', %s)
            """,
            (
                workflow_run_id,
                model_id,
                workflow_stage_id,
                prompt_version_id,
                prompt_digest,
            ),
        )

        if seed_prior_artifact:
            prior_sql = "SELECT 'prior' AS artifact_version;\n"
            prior_context = connection.execute(
                """
                SELECT mapping_context_digest,
                       source_context_digest
                  FROM workflow.list_code_generation_target_context(
                           %s,
                           'logical_entity'
                       )
                 WHERE object_id = %s
                """,
                (model_id, object_ids[0]),
            ).fetchone()
            prior_mapping_digest = _required_str(
                prior_context,
                "mapping_context_digest",
            )
            prior_source_digest = _required_str(
                prior_context,
                "source_context_digest",
            )
            connection.execute(
                """
                SELECT *
                  FROM application.store_generated_sql_artifact(
                      %s::UUID, %s::UUID, 'user'::VARCHAR,
                      %s::BIGINT, %s::BIGINT, 'logical_entity'::VARCHAR,
                      %s::BIGINT, %s::CHAR(64), %s::CHAR(64),
                      %s::BIGINT, NULL::BIGINT, 'gds.web.sql'::VARCHAR,
                      '0.9.0'::VARCHAR, %s::TEXT, %s::CHAR(64)
                  )
                """,
                (
                    entra_tenant_id,
                    entra_object_id,
                    model_id,
                    model_revision,
                    object_ids[0],
                    prior_mapping_digest,
                    prior_source_digest,
                    guide_version_id,
                    prior_sql,
                    hashlib.sha256(prior_sql.encode()).hexdigest(),
                ),
            ).fetchone()

    stage = FrozenAgentStage(
        workflow_stage_id=workflow_stage_id,
        stage_code=stage_code,
        stage_order=stage_order,
        prompt_template_version_id=prompt_version_id,
        prompt_template_digest=prompt_digest,
        templates=PromptComponentTemplates(
            system=system_prompt,
            instruction=instruction_prompt,
        ),
        variables=(),
    )
    return SeededCodeGeneration(
        tenant_id=tenant_id,
        model_id=model_id,
        model_revision=model_revision,
        principal=RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
        ),
        principal_id=principal_id,
        object_ids=tuple(object_ids),
        workflow_run_id=workflow_run_id,
        correlation_id=correlation_id,
        guide_id=guide_id,
        guide_version_id=guide_version_id,
        guide_digest=guide_digest,
        stage=stage,
        workflow_run_claim_token=workflow_run_claim_token,
    )


@pytest.mark.asyncio
async def test_shared_mapping_package_generates_and_stores_one_atomic_sql_artifact(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    seeded = _seed_code_generation(
        web_postgres_database,
        mappings_per_target=(2,),
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    storage = DatabaseGeneratedSqlStorage(
        database=database,
        generator=SqlGeneratorIdentity(code="gds.web.sql", version="1.0.0"),
    )
    generated_sql = "SELECT customer_id\nFROM silver.customer;\n"

    await database.open()
    try:
        async with database.read_transaction() as transaction:
            context = await PostgresCodeGenerationContextRepository().load(
                transaction,
                tenant_id=seeded.tenant_id,
                plan=seeded.plan(),
            )
        agent_context = context.agent_context
        assert isinstance(agent_context, dict)
        targets = agent_context.get("targets")
        assert isinstance(targets, list) and len(targets) == 1
        target_context = targets[0]
        assert isinstance(target_context, dict)
        source_context = target_context.get("context")
        assert isinstance(source_context, dict)
        source_systems = source_context.get("source_systems")
        assert isinstance(source_systems, list) and len(source_systems) == 2
        dependency_orders: list[object] = []
        for source_system in source_systems:
            assert isinstance(source_system, dict)
            dependency_orders.append(source_system.get("dependency_order"))
        assert dependency_orders == [1, 2]
        object_mappings = source_context.get("object_mappings")
        assert isinstance(object_mappings, list) and len(object_mappings) == 2

        result = await storage.store(
            seeded.principal,
            model_id=seeded.model_id,
            modeled_entity_type="logical_entity",
            workflow_run_id=seeded.workflow_run_id,
            expected_model_revision=seeded.model_revision,
            workflow_run_claim_token=seeded.workflow_run_claim_token,
            artifacts=(
                GeneratedSqlArtifact(
                    target_ref=context.targets[0].target_ref,
                    object_id=context.targets[0].object_id,
                    generated_sql=generated_sql,
                ),
            ),
            contexts=context.targets,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        artifact = connection.execute(
            """
            SELECT generated_sql,
                   generated_sql_digest,
                   workflow_run_id,
                   mapping_context_digest,
                   source_context_digest
             FROM application.generated_sql_artifact
             WHERE model_id = %s
               AND object_id = %s
            """,
            (seeded.model_id, seeded.object_ids[0]),
        ).fetchone()
        run = connection.execute(
            """
            SELECT workflow_run_state, completed_time
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
            (seeded.workflow_run_id,),
        ).fetchone()

    assert result.workflow_run_state == "completed"
    assert result.artifact_count == 1
    assert artifact == {
        "generated_sql": generated_sql,
        "generated_sql_digest": hashlib.sha256(generated_sql.encode()).hexdigest(),
        "workflow_run_id": seeded.workflow_run_id,
        "mapping_context_digest": context.targets[0].mapping_context_digest,
        "source_context_digest": context.targets[0].source_context_digest,
    }
    assert run is not None and run["workflow_run_state"] == "completed"
    assert run["completed_time"] is not None


@pytest.mark.asyncio
async def test_generated_sql_storage_rejects_a_stale_claim_without_writes(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    seeded = _seed_code_generation(
        web_postgres_database,
        mappings_per_target=(1,),
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    storage = DatabaseGeneratedSqlStorage(
        database=database,
        generator=SqlGeneratorIdentity(code="gds.web.sql", version="1.0.0"),
    )
    stale_claim_token = uuid4()

    await database.open()
    try:
        async with database.read_transaction() as transaction:
            context = await PostgresCodeGenerationContextRepository().load(
                transaction,
                tenant_id=seeded.tenant_id,
                plan=seeded.plan(),
            )
        with pytest.raises(GeneratedSqlStorageError) as raised:
            await storage.store(
                seeded.principal,
                model_id=seeded.model_id,
                modeled_entity_type="logical_entity",
                workflow_run_id=seeded.workflow_run_id,
                expected_model_revision=seeded.model_revision,
                workflow_run_claim_token=stale_claim_token,
                artifacts=(
                    GeneratedSqlArtifact(
                        target_ref=context.targets[0].target_ref,
                        object_id=context.targets[0].object_id,
                        generated_sql="SELECT 1;",
                    ),
                ),
                contexts=context.targets,
            )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        artifact_count = connection.execute(
            """
            SELECT count(*) AS artifact_count
              FROM application.generated_sql_artifact
             WHERE model_id = %s
            """,
            (seeded.model_id,),
        ).fetchone()
        run = connection.execute(
            """
            SELECT workflow_run_state,
                   completed_time,
                   workflow_run_claim_token_digest
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
            (seeded.workflow_run_id,),
        ).fetchone()

    assert artifact_count == {"artifact_count": 0}
    assert run == {
        "workflow_run_state": "running",
        "completed_time": None,
        "workflow_run_claim_token_digest": hashlib.sha256(
            str(seeded.workflow_run_claim_token).encode()
        ).hexdigest(),
    }
    assert str(seeded.workflow_run_claim_token) not in str(raised.value)
    assert str(seeded.workflow_run_claim_token) not in repr(raised.value)
    assert str(stale_claim_token) not in str(raised.value)
    assert str(stale_claim_token) not in repr(raised.value)


@pytest.mark.asyncio
async def test_generated_sql_storage_rolls_back_an_earlier_upsert_on_late_failure(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    seeded = _seed_code_generation(
        web_postgres_database,
        mappings_per_target=(1, 1),
        seed_prior_artifact=True,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    storage = DatabaseGeneratedSqlStorage(
        database=database,
        generator=SqlGeneratorIdentity(code="gds.web.sql", version="1.0.0"),
    )
    replacement_sql = "SELECT 'replacement' AS artifact_version;\n"
    second_sql = "SELECT 'second' AS artifact_version;\n"

    await database.open()
    try:
        async with database.read_transaction() as transaction:
            context = await PostgresCodeGenerationContextRepository().load(
                transaction,
                tenant_id=seeded.tenant_id,
                plan=seeded.plan(),
            )
        assert len(context.targets) == 2
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET object_mapping_transformation_document =
                       jsonb_build_object(
                           'schema_version', '1.0',
                           'transformation_kind', 'derived',
                           'drift_version', 2
                       ),
                       updated_time = CURRENT_TIMESTAMP,
                       updated_by = CURRENT_USER
                 WHERE model_id = %s
                   AND object_id = %s
                   AND modeled_entity_type = 'logical_entity'
                """,
                (seeded.model_id, seeded.object_ids[1]),
            )

        with pytest.raises(GeneratedSqlStorageError):
            await storage.store(
                seeded.principal,
                model_id=seeded.model_id,
                modeled_entity_type="logical_entity",
                workflow_run_id=seeded.workflow_run_id,
                expected_model_revision=seeded.model_revision,
                workflow_run_claim_token=seeded.workflow_run_claim_token,
                artifacts=(
                    GeneratedSqlArtifact(
                        target_ref=context.targets[0].target_ref,
                        object_id=context.targets[0].object_id,
                        generated_sql=replacement_sql,
                    ),
                    GeneratedSqlArtifact(
                        target_ref=context.targets[1].target_ref,
                        object_id=context.targets[1].object_id,
                        generated_sql=second_sql,
                    ),
                ),
                contexts=context.targets,
            )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        prior = connection.execute(
            """
            SELECT generated_sql, generated_sql_digest, workflow_run_id, generator_version
             FROM application.generated_sql_artifact
             WHERE model_id = %s
               AND object_id = %s
            """,
            (seeded.model_id, seeded.object_ids[0]),
        ).fetchone()
        second_count_row = connection.execute(
            """
            SELECT count(*) AS artifact_count
             FROM application.generated_sql_artifact
             WHERE model_id = %s
               AND object_id = %s
            """,
            (seeded.model_id, seeded.object_ids[1]),
        ).fetchone()
        run = connection.execute(
            """
            SELECT workflow_run_state, completed_time
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
            (seeded.workflow_run_id,),
        ).fetchone()

    prior_sql = "SELECT 'prior' AS artifact_version;\n"
    assert prior == {
        "generated_sql": prior_sql,
        "generated_sql_digest": hashlib.sha256(prior_sql.encode()).hexdigest(),
        "workflow_run_id": None,
        "generator_version": "0.9.0",
    }
    assert second_count_row == {"artifact_count": 0}
    assert run == {"workflow_run_state": "running", "completed_time": None}
