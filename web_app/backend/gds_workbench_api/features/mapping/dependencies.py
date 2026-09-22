"""Manual System ordering through the existing governed Model Change Set path."""

from typing import Literal

from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_validation import (
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import BaseModel, ConfigDict, Field


class SaveMappingDependencyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, str_strip_whitespace=True)

    expected_model_revision: int = Field(gt=0)
    entity_type: Literal["logical_entity", "dimensional_entity"]
    source_system_code: str = Field(min_length=1, max_length=100, pattern=r"\S")
    dependency_order: int = Field(ge=0)


async def prepare_mapping_dependency(
    transaction: ReadTransaction,
    model: ModelReadContext,
    command: SaveMappingDependencyRequest,
) -> ValidatedModelChangeSet:
    snapshot = await build_model_snapshot(transaction, model, enforce_row_limits=False)
    existing = next(
        (
            row
            for row in snapshot.mapping.dependencies
            if row.modeled_entity_type == command.entity_type
            and row.source_system_code.casefold() == command.source_system_code.casefold()
        ),
        None,
    )
    if existing is not None and existing.mapping_source_system_dependency_is_locked:
        raise InvalidRequestError("Unlock this System dependency before editing its order.")
    document: dict[str, object] = {
        "modeled_entity_type": command.entity_type,
        "source_system_code": command.source_system_code,
        "source_system_dependency_order": command.dependency_order,
        "mapping_source_system_dependency_status": (
            existing.mapping_source_system_dependency_status if existing else "active"
        ),
        "mapping_source_system_dependency_is_locked": False,
    }
    validation = validate_future_graph(
        snapshot=snapshot,
        staged_documents={"mapping_dependency": [document]},
        physical_scope=await load_model_physical_scope(transaction, model),
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "The System order is invalid. Choose an active, visible Source System and "
            "an order compatible with existing dependencies."
        )
    return validation
