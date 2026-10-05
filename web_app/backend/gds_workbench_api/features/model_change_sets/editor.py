"""Human edits to modeled definitions, preserving identity, evidence, and lifecycle."""

from typing import Any, Literal

from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_snapshot import ModelReviewSnapshot
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.snapshots.model import DATASETS_BY_NAME
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .review import review_lifecycle

type EditableDataset = Literal[
    "mapping_object",
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
]


class NewMappingTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    entity_type: Literal["logical_entity", "dimensional_entity"]
    entity_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)


class ModelRecordEditorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    dataset: EditableDataset
    record_id: int = Field(default=0, ge=0)
    mapping_target: NewMappingTarget | None = None
    expected_model_revision: int = Field(gt=0)

    @model_validator(mode="after")
    def require_record_or_mapping_target(self) -> ModelRecordEditorRequest:
        if self.mapping_target is not None:
            if self.dataset != "mapping_object" or self.record_id != 0:
                raise ValueError("A new Mapping uses a target instead of a saved record ID")
        elif self.record_id == 0:
            raise ValueError("A saved record ID is required")
        return self


class SaveModelRecordRequest(ModelRecordEditorRequest):
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


class ModelRecordEditor(BaseModel):
    model_revision: int
    label: str
    fields: list[EditorField]
    is_locked: bool
    mapping: dict[str, Any] | None = None


def model_record_editor(
    review: ModelReviewSnapshot, command: ModelRecordEditorRequest
) -> ModelRecordEditor:
    record = review.records_by_id.get(command.dataset, {}).get(command.record_id)
    if record is None:
        raise WorkbenchError("model_record_not_found", "This record is unavailable.")
    definition = DATASETS_BY_NAME[command.dataset]
    values = record.model_dump(mode="json")
    fields: list[EditorField] = []
    # Only fields owned by this modeled record; canonical references, evidence,
    # membership, and lifecycle are managed by their existing governed operations.
    for name, schema in definition.row_model.model_json_schema()["properties"].items():
        if name in definition.canonical_key or name.endswith(("_status", "_is_locked")):
            continue
        if not name.startswith(command.dataset + "_") and name != "dimensional_fact_type":
            continue
        variants = schema.get("anyOf", [schema])
        nullable = any(item.get("type") == "null" for item in variants)
        spec = next(item for item in variants if item.get("type") != "null")
        field_type = spec.get("type")
        if (
            field_type not in {"string", "integer", "boolean"}
            and name != "conceptual_object_aliases"
        ):
            continue
        label = name.removeprefix(command.dataset + "_").removeprefix("dimensional_")
        label = label.removeprefix("is_").replace("_", " ").capitalize()
        kind = (
            "lines"
            if name == "conceptual_object_aliases"
            else "choice"
            if "enum" in spec
            else "boolean"
            if field_type == "boolean"
            else "number"
            if field_type == "integer"
            else "multiline"
            if any(part in name for part in ("definition", "basis", "grain", "detail"))
            else "text"
        )
        fields.append(
            EditorField(
                name=name,
                label=label,
                kind=kind,
                value=values[name],
                required=not nullable,
                options=spec.get("enum", []),
                maximum_length=spec.get("maxLength"),
                minimum=spec.get("minimum", spec.get("exclusiveMinimum", -1) + 1)
                if field_type == "integer"
                else None,
            )
        )
    return ModelRecordEditor(
        model_revision=review.snapshot.model_revision,
        label=" · ".join(str(values[name]) for name in definition.canonical_key),
        fields=fields,
        is_locked=review_lifecycle(record, command.dataset)[0],
    )


def prepare_model_record_edit(
    review: ModelReviewSnapshot,
    command: SaveModelRecordRequest,
    physical_scope: PhysicalModelCatalog,
) -> ValidatedModelChangeSet:
    editor = model_record_editor(review, command)
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
            "This edit conflicts with model references or locked evidence. "
            "Review the related records before saving."
        )
    return validation
