"""Context edits use the same revision-fenced Project graph validation as agents."""

from typing import Annotated, Literal

from gds_etl_workbench.application.change_sets.project import load_project_physical_scope
from gds_etl_workbench.application.change_sets.project_validation import (
    ValidatedProjectChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import read_project_review_snapshot
from gds_etl_workbench.domain.context_safety import (
    CONTEXT_RECORD_TEXT_MAX_CHARACTERS,
    CONTEXT_SOURCE_REFERENCE_MAX_BYTES,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ContextRecord,
    ContextRecordId,
    normalize_project_key_value,
)
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class SaveContextGroupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, str_strip_whitespace=True)

    action: Literal["create", "edit"]
    expected_project_revision: int = Field(gt=0)
    context_group_id: int | None = Field(default=None, gt=0)
    context_group_name: str = Field(min_length=1, max_length=255, pattern=r"\S")
    context_type_id: int = Field(gt=0)
    context_group_description: str | None = Field(default=None, min_length=1, max_length=2000)
    source_system_id: int | None = Field(default=None, gt=0)
    is_active: bool = True

    @model_validator(mode="after")
    def require_matching_identity(self) -> SaveContextGroupRequest:
        if (self.action == "edit") != (self.context_group_id is not None):
            raise ValueError("Edit requires an existing Context Group ID; create must omit it.")
        return self


class SaveContextRecordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, str_strip_whitespace=True)

    action: Literal["create", "edit"]
    expected_project_revision: int = Field(gt=0)
    context_record_id: ContextRecordId
    context_group_id: int = Field(gt=0)
    context_text: Annotated[
        str,
        StringConstraints(
            min_length=1, max_length=CONTEXT_RECORD_TEXT_MAX_CHARACTERS, pattern=r"\S"
        ),
    ]
    source_reference: str | None = Field(
        default=None, max_length=CONTEXT_SOURCE_REFERENCE_MAX_BYTES
    )

    @field_validator("source_reference")
    @classmethod
    def bound_source_reference(cls, value: str | None) -> str | None:
        if value is not None and len(value.encode("utf-8")) > CONTEXT_SOURCE_REFERENCE_MAX_BYTES:
            raise ValueError("Context source reference is too large")
        return value


async def prepare_context_group(
    transaction: ReadTransaction,
    project: ProjectReadContext,
    command: SaveContextGroupRequest,
) -> ValidatedProjectChangeSet:
    review = await read_project_review_snapshot(transaction, project, enforce_row_limits=False)
    snapshot = review.snapshot
    group_name = command.context_group_name
    existing = next(
        (
            group
            for group in snapshot.context.groups
            if normalize_project_key_value(group.context_group_name)
            == normalize_project_key_value(group_name)
        ),
        None,
    )
    if command.action == "create":
        if existing is not None:
            raise InvalidRequestError("This Context Group name already exists.")
    else:
        owned = await transaction.fetch_one(
            (
                "SELECT name AS context_group_name FROM "
                "project.context_group WHERE project_id = %s AND "
                "context_group_id = %s"
            ),
            (project.project_id, command.context_group_id),
        )
        if owned is None or owned["context_group_name"] != group_name or existing is None:
            raise InvalidRequestError(
                "The Context Group is unavailable or its name changed. Refresh and retry."
            )
        if any(
            record.is_locked
            and normalize_project_key_value(record.context_group_name)
            == normalize_project_key_value(group_name)
            for record in snapshot.context.records
        ):
            raise InvalidRequestError(
                "Unlock this Group's Context Records before changing the Group."
            )
    context_type = await transaction.fetch_one(
        "SELECT name AS context_type_name FROM reference.context_type WHERE context_type_id = %s",
        (command.context_type_id,),
    )
    if context_type is None:
        raise InvalidRequestError("Choose an available Context Type.")
    system_code = None
    if command.source_system_id is not None:
        system = await transaction.fetch_one(
            "SELECT system_code FROM core.system WHERE system_id = %s AND is_active",
            (command.source_system_id,),
        )
        if system is None:
            raise InvalidRequestError("Choose an active Source System.")
        system_code = system["system_code"]
    validation = validate_future_graph(
        snapshot=snapshot,
        staged_documents={
            "context_group": [
                {
                    "context_group_name": group_name,
                    "context_type_name": context_type["context_type_name"],
                    "context_group_description": command.context_group_description,
                    "source_system_code": system_code,
                    "is_active": command.is_active,
                }
            ]
        },
        physical_scope=await load_project_physical_scope(transaction, project),
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "The Context Group could not be saved. Check its Type, System and dependent records."
        )
    return validation


async def prepare_context_record(
    transaction: ReadTransaction,
    project: ProjectReadContext,
    command: SaveContextRecordRequest,
) -> ValidatedProjectChangeSet:
    review = await read_project_review_snapshot(transaction, project, enforce_row_limits=False)
    snapshot = review.snapshot
    existing = next(
        (
            record
            for record in snapshot.context.records
            if record.context_record_id == command.context_record_id
        ),
        None,
    )
    if command.action == "create":
        # UUIDs are global identities. Never allow a UUID already belonging to another Project.
        collision = await transaction.fetch_one(
            "SELECT 1 AS present FROM project.context_record WHERE context_record_id = %s::UUID",
            (command.context_record_id,),
        )
        if collision is not None:
            raise InvalidRequestError("This Context Record ID is unavailable. Start a new record.")
    elif not isinstance(existing, ContextRecord):
        raise InvalidRequestError("The Context Record is unavailable. Refresh and retry.")
    elif existing.is_locked:
        raise InvalidRequestError("Unlock this Context Record before editing it.")
    owned_group = await transaction.fetch_one(
        (
            "SELECT name AS context_group_name FROM "
            "project.context_group WHERE project_id = %s AND "
            "context_group_id = %s AND is_active"
        ),
        (project.project_id, command.context_group_id),
    )
    if owned_group is None:
        raise InvalidRequestError("Choose an active Context Group in this Project.")
    group_name = owned_group["context_group_name"]
    if existing is not None and normalize_project_key_value(
        existing.context_group_name
    ) != normalize_project_key_value(group_name):
        raise InvalidRequestError("A Context Record must stay in its original Group.")
    validation = validate_future_graph(
        snapshot=snapshot,
        staged_documents={
            "context_record": [
                {
                    "context_record_id": command.context_record_id,
                    "context_group_name": group_name,
                    "context_text": command.context_text,
                    "source_reference": command.source_reference,
                    "status": existing.status if existing else "active",
                    "is_locked": False,
                }
            ]
        },
        physical_scope=await load_project_physical_scope(transaction, project),
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "The Context Record could not be saved. Check its Group and dependent records."
        )
    return validation
