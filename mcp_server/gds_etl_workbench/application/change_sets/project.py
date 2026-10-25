"""Governed Project Change Set operations shared by web and MCP adapters."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, LiteralString, cast
from uuid import UUID

from pydantic import Field

from gds_etl_workbench.application.authorization import (
    ResolvedPrincipal,
)
from gds_etl_workbench.application.change_sets.action_review import DatasetActionReview
from gds_etl_workbench.application.change_sets.contracts import (
    MAX_AGENT_VALIDATION_ERROR_EXAMPLES,
    MAX_PROJECT_STAGE_CHUNK_BYTES,
    MAX_PROJECT_STAGE_PAYLOAD_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
    ChangeSetContractModel,
    ChangeSetValidationErrorGroup,
)
from gds_etl_workbench.application.change_sets.project_validation import (
    PhysicalProjectCatalog,
    ProjectValidationIssue,
    ValidatedProjectChangeSet,
    validate_future_graph,
    validate_staged_records,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.context_safety import CONTEXT_SECTION_MAX_BYTES
from gds_etl_workbench.domain.errors import (
    InvalidRequestError,
    ProjectChangeSetNotActiveError,
    StageBatchNotActiveError,
    StageBatchNotFoundError,
)
from gds_etl_workbench.domain.modeling_records import normalize_project_key_value
from gds_etl_workbench.domain.snapshots.project import (
    CHANGE_SET_DATASETS_BY_NAME,
    ProjectChangeSetDataset,
    ProjectDataset,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadTransaction,
    WriteTransaction,
)

ContractModel = ChangeSetContractModel
ProjectStagePayloadMode = Literal["records", "json_fragments"]

READ_SECTION_COLUMNS = (
    "project_input_scope_document",
    "profiling_document",
    "enrichment_document",
    "analysis_document",
    "context_document",
    "subject_area_document",
    "logical_document",
    "dimensional_document",
    "mapping_document",
    "code_generation_document",
    "validation_document",
)


_PROJECT_PHYSICAL_SCOPE_SQL: LiteralString = """
SELECT project_tenant.tenant_code AS project_tenant_code,
       object.object_id, placement_tenant.tenant_code, system.system_code,
       connection.connection_code, object.object_schema, object.object_name,
       attribute.attribute_id, attribute.attribute_name
  FROM core.tenant AS project_tenant
  LEFT JOIN core.object AS object
    ON object.source_tenant_id = project_tenant.tenant_id
    OR (object.source_tenant_id = ANY(%s::BIGINT[]) AND EXISTS (
        SELECT 1 FROM reference.zone AS zone WHERE zone.zone_id = object.zone_id
          AND lower(btrim(zone.zone_code)) IN ('source', 'bronze')
    ))
  LEFT JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id AND connection.is_active
  LEFT JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id AND placement_tenant.is_active
  LEFT JOIN core.system AS system
    ON system.system_id = connection.system_id AND system.is_active
  LEFT JOIN core.attribute AS attribute ON attribute.object_id = object.object_id
 WHERE project_tenant.tenant_id = %s AND project_tenant.is_active
"""

# Physical identity retains inactive records for historical references. These
# separate governed selectors still restrict new work to current eligibility.
_PROJECT_OBJECT_ELIGIBILITY_SQL: LiteralString = """
SELECT object_id,
       is_project_input_eligible
  FROM workflow.list_project_object_eligibility(%s)
"""

_PROJECT_ATTRIBUTE_ELIGIBILITY_SQL: LiteralString = """
SELECT attribute_id,
       is_project_input_eligible
  FROM workflow.list_project_attribute_eligibility(%s)
"""

_OTHER_PROJECT_NAMES_SQL: LiteralString = """
SELECT project_name
  FROM project.project
 WHERE tenant_id = %s
   AND project_id <> %s
   AND is_active
"""

_ACTIVE_SYSTEM_CODES_SQL: LiteralString = """
SELECT system_code
  FROM core.system
 WHERE is_active
"""


class StageProjectChange(ContractModel):
    dataset: ProjectChangeSetDataset = Field(
        description="Project dataset whose complete pending replacement is supplied."
    )
    records: Annotated[
        list[dict[str, object]],
        Field(
            max_length=20_000,
            description=(
                "Complete pending record list for this dataset; an empty list clears only "
                "this pending dataset and omitted datasets remain unchanged."
            ),
        ),
    ]


class ProjectDatasetCount(ContractModel):
    dataset: ProjectDataset
    record_count: int = Field(ge=0)


class ProjectChangeSetDatasetCount(ContractModel):
    dataset: ProjectChangeSetDataset
    record_count: int = Field(ge=0)


class ProjectValidationError(ContractModel):
    code: str
    dataset: str
    record_number: int | None
    fields: tuple[str, ...]
    message: str


class ProjectChangeSetActionKey(ContractModel):
    action: Literal["insert", "update", "deactivate", "reactivate", "no_change"]
    natural_key: dict[str, str | int | bool | None]


class ProjectChangeSetActionReview(ContractModel):
    dataset: ProjectChangeSetDataset
    insert_count: int = Field(ge=0)
    update_count: int = Field(ge=0)
    deactivate_count: int = Field(ge=0)
    reactivate_count: int = Field(ge=0)
    no_change_count: int = Field(ge=0)
    keys: tuple[ProjectChangeSetActionKey, ...] = Field(max_length=100)
    keys_truncated: bool


class CreateProjectChangeSetResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    created: bool
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    created_at: datetime
    expires_at: datetime


class StageProjectChangeSetResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    staged: Literal[True] = True
    datasets: tuple[ProjectChangeSetDatasetCount, ...] = Field(
        min_length=1,
        max_length=25,
    )
    draft_revision: int = Field(gt=0)
    status: Literal["active"] = "active"
    expires_at: datetime


class BeginProjectStageBatchResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ProjectChangeSetDataset
    created: bool
    total_record_count: int = Field(gt=0, le=20_000)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    received_chunk_count: int = Field(ge=0, le=MAX_STAGE_CHUNKS)
    expected_draft_revision: int = Field(gt=0)
    expires_at: datetime
    payload_mode: ProjectStagePayloadMode = "records"
    total_payload_bytes: int | None = Field(
        default=None,
        gt=0,
        le=MAX_PROJECT_STAGE_PAYLOAD_BYTES,
    )


class PutProjectStageChunkResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ProjectChangeSetDataset
    accepted: Literal[True] = True
    duplicate: bool
    chunk_index: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    record_count: int = Field(ge=0, le=MAX_STAGE_CHUNK_RECORDS)
    received_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    expires_at: datetime
    payload_mode: ProjectStagePayloadMode = "records"
    payload_byte_count: int | None = Field(
        default=None,
        gt=0,
        le=MAX_PROJECT_STAGE_CHUNK_BYTES,
    )


class CommitProjectStageBatchResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ProjectChangeSetDataset
    committed: Literal[True] = True
    replayed: bool
    record_count: int = Field(gt=0, le=20_000)
    draft_revision: int = Field(gt=0)
    status: Literal["active"] = "active"
    expires_at: datetime


class GetProjectChangeSetResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    status: Literal["active", "validated", "applied", "expired", "discarded", "superseded"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None
    validation_outcome: dict[str, object] | None
    dataset_counts: tuple[ProjectDatasetCount, ...]
    dataset: ProjectDataset | None
    records: Annotated[list[dict[str, object]], Field(max_length=20_000)] | None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    validated_at: datetime | None
    applied_at: datetime | None
    terminal_at: datetime | None


class ProjectChangeSetDatasetFingerprint(ContractModel):
    dataset: ProjectChangeSetDataset
    record_count: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)


class GetProjectChangeSetFingerprintResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    # Versions the aggregate fingerprint document, not the result schema; Stage Runner
    # recomputes that document with this exact value.
    fingerprint_version: Literal["1.0"] = "1.0"
    area: Literal["project"] = "project"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    status: Literal["active", "validated", "applied", "expired", "discarded", "superseded"]
    draft_revision: int = Field(gt=0)
    dataset_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    datasets: tuple[ProjectChangeSetDatasetFingerprint, ...]
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    expires_at: datetime


class ValidateProjectChangeSetResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    valid: bool
    phase: str
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None
    staged_record_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    error_groups: tuple[ChangeSetValidationErrorGroup, ...]
    errors: tuple[ProjectValidationError, ...]
    errors_truncated: bool
    action_review: tuple[ProjectChangeSetActionReview, ...]
    validated_at: datetime | None
    expires_at: datetime


class ApplyProjectChangeSetResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    applied: Literal[True] = True
    status: Literal["applied"] = "applied"
    draft_revision: int = Field(gt=0)
    candidate_digest: str
    action_count: int = Field(ge=0)
    project_revision: int = Field(gt=0)
    applied_at: datetime


class ArchiveProjectChangeSetResult(ContractModel):
    schema_version: Literal["2.0"] = "2.0"
    project_id: int = Field(gt=0)
    project_change_set_id: UUID
    archived: Literal[True] = True
    status: Literal["archived"] = "archived"
    draft_revision: int = Field(gt=0)
    archived_at: datetime


def require_mutable_project_change_set(row: Mapping[str, Any]) -> None:
    _require_generic_change_set(row)
    if row["project_change_set_status"] not in ("active", "validated"):
        raise ProjectChangeSetNotActiveError()
    if row.get("is_expired") is True:
        raise ProjectChangeSetNotActiveError()


def require_project_stage_batch(
    row: Mapping[str, Any] | None,
    principal: ResolvedPrincipal,
    dataset: ProjectChangeSetDataset | None,
) -> None:
    if row is None or row["created_by_principal_id"] != principal.principal_id:
        raise StageBatchNotFoundError()
    if dataset is not None and row["dataset_name"] != dataset:
        raise InvalidRequestError("Dataset does not match the Stage Batch manifest.")
    if row["dataset_name"] not in CHANGE_SET_DATASETS_BY_NAME:
        raise InvalidRequestError("The Stage Batch dataset is not writable through MCP.")
    if row["stage_batch_status"] != "active":
        raise StageBatchNotActiveError()
    if row.get("is_expired") is True:
        raise StageBatchNotActiveError()


def validate_project_stage_changes(
    changes: list[StageProjectChange],
) -> dict[str, list[dict[str, object]]]:
    staged: dict[str, list[dict[str, object]]] = {}
    for change in changes:
        if change.dataset in staged:
            raise InvalidRequestError("Each Project dataset may be staged only once per call.")
        records, issues = validate_staged_records(change.dataset, change.records)
        if issues:
            issue = issues[0]
            field_path = ".".join(issue.fields) or "<record>"
            raise InvalidRequestError(
                f"Record {issue.record_number or 1} at {field_path}: {issue.message}"
            )
        staged[change.dataset] = [record.model_dump(mode="json") for record in records]
    if sum(len(records) for records in staged.values()) > 50_000:
        raise InvalidRequestError("A Project Change Set stage is limited to 50,000 records.")
    return staged


def decode_canonical_project_stage_payload(
    payload: bytes,
    *,
    expected_record_count: int,
) -> list[dict[str, object]]:
    try:
        parsed = cast(object, json.loads(payload.decode("utf-8")))
    except UnicodeDecodeError, json.JSONDecodeError:
        raise InvalidRequestError("The Stage payload is not valid UTF-8 JSON.") from None
    records = cast(list[object], parsed) if isinstance(parsed, list) else None
    if (
        records is None
        or len(records) != expected_record_count
        or any(not isinstance(record, dict) for record in records)
    ):
        raise InvalidRequestError("The Stage payload must contain the declared JSON record array.")
    return cast(list[dict[str, object]], records)


def validate_project_change_set_document_bounds(
    documents: dict[str, dict[str, list[dict[str, object]]]],
) -> None:
    if sum(len(records) for section in documents.values() for records in section.values()) > 50_000:
        raise InvalidRequestError("A Project Change Set is limited to 50,000 pending records.")
    for section_name, section in documents.items():
        encoded_size = len(
            json.dumps(
                section,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if section_name == "context" and encoded_size > CONTEXT_SECTION_MAX_BYTES:
            raise InvalidRequestError("The Context section exceeds 4 MiB.")
        if section_name not in {"context", "code_generation"} and encoded_size > 16 * 1024 * 1024:
            raise InvalidRequestError("A Project Change Set section exceeds 16 MiB.")


def project_change_set_documents(
    row: Mapping[str, Any],
) -> dict[str, dict[str, list[dict[str, object]]]]:
    return {
        column.removesuffix("_document"): dict(row[column] or {}) for column in READ_SECTION_COLUMNS
    }


def pending_project_change_set_datasets(
    row: Mapping[str, Any],
) -> dict[str, list[dict[str, object]]]:
    return {
        dataset: records
        for section in project_change_set_documents(row).values()
        for dataset, records in section.items()
    }


def require_mcp_writable_pending(row: Mapping[str, Any]) -> None:
    _require_generic_change_set(row)
    if any(
        dataset not in CHANGE_SET_DATASETS_BY_NAME
        for dataset in pending_project_change_set_datasets(row)
    ):
        raise InvalidRequestError(
            "The Project Change Set contains a dataset that is not writable through MCP."
        )


def _require_generic_change_set(row: Mapping[str, Any]) -> None:
    if row.get("workflow_run_id") is not None:
        raise InvalidRequestError(
            "Workflow-bound Project Change Sets are managed only by their Workflow Run."
        )


async def validate_locked_project_change_set(
    transaction: WriteTransaction,
    project: ProjectReadContext,
    row: Mapping[str, Any],
    *,
    enforce_row_limits: bool = True,
) -> ValidatedProjectChangeSet:
    if row["base_project_revision"] != project.project_revision:
        issue = ProjectValidationIssue(
            code="stale_project_revision",
            dataset="project",
            record_number=None,
            fields=("project_revision",),
            message="Applied Project revision changed after this Change Set was created.",
        )
        return ValidatedProjectChangeSet(
            records={},
            phase="project_revision",
            candidate_digest=None,
            issues=(issue,),
            action_review=(),
        )
    staged_documents = cast(
        dict[ProjectChangeSetDataset, list[dict[str, object]]],
        pending_project_change_set_datasets(row),
    )
    snapshot = await build_project_snapshot(
        transaction, project, enforce_row_limits=enforce_row_limits
    )
    physical_scope = await load_project_physical_scope(transaction, project)
    return validate_future_graph(
        snapshot=snapshot,
        staged_documents=staged_documents,
        physical_scope=physical_scope,
    )


async def load_project_physical_scope(
    transaction: ReadTransaction,
    project: ProjectReadContext,
) -> PhysicalProjectCatalog:
    rows = await transaction.fetch_all(
        _PROJECT_PHYSICAL_SCOPE_SQL, (list(project.readable_source_tenant_ids), project.tenant_id)
    )
    if not rows:
        raise InvalidRequestError("Project physical Scope could not be resolved.")
    system_rows = await transaction.fetch_all(_ACTIVE_SYSTEM_CODES_SQL)
    other_project_rows = await transaction.fetch_all(
        _OTHER_PROJECT_NAMES_SQL,
        (project.tenant_id, project.project_id),
    )
    object_eligibility_rows = await transaction.fetch_all(
        _PROJECT_OBJECT_ELIGIBILITY_SQL,
        (project.project_id,),
    )
    attribute_eligibility_rows = await transaction.fetch_all(
        _PROJECT_ATTRIBUTE_ELIGIBILITY_SQL,
        (project.project_id,),
    )
    objects: set[tuple[str, str, str, str, str]] = set()
    attributes: set[tuple[str, str, str, str, str, str]] = set()
    object_keys_by_id: dict[int, tuple[str, str, str, str, str]] = {}
    attribute_keys_by_id: dict[int, tuple[str, str, str, str, str, str]] = {}
    for physical in rows:
        object_values = tuple(
            physical[field]
            for field in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        )
        if all(isinstance(value, str) for value in object_values):
            object_key = cast(
                tuple[str, str, str, str, str],
                tuple(normalize_project_key_value(value) for value in object_values),
            )
            objects.add(object_key)
            object_id = physical["object_id"]
            if isinstance(object_id, int):
                object_keys_by_id[object_id] = object_key
            attribute_name = physical["attribute_name"]
            if isinstance(attribute_name, str):
                attribute_key = (*object_key, normalize_project_key_value(attribute_name))
                attributes.add(attribute_key)
                attribute_id = physical["attribute_id"]
                if isinstance(attribute_id, int):
                    attribute_keys_by_id[attribute_id] = attribute_key

    eligibility_flags = ("is_project_input_eligible",)
    eligible_objects: dict[str, set[tuple[str, str, str, str, str]]] = {
        flag: set() for flag in eligibility_flags
    }
    eligible_attributes: dict[str, set[tuple[str, str, str, str, str, str]]] = {
        flag: set() for flag in eligibility_flags
    }
    for eligibility in object_eligibility_rows:
        key = object_keys_by_id.get(eligibility["object_id"])
        if key is not None:
            for flag in eligibility_flags:
                if eligibility[flag] is True:
                    eligible_objects[flag].add(key)
    for eligibility in attribute_eligibility_rows:
        key = attribute_keys_by_id.get(eligibility["attribute_id"])
        if key is not None:
            for flag in eligibility_flags:
                if eligibility[flag] is True:
                    eligible_attributes[flag].add(key)
    return PhysicalProjectCatalog(
        project_tenant_code=rows[0]["project_tenant_code"],
        active_system_codes=frozenset(
            normalize_project_key_value(system["system_code"]) for system in system_rows
        ),
        objects=frozenset(objects),
        attributes=frozenset(attributes),
        project_input_objects=frozenset(eligible_objects["is_project_input_eligible"]),
        project_input_attributes=frozenset(eligible_attributes["is_project_input_eligible"]),
        other_project_names=frozenset(
            normalize_project_key_value(other_project["project_name"])
            for other_project in other_project_rows
        ),
    )


def project_validation_outcome(validation: ValidatedProjectChangeSet) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "valid": validation.valid,
        "phase": validation.phase,
        "staged_record_count": sum(len(records) for records in validation.records.values()),
        "error_count": len(validation.issues),
        "error_groups": [
            group.model_dump(mode="json") for group in project_validation_error_groups(validation)
        ],
        "errors": [
            {
                "code": issue.code,
                "dataset": issue.dataset,
                "record_number": issue.record_number,
                "fields": list(issue.fields),
                "message": issue.message,
            }
            for issue in validation.issues[:MAX_AGENT_VALIDATION_ERROR_EXAMPLES]
        ],
        "errors_truncated": len(validation.issues) > MAX_AGENT_VALIDATION_ERROR_EXAMPLES,
        "action_review": [summary.as_document() for summary in validation.action_review],
    }


def project_validation_error_groups(
    validation: ValidatedProjectChangeSet,
) -> tuple[ChangeSetValidationErrorGroup, ...]:
    groups = Counter((issue.dataset, issue.code) for issue in validation.issues)
    return tuple(
        ChangeSetValidationErrorGroup(dataset=dataset, code=code, count=count)
        for (dataset, code), count in sorted(groups.items())
    )


def project_validation_error(issue: ProjectValidationIssue) -> ProjectValidationError:
    return ProjectValidationError(
        code=issue.code,
        dataset=issue.dataset,
        record_number=issue.record_number,
        fields=issue.fields,
        message=issue.message,
    )


def project_action_review(
    action_review: tuple[DatasetActionReview, ...],
) -> tuple[ProjectChangeSetActionReview, ...]:
    return tuple(
        ProjectChangeSetActionReview(
            dataset=cast(ProjectChangeSetDataset, summary.dataset),
            insert_count=summary.insert_count,
            update_count=summary.update_count,
            deactivate_count=summary.deactivate_count,
            reactivate_count=summary.reactivate_count,
            no_change_count=summary.no_change_count,
            keys=tuple(
                ProjectChangeSetActionKey(
                    action=key.action,
                    natural_key=cast(dict[str, str | int | bool | None], key.natural_key),
                )
                for key in summary.keys
            ),
            keys_truncated=summary.keys_truncated,
        )
        for summary in action_review
    )


__all__ = [
    "ProjectStagePayloadMode",
    "ProjectChangeSetDatasetCount",
    "ProjectDatasetCount",
    "StageProjectChange",
    "decode_canonical_project_stage_payload",
    "load_project_physical_scope",
    "project_action_review",
    "project_change_set_documents",
    "project_validation_error",
    "project_validation_error_groups",
    "project_validation_outcome",
    "pending_project_change_set_datasets",
    "require_mcp_writable_pending",
    "require_project_stage_batch",
    "require_mutable_project_change_set",
    "validate_locked_project_change_set",
    "validate_project_change_set_document_bounds",
    "validate_project_stage_changes",
]
