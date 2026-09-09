"""Prepare additive Input Scope changes from visible, registered Object IDs."""

from typing import Annotated, LiteralString

from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_validation import (
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import read_model_review_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.metadata_visibility import VISIBLE_OBJECTS_CTE
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AddInputScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)
    object_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1, max_length=200)

    @field_validator("object_ids")
    @classmethod
    def unique_objects(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("Select each Object once.")
        return sorted(value)


_SCOPE_OBJECTS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT placement.tenant_code, system.system_code, connection.connection_code,
       object.object_schema, object.object_name,
       coalesce(scope.model_input_scope_is_locked, FALSE) AS model_input_scope_is_locked,
       TRUE AS is_active
  FROM visible_objects AS visible
  JOIN core.object AS object ON object.object_id = visible.object_id
  JOIN core.connection AS connection ON connection.connection_id = object.connection_id
  JOIN core.tenant AS placement ON placement.tenant_id = connection.tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
  JOIN reference.zone AS zone ON zone.zone_id = object.zone_id
  LEFT JOIN model.model_input_scope AS scope
    ON scope.object_id = object.object_id AND scope.model_id = %s
 WHERE object.object_id = ANY(%s::BIGINT[])
   AND object.is_active AND connection.is_active AND placement.is_active
   AND system.is_active AND zone.is_active
   AND lower(btrim(zone.zone_code)) IN ('source', 'bronze')
 ORDER BY object.object_id
"""


async def prepare_input_scope_addition(
    transaction: ReadTransaction, model: ModelReadContext, object_ids: list[int]
) -> ValidatedModelChangeSet:
    rows = await transaction.fetch_all(
        _SCOPE_OBJECTS_SQL, (model.tenant_id, model.model_id, object_ids)
    )
    if len(rows) != len(object_ids):
        raise InvalidRequestError("Choose active Source or Bronze Objects visible to this Model.")
    review = await read_model_review_snapshot(transaction, model)
    validation = validate_future_graph(
        snapshot=review.snapshot,
        staged_documents={"model_input_scope": rows},
        physical_scope=await load_model_physical_scope(transaction, model),
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "The selected Objects cannot be added. Check Source/Bronze eligibility and Scope locks."
        )
    return validation
