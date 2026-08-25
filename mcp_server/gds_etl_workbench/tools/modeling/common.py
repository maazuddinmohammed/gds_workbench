"""Shared Model read authorization, selection, and audit contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, LiteralString, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

MAX_OBJECT_FILTER = 100
POLICY = ToolPolicy.TENANT_READ

_MODEL_CONTEXT_SQL: LiteralString = """
SELECT model_id,
       tenant_id,
       model_name,
       model_revision
  FROM model.model
 WHERE model_id = %s
   AND is_active
"""

_MODEL_OBJECT_COUNT_SQL: LiteralString = """
SELECT count(*) AS object_count
 FROM model.model_scope
 WHERE model_id = %s
   AND object_id = ANY(%s::BIGINT[])
   AND is_active
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelObjectSelection(ContractModel):
    model_id: int = Field(gt=0)
    object_ids: tuple[int, ...] = Field(default=(), max_length=MAX_OBJECT_FILTER)

    @field_validator("object_ids")
    @classmethod
    def validate_object_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(object_id <= 0 for object_id in value) or len(set(value)) != len(value):
            raise ValueError("Object IDs must be unique positive integers.")
        return value


@dataclass(frozen=True, slots=True)
class ModelReadContext:
    model_id: int
    tenant_id: int
    model_name: str
    model_revision: int


async def authorize_model_read(
    transaction: ReadTransaction,
    *,
    authorizer: AuthorizationService,
    principal: RequestPrincipal,
    model_id: int,
) -> ModelReadContext:
    row = await transaction.fetch_one(_MODEL_CONTEXT_SQL, (model_id,))
    if row is None:
        raise InvalidRequestError("Model was not found.")
    await authorizer.authorize_tenant(
        transaction,
        principal,
        tenant_id=row["tenant_id"],
        policy=POLICY,
    )
    return ModelReadContext(
        model_id=row["model_id"],
        tenant_id=row["tenant_id"],
        model_name=row["model_name"],
        model_revision=row["model_revision"],
    )


async def validate_model_object_selection(
    transaction: ReadTransaction,
    *,
    model_id: int,
    object_ids: tuple[int, ...],
) -> None:
    if not object_ids:
        return
    row = await transaction.fetch_one(
        _MODEL_OBJECT_COUNT_SQL,
        (model_id, list(object_ids)),
    )
    if row is None or row["object_count"] != len(object_ids):
        raise InvalidRequestError("One or more Objects are not in the Model Scope.")


def summarize_model_object_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    model_id = arguments.get("model_id")
    object_ids = arguments.get("object_ids", [])
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "object_count": (
            len(cast(list[object], object_ids)) if isinstance(object_ids, list) else "invalid"
        ),
    }
