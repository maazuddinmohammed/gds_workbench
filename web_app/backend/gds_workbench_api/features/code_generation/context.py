"""Bounded Mapping and artifact context for SQL-only Code Generation."""

from __future__ import annotations

from typing import Any, LiteralString, Protocol, cast

from gds_etl_workbench.application.change_sets.model_validation import PhysicalModelCatalog
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
)
from gds_etl_workbench.domain.snapshots.model import ModelSnapshot
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

from gds_workbench_api.features.workflows.authoring.context import (
    load_frozen_model_graph,
    reject_forbidden_provider_json,
)
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan

from .artifact_context import CodeGenerationArtifactContext

_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

_CONTEXT_SQL: LiteralString = """
WITH requested_run AS MATERIALIZED (
    SELECT run.workflow_run_id,
           run.model_id,
           run.modeled_entity_type
      FROM application.workflow_run AS run
      JOIN model.model AS target_model
        ON target_model.model_id = run.model_id
       AND target_model.tenant_id = %s
       AND target_model.is_active
     WHERE run.model_id = %s
       AND run.workflow_run_id = %s
       AND run.model_revision = target_model.model_revision
       AND target_model.model_revision = %s
       AND run.model_workflow = 'code_generation'
       AND run.workflow_run_state = 'running'
       AND run.modeled_entity_type = %s
), selected AS MATERIALIZED (
    SELECT selection.modeled_entity_id,
           selection.selection_order
      FROM requested_run AS run
      JOIN application.workflow_run_entity_selection AS selection
        ON selection.workflow_run_id = run.workflow_run_id
       AND selection.model_id = run.model_id
)
SELECT target.modeled_entity_id,
       target.modeled_entity_schema_name,
       target.source_system_count,
       target.code_input_digest,
       jsonb_array_length(target.source_context -> 'object_mappings')
           AS mapping_count,
       jsonb_array_length(target.source_context -> 'attribute_mappings')
           AS attribute_mapping_count,
       target.source_context,
       applied.applied_artifacts
  FROM requested_run AS run
  JOIN selected
    ON TRUE
  JOIN workflow.list_code_generation_target_context(
           run.model_id,
           run.modeled_entity_type
       ) AS target
    ON target.modeled_entity_id = selected.modeled_entity_id
  LEFT JOIN LATERAL (
      SELECT coalesce(
                 jsonb_agg(
                     jsonb_build_object(
                         'modeled_entity_type', run.modeled_entity_type,
                         'modeled_entity_schema_name', target.modeled_entity_schema_name,
                         'modeled_entity_name',
                             target.source_context -> 'object_mappings' -> 0
                             -> 'entity' ->> 'entity_name',
                         'artifact_name', generated.artifact_name,
                         'artifact_type', generated.artifact_type,
                         'generated_code_content',
                             generated.generated_code_content,
                         'generated_code_is_locked', generated.generated_code_is_locked,
                         'generated_code_status',
                             generated.generated_code_status,
                         '_is_current',
                             generated.code_input_digest = target.code_input_digest,
                         'source_systems', association.source_systems
                     ) ORDER BY lower(btrim(generated.artifact_name)),
                                generated.generated_code_id
                 ),
                 '[]'::JSONB
             ) AS applied_artifacts
        FROM workflow.generated_code AS generated
       CROSS JOIN LATERAL (
           SELECT coalesce(
                      jsonb_agg(
                          jsonb_build_object(
                              'source_system_code', system.system_code,
                              'generated_code_source_system_is_locked',
                                  source.generated_code_source_system_is_locked,
                              'generated_code_source_system_status',
                                  source.generated_code_source_system_status
                          ) ORDER BY lower(btrim(system.system_code)),
                                     source.generated_code_source_system_id
                      ),
                      '[]'::JSONB
                  ) AS source_systems
             FROM workflow.generated_code_source_system AS source
             JOIN core.system AS system
               ON system.system_id = source.source_system_id
            WHERE source.generated_code_id = generated.generated_code_id
       ) AS association
       WHERE generated.model_id = run.model_id
         AND generated.modeled_entity_type = run.modeled_entity_type
         AND coalesce(generated.logical_entity_id, generated.dimensional_entity_id) =
             target.modeled_entity_id
  ) AS applied ON TRUE
 ORDER BY selected.selection_order
"""


class CodeGenerationContextTransaction(Protocol):
    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]: ...


class CodeGenerationExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    targets: tuple[CodeGenerationArtifactContext, ...] = Field(
        min_length=1,
    )
    agent_context: JsonValue = Field(repr=False)
    snapshot: ModelSnapshot | None = Field(default=None, repr=False, exclude=True)
    physical_scope: PhysicalModelCatalog | None = Field(default=None, repr=False, exclude=True)


class PostgresCodeGenerationContextRepository:
    async def load(
        self,
        transaction: CodeGenerationContextTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> CodeGenerationExecutionContext:
        if plan.model_workflow != "code_generation" or plan.modeled_entity_type is None:
            raise InvalidRequestError("The Code Generation run plan is invalid.")
        rows = await transaction.fetch_all(
            _CONTEXT_SQL,
            (
                tenant_id,
                plan.model_id,
                plan.workflow_run_id,
                plan.model_revision,
                plan.modeled_entity_type,
            ),
        )
        try:
            context = _assemble_context(plan=plan, rows=rows)
            snapshot, physical_scope = await load_frozen_model_graph(
                cast(ReadTransaction, transaction),
                tenant_id=tenant_id,
                plan=plan,
            )
            return context.model_copy(
                update={"snapshot": snapshot, "physical_scope": physical_scope}
            )
        except InvalidRequestError:
            raise
        except TypeError, ValueError, ValidationError:
            raise InvalidRequestError("The Code Generation context is unavailable.") from None


def _assemble_context(
    *,
    plan: AgentRunPlan,
    rows: list[dict[str, Any]],
) -> CodeGenerationExecutionContext:
    modeled_entity_type = plan.modeled_entity_type
    if modeled_entity_type is None:
        raise InvalidRequestError("The Code Generation run plan is invalid.")
    if not rows:
        raise InvalidRequestError("The Code Generation Mapping context is incomplete.")
    rows.sort(key=lambda row: _positive_int(row, "modeled_entity_id"))
    identities = [_positive_int(row, "modeled_entity_id") for row in rows]
    if len(identities) != len(set(identities)):
        raise InvalidRequestError("The Code Generation Mapping context is ambiguous.")
    if set(identities) != set(plan.selected_entity_ids):
        raise InvalidRequestError("The Code Generation Mapping context is incomplete.")

    targets: list[CodeGenerationArtifactContext] = []
    agent_targets: list[dict[str, JsonValue]] = []
    for position, row in enumerate(rows, start=1):
        mapping_count = _positive_int(row, "mapping_count")
        attribute_count = _nonnegative_int(row, "attribute_mapping_count")
        source_system_count = _positive_int(row, "source_system_count")
        source_context = _JSON_VALUE.validate_python(row.get("source_context"), strict=True)
        if not isinstance(source_context, dict):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        source_systems = source_context.get("source_systems")
        object_mappings = source_context.get("object_mappings")
        attribute_mappings = source_context.get("attribute_mappings")
        if (
            not isinstance(source_systems, list)
            or len(source_systems) != source_system_count
            or not isinstance(object_mappings, list)
            or len(object_mappings) != mapping_count
            or not isinstance(attribute_mappings, list)
            or len(attribute_mappings) != attribute_count
        ):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        source_system_codes = _source_system_codes(source_systems)
        modeled_entity_name = _modeled_entity_name(
            object_mappings,
            modeled_entity_type=modeled_entity_type,
        )
        reject_forbidden_provider_json(
            source_context,
            allow_identity_keys=True,
            reject_sensitive_values=True,
        )
        schema_name = row.get("modeled_entity_schema_name")
        if not isinstance(schema_name, str) or not schema_name.strip() or len(schema_name) > 400:
            raise InvalidRequestError("The Code Generation Entity schema is unavailable.")
        for mapping in object_mappings:
            entity = mapping.get("entity") if isinstance(mapping, dict) else None
            if not isinstance(entity, dict) or entity.get("entity_schema_name") != schema_name:
                raise InvalidRequestError("The Code Generation Entity schema is ambiguous.")
        target_ref = f"target_{position}"
        applied_code, applied_systems, current_artifact_names = _applied_generated_code(
            row,
            modeled_entity_type=modeled_entity_type,
            modeled_entity_schema_name=schema_name,
            modeled_entity_name=modeled_entity_name,
        )
        selected_codes = {code.strip().casefold() for code in plan.selected_system_codes}
        selected_codes = selected_codes or {code.strip().casefold() for code in source_system_codes}
        all_source_codes = {code.strip().casefold() for code in source_system_codes}
        source_system_codes = tuple(
            code for code in source_system_codes if code.strip().casefold() in selected_codes
        )
        if not source_system_codes:
            raise InvalidRequestError("A selected Entity has no Mapping for the selected Systems.")
        selected_codes = {code.strip().casefold() for code in source_system_codes}
        preserved_names: set[str] = set()
        for artifact in applied_code:
            name = artifact.artifact_name.strip().casefold()
            assignments = [
                item
                for item in applied_systems
                if item.artifact_name.strip().casefold() == name
                and item.generated_code_source_system_status == "active"
            ]
            assigned_codes = {item.source_system_code.strip().casefold() for item in assignments}
            if (
                artifact.generated_code_is_locked
                or any(item.generated_code_source_system_is_locked for item in assignments)
                # Retire obsolete assignments with their unlocked file; only still
                # eligible Systems can make a combined file partially selected.
                or (assigned_codes and not (assigned_codes & all_source_codes) <= selected_codes)
                or (not assigned_codes and selected_codes != all_source_codes)
            ):
                preserved_names.add(name)
                if artifact.generated_code_status == "active" and assigned_codes & selected_codes:
                    raise InvalidRequestError(
                        "Selected Systems share a locked or partially selected SQL file. "
                        "Unlock the file or select all of its Systems before regenerating."
                    )
        if plan.selected_system_codes:
            system_ids = {
                cast(int, item["source_system_id"])
                for item in source_systems
                if isinstance(item, dict)
                and str(item.get("system_code", "")).strip().casefold() in selected_codes
            }
            source_context = {
                **source_context,
                "source_systems": [
                    item
                    for item in source_systems
                    if isinstance(item, dict) and item.get("source_system_id") in system_ids
                ],
                "object_mappings": [
                    item
                    for item in object_mappings
                    if isinstance(item, dict) and item.get("source_system_id") in system_ids
                ],
                "attribute_mappings": [
                    item
                    for item in attribute_mappings
                    if isinstance(item, dict) and item.get("source_system_id") in system_ids
                ],
                "physical_sources": [
                    item
                    for item in cast(
                        list[dict[str, JsonValue]], source_context.get("physical_sources", [])
                    )
                    if item.get("selected_source_system_id") in system_ids
                ],
            }
            used_templates = {
                code
                for component in ("object_mappings", "attribute_mappings")
                for item in cast(list[dict[str, JsonValue]], source_context[component])
                if isinstance(code := item.get("output_template_code"), str)
            }
            source_context["mapping_templates"] = [
                item
                for item in cast(
                    list[dict[str, JsonValue]], source_context.get("mapping_templates", [])
                )
                if isinstance(code := item.get("code"), str) and code in used_templates
            ]
        applied_code = tuple(
            item
            for item in applied_code
            if item.artifact_name.strip().casefold() not in preserved_names
        )
        applied_systems = tuple(
            item
            for item in applied_systems
            if item.artifact_name.strip().casefold() not in preserved_names
        )
        provider_context = cast(
            JsonValue,
            {
                **source_context,
                "artifact_requirements": {
                    "source_system_codes": list(source_system_codes),
                    "file_layout": plan.code_generation_file_layout or "combined",
                    "preserved_artifact_names": sorted(preserved_names),
                },
            },
        )
        context = CodeGenerationArtifactContext(
            target_ref=target_ref,
            modeled_entity_id=_positive_int(row, "modeled_entity_id"),
            code_input_digest=_required_digest(row, "code_input_digest"),
            modeled_entity_type=modeled_entity_type,
            modeled_entity_schema_name=schema_name,
            modeled_entity_name=modeled_entity_name,
            source_system_codes=source_system_codes,
            preserved_artifact_names=tuple(sorted(preserved_names)),
            applied_generated_code=applied_code,
            applied_generated_code_source_systems=applied_systems,
            current_artifact_names=current_artifact_names,
        )
        targets.append(context)
        agent_targets.append(
            {
                "target_ref": target_ref,
                "context": provider_context,
            }
        )
    agent_context = cast(JsonValue, {"targets": agent_targets})
    return CodeGenerationExecutionContext(
        targets=tuple(targets),
        agent_context=agent_context,
    )


def _positive_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidRequestError("The Code Generation context is unavailable.")
    return value


def _nonnegative_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidRequestError("The Code Generation context is unavailable.")
    return value


def _required_digest(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not _is_sha256_digest(value):
        raise InvalidRequestError("The Code Generation context is unavailable.")
    return value


def _applied_generated_code(
    row: dict[str, Any],
    *,
    modeled_entity_type: str,
    modeled_entity_schema_name: str,
    modeled_entity_name: str,
) -> tuple[
    tuple[GeneratedCodeRecord, ...],
    tuple[GeneratedCodeSourceSystemRecord, ...],
    tuple[str, ...],
]:
    raw = _JSON_VALUE.validate_python(row.get("applied_artifacts"), strict=True)
    if not isinstance(raw, list) or len(raw) > 5_000:
        raise InvalidRequestError("The Code Generation context is unavailable.")
    artifacts: list[GeneratedCodeRecord] = []
    systems: list[GeneratedCodeSourceSystemRecord] = []
    current_artifact_names: list[str] = []
    for value in raw:
        if not isinstance(value, dict):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        artifact = GeneratedCodeRecord.model_validate(
            {name: value.get(name) for name in GeneratedCodeRecord.model_fields},
            strict=True,
        )
        if (
            artifact.modeled_entity_type != modeled_entity_type
            or artifact.modeled_entity_schema_name != modeled_entity_schema_name
            or artifact.modeled_entity_name != modeled_entity_name
        ):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        artifacts.append(artifact)
        is_current = value.get("_is_current")
        if not isinstance(is_current, bool):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        if is_current:
            current_artifact_names.append(artifact.artifact_name)
        raw_systems = value.get("source_systems")
        if not isinstance(raw_systems, list):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        for source in raw_systems:
            if not isinstance(source, dict):
                raise InvalidRequestError("The Code Generation context is unavailable.")
            systems.append(
                GeneratedCodeSourceSystemRecord.model_validate(
                    {
                        "modeled_entity_type": modeled_entity_type,
                        "modeled_entity_schema_name": modeled_entity_schema_name,
                        "modeled_entity_name": modeled_entity_name,
                        "artifact_name": artifact.artifact_name,
                        "source_system_code": source.get("source_system_code"),
                        "generated_code_source_system_is_locked": source.get(
                            "generated_code_source_system_is_locked"
                        ),
                        "generated_code_source_system_status": source.get(
                            "generated_code_source_system_status"
                        ),
                    },
                    strict=True,
                )
            )
    if len(systems) > 50_000:
        raise InvalidRequestError("The Code Generation context is unavailable.")
    return tuple(artifacts), tuple(systems), tuple(current_artifact_names)


def _source_system_codes(source_systems: list[JsonValue]) -> tuple[str, ...]:
    values: list[str] = []
    for source in source_systems:
        if not isinstance(source, dict):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        code = source.get("system_code")
        if not isinstance(code, str) or not code.strip() or len(code) > 100:
            raise InvalidRequestError("The Code Generation context is unavailable.")
        values.append(code)
    normalized = tuple(value.strip().casefold() for value in values)
    if len(normalized) != len(set(normalized)):
        raise InvalidRequestError("The Code Generation context is unavailable.")
    return tuple(values)


def _modeled_entity_name(
    object_mappings: list[JsonValue],
    *,
    modeled_entity_type: str,
) -> str:
    values: list[str] = []
    for mapping in object_mappings:
        if not isinstance(mapping, dict):
            raise InvalidRequestError("The Code Generation context is unavailable.")
        entity = mapping.get("entity")
        if not isinstance(entity, dict) or entity.get("entity_type") != modeled_entity_type:
            raise InvalidRequestError("The Code Generation context is unavailable.")
        name = entity.get("entity_name")
        if not isinstance(name, str) or not name.strip() or len(name) > 255:
            raise InvalidRequestError("The Code Generation context is unavailable.")
        values.append(name)
    normalized = {value.strip().casefold() for value in values}
    if len(normalized) != 1:
        raise InvalidRequestError("The Code Generation context is unavailable.")
    return values[0]


def _is_sha256_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
