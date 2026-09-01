"""Frozen QA selection plus live applied Mapping, current Code, and existing QA.

The stored System ID/code/order is an immutable audit scope, not permission to
author against renamed or inactive live metadata. Mapping drift fails closed.
"""

from __future__ import annotations

import json
from typing import Any, Literal, LiteralString, Protocol, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    ValidationCheckRecord,
    ValidationGroupRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.change_sets.model_validation import (
    CodeGenerationTargetContext,
    qa_code_context_digest,
    qa_mapping_context_digest,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

from gds_workbench_api.features.workflows.authoring.context import (
    reject_forbidden_provider_json,
)
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan

_MAX_SYSTEMS = 1_000
_MAX_TARGET_CONTEXTS = 50_000
_MAX_APPLIED_GROUPS = 10_000
_MAX_APPLIED_CHECKS = 50_000
_MAX_SYSTEM_CONTEXT_BYTES = 10 * 1024 * 1024
_MAX_AGGREGATE_CONTEXT_BYTES = 64 * 1024 * 1024
_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

_SYSTEM_SELECTION_SQL: LiteralString = """
SELECT tenant.tenant_code,
       selection.system_code,
       selection.selection_order
  FROM application.workflow_run AS run
  JOIN model.model AS target_model
    ON target_model.model_id = run.model_id
   AND target_model.tenant_id = %s
   AND target_model.is_active
   AND target_model.model_revision = run.model_revision
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = target_model.tenant_id
   AND tenant.is_active
  JOIN application.workflow_run_system_selection AS selection
    ON selection.workflow_run_id = run.workflow_run_id
   AND selection.model_id = run.model_id
 WHERE run.model_id = %s
   AND run.workflow_run_id = %s
   AND run.model_revision = %s
   AND run.model_workflow = 'qa'
   AND run.workflow_run_state = 'running'
 ORDER BY selection.selection_order,
          selection.workflow_run_system_selection_id
"""

_TARGET_CONTEXT_SQL: LiteralString = """
WITH requested_run AS MATERIALIZED (
    SELECT run.workflow_run_id,
           run.model_id
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.tenant_id = %s
       AND target_model.is_active
       AND target_model.model_revision = run.model_revision
     WHERE run.model_id = %s
       AND run.workflow_run_id = %s
       AND run.model_revision = %s
       AND run.model_workflow = 'qa'
       AND run.workflow_run_state = 'running'
), selected_system AS MATERIALIZED (
    SELECT selection.system_id
      FROM requested_run AS run
      JOIN application.workflow_run_system_selection AS selection
        ON selection.workflow_run_id = run.workflow_run_id
       AND selection.model_id = run.model_id
), target_context AS MATERIALIZED (
    SELECT context.*
      FROM requested_run AS run
      JOIN LATERAL workflow.list_code_generation_target_context(
          run.model_id,
          'logical_entity',
          NULL
      ) AS context ON TRUE
    UNION ALL
    SELECT context.*
      FROM requested_run AS run
      JOIN LATERAL workflow.list_code_generation_target_context(
          run.model_id,
          'dimensional_entity',
          NULL
      ) AS context ON TRUE
)
SELECT context.object_id,
       context.modeled_entity_type,
       context.mapping_context_digest,
       context.source_context_digest,
       context.source_context,
       generated.artifact_type AS generated_artifact_type,
       generated.generated_code_content,
       generated.mapping_context_digest AS generated_mapping_context_digest,
       generated.source_context_digest AS generated_source_context_digest,
       generated.generated_code_digest,
       generated.generated_code_status,
       generated.generated_code_is_locked
  FROM target_context AS context
  LEFT JOIN workflow.generated_code AS generated
    ON generated.model_id = context.model_id
   AND generated.object_id = context.object_id
   AND generated.modeled_entity_type = context.modeled_entity_type
   AND generated.generated_code_status = 'active'
   AND generated.mapping_context_digest = context.mapping_context_digest
   AND generated.source_context_digest = context.source_context_digest
 WHERE EXISTS (
       SELECT 1
         FROM jsonb_array_elements(
             context.source_context -> 'source_systems'
         ) AS source_system(document)
         JOIN selected_system AS selected
           ON selected.system_id =
              (source_system.document ->> 'source_system_id')::BIGINT
   )
 ORDER BY context.modeled_entity_type,
          context.object_id
"""

_APPLIED_QA_SQL: LiteralString = """
WITH requested_run AS MATERIALIZED (
    SELECT run.workflow_run_id,
           run.model_id,
           target_model.tenant_id
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.tenant_id = %s
       AND target_model.is_active
       AND target_model.model_revision = run.model_revision
     WHERE run.model_id = %s
       AND run.workflow_run_id = %s
       AND run.model_revision = %s
       AND run.model_workflow = 'qa'
       AND run.workflow_run_state = 'running'
)
SELECT tenant.tenant_code,
       selection.system_code,
       selection.selection_order,
       validation_group.validation_group_name,
       validation_group.validation_group_description,
       validation_group.mapping_context_digest,
       validation_group.code_context_digest,
       validation_group.is_active AS validation_group_is_active,
       validation_check.validation_check_name,
       validation_check.validation_check_description,
       validation_check.validation_category_code,
       validation_check.validation_severity,
       validation_check.validation_query_sql,
       validation_check.validation_comparison_query_sql,
       validation_check.validation_result_data_type,
       validation_check.validation_comparison_operator,
       validation_check.validation_comparison_value_type,
       validation_check.validation_comparison_value,
       validation_check.is_active AS validation_check_is_active
  FROM requested_run AS run
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = run.tenant_id
  JOIN workflow.validation_group AS validation_group
    ON validation_group.model_id = run.model_id
   AND validation_group.tenant_id = run.tenant_id
  JOIN application.workflow_run_system_selection AS selection
    ON selection.workflow_run_id = run.workflow_run_id
   AND selection.model_id = run.model_id
   AND selection.system_id = validation_group.system_id
  LEFT JOIN workflow.validation_check AS validation_check
    ON validation_check.validation_group_id = validation_group.validation_group_id
 ORDER BY selection.selection_order,
          lower(btrim(validation_group.validation_group_name)),
          lower(btrim(validation_check.validation_check_name)) NULLS LAST
"""

_CONTEXT_BOUNDS_SQL: LiteralString = """
WITH requested_run AS MATERIALIZED (
    SELECT run.workflow_run_id,
           run.model_id,
           target_model.tenant_id
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.tenant_id = %s
       AND target_model.is_active
       AND target_model.model_revision = run.model_revision
     WHERE run.model_id = %s
       AND run.workflow_run_id = %s
       AND run.model_revision = %s
       AND run.model_workflow = 'qa'
       AND run.workflow_run_state = 'running'
), selected_system AS MATERIALIZED (
    SELECT selection.system_id
      FROM requested_run AS run
      JOIN application.workflow_run_system_selection AS selection
        ON selection.workflow_run_id = run.workflow_run_id
       AND selection.model_id = run.model_id
), target_context AS MATERIALIZED (
    SELECT context.*
      FROM requested_run AS run
      JOIN LATERAL workflow.list_code_generation_target_context(
          run.model_id,
          'logical_entity',
          NULL
      ) AS context ON TRUE
    UNION ALL
    SELECT context.*
      FROM requested_run AS run
      JOIN LATERAL workflow.list_code_generation_target_context(
          run.model_id,
          'dimensional_entity',
          NULL
      ) AS context ON TRUE
), relevant_context AS MATERIALIZED (
    SELECT context.*,
           matching_system.match_count,
           generated.generated_code_content
      FROM target_context AS context
      CROSS JOIN LATERAL (
          SELECT count(*)::INTEGER AS match_count
            FROM jsonb_array_elements(
                     context.source_context -> 'source_systems'
                 ) AS source_system(document)
            JOIN selected_system AS selected
              ON selected.system_id =
                 (source_system.document ->> 'source_system_id')::BIGINT
      ) AS matching_system
      LEFT JOIN workflow.generated_code AS generated
        ON generated.model_id = context.model_id
       AND generated.object_id = context.object_id
       AND generated.modeled_entity_type = context.modeled_entity_type
       AND generated.generated_code_status = 'active'
       AND generated.mapping_context_digest = context.mapping_context_digest
       AND generated.source_context_digest = context.source_context_digest
     WHERE matching_system.match_count > 0
), applied_group AS MATERIALIZED (
    SELECT validation_group.validation_group_id,
           validation_group.validation_group_name,
           validation_group.validation_group_description
      FROM requested_run AS run
      JOIN workflow.validation_group AS validation_group
        ON validation_group.model_id = run.model_id
       AND validation_group.tenant_id = run.tenant_id
      JOIN selected_system AS selected
        ON selected.system_id = validation_group.system_id
), applied_check AS MATERIALIZED (
    SELECT validation_check.*
      FROM applied_group
      JOIN workflow.validation_check AS validation_check
        ON validation_check.validation_group_id =
           applied_group.validation_group_id
)
SELECT (SELECT count(*) FROM selected_system)::INTEGER AS selected_system_count,
       (SELECT count(*) FROM relevant_context)::INTEGER AS target_context_count,
       (SELECT count(*) FROM applied_group)::INTEGER AS applied_group_count,
       (SELECT count(*) FROM applied_check)::INTEGER AS applied_check_count,
       (
           coalesce((
               SELECT sum(
                   relevant_context.match_count * (
                       octet_length(relevant_context.source_context::TEXT)
                       + coalesce(
                           octet_length(relevant_context.generated_code_content),
                           0
                       )
                   )
               )
                 FROM relevant_context
           ), 0)
           + coalesce((
               SELECT sum(
                   octet_length(applied_group.validation_group_name)
                   + coalesce(
                       octet_length(applied_group.validation_group_description),
                       0
                   )
               )
                 FROM applied_group
           ), 0)
           + coalesce((
               SELECT sum(
                   octet_length(applied_check.validation_check_name)
                   + coalesce(
                       octet_length(applied_check.validation_check_description),
                       0
                   )
                   + octet_length(applied_check.validation_query_sql)
                   + coalesce(
                       octet_length(applied_check.validation_comparison_query_sql),
                       0
                   )
                   + coalesce(
                       octet_length(applied_check.validation_comparison_value::TEXT),
                       0
                   )
               )
                 FROM applied_check
           ), 0)
       )::BIGINT AS aggregate_context_bytes
"""


class QAContextTransaction(Protocol):
    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]: ...


class QAMappingTargetContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object_id: int = Field(gt=0, repr=False)
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    source_system_codes: tuple[str, ...] = Field(min_length=1, max_length=1_000)
    mapping_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_context: JsonValue = Field(repr=False)
    generated_code: GeneratedCodeRecord | None = Field(default=None, repr=False)

    def digest_context(self) -> CodeGenerationTargetContext:
        return CodeGenerationTargetContext(
            object_key=(
                normalize_model_key_value(self.tenant_code),
                normalize_model_key_value(self.system_code),
                normalize_model_key_value(self.connection_code),
                normalize_model_key_value(self.object_schema),
                normalize_model_key_value(self.object_name),
            ),
            modeled_entity_type=self.modeled_entity_type,
            source_system_codes=frozenset(self.source_system_codes),
            mapping_context_digest=self.mapping_context_digest,
            source_context_digest=self.source_context_digest,
        )


class QASystemAuthoringContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    system_ref: str = Field(pattern=r"^system_[1-9][0-9]{0,3}$")
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    mapping_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_context_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    applied_groups: tuple[ValidationGroupRecord, ...] = Field(max_length=10_000)
    applied_checks: tuple[ValidationCheckRecord, ...] = Field(max_length=50_000)
    agent_context: JsonValue = Field(repr=False)


class QAExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    systems: tuple[QASystemAuthoringContext, ...] = Field(
        min_length=1,
        max_length=_MAX_SYSTEMS,
    )


class PostgresQAContextRepository:
    async def load(
        self,
        transaction: QAContextTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> QAExecutionContext:
        if (
            plan.model_workflow != "qa"
            or plan.workflow_execution_mode is not None
            or plan.modeled_entity_type is not None
            or not plan.selected_system_codes
            or plan.selected_object_ids
        ):
            raise InvalidRequestError("The QA run plan is invalid.")
        parameters = (
            tenant_id,
            plan.model_id,
            plan.workflow_run_id,
            plan.model_revision,
        )
        system_rows = await transaction.fetch_all(_SYSTEM_SELECTION_SQL, parameters)
        bounds_rows = await transaction.fetch_all(_CONTEXT_BOUNDS_SQL, parameters)
        _validate_context_bounds(bounds_rows)
        target_rows = await transaction.fetch_all(_TARGET_CONTEXT_SQL, parameters)
        applied_rows = await transaction.fetch_all(_APPLIED_QA_SQL, parameters)
        try:
            return _assemble_context(
                plan=plan,
                system_rows=system_rows,
                target_rows=target_rows,
                applied_rows=applied_rows,
            )
        except InvalidRequestError:
            raise
        except (TypeError, ValueError, ValidationError):
            raise InvalidRequestError("The QA context is unavailable.") from None


def _assemble_context(
    *,
    plan: AgentRunPlan,
    system_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    applied_rows: list[dict[str, Any]],
) -> QAExecutionContext:
    if (
        not system_rows
        or len(system_rows) > _MAX_SYSTEMS
        or not target_rows
        or len(target_rows) > _MAX_TARGET_CONTEXTS
        or len(applied_rows) > _MAX_APPLIED_CHECKS + _MAX_APPLIED_GROUPS
    ):
        raise InvalidRequestError("The QA Mapping context is incomplete or too large.")
    tenant_code, selected_systems = _selected_systems(plan, system_rows)
    targets = tuple(qa_mapping_target_from_row(row) for row in target_rows)
    target_keys = [(target.object_id, target.modeled_entity_type) for target in targets]
    if len(target_keys) != len(set(target_keys)):
        raise InvalidRequestError("The QA Mapping context is ambiguous.")

    groups, checks = _applied_qa(
        applied_rows,
        tenant_code=tenant_code,
        selected_systems=frozenset(selected_systems),
    )
    digest_contexts = tuple(target.digest_context() for target in targets)
    generated_code = tuple(
        target.generated_code for target in targets if target.generated_code is not None
    )
    systems: list[QASystemAuthoringContext] = []
    aggregate_context_bytes = 0
    for position, system_code in enumerate(selected_systems, start=1):
        normalized_system = normalize_model_key_value(system_code)
        relevant_targets = tuple(
            target
            for target in targets
            if normalized_system
            in {
                normalize_model_key_value(source_code) for source_code in target.source_system_codes
            }
        )
        mapping_digest = qa_mapping_context_digest(digest_contexts, system_code)
        if not relevant_targets or mapping_digest is None:
            raise InvalidRequestError(
                "Each selected QA System requires complete active applied Mapping."
            )
        code_digest = qa_code_context_digest(
            digest_contexts,
            generated_code,
            system_code,
        )
        system_groups = tuple(
            group
            for group in groups
            if normalize_model_key_value(group.system_code) == normalized_system
        )
        group_names = {
            normalize_model_key_value(group.validation_group_name) for group in system_groups
        }
        system_checks = tuple(
            check
            for check in checks
            if normalize_model_key_value(check.system_code) == normalized_system
            and normalize_model_key_value(check.validation_group_name) in group_names
        )
        provider_context = _provider_context(
            system_ref=f"system_{position}",
            tenant_code=tenant_code,
            system_code=system_code,
            mapping_digest=mapping_digest,
            code_digest=code_digest,
            targets=relevant_targets,
            groups=system_groups,
            checks=system_checks,
        )
        provider_context_bytes = len(_canonical_json(provider_context))
        if provider_context_bytes > _MAX_SYSTEM_CONTEXT_BYTES:
            raise InvalidRequestError("The QA context exceeds its bounded size.")
        aggregate_context_bytes += provider_context_bytes
        if aggregate_context_bytes > _MAX_AGGREGATE_CONTEXT_BYTES:
            raise InvalidRequestError("The aggregate QA context exceeds its bounded size.")
        systems.append(
            QASystemAuthoringContext(
                system_ref=f"system_{position}",
                tenant_code=tenant_code,
                system_code=system_code,
                mapping_context_digest=mapping_digest,
                code_context_digest=code_digest,
                applied_groups=system_groups,
                applied_checks=system_checks,
                agent_context=provider_context,
            )
        )
    return QAExecutionContext(systems=tuple(systems))


def _validate_context_bounds(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 1:
        raise InvalidRequestError("The QA context bounds are unavailable.")
    row = rows[0]
    values = {
        key: row.get(key)
        for key in (
            "selected_system_count",
            "target_context_count",
            "applied_group_count",
            "applied_check_count",
            "aggregate_context_bytes",
        )
    }
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in values.values()
    ):
        raise InvalidRequestError("The QA context bounds are unavailable.")
    if (
        not 1 <= cast(int, values["selected_system_count"]) <= _MAX_SYSTEMS
        or not 1 <= cast(int, values["target_context_count"]) <= _MAX_TARGET_CONTEXTS
        or cast(int, values["applied_group_count"]) > _MAX_APPLIED_GROUPS
        or cast(int, values["applied_check_count"]) > _MAX_APPLIED_CHECKS
        or cast(int, values["aggregate_context_bytes"]) > _MAX_AGGREGATE_CONTEXT_BYTES
    ):
        raise InvalidRequestError("The QA context exceeds its bounded size.")


def _selected_systems(
    plan: AgentRunPlan,
    rows: list[dict[str, Any]],
) -> tuple[str, tuple[str, ...]]:
    tenant_codes: set[str] = set()
    system_codes: list[str] = []
    for expected_order, row in enumerate(rows, start=1):
        if _positive_int(row, "selection_order") != expected_order:
            raise InvalidRequestError("The QA System selection is unavailable.")
        tenant_codes.add(_required_text(row, "tenant_code", maximum=100))
        system_codes.append(_required_text(row, "system_code", maximum=100))
    if len(tenant_codes) != 1 or tuple(system_codes) != plan.selected_system_codes:
        raise InvalidRequestError("The QA System selection changed.")
    normalized = [normalize_model_key_value(code) for code in system_codes]
    if len(normalized) != len(set(normalized)):
        raise InvalidRequestError("The QA System selection is ambiguous.")
    return next(iter(tenant_codes)), tuple(system_codes)


def qa_mapping_target_from_row(row: dict[str, Any]) -> QAMappingTargetContext:
    source_context = _JSON_VALUE.validate_python(row.get("source_context"), strict=True)
    if not isinstance(source_context, dict):
        raise InvalidRequestError("The QA Mapping context is unavailable.")
    reject_forbidden_provider_json(
        source_context,
        allow_identity_keys=True,
        reject_sensitive_values=True,
    )
    target = source_context.get("target")
    sources = source_context.get("source_systems")
    if not isinstance(target, dict) or not isinstance(sources, list) or not sources:
        raise InvalidRequestError("The QA Mapping context is unavailable.")
    source_codes = tuple(
        _required_nested_text(source, "system_code", maximum=100) for source in sources
    )
    if len({normalize_model_key_value(code) for code in source_codes}) != len(source_codes):
        raise InvalidRequestError("The QA Mapping context is ambiguous.")
    context = QAMappingTargetContext(
        object_id=_positive_int(row, "object_id"),
        modeled_entity_type=cast(Any, row.get("modeled_entity_type")),
        tenant_code=_required_nested_text(target, "tenant_code", maximum=100),
        system_code=_required_nested_text(target, "system_code", maximum=100),
        connection_code=_required_nested_text(target, "connection_code", maximum=100),
        object_schema=_required_nested_text(target, "object_schema", maximum=400),
        object_name=_required_nested_text(target, "object_name", maximum=400),
        source_system_codes=source_codes,
        mapping_context_digest=_required_digest(row, "mapping_context_digest"),
        source_context_digest=_required_digest(row, "source_context_digest"),
        source_context=source_context,
    )
    generated = _generated_code(row, context=context)
    return context.model_copy(update={"generated_code": generated})


def _generated_code(
    row: dict[str, Any],
    *,
    context: QAMappingTargetContext,
) -> GeneratedCodeRecord | None:
    content = row.get("generated_code_content")
    if content is None:
        return None
    record = GeneratedCodeRecord.model_validate(
        {
            "tenant_code": context.tenant_code,
            "system_code": context.system_code,
            "connection_code": context.connection_code,
            "object_schema": context.object_schema,
            "object_name": context.object_name,
            "modeled_entity_type": context.modeled_entity_type,
            "artifact_type": row.get("generated_artifact_type"),
            "generated_code_content": content,
            "mapping_context_digest": row.get("generated_mapping_context_digest"),
            "source_context_digest": row.get("generated_source_context_digest"),
            "generated_code_digest": row.get("generated_code_digest"),
            "generated_code_status": row.get("generated_code_status"),
            "generated_code_is_locked": row.get("generated_code_is_locked"),
        },
        strict=True,
    )
    if (
        record.generated_code_status != "active"
        or record.mapping_context_digest != context.mapping_context_digest
        or record.source_context_digest != context.source_context_digest
    ):
        return None
    return record


def _applied_qa(
    rows: list[dict[str, Any]],
    *,
    tenant_code: str,
    selected_systems: frozenset[str],
) -> tuple[tuple[ValidationGroupRecord, ...], tuple[ValidationCheckRecord, ...]]:
    normalized_systems = {
        normalize_model_key_value(system_code) for system_code in selected_systems
    }
    groups: dict[tuple[str, str], ValidationGroupRecord] = {}
    checks: dict[tuple[str, str, str], ValidationCheckRecord] = {}
    for row in rows:
        row_tenant = _required_text(row, "tenant_code", maximum=100)
        system_code = _required_text(row, "system_code", maximum=100)
        if (
            normalize_model_key_value(row_tenant) != normalize_model_key_value(tenant_code)
            or normalize_model_key_value(system_code) not in normalized_systems
        ):
            continue
        group = ValidationGroupRecord.model_validate(
            {
                "tenant_code": row_tenant,
                "system_code": system_code,
                "validation_group_name": row.get("validation_group_name"),
                "validation_group_description": row.get("validation_group_description"),
                "mapping_context_digest": row.get("mapping_context_digest"),
                "code_context_digest": row.get("code_context_digest"),
                "is_active": row.get("validation_group_is_active"),
            },
            strict=True,
        )
        group_key = (
            normalize_model_key_value(system_code),
            normalize_model_key_value(group.validation_group_name),
        )
        prior_group = groups.setdefault(group_key, group)
        if prior_group != group:
            raise InvalidRequestError("The applied QA context is ambiguous.")
        if row.get("validation_check_name") is None:
            continue
        comparison_value = row.get("validation_comparison_value")
        if isinstance(comparison_value, list):
            comparison_value = tuple(cast(list[bool | int | float | str], comparison_value))
        check = ValidationCheckRecord.model_validate(
            {
                "tenant_code": row_tenant,
                "system_code": system_code,
                "validation_group_name": group.validation_group_name,
                "validation_check_name": row.get("validation_check_name"),
                "validation_check_description": row.get("validation_check_description"),
                "validation_category_code": row.get("validation_category_code"),
                "validation_severity": row.get("validation_severity"),
                "validation_query_sql": row.get("validation_query_sql"),
                "validation_comparison_query_sql": row.get("validation_comparison_query_sql"),
                "validation_result_data_type": row.get("validation_result_data_type"),
                "validation_comparison_operator": row.get("validation_comparison_operator"),
                "validation_comparison_value_type": row.get("validation_comparison_value_type"),
                "validation_comparison_value": comparison_value,
                "is_active": row.get("validation_check_is_active"),
            },
            strict=True,
        )
        check_key = (
            *group_key,
            normalize_model_key_value(check.validation_check_name),
        )
        if check_key in checks:
            raise InvalidRequestError("The applied QA context is ambiguous.")
        checks[check_key] = check
    if len(groups) > _MAX_APPLIED_GROUPS or len(checks) > _MAX_APPLIED_CHECKS:
        raise InvalidRequestError("The applied QA context is too large.")
    return tuple(groups.values()), tuple(checks.values())


def _provider_context(
    *,
    system_ref: str,
    tenant_code: str,
    system_code: str,
    mapping_digest: str,
    code_digest: str | None,
    targets: tuple[QAMappingTargetContext, ...],
    groups: tuple[ValidationGroupRecord, ...],
    checks: tuple[ValidationCheckRecord, ...],
) -> JsonValue:
    mapping_targets = [
        {
            "modeled_entity_type": target.modeled_entity_type,
            "mapping_context_digest": target.mapping_context_digest,
            "source_context_digest": target.source_context_digest,
            "context": target.source_context,
        }
        for target in targets
    ]
    generated_code = [
        target.generated_code.model_dump(mode="json")
        for target in targets
        if target.generated_code is not None
    ]
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "workflow": "qa",
            "system_ref": system_ref,
            "scope": {
                "tenant_code": tenant_code,
                "system_code": system_code,
                "mapping_context_digest": mapping_digest,
                "code_context_digest": code_digest,
            },
            "mapping_targets": mapping_targets,
            "generated_code": generated_code,
            "applied_validation_groups": [group.model_dump(mode="json") for group in groups],
            "applied_validation_checks": [check.model_dump(mode="json") for check in checks],
        },
    )


def _canonical_json(value: JsonValue) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _positive_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidRequestError("The QA context is unavailable.")
    return value


def _required_text(row: dict[str, Any], key: str, *, maximum: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InvalidRequestError("The QA context is unavailable.")
    return value


def _required_nested_text(value: object, key: str, *, maximum: int) -> str:
    if not isinstance(value, dict):
        raise InvalidRequestError("The QA context is unavailable.")
    item = cast(dict[str, object], value).get(key)
    if not isinstance(item, str) or not item.strip() or len(item) > maximum:
        raise InvalidRequestError("The QA context is unavailable.")
    return item


def _required_digest(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InvalidRequestError("The QA context is unavailable.")
    return value
