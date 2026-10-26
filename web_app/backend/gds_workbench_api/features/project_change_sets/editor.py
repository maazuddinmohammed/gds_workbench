"""Human edits to modeled definitions, preserving identity, evidence, and lifecycle."""

from typing import Any, Literal

from gds_etl_workbench.application.change_sets.project_validation import (
    PhysicalProjectCatalog,
    ValidatedProjectChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.project_snapshot import ProjectReviewSnapshot
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.snapshots.project import DATASETS_BY_NAME
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .review import review_lifecycle

# Subject Areas are edited through their own save command, which also moves tables.
type EditableDataset = Literal[
    "mapping_object",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
]


class NewMappingTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    entity_type: Literal["logical_entity", "dimensional_entity"]
    entity_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)


class ProjectRecordEditorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    dataset: EditableDataset
    record_id: int = Field(default=0, ge=0)
    mapping_target: NewMappingTarget | None = None
    expected_project_revision: int = Field(gt=0)

    @model_validator(mode="after")
    def require_record_or_mapping_target(self) -> ProjectRecordEditorRequest:
        if self.mapping_target is not None:
            if self.dataset != "mapping_object" or self.record_id != 0:
                raise ValueError("A new Mapping uses a target instead of a saved record ID")
        elif self.record_id == 0:
            raise ValueError("A saved record ID is required")
        return self


class SaveProjectRecordRequest(ProjectRecordEditorRequest):
    changes: dict[str, Any] = Field(min_length=1)


class EditorField(BaseModel):
    name: str
    label: str
    kind: Literal["text", "multiline", "number", "boolean", "choice", "lines"]
    value: Any
    required: bool
    options: list[str] = Field(default_factory=list)
    minimum: int | None = None
    maximum_length: int | None = None


class ProjectRecordEditor(BaseModel):
    project_revision: int
    label: str
    fields: list[EditorField]
    is_locked: bool
    mapping: dict[str, Any] | None = None


def project_record_editor(
    review: ProjectReviewSnapshot, command: ProjectRecordEditorRequest
) -> ProjectRecordEditor:
    record = review.records_by_id.get(command.dataset, {}).get(command.record_id)
    if record is None:
        raise WorkbenchError("project_record_not_found", "This record is unavailable.")
    definition = DATASETS_BY_NAME[command.dataset]
    values = record.model_dump(mode="json")
    # Type labels are codes from reference lists; offer only the active codes.
    label_choices = {
        "logical_entity_type": [
            row.logical_entity_type_code
            for row in review.snapshot.logical.entity_types
            if row.logical_entity_type_is_active
        ],
        "dimensional_fact_type": [
            row.dimensional_fact_type_code
            for row in review.snapshot.dimensional.fact_types
            if row.dimensional_fact_type_is_active
        ],
    }
    fields: list[EditorField] = []
    # Only fields owned by this modeled record; canonical references, evidence,
    # and lifecycle are managed by their existing governed operations.
    for name, schema in definition.row_model.model_json_schema()["properties"].items():
        if name in definition.canonical_key or name.endswith(
            ("_status", "_is_active", "_is_locked")
        ):
            continue
        if not name.startswith(command.dataset + "_") and name != "dimensional_fact_type":
            continue
        variants = schema.get("anyOf", [schema])
        nullable = any(item.get("type") == "null" for item in variants)
        spec = next(item for item in variants if item.get("type") != "null")
        field_type = spec.get("type")
        if field_type not in {"string", "integer", "boolean"}:
            continue
        label = name.removeprefix(command.dataset + "_").removeprefix("dimensional_")
        label = label.removeprefix("is_").replace("_", " ").capitalize()
        options = label_choices.get(name) or spec.get("enum", [])
        kind = (
            "choice"
            if options
            else "boolean"
            if field_type == "boolean"
            else "number"
            if field_type == "integer"
            else "multiline"
            if any(part in name for part in ("definition", "basis", "grain"))
            else "text"
        )
        fields.append(
            EditorField(
                name=name,
                label=label,
                kind=kind,
                value=values[name],
                required=not nullable,
                options=options,
                maximum_length=spec.get("maxLength"),
                minimum=spec.get("minimum", spec.get("exclusiveMinimum", -1) + 1)
                if field_type == "integer"
                else None,
            )
        )
    return ProjectRecordEditor(
        project_revision=review.snapshot.project_revision,
        label=" · ".join(str(values[name]) for name in definition.canonical_key),
        fields=fields,
        is_locked=review_lifecycle(record, command.dataset)[0],
    )


def prepare_project_record_edit(
    review: ProjectReviewSnapshot,
    command: SaveProjectRecordRequest,
    physical_scope: PhysicalProjectCatalog,
) -> ValidatedProjectChangeSet:
    editor = project_record_editor(review, command)
    if editor.is_locked:
        raise WorkbenchError("record_locked", "Unlock this record before editing it.")
    if command.changes.keys() - {field.name for field in editor.fields}:
        raise InvalidRequestError(
            "Edit only the displayed definition fields. Identity and evidence are preserved."
        )
    original = review.records_by_id[command.dataset][command.record_id]
    try:
        edited = DATASETS_BY_NAME[command.dataset].row_model.model_validate(
            {**original.model_dump(mode="json"), **command.changes},
            strict=False,
        )
    except ValidationError as error:
        # Validation messages omit field input, which may contain authored text.
        messages = [
            item["msg"].removeprefix("Value error, ")
            for item in error.errors(include_input=False)[:5]
        ]
        raise InvalidRequestError(" ".join(messages)) from None
    validation = validate_future_graph(
        snapshot=review.snapshot,
        staged_documents={command.dataset: [edited.model_dump(mode="json")]},
        physical_scope=physical_scope,
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "This edit conflicts with project references or locked evidence. "
            "Review the related records before saving."
        )
    return validation
