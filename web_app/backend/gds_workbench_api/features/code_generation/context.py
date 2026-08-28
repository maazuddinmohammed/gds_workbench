"""Bounded Mapping and guide context for SQL-only Code Generation."""

from __future__ import annotations

import json
from typing import Any, LiteralString, Protocol, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, ValidationError

from gds_workbench_api.features.workflows.authoring.context import (
    reject_forbidden_provider_json,
)
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan

from .storage import CodeGenerationArtifactContext

_MAX_OBJECT_MAPPINGS = 200
_MAX_ATTRIBUTE_MAPPINGS = 5_000
_MAX_CONTEXT_BYTES = 10 * 1024 * 1024
_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

_CONTEXT_SQL: LiteralString = """
WITH requested_run AS MATERIALIZED (
    SELECT run.workflow_run_id,
           run.model_id,
           run.modeled_entity_type,
           run.sql_generation_guide_id,
           run.sql_generation_guide_version_id,
           run.sql_generation_guide_digest
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
    SELECT selection.object_id,
           selection.selection_order
      FROM requested_run AS run
      JOIN application.workflow_run_object_selection AS selection
        ON selection.workflow_run_id = run.workflow_run_id
       AND selection.model_id = run.model_id
)
SELECT target.object_id,
       target.source_system_count,
       target.mapping_context_digest,
       target.source_context_digest,
       run.sql_generation_guide_version_id,
       jsonb_array_length(target.source_context -> 'object_mappings')
           AS mapping_count,
       jsonb_array_length(target.source_context -> 'attribute_mappings')
           AS attribute_mapping_count,
       target.source_context,
       jsonb_build_object(
           'guide_code', guide.sql_generation_guide_code,
           'guide_name', guide.sql_generation_guide_name,
           'version_number', version.sql_generation_guide_version_number,
           'content', version.sql_generation_guide_content
       ) AS guide_document
  FROM requested_run AS run
  JOIN selected
    ON TRUE
  JOIN workflow.list_code_generation_target_context(
           run.model_id,
           run.modeled_entity_type
       ) AS target
    ON target.object_id = selected.object_id
  JOIN application.sql_generation_guide_version AS version
    ON version.sql_generation_guide_version_id =
       run.sql_generation_guide_version_id
   AND version.sql_generation_guide_id = run.sql_generation_guide_id
   AND version.sql_generation_guide_digest = run.sql_generation_guide_digest
  JOIN application.sql_generation_guide AS guide
    ON guide.sql_generation_guide_id = run.sql_generation_guide_id
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
        max_length=50_000,
    )
    agent_context: JsonValue = Field(repr=False)


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
            return _assemble_context(plan=plan, rows=rows)
        except InvalidRequestError:
            raise
        except (TypeError, ValueError, ValidationError):
            raise InvalidRequestError("The Code Generation context is unavailable.") from None


def _assemble_context(
    *,
    plan: AgentRunPlan,
    rows: list[dict[str, Any]],
) -> CodeGenerationExecutionContext:
    if not rows:
        raise InvalidRequestError("The Code Generation Mapping context is incomplete.")
    rows.sort(key=lambda row: _positive_int(row, "object_id"))
    identities = [_positive_int(row, "object_id") for row in rows]
    if len(identities) != len(set(identities)):
        raise InvalidRequestError("The Code Generation Mapping context is ambiguous.")
    if set(identities) != set(plan.selected_object_ids):
        raise InvalidRequestError("The Code Generation Mapping context is incomplete.")

    targets: list[CodeGenerationArtifactContext] = []
    agent_targets: list[dict[str, JsonValue]] = []
    for position, row in enumerate(rows, start=1):
        mapping_count = _positive_int(row, "mapping_count")
        attribute_count = _nonnegative_int(row, "attribute_mapping_count")
        source_system_count = _positive_int(row, "source_system_count")
        if mapping_count > _MAX_OBJECT_MAPPINGS or attribute_count > _MAX_ATTRIBUTE_MAPPINGS:
            raise InvalidRequestError("The Code Generation context exceeds bounded collections.")
        source_context = _JSON_VALUE.validate_python(row.get("source_context"), strict=True)
        guide_document = _JSON_VALUE.validate_python(
            row.get("guide_document"),
            strict=True,
        )
        if not isinstance(source_context, dict) or not isinstance(guide_document, dict):
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
        reject_forbidden_provider_json(
            source_context,
            allow_identity_keys=True,
            reject_sensitive_values=True,
        )
        reject_forbidden_provider_json(
            guide_document,
            allow_identity_keys=True,
            reject_sensitive_values=True,
        )
        provider_context = cast(
            JsonValue,
            {**source_context, "guide": guide_document},
        )
        target_ref = f"target_{position}"
        context = CodeGenerationArtifactContext(
            target_ref=target_ref,
            object_id=_positive_int(row, "object_id"),
            mapping_context_digest=_required_digest(row, "mapping_context_digest"),
            source_context_digest=_required_digest(row, "source_context_digest"),
            sql_generation_guide_version_id=_positive_int(
                row,
                "sql_generation_guide_version_id",
            ),
        )
        targets.append(context)
        agent_targets.append(
            {
                "target_ref": target_ref,
                "context": provider_context,
            }
        )
    agent_context = cast(JsonValue, {"targets": agent_targets})
    if len(_canonical_json(agent_context)) > _MAX_CONTEXT_BYTES:
        raise InvalidRequestError("The Code Generation context exceeds its bounded size.")
    return CodeGenerationExecutionContext(
        targets=tuple(targets),
        agent_context=agent_context,
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


def _is_sha256_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
