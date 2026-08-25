from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import psycopg
import pytest
from database_test_support import require_row
from psycopg.errors import RaiseException

if TYPE_CHECKING:
    from conftest import DisposablePostgres, TestRow


SAVE_PROMPT_TEMPLATE_SQL = """
    SELECT *
      FROM application.save_prompt_template(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::TEXT,
          %s::BOOLEAN,
          %s::TIMESTAMPTZ
      )
"""

SAVE_PROMPT_TEMPLATE_DRAFT_SQL = """
    SELECT *
      FROM application.save_prompt_template_draft(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::TEXT,
          %s::TEXT,
          %s::TEXT,
          %s::TIMESTAMPTZ
      )
"""

TRANSITION_PROMPT_TEMPLATE_VERSION_SQL = """
    SELECT *
      FROM application.transition_prompt_template_version(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR
      )
"""

SET_PROMPT_ASSIGNMENT_SQL = """
    SELECT *
      FROM application.set_prompt_assignment(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::BIGINT
      )
"""


@dataclass(frozen=True, slots=True)
class PromptActor:
    entra_tenant_id: UUID
    entra_object_id: UUID
    principal_id: int


@dataclass(frozen=True, slots=True)
class PromptContext:
    tenant_id: int
    model_id: int
    workflow_stage_id: int
    architect: PromptActor
    super_admin: PromptActor


def _seed_prompt_context(
    postgres_database: DisposablePostgres,
) -> PromptContext:
    suffix = uuid4().hex
    architect = PromptActor(uuid4(), uuid4(), 0)
    super_admin = PromptActor(uuid4(), uuid4(), 0)

    with postgres_database.connect_owner() as connection:
        project_id = require_row(
            connection.execute(
                """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
                (f"prompt_project_{suffix}", f"Prompt Project {suffix}"),
            ).fetchone()
        )["project_id"]
        tenant_id = require_row(
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
                    f"prompt_tenant_{suffix}",
                    f"Prompt Tenant {suffix}",
                    f"prompt_catalog_{suffix}",
                    f"prompt_admin_{suffix}",
                ),
            ).fetchone()
        )["tenant_id"]
        model_id = require_row(
            connection.execute(
                """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id
            """,
                (tenant_id, f"Prompt Model {suffix}"),
            ).fetchone()
        )["model_id"]
        workflow_stage_order = require_row(
            connection.execute(
                """
            SELECT coalesce(max(workflow_stage_order), 0) + 1 AS next_order
              FROM application.workflow_stage
             WHERE model_workflow = 'analysis'
               AND workflow_execution_mode = 'one_shot'
            """
            ).fetchone()
        )["next_order"]
        workflow_stage_id = require_row(
            connection.execute(
                """
            INSERT INTO application.workflow_stage (
                model_workflow,
                workflow_execution_mode,
                workflow_stage_code,
                workflow_stage_name,
                workflow_stage_order,
                workflow_stage_is_agentic
            ) VALUES (
                'analysis',
                'one_shot',
                %s,
                'Prompt mutation stage',
                %s,
                TRUE
            )
            RETURNING workflow_stage_id
            """,
                (f"prompt_mutation_{suffix}", workflow_stage_order),
            ).fetchone()
        )["workflow_stage_id"]

        architect_principal_id = require_row(
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
                    f"Prompt Architect {suffix}",
                    f"prompt_architect_{suffix}@example.test",
                ),
            ).fetchone()
        )["principal_id"]
        super_admin_principal_id = require_row(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES ('user', %s, %s, TRUE)
            RETURNING principal_id
            """,
                (
                    f"Prompt Super Admin {suffix}",
                    f"prompt_super_admin_{suffix}@example.test",
                ),
            ).fetchone()
        )["principal_id"]
        for actor, principal_id in (
            (architect, architect_principal_id),
            (super_admin, super_admin_principal_id),
        ):
            connection.execute(
                """
                INSERT INTO security.entra_principal_identity (
                    principal_id,
                    principal_type,
                    entra_tenant_id,
                    entra_object_id
                ) VALUES (%s, 'user', %s, %s)
                """,
                (principal_id, actor.entra_tenant_id, actor.entra_object_id),
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
            (tenant_id, architect_principal_id, super_admin_principal_id),
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
                'Prompt mutation tests',
                CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            )
            """,
            (tenant_id, architect_principal_id),
        )

    return PromptContext(
        tenant_id=tenant_id,
        model_id=model_id,
        workflow_stage_id=workflow_stage_id,
        architect=PromptActor(
            architect.entra_tenant_id,
            architect.entra_object_id,
            architect_principal_id,
        ),
        super_admin=PromptActor(
            super_admin.entra_tenant_id,
            super_admin.entra_object_id,
            super_admin_principal_id,
        ),
    )


def _save_prompt_template(
    postgres_database: DisposablePostgres,
    actor: PromptActor,
    *,
    prompt_template_id: int | None,
    workflow_stage_id: int,
    ownership_scope: str,
    owner_tenant_id: int | None,
    code: str,
    name: str,
    description: str | None = None,
    is_active: bool = True,
    expected_updated_time: object | None = None,
) -> TestRow:
    with postgres_database.connect_owner() as connection:
        return require_row(
            connection.execute(
                SAVE_PROMPT_TEMPLATE_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    prompt_template_id,
                    workflow_stage_id,
                    ownership_scope,
                    owner_tenant_id,
                    code,
                    name,
                    description,
                    is_active,
                    expected_updated_time,
                ),
            ).fetchone()
        )


def _save_prompt_template_draft(
    postgres_database: DisposablePostgres,
    actor: PromptActor,
    *,
    prompt_template_id: int,
    expected_prompt_template_version_id: int | None,
    system_prompt: str,
    instruction_prompt: str,
    tool_instruction_prompt: str | None,
    expected_updated_time: object | None,
) -> TestRow:
    with postgres_database.connect_owner() as connection:
        return require_row(
            connection.execute(
                SAVE_PROMPT_TEMPLATE_DRAFT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    prompt_template_id,
                    expected_prompt_template_version_id,
                    system_prompt,
                    instruction_prompt,
                    tool_instruction_prompt,
                    expected_updated_time,
                ),
            ).fetchone()
        )


def _transition_prompt_template_version(
    postgres_database: DisposablePostgres,
    actor: PromptActor,
    *,
    prompt_template_version_id: int,
    expected_status: str,
    target_status: str,
) -> TestRow:
    with postgres_database.connect_owner() as connection:
        return require_row(
            connection.execute(
                TRANSITION_PROMPT_TEMPLATE_VERSION_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    prompt_template_version_id,
                    expected_status,
                    target_status,
                ),
            ).fetchone()
        )


def _set_prompt_assignment(
    postgres_database: DisposablePostgres,
    actor: PromptActor,
    *,
    workflow_stage_id: int,
    assignment_scope: str,
    model_id: int | None,
    prompt_template_version_id: int | None,
    expected_prompt_assignment_id: int | None,
) -> TestRow:
    with postgres_database.connect_owner() as connection:
        return require_row(
            connection.execute(
                SET_PROMPT_ASSIGNMENT_SQL,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    workflow_stage_id,
                    assignment_scope,
                    model_id,
                    prompt_template_version_id,
                    expected_prompt_assignment_id,
                ),
            ).fetchone()
        )


def _expected_prompt_digest(
    postgres_database: DisposablePostgres,
    system_prompt: str,
    instruction_prompt: str,
    tool_instruction_prompt: str | None,
) -> str:
    with postgres_database.connect_owner() as connection:
        return require_row(
            connection.execute(
                """
            SELECT encode(
                       sha256(
                           convert_to(
                               jsonb_build_object(
                                   'system_prompt_template', %s::TEXT,
                                   'instruction_prompt_template', %s::TEXT,
                                   'tool_instruction_prompt_template', %s::TEXT
                               )::TEXT,
                               'UTF8'
                           )
                       ),
                       'hex'
                   ) AS prompt_template_digest
            """,
                (system_prompt, instruction_prompt, tool_instruction_prompt),
            ).fetchone()
        )["prompt_template_digest"]


def _create_global_prompt_with_model_assignment(
    postgres_database: DisposablePostgres,
    context: PromptContext,
) -> tuple[TestRow, TestRow, TestRow]:
    prompt = _save_prompt_template(
        postgres_database,
        context.super_admin,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="global",
        owner_tenant_id=None,
        code=f"global_model_prompt_{uuid4().hex}",
        name="Global Model prompt",
    )
    draft = _save_prompt_template_draft(
        postgres_database,
        context.super_admin,
        prompt_template_id=prompt["prompt_template_id"],
        expected_prompt_template_version_id=None,
        system_prompt="Global Model system prompt.",
        instruction_prompt="Global Model instruction prompt.",
        tool_instruction_prompt=None,
        expected_updated_time=None,
    )
    version = _transition_prompt_template_version(
        postgres_database,
        context.super_admin,
        prompt_template_version_id=draft["prompt_template_version_id"],
        expected_status="draft",
        target_status="published",
    )
    assignment = _set_prompt_assignment(
        postgres_database,
        context.architect,
        workflow_stage_id=context.workflow_stage_id,
        assignment_scope="model_default",
        model_id=context.model_id,
        prompt_template_version_id=version["prompt_template_version_id"],
        expected_prompt_assignment_id=None,
    )
    return prompt, version, assignment


def _wait_for_lock_wait(
    postgres_database: DisposablePostgres,
    backend_process_id: int,
) -> None:
    deadline = time.monotonic() + 5
    with postgres_database.connect_owner() as observer:
        while time.monotonic() < deadline:
            activity = observer.execute(
                """
                SELECT wait_event_type
                  FROM pg_catalog.pg_stat_activity
                 WHERE pid = %s
                """,
                (backend_process_id,),
            ).fetchone()
            if activity and activity["wait_event_type"] == "Lock":
                return
            time.sleep(0.02)
    pytest.fail("concurrent Prompt Template request did not reach a lock wait")


def test_prompt_headers_derive_actor_enforce_scope_and_keep_identity_stable(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    tenant_code = f"tenant_prompt_{uuid4().hex}"
    global_code = f"global_prompt_{uuid4().hex}"

    tenant_prompt = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=tenant_code,
        name="Tenant prompt",
    )
    global_prompt = _save_prompt_template(
        postgres_database,
        context.super_admin,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="global",
        owner_tenant_id=None,
        code=global_code,
        name="Global prompt",
    )

    assert tenant_prompt["created_by_principal_id"] == context.architect.principal_id
    assert tenant_prompt["updated_by_principal_id"] == context.architect.principal_id
    assert global_prompt["created_by_principal_id"] == context.super_admin.principal_id
    assert global_prompt["owner_tenant_id"] is None

    with pytest.raises(RaiseException, match="lock|locked"):
        _save_prompt_template(
            postgres_database,
            context.super_admin,
            prompt_template_id=None,
            workflow_stage_id=context.workflow_stage_id,
            ownership_scope="tenant",
            owner_tenant_id=context.tenant_id,
            code=f"forbidden_{uuid4().hex}",
            name="Super Admin without owned lock",
        )

    with pytest.raises(RaiseException, match="identity|immutable"):
        _save_prompt_template(
            postgres_database,
            context.architect,
            prompt_template_id=tenant_prompt["prompt_template_id"],
            workflow_stage_id=context.workflow_stage_id,
            ownership_scope="tenant",
            owner_tenant_id=context.tenant_id,
            code=f"changed_{tenant_code}",
            name="Changed identity",
            expected_updated_time=tenant_prompt["updated_time"],
        )

    updated = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=tenant_prompt["prompt_template_id"],
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=tenant_code,
        name="Tenant prompt renamed",
        description="Editable header metadata.",
        expected_updated_time=tenant_prompt["updated_time"],
    )
    assert updated["prompt_template_id"] == tenant_prompt["prompt_template_id"]
    assert updated["prompt_template_name"] == "Tenant prompt renamed"
    assert updated["updated_by_principal_id"] == context.architect.principal_id

    with pytest.raises(RaiseException, match="stale|conflict|updated"):
        _save_prompt_template(
            postgres_database,
            context.architect,
            prompt_template_id=tenant_prompt["prompt_template_id"],
            workflow_stage_id=context.workflow_stage_id,
            ownership_scope="tenant",
            owner_tenant_id=context.tenant_id,
            code=tenant_code,
            name="Stale update",
            expected_updated_time=tenant_prompt["updated_time"],
        )


def test_prompt_draft_is_server_versioned_digested_and_idempotent(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    prompt = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=f"draft_prompt_{uuid4().hex}",
        name="Draft prompt",
    )
    system_prompt = "Use only the provided metadata context."
    instruction_prompt = "Propose relationship candidates for {{ object_metadata }}."
    tool_prompt = "Use {{ analysis_findings }} only when needed."

    created = _save_prompt_template_draft(
        postgres_database,
        context.architect,
        prompt_template_id=prompt["prompt_template_id"],
        expected_prompt_template_version_id=None,
        system_prompt=system_prompt,
        instruction_prompt=instruction_prompt,
        tool_instruction_prompt=tool_prompt,
        expected_updated_time=None,
    )
    replayed = _save_prompt_template_draft(
        postgres_database,
        context.architect,
        prompt_template_id=prompt["prompt_template_id"],
        expected_prompt_template_version_id=created["prompt_template_version_id"],
        system_prompt=system_prompt,
        instruction_prompt=instruction_prompt,
        tool_instruction_prompt=tool_prompt,
        expected_updated_time=created["updated_time"],
    )

    assert created["prompt_template_version_number"] == 1
    assert created["prompt_template_version_status"] == "draft"
    assert created["created_by_principal_id"] == context.architect.principal_id
    assert created["prompt_template_digest"] == _expected_prompt_digest(
        postgres_database,
        system_prompt,
        instruction_prompt,
        tool_prompt,
    )
    assert (
        replayed["prompt_template_version_id"] == created["prompt_template_version_id"]
    )
    assert replayed["updated_time"] == created["updated_time"]

    changed = _save_prompt_template_draft(
        postgres_database,
        context.architect,
        prompt_template_id=prompt["prompt_template_id"],
        expected_prompt_template_version_id=created["prompt_template_version_id"],
        system_prompt=system_prompt,
        instruction_prompt="Review {{ object_metadata }} and return only candidates.",
        tool_instruction_prompt=tool_prompt,
        expected_updated_time=created["updated_time"],
    )
    assert (
        changed["prompt_template_version_id"] == created["prompt_template_version_id"]
    )
    assert changed["prompt_template_version_number"] == 1
    assert changed["prompt_template_digest"] != created["prompt_template_digest"]

    with postgres_database.connect_owner() as connection:
        draft_count = require_row(
            connection.execute(
                """
            SELECT count(*) AS draft_count
              FROM application.prompt_template_version
             WHERE prompt_template_id = %s
               AND prompt_template_version_status = 'draft'
            """,
                (prompt["prompt_template_id"],),
            ).fetchone()
        )["draft_count"]
    assert draft_count == 1

    published = _transition_prompt_template_version(
        postgres_database,
        context.architect,
        prompt_template_version_id=changed["prompt_template_version_id"],
        expected_status="draft",
        target_status="published",
    )
    second_draft = _save_prompt_template_draft(
        postgres_database,
        context.architect,
        prompt_template_id=prompt["prompt_template_id"],
        expected_prompt_template_version_id=None,
        system_prompt="Second version system prompt.",
        instruction_prompt="Second version instruction prompt.",
        tool_instruction_prompt=None,
        expected_updated_time=None,
    )
    assert published["prompt_template_version_status"] == "published"
    assert published["published_by_principal_id"] == context.architect.principal_id
    assert second_draft["prompt_template_version_number"] == 2


def test_prompt_lifecycle_and_assignments_enforce_scope_fences_and_retirement(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    global_prompt = _save_prompt_template(
        postgres_database,
        context.super_admin,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="global",
        owner_tenant_id=None,
        code=f"global_assignment_{uuid4().hex}",
        name="Global assignment prompt",
    )
    global_draft = _save_prompt_template_draft(
        postgres_database,
        context.super_admin,
        prompt_template_id=global_prompt["prompt_template_id"],
        expected_prompt_template_version_id=None,
        system_prompt="Global system prompt.",
        instruction_prompt="Global instruction prompt.",
        tool_instruction_prompt=None,
        expected_updated_time=None,
    )
    global_version = _transition_prompt_template_version(
        postgres_database,
        context.super_admin,
        prompt_template_version_id=global_draft["prompt_template_version_id"],
        expected_status="draft",
        target_status="published",
    )

    with pytest.raises(RaiseException, match="Super Admin|authorized"):
        _set_prompt_assignment(
            postgres_database,
            context.architect,
            workflow_stage_id=context.workflow_stage_id,
            assignment_scope="global_default",
            model_id=None,
            prompt_template_version_id=global_version["prompt_template_version_id"],
            expected_prompt_assignment_id=None,
        )

    global_assignment = _set_prompt_assignment(
        postgres_database,
        context.super_admin,
        workflow_stage_id=context.workflow_stage_id,
        assignment_scope="global_default",
        model_id=None,
        prompt_template_version_id=global_version["prompt_template_version_id"],
        expected_prompt_assignment_id=None,
    )
    replayed_global_assignment = _set_prompt_assignment(
        postgres_database,
        context.super_admin,
        workflow_stage_id=context.workflow_stage_id,
        assignment_scope="global_default",
        model_id=None,
        prompt_template_version_id=global_version["prompt_template_version_id"],
        expected_prompt_assignment_id=global_assignment["prompt_assignment_id"],
    )
    assert (
        replayed_global_assignment["prompt_assignment_id"]
        == global_assignment["prompt_assignment_id"]
    )
    assert global_assignment["assigned_by_principal_id"] == (
        context.super_admin.principal_id
    )

    with pytest.raises(RaiseException, match="stale|conflict|assignment"):
        _set_prompt_assignment(
            postgres_database,
            context.super_admin,
            workflow_stage_id=context.workflow_stage_id,
            assignment_scope="global_default",
            model_id=None,
            prompt_template_version_id=None,
            expected_prompt_assignment_id=global_assignment["prompt_assignment_id"]
            + 1000,
        )

    with pytest.raises(RaiseException, match="status|transition|published"):
        _transition_prompt_template_version(
            postgres_database,
            context.super_admin,
            prompt_template_version_id=global_version["prompt_template_version_id"],
            expected_status="draft",
            target_status="retired",
        )

    with pytest.raises(RaiseException, match="active assignments"):
        _transition_prompt_template_version(
            postgres_database,
            context.super_admin,
            prompt_template_version_id=global_version["prompt_template_version_id"],
            expected_status="published",
            target_status="retired",
        )
    deactivated_global_assignment = _set_prompt_assignment(
        postgres_database,
        context.super_admin,
        workflow_stage_id=context.workflow_stage_id,
        assignment_scope="global_default",
        model_id=None,
        prompt_template_version_id=None,
        expected_prompt_assignment_id=global_assignment["prompt_assignment_id"],
    )
    retired = _transition_prompt_template_version(
        postgres_database,
        context.super_admin,
        prompt_template_version_id=global_version["prompt_template_version_id"],
        expected_status="published",
        target_status="retired",
    )
    with postgres_database.connect_owner() as connection:
        stored_assignment = require_row(
            connection.execute(
                """
            SELECT is_active
              FROM application.prompt_assignment
             WHERE prompt_assignment_id = %s
                """,
                (global_assignment["prompt_assignment_id"],),
            ).fetchone()
        )
    assert retired["prompt_template_version_status"] == "retired"
    assert retired["retired_by_principal_id"] == context.super_admin.principal_id
    assert deactivated_global_assignment["deactivated_by_principal_id"] == (
        context.super_admin.principal_id
    )
    assert deactivated_global_assignment["deactivated_time"] is not None
    assert stored_assignment["is_active"] is False

    tenant_prompt = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=f"tenant_assignment_{uuid4().hex}",
        name="Tenant assignment prompt",
    )
    tenant_draft = _save_prompt_template_draft(
        postgres_database,
        context.architect,
        prompt_template_id=tenant_prompt["prompt_template_id"],
        expected_prompt_template_version_id=None,
        system_prompt="Tenant system prompt.",
        instruction_prompt="Tenant instruction prompt.",
        tool_instruction_prompt=None,
        expected_updated_time=None,
    )
    tenant_version = _transition_prompt_template_version(
        postgres_database,
        context.architect,
        prompt_template_version_id=tenant_draft["prompt_template_version_id"],
        expected_status="draft",
        target_status="published",
    )

    with pytest.raises(RaiseException, match="global [Pp]rompt|scope"):
        _set_prompt_assignment(
            postgres_database,
            context.super_admin,
            workflow_stage_id=context.workflow_stage_id,
            assignment_scope="global_default",
            model_id=None,
            prompt_template_version_id=tenant_version["prompt_template_version_id"],
            expected_prompt_assignment_id=None,
        )

    model_assignment = _set_prompt_assignment(
        postgres_database,
        context.architect,
        workflow_stage_id=context.workflow_stage_id,
        assignment_scope="model_default",
        model_id=context.model_id,
        prompt_template_version_id=tenant_version["prompt_template_version_id"],
        expected_prompt_assignment_id=None,
    )
    assert model_assignment["model_id"] == context.model_id
    assert model_assignment["assigned_by_principal_id"] == (
        context.architect.principal_id
    )


def test_global_prompt_deactivation_rejects_active_model_assignments(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    prompt, _, _ = _create_global_prompt_with_model_assignment(
        postgres_database,
        context,
    )

    with pytest.raises(RaiseException):
        _save_prompt_template(
            postgres_database,
            context.super_admin,
            prompt_template_id=prompt["prompt_template_id"],
            workflow_stage_id=context.workflow_stage_id,
            ownership_scope="global",
            owner_tenant_id=None,
            code=prompt["prompt_template_code"],
            name=prompt["prompt_template_name"],
            description=prompt["prompt_template_description"],
            is_active=False,
            expected_updated_time=prompt["updated_time"],
        )


def test_global_prompt_retirement_rejects_active_model_assignments(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    _, version, _ = _create_global_prompt_with_model_assignment(
        postgres_database,
        context,
    )

    with pytest.raises(RaiseException):
        _transition_prompt_template_version(
            postgres_database,
            context.super_admin,
            prompt_template_version_id=version["prompt_template_version_id"],
            expected_status="published",
            target_status="retired",
        )


def test_invalid_prompt_input_does_not_echo_prompt_content(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    prompt = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=f"sanitized_prompt_{uuid4().hex}",
        name="Sanitized error prompt",
    )
    marker = "synthetic_prompt_body_marker_must_not_be_echoed"

    with pytest.raises(psycopg.Error) as error_info:
        _save_prompt_template_draft(
            postgres_database,
            context.architect,
            prompt_template_id=prompt["prompt_template_id"],
            expected_prompt_template_version_id=None,
            system_prompt=marker,
            instruction_prompt="   ",
            tool_instruction_prompt=None,
            expected_updated_time=None,
        )

    error_detail = error_info.value.diag.message_detail or ""
    assert marker not in f"{error_info.value} {error_detail}"


def test_prompt_template_primary_identity_is_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    prompt = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=f"immutable_header_{uuid4().hex}",
        name="Immutable Prompt Template identity",
    )

    with postgres_database.connect_owner() as connection:
        with pytest.raises(RaiseException, match="immutable"):
            connection.execute(
                """
                UPDATE application.prompt_template
                   SET prompt_template_id = DEFAULT
                 WHERE prompt_template_id = %s
                """,
                (prompt["prompt_template_id"],),
            )


def test_prompt_version_primary_identity_is_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    prompt = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=f"immutable_version_{uuid4().hex}",
        name="Immutable Prompt Version identity",
    )
    draft = _save_prompt_template_draft(
        postgres_database,
        context.architect,
        prompt_template_id=prompt["prompt_template_id"],
        expected_prompt_template_version_id=None,
        system_prompt="Immutable version system prompt.",
        instruction_prompt="Immutable version instruction prompt.",
        tool_instruction_prompt=None,
        expected_updated_time=None,
    )

    with postgres_database.connect_owner() as connection:
        with pytest.raises(RaiseException, match="immutable"):
            connection.execute(
                """
                UPDATE application.prompt_template_version
                   SET prompt_template_version_id = DEFAULT
                 WHERE prompt_template_version_id = %s
                """,
                (draft["prompt_template_version_id"],),
            )


def test_retired_prompt_replay_still_enforces_expected_source_status(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    prompt = _save_prompt_template(
        postgres_database,
        context.architect,
        prompt_template_id=None,
        workflow_stage_id=context.workflow_stage_id,
        ownership_scope="tenant",
        owner_tenant_id=context.tenant_id,
        code=f"transition_fence_{uuid4().hex}",
        name="Transition fence prompt",
    )
    draft = _save_prompt_template_draft(
        postgres_database,
        context.architect,
        prompt_template_id=prompt["prompt_template_id"],
        expected_prompt_template_version_id=None,
        system_prompt="Transition fence system prompt.",
        instruction_prompt="Transition fence instruction prompt.",
        tool_instruction_prompt=None,
        expected_updated_time=None,
    )
    published = _transition_prompt_template_version(
        postgres_database,
        context.architect,
        prompt_template_version_id=draft["prompt_template_version_id"],
        expected_status="draft",
        target_status="published",
    )
    _transition_prompt_template_version(
        postgres_database,
        context.architect,
        prompt_template_version_id=published["prompt_template_version_id"],
        expected_status="published",
        target_status="retired",
    )

    with pytest.raises(RaiseException):
        _transition_prompt_template_version(
            postgres_database,
            context.architect,
            prompt_template_version_id=published["prompt_template_version_id"],
            expected_status="draft",
            target_status="retired",
        )


def test_same_prompt_assignment_replay_enforces_expected_assignment_fence(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    _, version, assignment = _create_global_prompt_with_model_assignment(
        postgres_database,
        context,
    )

    with pytest.raises(RaiseException):
        _set_prompt_assignment(
            postgres_database,
            context.architect,
            workflow_stage_id=context.workflow_stage_id,
            assignment_scope="model_default",
            model_id=context.model_id,
            prompt_template_version_id=version["prompt_template_version_id"],
            expected_prompt_assignment_id=assignment["prompt_assignment_id"] + 1,
        )


def test_prompt_assignment_deactivation_records_derived_actor_and_time(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    _, _, assignment = _create_global_prompt_with_model_assignment(
        postgres_database,
        context,
    )

    deactivated = _set_prompt_assignment(
        postgres_database,
        context.architect,
        workflow_stage_id=context.workflow_stage_id,
        assignment_scope="model_default",
        model_id=context.model_id,
        prompt_template_version_id=None,
        expected_prompt_assignment_id=assignment["prompt_assignment_id"],
    )

    assert deactivated["is_active"] is False
    assert deactivated["deactivated_by_principal_id"] == (
        context.architect.principal_id
    )
    assert deactivated["deactivated_time"] is not None


def test_concurrent_exact_prompt_template_create_is_idempotent(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_prompt_context(postgres_database)
    prompt_code = f"concurrent_prompt_{uuid4().hex}"
    parameters = (
        context.architect.entra_tenant_id,
        context.architect.entra_object_id,
        None,
        context.workflow_stage_id,
        "tenant",
        context.tenant_id,
        prompt_code,
        "Concurrent Prompt Template",
        None,
        True,
        None,
    )

    with (
        postgres_database.connect_owner() as first_connection,
        postgres_database.connect_owner() as second_connection,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        first_prompt = require_row(
            first_connection.execute(
                SAVE_PROMPT_TEMPLATE_SQL,
                parameters,
            ).fetchone()
        )
        second_future = executor.submit(
            second_connection.execute,
            SAVE_PROMPT_TEMPLATE_SQL,
            parameters,
        )
        try:
            _wait_for_lock_wait(
                postgres_database,
                second_connection.info.backend_pid,
            )
        finally:
            first_connection.commit()
        second_prompt = require_row(second_future.result(timeout=5).fetchone())

    assert second_prompt["prompt_template_id"] == first_prompt["prompt_template_id"]


def test_prompt_mutators_are_web_only_security_definers_without_direct_dml(
    postgres_database: DisposablePostgres,
) -> None:
    expected_functions = {
        "save_prompt_template": 12,
        "save_prompt_template_draft": 9,
        "set_prompt_assignment": 8,
        "transition_prompt_template_version": 6,
    }
    prompt_tables = (
        "prompt_assignment",
        "prompt_template",
        "prompt_template_version",
    )

    with postgres_database.connect_owner() as connection:
        functions = connection.execute(
            """
            SELECT procedure.proname AS function_name,
                   procedure.pronargs AS argument_count,
                   procedure.prosecdef AS is_security_definer,
                   procedure.proconfig AS function_configuration,
                   has_function_privilege(
                       'gds_web_write', procedure.oid, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', procedure.oid, 'EXECUTE'
                   ) AS mcp_can_execute,
                   has_function_privilege(
                       'public', procedure.oid, 'EXECUTE'
                   ) AS public_can_execute
              FROM pg_catalog.pg_proc AS procedure
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'application'
               AND procedure.proname = ANY (%s::TEXT[])
             ORDER BY procedure.proname
            """,
            (list(expected_functions),),
        ).fetchall()
        table_privileges = connection.execute(
            """
            SELECT table_name,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'SELECT'
                   ) AS web_can_select,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate,
                   has_table_privilege(
                       'gds_app_write',
                       'application.' || quote_ident(table_name),
                       'SELECT,INSERT,UPDATE,DELETE'
                   ) AS mcp_can_access
              FROM unnest(%s::TEXT[]) AS prompt_table(table_name)
             ORDER BY table_name
            """,
            (list(prompt_tables),),
        ).fetchall()

    assert {row["function_name"]: row["argument_count"] for row in functions} == (
        expected_functions
    )
    assert all(row["is_security_definer"] for row in functions)
    assert all(
        row["function_configuration"]
        and any(
            setting.startswith("search_path=")
            for setting in row["function_configuration"]
        )
        for row in functions
    )
    assert all(row["web_can_execute"] for row in functions)
    assert not any(row["mcp_can_execute"] for row in functions)
    assert not any(row["public_can_execute"] for row in functions)
    assert table_privileges == [
        {
            "table_name": table_name,
            "web_can_select": True,
            "web_can_mutate": False,
            "mcp_can_access": False,
        }
        for table_name in sorted(prompt_tables)
    ]
