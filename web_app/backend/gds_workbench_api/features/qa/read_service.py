"""Tenant-fenced QA eligibility and applied-ledger reads."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, LiteralString, Protocol, cast

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import normalize_model_key_value
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction
from gds_etl_workbench.tools.change_sets.model_validation import (
    CodeGenerationTargetContext,
    qa_code_context_digest,
    qa_mapping_context_digest,
)

from gds_workbench_api.features.models import ModelNotFoundError

from .contracts import (
    QAEligibleSystem,
    QAEligibleSystemCollection,
    QALedger,
    QAValidationCheck,
    QAValidationGroup,
)

_MAX_SYSTEMS = 1_000
_MAX_GROUPS = 10_000
_MAX_CHECKS = 50_000
_MAX_CONTEXTS = 50_000
_MAX_LEDGER_BYTES = 32 * 1024 * 1024

_MODEL_HEADER_SQL: LiteralString = """
SELECT target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
"""

_ELIGIBLE_SYSTEMS_SQL: LiteralString = """
WITH target_model AS MATERIALIZED (
    SELECT target_model.model_id,
           target_model.tenant_id
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
), current_context AS MATERIALIZED (
    SELECT context.*
      FROM target_model
      CROSS JOIN LATERAL workflow.list_code_generation_target_context(
          target_model.model_id,
          'logical_entity',
          NULL
      ) AS context
    UNION ALL
    SELECT context.*
      FROM target_model
      CROSS JOIN LATERAL workflow.list_code_generation_target_context(
          target_model.model_id,
          'dimensional_entity',
          NULL
      ) AS context
), expanded AS MATERIALIZED (
    SELECT context.*,
           (source_system.document ->> 'source_system_id')::BIGINT AS source_system_id
      FROM current_context AS context
      CROSS JOIN LATERAL jsonb_array_elements(
          context.source_context -> 'source_systems'
      ) AS source_system(document)
)
SELECT source_system.system_id,
       source_system.system_code,
       source_system.system_name,
       count(DISTINCT (context.modeled_entity_type, context.object_id))::INTEGER
           AS mapping_target_count,
       count(DISTINCT (context.modeled_entity_type, context.object_id)) FILTER (
           WHERE generated.generated_code_id IS NOT NULL
             AND generated.generated_code_status = 'active'
             AND generated.mapping_context_digest = context.mapping_context_digest
             AND generated.source_context_digest = context.source_context_digest
       )::INTEGER AS current_code_target_count,
       EXISTS (
           SELECT 1
             FROM target_model
             JOIN workflow.validation_group AS validation_group
               ON validation_group.model_id = target_model.model_id
              AND validation_group.tenant_id = target_model.tenant_id
              AND validation_group.system_id = source_system.system_id
              AND validation_group.is_active
       ) AS has_applied_qa
  FROM expanded AS context
  JOIN core.system AS source_system
    ON source_system.system_id = context.source_system_id
   AND source_system.is_active
  LEFT JOIN workflow.generated_code AS generated
    ON generated.model_id = context.model_id
   AND generated.object_id = context.object_id
   AND generated.modeled_entity_type = context.modeled_entity_type
 GROUP BY source_system.system_id,
          source_system.system_code,
          source_system.system_name
 ORDER BY lower(btrim(source_system.system_code)),
          source_system.system_id
 LIMIT 1001
"""

_LEDGER_BOUNDS_SQL: LiteralString = """
WITH target_model AS MATERIALIZED (
    SELECT target_model.model_id,
           target_model.tenant_id
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
), group_summary AS (
    SELECT count(*)::INTEGER AS group_count,
           coalesce(sum(
               octet_length(validation_group.validation_group_name)
               + coalesce(
                   octet_length(validation_group.validation_group_description),
                   0
               )
               + 128
           ), 0)::BIGINT AS group_bytes
      FROM target_model
      JOIN workflow.validation_group AS validation_group
        ON validation_group.model_id = target_model.model_id
       AND validation_group.tenant_id = target_model.tenant_id
), check_summary AS (
    SELECT count(*)::INTEGER AS check_count,
           coalesce(sum(
               octet_length(validation_check.validation_check_name)
               + coalesce(
                   octet_length(validation_check.validation_check_description),
                   0
               )
               + octet_length(validation_check.validation_category_code)
               + octet_length(validation_check.validation_severity)
               + octet_length(validation_check.validation_query_sql)
               + coalesce(
                   octet_length(validation_check.validation_comparison_query_sql),
                   0
               )
               + coalesce(
                   octet_length(validation_check.validation_result_data_type),
                   0
               )
               + octet_length(validation_check.validation_comparison_operator)
               + octet_length(validation_check.validation_comparison_value_type)
               + coalesce(
                   octet_length(validation_check.validation_comparison_value::TEXT),
                   0
               )
           ), 0)::BIGINT AS check_bytes
      FROM target_model
      JOIN workflow.validation_group AS validation_group
        ON validation_group.model_id = target_model.model_id
       AND validation_group.tenant_id = target_model.tenant_id
      JOIN workflow.validation_check AS validation_check
        ON validation_check.validation_group_id =
           validation_group.validation_group_id
)
SELECT group_summary.group_count,
       check_summary.check_count,
       group_summary.group_bytes + check_summary.check_bytes AS ledger_bytes
  FROM group_summary
  CROSS JOIN check_summary
"""

_LEDGER_GROUPS_SQL: LiteralString = """
SELECT validation_group.validation_group_id,
       validation_group.system_id,
       source_system.system_code,
       validation_group.validation_group_name,
       validation_group.validation_group_description,
       btrim(validation_group.mapping_context_digest::TEXT)
           AS mapping_context_digest,
       btrim(validation_group.code_context_digest::TEXT) AS code_context_digest,
       validation_group.is_active
  FROM model.model AS target_model
  JOIN workflow.validation_group AS validation_group
    ON validation_group.model_id = target_model.model_id
   AND validation_group.tenant_id = target_model.tenant_id
  JOIN core.system AS source_system
    ON source_system.system_id = validation_group.system_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
 ORDER BY lower(btrim(source_system.system_code)),
          validation_group.system_id,
          lower(btrim(validation_group.validation_group_name)),
          validation_group.validation_group_id
"""

_LEDGER_CHECKS_SQL: LiteralString = """
SELECT validation_group.validation_group_id,
       validation_check.validation_check_id,
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
  FROM model.model AS target_model
  JOIN workflow.validation_group AS validation_group
    ON validation_group.model_id = target_model.model_id
   AND validation_group.tenant_id = target_model.tenant_id
  JOIN core.system AS source_system
    ON source_system.system_id = validation_group.system_id
  JOIN workflow.validation_check AS validation_check
    ON validation_check.validation_group_id = validation_group.validation_group_id
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
 ORDER BY lower(btrim(source_system.system_code)),
          validation_group.system_id,
          lower(btrim(validation_group.validation_group_name)),
          validation_group.validation_group_id,
          lower(btrim(validation_check.validation_check_name)),
          validation_check.validation_check_id
"""

_CURRENT_CONTEXT_SQL: LiteralString = """
WITH target_model AS MATERIALIZED (
    SELECT target_model.model_id
      FROM model.model AS target_model
     WHERE target_model.tenant_id = %s
       AND target_model.model_id = %s
       AND target_model.is_active
), group_system AS MATERIALIZED (
    SELECT DISTINCT validation_group.system_id
      FROM target_model
      JOIN workflow.validation_group AS validation_group
        ON validation_group.model_id = target_model.model_id
), current_context AS MATERIALIZED (
    SELECT context.*
      FROM target_model
      CROSS JOIN LATERAL workflow.list_code_generation_target_context(
          target_model.model_id,
          'logical_entity',
          NULL
      ) AS context
    UNION ALL
    SELECT context.*
      FROM target_model
      CROSS JOIN LATERAL workflow.list_code_generation_target_context(
          target_model.model_id,
          'dimensional_entity',
          NULL
      ) AS context
)
SELECT context.object_id,
       context.modeled_entity_type,
       context.source_context -> 'target' ->> 'tenant_code' AS tenant_code,
       context.source_context -> 'target' ->> 'system_code' AS system_code,
       context.source_context -> 'target' ->> 'connection_code' AS connection_code,
       context.source_context -> 'target' ->> 'object_schema' AS object_schema,
       context.source_context -> 'target' ->> 'object_name' AS object_name,
       source_system.source_system_codes,
       btrim(context.mapping_context_digest::TEXT) AS mapping_context_digest,
       btrim(context.source_context_digest::TEXT) AS source_context_digest,
       generated.artifact_type,
       btrim(generated.mapping_context_digest::TEXT)
           AS generated_mapping_context_digest,
       btrim(generated.source_context_digest::TEXT)
           AS generated_source_context_digest,
       btrim(generated.generated_code_digest::TEXT) AS generated_code_digest,
       generated.generated_code_status
  FROM current_context AS context
  CROSS JOIN LATERAL (
      SELECT jsonb_agg(
                 source_entry.document ->> 'system_code'
                 ORDER BY source_entry.position
             ) AS source_system_codes
        FROM jsonb_array_elements(
                 context.source_context -> 'source_systems'
             ) WITH ORDINALITY AS source_entry(document, position)
  ) AS source_system
  LEFT JOIN workflow.generated_code AS generated
    ON generated.model_id = context.model_id
   AND generated.object_id = context.object_id
   AND generated.modeled_entity_type = context.modeled_entity_type
 WHERE EXISTS (
       SELECT 1
         FROM jsonb_array_elements(
             context.source_context -> 'source_systems'
         ) AS source_system(document)
         JOIN group_system
           ON group_system.system_id =
              (source_system.document ->> 'source_system_id')::BIGINT
   )
 ORDER BY context.modeled_entity_type,
          context.object_id
 LIMIT 50001
"""


class QAReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class QAReadService(Protocol):
    async def list_eligible_systems(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> QAEligibleSystemCollection: ...

    async def read_ledger(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> QALedger: ...


class DatabaseQAReadService:
    def __init__(
        self,
        *,
        database: QAReadDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def list_eligible_systems(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> QAEligibleSystemCollection:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            rows = await transaction.fetch_all(
                _ELIGIBLE_SYSTEMS_SQL,
                (tenant_id, model_id),
            )
        return QAEligibleSystemCollection(
            model_id=model_id,
            model_revision=header["model_revision"],
            items=tuple(
                QAEligibleSystem.model_validate(row, strict=False) for row in rows[:_MAX_SYSTEMS]
            ),
            is_truncated=len(rows) > _MAX_SYSTEMS,
        )

    async def read_ledger(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> QALedger:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            header = await transaction.fetch_one(_MODEL_HEADER_SQL, (tenant_id, model_id))
            if header is None:
                raise ModelNotFoundError()
            bounds = await transaction.fetch_one(
                _LEDGER_BOUNDS_SQL,
                (tenant_id, model_id),
            )
            if bounds is None or (
                _bounded_nonnegative_int(bounds, "group_count") > _MAX_GROUPS
                or _bounded_nonnegative_int(bounds, "check_count") > _MAX_CHECKS
                or _bounded_nonnegative_int(bounds, "ledger_bytes") > _MAX_LEDGER_BYTES
            ):
                raise InvalidRequestError("The QA ledger exceeds its bounded size.")
            group_rows = await transaction.fetch_all(
                _LEDGER_GROUPS_SQL,
                (tenant_id, model_id),
            )
            check_rows = await transaction.fetch_all(
                _LEDGER_CHECKS_SQL,
                (tenant_id, model_id),
            )
            context_rows = await transaction.fetch_all(
                _CURRENT_CONTEXT_SQL,
                (tenant_id, model_id),
            )
        groups = _assemble_ledger_groups(
            group_rows=group_rows,
            check_rows=check_rows,
            context_rows=context_rows,
        )
        return QALedger(
            model_id=model_id,
            model_revision=header["model_revision"],
            groups=groups,
        )


def _assemble_ledger_groups(
    *,
    group_rows: list[dict[str, Any]],
    check_rows: list[dict[str, Any]],
    context_rows: list[dict[str, Any]],
) -> tuple[QAValidationGroup, ...]:
    if (
        len(group_rows) > _MAX_GROUPS
        or len(check_rows) > _MAX_CHECKS
        or len(context_rows) > _MAX_CONTEXTS
    ):
        raise InvalidRequestError("The QA ledger exceeds its bounded size.")
    digest_contexts, generated_code = _ledger_digest_context(context_rows)
    target_keys = [(target.object_key, target.modeled_entity_type) for target in digest_contexts]
    if len(target_keys) != len(set(target_keys)):
        raise InvalidRequestError("The current QA context is ambiguous.")

    groups_by_id: dict[int, dict[str, Any]] = {}
    checks: dict[int, list[QAValidationCheck]] = {}
    check_ids: set[int] = set()
    for row in group_rows:
        group_id = _positive_int(row, "validation_group_id")
        if group_id in groups_by_id:
            raise InvalidRequestError("The QA ledger is ambiguous.")
        groups_by_id[group_id] = row
    for row in check_rows:
        group_id = _positive_int(row, "validation_group_id")
        if group_id not in groups_by_id:
            raise InvalidRequestError("The QA ledger is ambiguous.")
        check_id = row.get("validation_check_id")
        if isinstance(check_id, bool) or not isinstance(check_id, int) or check_id <= 0:
            raise InvalidRequestError("The QA ledger is invalid.")
        if check_id in check_ids:
            raise InvalidRequestError("The QA ledger is ambiguous.")
        check_ids.add(check_id)
        checks.setdefault(group_id, []).append(
            QAValidationCheck.model_validate(
                {
                    "validation_check_id": check_id,
                    "validation_check_name": row.get("validation_check_name"),
                    "validation_check_description": row.get("validation_check_description"),
                    "validation_category_code": row.get("validation_category_code"),
                    "validation_severity": row.get("validation_severity"),
                    "validation_query_sql": row.get("validation_query_sql"),
                    "validation_comparison_query_sql": row.get("validation_comparison_query_sql"),
                    "validation_result_data_type": row.get("validation_result_data_type"),
                    "validation_comparison_operator": row.get("validation_comparison_operator"),
                    "validation_comparison_value_type": row.get("validation_comparison_value_type"),
                    "validation_comparison_value": row.get("validation_comparison_value"),
                    "is_active": row.get("validation_check_is_active"),
                },
                strict=False,
            )
        )
    if len(groups_by_id) > _MAX_GROUPS or len(check_ids) > _MAX_CHECKS:
        raise InvalidRequestError("The QA ledger exceeds its bounded size.")

    current_digests: dict[str, tuple[str | None, str | None]] = {}
    groups: list[QAValidationGroup] = []
    for group_id, row in groups_by_id.items():
        system_code = row.get("system_code")
        if not isinstance(system_code, str) or not system_code.strip():
            raise InvalidRequestError("The QA ledger is invalid.")
        normalized = normalize_model_key_value(system_code)
        if normalized not in current_digests:
            current_digests[normalized] = (
                qa_mapping_context_digest(digest_contexts, system_code),
                qa_code_context_digest(digest_contexts, generated_code, system_code),
            )
        current_mapping, current_code = current_digests[normalized]
        stored_mapping = row.get("mapping_context_digest")
        stored_code = row.get("code_context_digest")
        mapping_is_current = current_mapping is not None and stored_mapping == current_mapping
        code_is_current = current_mapping is not None and stored_code == current_code
        is_active = row.get("is_active") is True
        groups.append(
            QAValidationGroup.model_validate(
                {
                    **row,
                    "current_mapping_context_digest": current_mapping,
                    "current_code_context_digest": current_code,
                    "mapping_context_is_current": mapping_is_current,
                    "code_context_is_current": code_is_current,
                    "validation_group_is_current": (
                        is_active and mapping_is_current and code_is_current
                    ),
                    "checks": tuple(checks.get(group_id, ())),
                },
                strict=False,
            )
        )
    return tuple(groups)


def _positive_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidRequestError("The QA ledger is invalid.")
    return value


@dataclass(frozen=True, slots=True)
class _GeneratedCodeDigestRecord:
    tenant_code: str
    system_code: str
    connection_code: str
    object_schema: str
    object_name: str
    modeled_entity_type: str
    artifact_type: str
    mapping_context_digest: str
    source_context_digest: str
    generated_code_digest: str
    generated_code_status: str


def _ledger_digest_context(
    rows: list[dict[str, Any]],
) -> tuple[
    tuple[CodeGenerationTargetContext, ...],
    tuple[_GeneratedCodeDigestRecord, ...],
]:
    contexts: list[CodeGenerationTargetContext] = []
    generated: list[_GeneratedCodeDigestRecord] = []
    for row in rows:
        modeled_entity_type = _required_text(row, "modeled_entity_type", maximum=30)
        if modeled_entity_type not in {"logical_entity", "dimensional_entity"}:
            raise InvalidRequestError("The current QA context is invalid.")
        object_key = (
            _required_text(row, "tenant_code", maximum=100),
            _required_text(row, "system_code", maximum=100),
            _required_text(row, "connection_code", maximum=100),
            _required_text(row, "object_schema", maximum=400),
            _required_text(row, "object_name", maximum=400),
        )
        raw_sources = row.get("source_system_codes")
        if not isinstance(raw_sources, list):
            raise InvalidRequestError("The current QA context is invalid.")
        source_objects = cast(list[object], raw_sources)
        if not 1 <= len(source_objects) <= _MAX_SYSTEMS or any(
            not isinstance(value, str) or not value.strip() or len(value) > 100
            for value in source_objects
        ):
            raise InvalidRequestError("The current QA context is invalid.")
        source_values = cast(list[str], source_objects)
        source_codes = frozenset(source_values)
        normalized_source_codes = {normalize_model_key_value(value) for value in source_values}
        if len(normalized_source_codes) != len(source_values):
            raise InvalidRequestError("The current QA context is ambiguous.")
        mapping_digest = _required_digest(row, "mapping_context_digest")
        source_digest = _required_digest(row, "source_context_digest")
        contexts.append(
            CodeGenerationTargetContext(
                object_key=object_key,
                modeled_entity_type=modeled_entity_type,
                source_system_codes=source_codes,
                mapping_context_digest=mapping_digest,
                source_context_digest=source_digest,
            )
        )
        generated_values = (
            row.get("artifact_type"),
            row.get("generated_mapping_context_digest"),
            row.get("generated_source_context_digest"),
            row.get("generated_code_digest"),
            row.get("generated_code_status"),
        )
        if all(value is None for value in generated_values):
            continue
        if any(value is None for value in generated_values):
            raise InvalidRequestError("The current QA Code context is invalid.")
        generated.append(
            _GeneratedCodeDigestRecord(
                tenant_code=object_key[0],
                system_code=object_key[1],
                connection_code=object_key[2],
                object_schema=object_key[3],
                object_name=object_key[4],
                modeled_entity_type=modeled_entity_type,
                artifact_type=_required_text(row, "artifact_type", maximum=30),
                mapping_context_digest=_required_digest(
                    row,
                    "generated_mapping_context_digest",
                ),
                source_context_digest=_required_digest(
                    row,
                    "generated_source_context_digest",
                ),
                generated_code_digest=_required_digest(row, "generated_code_digest"),
                generated_code_status=_required_text(
                    row,
                    "generated_code_status",
                    maximum=20,
                ),
            )
        )
    return tuple(contexts), tuple(generated)


def _bounded_nonnegative_int(row: dict[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidRequestError("The QA ledger bounds are unavailable.")
    return value


def _required_text(row: dict[str, Any], key: str, *, maximum: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise InvalidRequestError("The current QA context is invalid.")
    return value


def _required_digest(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if (
        not isinstance(value, str)
        or len(value.strip()) != 64
        or any(character not in "0123456789abcdef" for character in value.strip())
    ):
        raise InvalidRequestError("The current QA context is invalid.")
    return value.strip()


__all__ = ["DatabaseQAReadService", "QAReadDatabase", "QAReadService"]
