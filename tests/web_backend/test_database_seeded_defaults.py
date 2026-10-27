"""Actual installed defaults inside real Analysis/Subject Area/Logical/Dimensional executor paths.

Only synthetic evidence/provider responses; no prompt or context artifacts.
"""

# Reuse synthetic executor factories, not production private storage APIs.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from jsonschema import Draft202012Validator
from tests.mcp.conftest import DisposablePostgres
from tests.mcp.conftest import (
    bootstrap_postgres_database as bootstrap_postgres_database,
)
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
    _snapshot,
)
from tests.web_backend import test_analysis_executor as analysis
from tests.web_backend import test_analysis_per_table as per_table
from tests.web_backend import test_dimensional_executor as dimensional
from tests.web_backend import test_logical_executor as logical
from tests.web_backend.test_database_project_change_sets import _seed_profile_project

from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.subject_areas.service import SubjectAreaWorkflow
from gds_workbench_api.features.workflows.authoring import stage_runner
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    DatabaseAuthoringNoOpService,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
)
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
)
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)
from gds_workbench_api.integrations.agents import LocalFakeAgentAdapter
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)

type StageIdentity = tuple[str, str | None, str]
type SeedStages = dict[tuple[str, str | None], tuple[FrozenAgentStage, ...]]


@pytest.fixture(scope="module")
def installed_stages(bootstrap_postgres_database: DisposablePostgres) -> SeedStages:
    database = bootstrap_postgres_database
    _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
    _seed_super_admin(database)
    _apply_sql(database, _render_seed())
    with database.connect_owner() as connection:
        variables = connection.execute(
            """
            SELECT stage.project_workflow, stage.workflow_execution_mode,
                   stage.workflow_stage_id, stage.workflow_stage_code,
                   stage.workflow_stage_order,
                   variable.workflow_stage_variable_name AS name,
                   variable.workflow_stage_variable_resolver_key AS resolver_key,
                   variable.workflow_stage_variable_data_type AS data_type,
                   variable.workflow_stage_variable_is_required AS is_required
              FROM application.workflow_stage AS stage
              JOIN application.workflow_stage_variable AS variable USING (workflow_stage_id)
             WHERE stage.project_workflow IN (
                   'analysis', 'subject_area', 'logical', 'dimensional', 'mapping',
                   'code_generation', 'validation')
               AND stage.workflow_stage_is_agentic AND stage.is_active AND variable.is_active
             ORDER BY stage.workflow_stage_order, variable.workflow_stage_variable_order
            """
        ).fetchall()
    stages: dict[tuple[str, str | None], list[FrozenAgentStage]] = {}
    for row in _snapshot(database):
        if row["project_workflow"] not in {
            "analysis",
            "subject_area",
            "logical",
            "dimensional",
            "mapping",
            "code_generation",
            "validation",
        }:
            continue
        identity = (
            row["project_workflow"],
            row["workflow_execution_mode"],
            row["workflow_stage_code"],
        )
        matching = [
            variable
            for variable in variables
            if (
                variable["project_workflow"],
                variable["workflow_execution_mode"],
                variable["workflow_stage_code"],
            )
            == identity
        ]
        assert matching
        stage = FrozenAgentStage(
            workflow_stage_id=matching[0]["workflow_stage_id"],
            stage_code=identity[2],
            stage_order=matching[0]["workflow_stage_order"],
            prompt_template_version_id=row["prompt_template_version_id"],
            prompt_template_digest=row["prompt_template_digest"],
            templates=PromptComponentTemplates(
                system=row["system_prompt_template"],
                instruction=row["instruction_prompt_template"],
                tool_instruction=row["tool_instruction_prompt_template"],
            ),
            variables=tuple(
                PromptVariableDefinition(
                    **{
                        key: value[key]
                        for key in ("name", "resolver_key", "data_type", "is_required")
                    }
                )
                for value in matching
            ),
        )
        stages.setdefault((identity[0], identity[1]), []).append(stage)
    # Logical and Dimensional have a Build and an Optimize stage per mode; one-shot
    # Analysis also has its per-table stage.
    assert sum(len(value) for value in stages.values()) == 17
    return {
        key: tuple(sorted(value, key=lambda item: item.stage_order))
        for key, value in stages.items()
    }


def prompt_fingerprint(system: str, instruction: str, tool: str | None) -> str:
    return sha256(
        json.dumps([system, instruction, tool], ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("family", "case"),
    [
        ("analysis", "one_shot"),
        ("analysis", "tool_assisted"),
        ("analysis", "repair"),
        ("analysis", "per_table"),
        ("logical", "one_shot"),
        ("logical", "tool_assisted"),
        ("logical", "repair"),
        ("logical", "optimize"),
        ("dimensional", "one_shot"),
        ("dimensional", "tool_assisted"),
        ("dimensional", "repair"),
        ("dimensional", "optimize"),
    ],
)
async def test_installed_defaults_execute_inside_real_authoring_paths(
    installed_stages: SeedStages,
    monkeypatch: pytest.MonkeyPatch,
    family: str,
    case: str,
) -> None:
    module = {
        "analysis": analysis,
        "dimensional": dimensional,
        "logical": logical,
    }[family]
    factory: Any = module._service
    original_render = stage_runner.render_prompt
    rendered: dict[StageIdentity, str] = {}
    seen: set[StageIdentity] = set()
    repaired: set[StageIdentity] = set()
    template_ids = {
        id(stage.templates): (workflow, mode, stage.stage_code)
        for (workflow, mode), stages in installed_stages.items()
        for stage in stages
    }
    stage_by_identity = {
        (workflow, mode, stage.stage_code): stage
        for (workflow, mode), stages in installed_stages.items()
        for stage in stages
    }

    def checked_render(**kwargs: Any) -> Any:
        identity = template_ids.get(id(kwargs["templates"]))
        assert identity is not None, "Executor must render the actual installed frozen stage."
        assert kwargs["variables"] == stage_by_identity[identity].variables
        for variable in kwargs["variables"]:
            contract = get_prompt_input_contract(
                project_workflow=identity[0],
                workflow_execution_mode=identity[1],
                stage_code=identity[2],
                resolver_key=variable.resolver_key,
            )
            if contract is not None:
                validator = cast(Any, Draft202012Validator(contract.value_schema))
                assert validator.is_valid(contract.example), "Invalid documented input example."
                assert validator.is_valid(kwargs["resolver_values"][variable.resolver_key]), (
                    "Actual stage input must satisfy its documented schema."
                )
        result = original_render(**kwargs)
        assert not result.warning_codes and not result.unknown_placeholders
        rendered[identity] = prompt_fingerprint(
            result.system, result.instruction, result.tool_instruction
        )
        return result

    class ObservedProvider:
        def __init__(self, delegate: Any) -> None:
            self.delegate = delegate

        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            workflow = "analysis" if request.workflow == "analysis_inference" else request.workflow
            identity = (workflow, request.execution_mode, request.stage)
            assert identity in rendered, "Only real seeded renders may reach the provider."
            fingerprint = prompt_fingerprint(
                request.system_prompt,
                request.instruction_prompt,
                request.tool_instruction,
            )
            assert fingerprint == rendered[identity]
            assert not any(
                "{{" in text
                for text in (
                    request.system_prompt,
                    request.instruction_prompt,
                    request.tool_instruction or "",
                )
            )
            seen.add(identity)
            if isinstance(request.context, dict) and request.context.get("repair") is not None:
                repaired.add(identity)
            return await self.delegate.execute(request)

    def seeded_service(*, agent: Any, plan: AgentRunPlan | None = None, **kwargs: Any) -> Any:
        original_plan = plan or module._plan()
        mode = original_plan.workflow_execution_mode
        assert mode is not None
        # A run with an operation freezes only its own installed stage; a whole-selection
        # Analysis run never freezes the per-table stage.
        operation = original_plan.workflow_operation
        selected = tuple(
            stage
            for stage in installed_stages[(original_plan.project_workflow, mode)]
            if (
                stage.stage_code == f"{operation}_authoring"
                if operation
                else stage.stage_code != "per_table_authoring"
            )
        )
        # Replace only frozen installed Prompt stages, before the real executor loads its plan.
        seeded = original_plan.model_copy(update={"stages": selected})
        assert seeded.stages is selected
        return factory(agent=ObservedProvider(agent), plan=seeded, **kwargs)

    monkeypatch.setattr(module, "_service", seeded_service)
    monkeypatch.setattr(stage_runner, "render_prompt", checked_render)
    if family == "analysis":
        if case == "repair":
            await analysis.test_analysis_inference_repairs_against_immutable_context()
        elif case == "per_table":
            await per_table.test_per_table_run_makes_one_call_per_table_and_hands_off_one_draft()
        else:
            await analysis.test_analysis_inference_hands_off_one_validated_draft(
                cast(WorkflowExecutionMode, case)
            )
    elif case == "repair":
        if family == "logical":
            await logical.test_validation_repair_keeps_original_context_then_hands_off_once()
        else:
            await dimensional.test_validation_repair_keeps_original_context_then_hands_off_once()
    elif case == "optimize":
        # Each mode's installed Optimize stage renders over the whole-model context.
        factory_module: Any = module
        empty: dict[str, list[object]] = (
            {"entities": [], "relationships": [], "retire": []}
            if family == "logical"
            else {"entities": [], "attributes": [], "relationships": []}
        )
        for optimize_mode in ("one_shot", "tool_assisted"):
            agent = factory_module._AgentExecutor(responses=[empty])
            service, _, _, handoff, lifecycle = factory_module._service(
                agent=agent, plan=factory_module._plan(mode=optimize_mode, operation="optimize")
            )
            await service.execute_started(
                factory_module._principal(),
                tenant_id=7,
                project_id=18,
                workflow_run_id=1048,
                expected_project_revision=7,
                workflow_run_claim_token=factory_module._CLAIM_TOKEN,
            )
            assert handoff.calls == [] and lifecycle.failed is None
    else:
        factory_module: Any = module
        agent = factory_module._AgentExecutor(responses=[factory_module._candidate()])
        service, _, _, handoff, lifecycle = factory_module._service(
            agent=agent, plan=factory_module._plan(mode=case)
        )
        await service.execute_started(
            factory_module._principal(),
            tenant_id=7,
            project_id=18,
            workflow_run_id=1048,
            expected_project_revision=7,
            workflow_run_claim_token=factory_module._CLAIM_TOKEN,
        )
        assert len(handoff.calls) == 1 and lifecycle.failed is None
        assert bool(agent.requests[0].allowed_tool_names) == (case == "tool_assisted")
    if case == "optimize":
        expected = {(family, mode, "optimize_authoring") for mode in ("one_shot", "tool_assisted")}
    elif case == "per_table":
        expected = {("analysis", "one_shot", "per_table_authoring")}
    else:
        mode = "one_shot" if case == "repair" else case
        expected = {
            (family, mode, stage.stage_code)
            for stage in installed_stages[(family, mode)]
            if stage.stage_code in ("relationship_inference", "build_authoring")
        }
    assert seen == expected
    if case == "repair":
        assert repaired


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["one_shot", "tool_assisted", "repair"])
async def test_installed_subject_area_defaults_complete_a_validated_draft(
    installed_stages: SeedStages,
    bootstrap_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    """A real Subject Area Run freezes the installed default; the local fake completes it."""
    database = bootstrap_postgres_database
    mode = cast(WorkflowExecutionMode, "one_shot" if case == "repair" else case)
    (stage,) = installed_stages[("subject_area", mode)]
    project_id, tenant_id, _, entra_tenant_id, entra_object_id, _ = _seed_profile_project(database)
    with database.connect_owner() as connection:
        scope = connection.execute(
            "SELECT object_id FROM project.project_input_scope WHERE project_id = %s",
            (project_id,),
        ).fetchall()
        acquired = require_row(
            connection.execute(
                "SELECT acquired FROM security.acquire_tenant_lock("
                "%s, %s, 'user', %s, 60, 'Seeded Subject Area defaults')",
                (entra_tenant_id, entra_object_id, tenant_id),
            ).fetchone()
        )
    assert acquired == {"acquired": True}
    original_render = stage_runner.render_prompt
    rendered: list[str] = []

    def checked_render(**kwargs: Any) -> Any:
        # The Run froze the installed global default, not a test Prompt.
        assert kwargs["templates"] == stage.templates
        assert kwargs["variables"] == stage.variables
        for variable in stage.variables:
            contract = get_prompt_input_contract(
                project_workflow="subject_area",
                workflow_execution_mode=mode,
                stage_code=stage.stage_code,
                resolver_key=variable.resolver_key,
            )
            if contract is not None:
                validator = cast(Any, Draft202012Validator(contract.value_schema))
                assert validator.is_valid(contract.example)
                assert validator.is_valid(kwargs["resolver_values"][variable.resolver_key])
        result = original_render(**kwargs)
        assert not result.warning_codes and not result.unknown_placeholders
        rendered.append(
            prompt_fingerprint(result.system, result.instruction, result.tool_instruction)
        )
        return result

    class ObservedFakeAgent(LocalFakeAgentAdapter):
        def __init__(self) -> None:
            super().__init__(sdk_code="openai_agents_sdk")
            self.requests: list[AgentExecutionRequest] = []

        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            self.requests.append(request)
            assert rendered and rendered[-1] == prompt_fingerprint(
                request.system_prompt, request.instruction_prompt, request.tool_instruction
            )
            if case == "repair" and len(self.requests) == 1:
                # Every table is left unaccounted for, so validation asks for a repair.
                return AgentExecutionResult(
                    candidate={"areas": [], "unassigned": [], "retire": []},
                    turn_count=1,
                    tool_call_count=0,
                )
            return await super().execute(request)

    monkeypatch.setattr(stage_runner, "render_prompt", checked_render)
    agent = ObservedFakeAgent()
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    authorizer = AuthorizationService()
    workflow = SubjectAreaWorkflow(
        database=runtime,
        authorizer=authorizer,
        agent_executor=agent,
        handoff=WorkflowChangeSetHandoff(database=runtime, authorizer=authorizer),
        no_op=DatabaseAuthoringNoOpService(database=runtime),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=runtime),
    )
    await runtime.open()
    try:
        created = await DatabaseWorkflowCommandService(
            database=runtime,
            authorizer=authorizer,
            agent_capability_registry=load_default_agent_capabilities(),
        ).create_run(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            correlation_id=uuid4(),
            command=CreateWorkflowRunRequest(
                expected_project_revision=1,
                project_workflow="subject_area",
                workflow_execution_mode=mode,
                selected_object_ids=[row["object_id"] for row in scope],
            ),
        )
        await workflow.start(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=created.workflow_run_id,
            expected_execution_mode=mode,
            expected_project_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=runtime).claim_next(
            lease_duration_seconds=300
        )
        assert claim is not None and claim.workflow_run_id == created.workflow_run_id
        draft = await workflow.execute_started(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=created.workflow_run_id,
            expected_project_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
    finally:
        await runtime.close()
    with database.connect_owner() as connection:
        state = require_row(
            connection.execute(
                "SELECT run.workflow_run_state, run.failure_code, "
                "draft.project_change_set_status, draft.candidate_digest "
                "FROM application.workflow_run AS run "
                "JOIN mcp.project_change_set AS draft USING (workflow_run_id) "
                "WHERE run.workflow_run_id = %s",
                (created.workflow_run_id,),
            ).fetchone()
        )

    assert created.prompt_snapshot_count == 1
    # One area and one membership for the single Bronze Scope table.
    assert isinstance(draft, WorkflowChangeSetHandoffResult) and draft.staged_record_count == 2
    assert state == {
        "workflow_run_state": "completed_with_repair" if case == "repair" else "completed",
        "failure_code": None,
        "project_change_set_status": "validated",
        "candidate_digest": draft.candidate_digest,
    }
    # A repair attempt resends the same rendered Prompt with repair context.
    assert len(rendered) == 1 and len(agent.requests) == (2 if case == "repair" else 1)
    assert bool(agent.requests[0].allowed_tool_names) == (mode == "tool_assisted")
    if case == "repair":
        repair_context = agent.requests[1].context
        assert isinstance(repair_context, dict) and repair_context.get("repair") is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_installed_mapping_defaults_execute(
    installed_stages: SeedStages,
    monkeypatch: pytest.MonkeyPatch,
    mode: WorkflowExecutionMode,
) -> None:

    from tests.web_backend import test_mapping_executor as mapping

    original_executor = mapping._executor
    original_render = stage_runner.render_prompt
    seen: set[str] = set()
    stages = installed_stages[("mapping", mode)]

    def checked_render(**kwargs: Any) -> Any:
        stage = next(item for item in stages if kwargs["templates"] is item.templates)
        for variable in stage.variables:
            contract = get_prompt_input_contract(
                project_workflow="mapping",
                workflow_execution_mode=mode,
                stage_code=stage.stage_code,
                resolver_key=variable.resolver_key,
            )
            if contract is not None:
                validator = cast(Any, Draft202012Validator(contract.value_schema))
                assert validator.is_valid(contract.example)
                assert validator.is_valid(kwargs["resolver_values"][variable.resolver_key])
        result = original_render(**kwargs)
        assert not result.warning_codes and not result.unknown_placeholders
        seen.add(stage.stage_code)
        return result

    def seeded_executor(preparation: Any, agent: Any, policy: Any = None) -> Any:
        agent_plan = preparation.plan.agent_plan.model_copy(update={"stages": stages})
        preparation = preparation.model_copy(
            update={"plan": preparation.plan.model_copy(update={"agent_plan": agent_plan})}
        )
        return original_executor(preparation, agent, policy)

    monkeypatch.setattr(mapping, "_executor", seeded_executor)
    monkeypatch.setattr(stage_runner, "render_prompt", checked_render)
    await mapping.test_mapping_local_fake_completes_each_mode(mode, "logical_entity")
    assert seen == {stage.stage_code for stage in stages}


@pytest.mark.asyncio
@pytest.mark.parametrize("repair", [False, True])
async def test_installed_sql_defaults_with_repository_projection(
    installed_stages: SeedStages,
    web_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    repair: bool,
) -> None:
    from tests.web_backend import test_code_generation_executor as code
    from tests.web_backend.test_code_generation_context import _row
    from tests.web_backend.test_database_mapping_source_context import (
        _seed_mapping_scope,
    )

    from gds_workbench_api.features.code_generation.context import (
        _assemble_context,
    )

    scope = _seed_mapping_scope(web_postgres_database, dimensional=False)
    with web_postgres_database.connect_owner() as connection:
        row = connection.execute(
            "SELECT * FROM workflow.list_code_generation_target_context("
            "%s, 'logical_entity', NULL) "
            "WHERE modeled_entity_id = %s",
            (scope.plan.project_id, scope.plan.pair.modeled_entity_id),
        ).fetchone()
    assert row is not None
    source = row["source_context"]
    supplied = _row(scope.plan.pair.modeled_entity_id)
    supplied.update(
        source_context=source,
        source_system_count=len(source["source_systems"]),
        mapping_count=len(source["object_mappings"]),
        attribute_mapping_count=len(source["attribute_mappings"]),
    )
    stages = installed_stages[("code_generation", None)]
    plan = code._plan().model_copy(
        update={
            "stages": stages,
            "selected_object_ids": (),
            "selected_entity_ids": (scope.plan.pair.modeled_entity_id,),
        }
    )
    context = _assemble_context(plan=plan, rows=[supplied])
    original_render = stage_runner.render_prompt
    renders = 0

    def checked_render(**kwargs: Any) -> Any:
        nonlocal renders
        # SQL policy is frozen in the published Prompt; no second policy is appended.
        actual_templates = kwargs["templates"]
        assert (
            sha256(actual_templates.system.encode()).digest()
            == sha256(stages[0].templates.system.encode()).digest()
        )
        assert (
            sha256(actual_templates.instruction.encode()).digest()
            == sha256(stages[0].templates.instruction.encode()).digest()
        )
        assert actual_templates.tool_instruction == stages[0].templates.tool_instruction
        for variable in stages[0].variables:
            contract = get_prompt_input_contract(
                project_workflow="code_generation",
                workflow_execution_mode=None,
                stage_code="sql_generation",
                resolver_key=variable.resolver_key,
            )
            if contract is not None:
                validator = cast(Any, Draft202012Validator(contract.value_schema))
                assert validator.is_valid(contract.example)
                assert validator.is_valid(kwargs["resolver_values"][variable.resolver_key])
        result = original_render(**kwargs)
        assert not result.warning_codes and not result.unknown_placeholders
        renders += 1
        return result

    monkeypatch.setattr(stage_runner, "render_prompt", checked_render)
    artifact = {
        "target_ref": "target_1",
        "artifact_name": "target_1.sql",
        "artifact_role": "target_transformation",
        "source_system_codes": list(context.targets[0].source_system_codes),
        "generated_sql": "SELECT 1;",
    }
    responses: list[Any] = [{"artifacts": [artifact]}]
    if repair:
        responses.insert(0, {"artifacts": [{**artifact, "target_ref": "outside"}]})

    class Provider:
        sdk_code = "openai_agents_sdk"

        def __init__(self) -> None:
            self.requests: list[AgentExecutionRequest] = []

        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            self.requests.append(request)
            return AgentExecutionResult(candidate=responses.pop(0), turn_count=1, tool_call_count=0)

    agent = Provider()
    service, _, _, handoff, no_op, _ = code._service(
        executor=agent, context=context, plan_repository=code._PlanRepository(plan=plan)
    )
    await service.execute_started(
        code._principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=code._CLAIM_TOKEN,
    )
    assert renders == 1 and len(agent.requests) == (2 if repair else 1)
    assert len(handoff.calls) == 1 and not no_op.requests
    for request in agent.requests:
        assert request.system_prompt == stages[0].templates.system.strip()
        assert '"file_layout":"combined"' in request.instruction_prompt.replace(" ", "")
        attempt = cast(dict[str, Any], request.context)
        assert attempt["original_context"]["values"]["artifact_requirements"] == {
            "file_layout": "combined",
            "source_system_codes": list(context.targets[0].source_system_codes),
            "preserved_artifact_names": [],
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("with_code", [False, True])
async def test_installed_validation_defaults_with_repository_context(
    installed_stages: SeedStages,
    web_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    with_code: bool,
) -> None:
    from tests.web_backend import test_validation_executor as validation
    from tests.web_backend.test_database_mapping_source_context import (
        _seed_mapping_scope,
    )
    from tests.web_backend.test_validation_context import _applied_row

    from gds_workbench_api.features.validation.context import _assemble_context

    scope = _seed_mapping_scope(web_postgres_database, dimensional=False)
    with web_postgres_database.connect_owner() as connection:
        row = connection.execute(
            "SELECT * FROM workflow.list_code_generation_target_context("
            "%s, 'logical_entity', NULL) WHERE modeled_entity_id = %s",
            (scope.plan.project_id, scope.plan.pair.modeled_entity_id),
        ).fetchone()
    assert row is not None
    system_code = row["source_context"]["source_systems"][0]["system_code"]
    stages = installed_stages[("validation", None)]
    plan = validation._plan().model_copy(
        update={"stages": stages, "selected_system_codes": (system_code,)}
    )
    row["generated_code"] = (
        [
            {
                "modeled_entity_type": row["modeled_entity_type"],
                "modeled_entity_schema_name": "silver",
                "modeled_entity_name": row["modeled_entity_name"],
                "artifact_name": "customer.sql",
                "artifact_type": "sql_file",
                "generated_code_content": "SELECT 1;",
                "generated_code_status": "active",
                "generated_code_is_locked": False,
                "source_system_codes": [system_code],
            }
        ]
        if with_code
        else []
    )
    applied = _applied_row() | {"system_code": system_code}
    context = _assemble_context(
        plan=plan,
        system_rows=[{"tenant_code": "acme", "system_code": system_code, "selection_order": 1}],
        target_rows=[row],
        applied_rows=[applied],
    )
    original_render = stage_runner.render_prompt
    renders = 0

    def checked_render(**kwargs: Any) -> Any:
        nonlocal renders
        assert kwargs["templates"] is stages[0].templates
        for variable in stages[0].variables:
            contract = get_prompt_input_contract(
                project_workflow="validation",
                workflow_execution_mode=None,
                stage_code="validation_generation",
                resolver_key=variable.resolver_key,
            )
            if contract is not None:
                validator = cast(Any, Draft202012Validator(contract.value_schema))
                assert validator.is_valid(contract.example)
                assert validator.is_valid(kwargs["resolver_values"][variable.resolver_key])
        result = original_render(**kwargs)
        assert not result.warning_codes and not result.unknown_placeholders
        renders += 1
        return result

    monkeypatch.setattr(stage_runner, "render_prompt", checked_render)
    monkeypatch.setattr(validation, "_plan", lambda: plan)
    service, _, agent, handoff, no_op, _ = validation._service(context=context)
    await service.execute_started(
        validation._principal(),
        tenant_id=7,
        project_id=18,
        workflow_run_id=1048,
        expected_project_revision=7,
        workflow_run_claim_token=validation._CLAIM_TOKEN,
    )
    assert renders == 1 and len(agent.requests) == 1
    assert len(handoff.calls) == 1 and not no_op.requests
    system = context.systems[0]
    assert isinstance(system.agent_context, dict)
    assert bool(system.agent_context["generated_code"]) == with_code
    assert len(system.applied_checks) == 1
