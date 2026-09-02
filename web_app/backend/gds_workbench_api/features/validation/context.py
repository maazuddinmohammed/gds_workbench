"""Frozen Validation selection plus live applied Mapping, current Code, and existing Validation.

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
    validation_code_context_digest,
    validation_mapping_context_digest,
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
   AND run.model_workflow = 'validation'
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
       AND run.model_workflow = 'validation'
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
       context.modeled_entity_name,
       context.code_input_digest,
       context.source_context,
       generated.generated_code
  FROM target_context AS context
  CROSS JOIN LATERAL (
      SELECT coalesce(
                 jsonb_agg(
                     jsonb_build_object(
                         'modeled_entity_type', context.modeled_entity_type,
                         'modeled_entity_name', context.modeled_entity_name,
                         'artifact_name', artifact.artifact_name,
                         'artifact_type', artifact.artifact_type,
                         'generated_code_content', artifact.generated_code_content,
                         'generated_code_status', artifact.generated_code_status,
                         'source_system_codes', assignment.source_system_codes
                     ) ORDER BY lower(btrim(artifact.artifact_name)),
                                artifact.generated_code_id
                 ),
                 '[]'::JSONB
             ) AS generated_code
        FROM workflow.generated_code AS artifact
       CROSS JOIN LATERAL (
           SELECT coalesce(
                      jsonb_agg(
                          system.system_code
                          ORDER BY lower(btrim(system.system_code)), system.system_id
                      ) FILTER (
                          WHERE source.generated_code_source_system_status = 'active'
                      ),
                      '[]'::JSONB
                  ) AS source_system_codes
             FROM workflow.generated_code_source_system AS source
             JOIN core.system AS system
               ON system.system_id = source.source_system_id
            WHERE source.generated_code_id = artifact.generated_code_id
       ) AS assignment
       WHERE artifact.model_object_binding_id = (
                 context.source_context -> 'object_mappings' -> 0
                 ->> 'model_object_binding_id'
             )::BIGINT
         AND artifact.generated_code_status = 'active'
         AND artifact.code_input_digest = context.code_input_digest
  ) AS generated
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

_APPLIED_VALIDATION_SQL: LiteralString = """
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
       AND run.model_workflow = 'validation'
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
       AND run.model_workflow = 'validation'
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
           generated.generated_code_bytes
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
      CROSS JOIN LATERAL (
          SELECT coalesce(
                     sum(octet_length(artifact.generated_code_content)),
                     0
                 )::BIGINT AS generated_code_bytes
            FROM workflow.generated_code AS artifact
           WHERE artifact.model_object_binding_id = (
                     context.source_context -> 'object_mappings' -> 0
                     ->> 'model_object_binding_id'
                 )::BIGINT
             AND artifact.generated_code_status = 'active'
             AND artifact.code_input_digest = context.code_input_digest
      ) AS generated
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
                       + relevant_context.generated_code_bytes
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


class ValidationContextTransaction(Protocol):
    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]: ...


class ValidationGeneratedCodeArtifact(GeneratedCodeRecord):
    source_system_codes: tuple[str, ...] = Field(max_length=1_000)


class ValidationMappingTargetContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    object_id: int = Field(gt=0, repr=False)
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    modeled_entity_name: str = Field(min_length=1, max_length=255)
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    source_system_codes: tuple[str, ...] = Field(min_length=1, max_length=1_000)
    code_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    source_context: JsonValue = Field(repr=False)
    generated_code: tuple[ValidationGeneratedCodeArtifact, ...] = Field(
        default=(),
        max_length=5_000,
        repr=False,
    )

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
            modeled_entity_name=self.modeled_entity_name,
            source_system_codes=frozenset(self.source_system_codes),
            code_input_digest=self.code_input_digest,
        )


class ValidationSystemAuthoringContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    system_ref: str = Field(pattern=r"^system_[1-9][0-9]{0,3}$")
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    applied_groups: tuple[ValidationGroupRecord, ...] = Field(max_length=10_000)
    applied_checks: tuple[ValidationCheckRecord, ...] = Field(max_length=50_000)
    current_group_names: tuple[str, ...] = Field(default=(), max_length=10_000)
    agent_context: JsonValue = Field(repr=False)


class ValidationExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    systems: tuple[ValidationSystemAuthoringContext, ...] = Field(
        min_length=1,
        max_length=_MAX_SYSTEMS,
    )


class PostgresValidationContextRepository:
    async def load(
        self,
        transaction: ValidationContextTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> ValidationExecutionContext:
        if (
            plan.model_workflow != "validation"
            or plan.workflow_execution_mode is not None
            or plan.modeled_entity_type is not None
            or not plan.selected_system_codes
            or plan.selected_object_ids
        ):
            raise InvalidRequestError("The Validation run plan is invalid.")
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
        applied_rows = await transaction.fetch_all(_APPLIED_VALIDATION_SQL, parameters)
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
            raise InvalidRequestError("The Validation context is unavailable.") from None


def _assemble_context(
    *,
    plan: AgentRunPlan,
    system_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    applied_rows: list[dict[str, Any]],
) -> ValidationExecutionContext:
    if (
        not system_rows
        or len(system_rows) > _MAX_SYSTEMS
        or not target_rows
        or len(target_rows) > _MAX_TARGET_CONTEXTS
        or len(applied_rows) > _MAX_APPLIED_CHECKS + _MAX_APPLIED_GROUPS
    ):
        raise InvalidRequestError("The Validation Mapping context is incomplete or too large.")
    tenant_code, selected_systems = _selected_systems(plan, system_rows)
    targets = tuple(validation_mapping_target_from_row(row) for row in target_rows)
    target_keys = [(target.object_id, target.modeled_entity_type) for target in targets]
    if len(target_keys) != len(set(target_keys)):
        raise InvalidRequestError("The Validation Mapping context is ambiguous.")

    groups, checks, group_witnesses = _applied_validation(
        applied_rows,
        tenant_code=tenant_code,
        selected_systems=frozenset(selected_systems),
    )
    digest_contexts = tuple(target.digest_context() for target in targets)
    generated_code = tuple(artifact for target in targets for artifact in target.generated_code)
    systems: list[ValidationSystemAuthoringContext] = []
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
        mapping_digest = validation_mapping_context_digest(digest_contexts, system_code)
        if not relevant_targets or mapping_digest is None:
            raise InvalidRequestError(
                "Each selected Validation System requires complete active applied Mapping."
            )
        code_digest = validation_code_context_digest(
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
        current_group_names = tuple(
            group.validation_group_name
            for group in system_groups
            if group_witnesses.get(
                (
                    normalized_system,
                    normalize_model_key_value(group.validation_group_name),
                )
            )
            == (mapping_digest, code_digest)
        )
        provider_context = _provider_context(
            system_ref=f"system_{position}",
            tenant_code=tenant_code,
            system_code=system_code,
            targets=relevant_targets,
            groups=system_groups,
            checks=system_checks,
        )
        provider_context_bytes = len(_canonical_json(provider_context))
        if provider_context_bytes > _MAX_SYSTEM_CONTEXT_BYTES:
            raise InvalidRequestError("The Validation context exceeds its bounded size.")
        aggregate_context_bytes += provider_context_bytes
        if aggregate_context_bytes > _MAX_AGGREGATE_CONTEXT_BYTES:
            raise InvalidRequestError("The aggregate Validation context exceeds its bounded size.")
        systems.append(
            ValidationSystemAuthoringContext(
                system_ref=f"system_{position}",
                tenant_code=tenant_code,
                system_code=system_code,
                applied_groups=system_groups,
                applied_checks=system_checks,
                current_group_names=current_group_names,
                agent_context=provider_context,
            )
        )
    return ValidationExecutionContext(systems=tuple(systems))


def _validate_context_bounds(rows: list[dict[str, Any]]) -> None:
    if len(rows) != 1:
        raise InvalidRequestError("The Validation context bounds are unavailable.")
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
        raise InvalidRequestError("The Validation context bounds are unavailable.")
    if (
        not 1 <= cast(int, values["selected_system_count"]) <= _MAX_SYSTEMS
        or not 1 <= cast(int, values["target_context_count"]) <= _MAX_TARGET_CONTEXTS
        or cast(int, values["applied_group_count"]) > _MAX_APPLIED_GROUPS
        or cast(int, values["applied_check_count"]) > _MAX_APPLIED_CHECKS
        or cast(int, values["aggregate_context_bytes"]) > _MAX_AGGREGATE_CONTEXT_BYTES
    ):
        raise InvalidRequestError("The Validation context exceeds its bounded size.")


def _selected_systems(
    plan: AgentRunPlan,
    rows: list[dict[str, Any]],
) -> tuple[str, tuple[str, ...]]:
    tenant_codes: set[str] = set()
    system_codes: list[str] = []
    for expected_order, row in enumerate(rows, start=1):
        if _positive_int(row, "selection_order") != expected_order:
            raise InvalidRequestError("The Validation System selection is unavailable.")
        tenant_codes.add(_required_text(row, "tenant_code", maximum=100))
        system_codes.append(_required_text(row, "system_code", maximum=100))
    if len(tenant_codes) != 1 or tuple(system_codes) != plan.selected_system_codes:
        raise InvalidRequestError("The Validation System selection changed.")
    normalized = [normalize_model_key_value(code) for code in system_codes]
    if len(normalized) != len(set(normalized)):
        raise InvalidRequestError("The Validation System selection is ambiguous.")
    return next(iter(tenant_codes)), tuple(system_codes)


def validation_mapping_target_from_row(row: dict[str, Any]) -> ValidationMappingTargetContext:
    source_context = _JSON_VALUE.validate_python(row.get("source_context"), strict=True)
    if not isinstance(source_context, dict):
        raise InvalidRequestError("The Validation Mapping context is unavailable.")
    reject_forbidden_provider_json(
        source_context,
        allow_identity_keys=True,
        reject_sensitive_values=True,
    )
    target = source_context.get("target")
    sources = source_context.get("source_systems")
    if not isinstance(target, dict) or not isinstance(sources, list) or not sources:
        raise InvalidRequestError("The Validation Mapping context is unavailable.")
    source_codes = tuple(
        _required_nested_text(source, "system_code", maximum=100) for source in sources
    )
    if len({normalize_model_key_value(code) for code in source_codes}) != len(source_codes):
        raise InvalidRequestError("The Validation Mapping context is ambiguous.")
    context = ValidationMappingTargetContext(
        object_id=_positive_int(row, "object_id"),
        modeled_entity_type=cast(Any, row.get("modeled_entity_type")),
        modeled_entity_name=_required_text(row, "modeled_entity_name", maximum=255),
        tenant_code=_required_nested_text(target, "tenant_code", maximum=100),
        system_code=_required_nested_text(target, "system_code", maximum=100),
        connection_code=_required_nested_text(target, "connection_code", maximum=100),
        object_schema=_required_nested_text(target, "object_schema", maximum=400),
        object_name=_required_nested_text(target, "object_name", maximum=400),
        source_system_codes=source_codes,
        code_input_digest=_required_digest(row, "code_input_digest"),
        source_context=source_context,
    )
    generated = _generated_code(row, context=context)
    return context.model_copy(update={"generated_code": generated})


def _generated_code(
    row: dict[str, Any],
    *,
    context: ValidationMappingTargetContext,
) -> tuple[ValidationGeneratedCodeArtifact, ...]:
    raw = _JSON_VALUE.validate_python(row.get("generated_code"), strict=True)
    if not isinstance(raw, list) or len(raw) > 5_000:
        raise InvalidRequestError("The Validation Code context is unavailable.")
    records: list[ValidationGeneratedCodeArtifact] = []
    for value in raw:
        if not isinstance(value, dict):
            raise InvalidRequestError("The Validation Code context is unavailable.")
        source_system_codes = value.get("source_system_codes")
        if not isinstance(source_system_codes, list):
            raise InvalidRequestError("The Validation Code context is unavailable.")
        record = ValidationGeneratedCodeArtifact.model_validate(
            {**value, "source_system_codes": tuple(source_system_codes)},
            strict=True,
        )
        if (
            record.modeled_entity_type != context.modeled_entity_type
            or normalize_model_key_value(record.modeled_entity_name)
            != normalize_model_key_value(context.modeled_entity_name)
            or record.generated_code_status != "active"
        ):
            raise InvalidRequestError("The Validation Code context is unavailable.")
        records.append(record)
    return tuple(records)


def _applied_validation(
    rows: list[dict[str, Any]],
    *,
    tenant_code: str,
    selected_systems: frozenset[str],
) -> tuple[
    tuple[ValidationGroupRecord, ...],
    tuple[ValidationCheckRecord, ...],
    dict[tuple[str, str], tuple[str, str | None]],
]:
    normalized_systems = {
        normalize_model_key_value(system_code) for system_code in selected_systems
    }
    groups: dict[tuple[str, str], ValidationGroupRecord] = {}
    checks: dict[tuple[str, str, str], ValidationCheckRecord] = {}
    group_witnesses: dict[tuple[str, str], tuple[str, str | None]] = {}
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
            raise InvalidRequestError("The applied Validation context is ambiguous.")
        mapping_digest = _required_digest(row, "mapping_context_digest")
        code_digest_value = row.get("code_context_digest")
        code_digest = (
            None if code_digest_value is None else _required_digest(row, "code_context_digest")
        )
        prior_witness = group_witnesses.setdefault(
            group_key,
            (mapping_digest, code_digest),
        )
        if prior_witness != (mapping_digest, code_digest):
            raise InvalidRequestError("The applied Validation context is ambiguous.")
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
            raise InvalidRequestError("The applied Validation context is ambiguous.")
        checks[check_key] = check
    if len(groups) > _MAX_APPLIED_GROUPS or len(checks) > _MAX_APPLIED_CHECKS:
        raise InvalidRequestError("The applied Validation context is too large.")
    return tuple(groups.values()), tuple(checks.values()), group_witnesses


def _provider_context(
    *,
    system_ref: str,
    tenant_code: str,
    system_code: str,
    targets: tuple[ValidationMappingTargetContext, ...],
    groups: tuple[ValidationGroupRecord, ...],
    checks: tuple[ValidationCheckRecord, ...],
) -> JsonValue:
    mapping_targets = [
        {
            "modeled_entity_type": target.modeled_entity_type,
            "modeled_entity_name": target.modeled_entity_name,
            "context": target.source_context,
        }
        for target in targets
    ]
    generated_code = [
        artifact.model_dump(mode="json") for target in targets for artifact in target.generated_code
    ]
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "workflow": "validation",
            "system_ref": system_ref,
            "scope": {
                "tenant_code": tenant_code,
                "system_code": system_code,
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
        raise InvalidRequestError("The Validation context is unavailable.")
    return value


def _required_text(row: dict[str, Any], key: str, *, maximum: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InvalidRequestError("The Validation context is unavailable.")
    return value


def _required_nested_text(value: object, key: str, *, maximum: int) -> str:
    if not isinstance(value, dict):
        raise InvalidRequestError("The Validation context is unavailable.")
    item = cast(dict[str, object], value).get(key)
    if not isinstance(item, str) or not item.strip() or len(item) > maximum:
        raise InvalidRequestError("The Validation context is unavailable.")
    return item


def _required_digest(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InvalidRequestError("The Validation context is unavailable.")
    return value
