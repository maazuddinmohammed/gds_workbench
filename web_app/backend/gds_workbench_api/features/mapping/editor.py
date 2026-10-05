"""Human Mapping document editing inside the governed Model review transaction."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, LiteralString, Self, cast

from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.mapping_context import MAPPING_REFERENCE_TEMPLATE_CODES
from gds_etl_workbench.application.model_snapshot import ModelReviewSnapshot
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    MappingAttributeRecord,
    MappingObjectRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from gds_workbench_api.features.model_change_sets.editor import (
    ModelRecordEditor,
    ModelRecordEditorRequest,
    SaveModelRecordRequest,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import OBJECT_FIELDS

from .contracts import MappingAttributeCandidate, MappingObjectCandidate

NEW_MAPPING_TARGET_SQL: LiteralString = """
SELECT entity.modeled_entity_schema_name, entity.modeled_entity_name,
       entity.dependency_order, system.system_code
  FROM workflow.modeled_entity AS entity
  JOIN model.model AS model ON model.model_id = entity.model_id
  JOIN core.system AS system ON system.system_id = %s AND system.is_active
 WHERE entity.model_id = %s AND entity.modeled_entity_id = %s
   AND entity.modeled_entity_type = %s AND entity.status = 'active'
   AND (EXISTS (
       SELECT 1 FROM workflow.list_mapping_source_objects(entity.model_id,
           entity.modeled_entity_id, entity.modeled_entity_type, system.system_id)
   ) OR (model.default_mapping_source_system_id = system.system_id
       AND workflow.is_assertion_only_mapping_target(entity.model_id,
           entity.modeled_entity_id, entity.modeled_entity_type)
       AND EXISTS (SELECT 1 FROM core.connection AS connection
           WHERE connection.tenant_id = model.tenant_id
             AND connection.system_id = system.system_id AND connection.is_active)))
   AND NOT EXISTS (SELECT 1 FROM workflow.mapping_object AS mapping
       WHERE mapping.model_id = entity.model_id
         AND mapping.modeled_entity_type = entity.modeled_entity_type
         AND coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id) =
             entity.modeled_entity_id
         AND mapping.source_system_id = system.system_id)
"""


# Choices come from the complete authorized Input Scope for this Mapping's System,
# including Bronze provenance resolved by the existing eligibility function.
MAPPING_INPUT_SCOPE_SQL: LiteralString = """
WITH selected_sources AS MATERIALIZED (
    SELECT object_id FROM workflow.list_model_input_sources(%s)
     WHERE source_system_id = %s ORDER BY object_id LIMIT 201
)
SELECT jsonb_build_object('object', jsonb_build_object(
    'tenant_code', tenant.tenant_code, 'system_code', system.system_code,
    'connection_code', connection.connection_code,
    'object_schema', object.object_schema, 'object_name', object.object_name,
    'attributes', coalesce(columns.items, '[]'::JSONB))) AS source
  FROM selected_sources AS source
  JOIN core.object AS object USING (object_id)
  JOIN core.connection AS connection USING (connection_id)
  JOIN core.tenant AS tenant ON tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system USING (system_id)
 CROSS JOIN LATERAL (
     SELECT jsonb_agg(jsonb_build_object('attribute_name', attribute.attribute_name,
         'attribute_data_type', attribute.attribute_data_type)
         ORDER BY attribute.attribute_ordinal_position, attribute.attribute_id) AS items
       FROM (SELECT attribute_id, attribute_name, attribute_data_type,
                    attribute_ordinal_position FROM core.attribute
              WHERE object_id = object.object_id AND is_active
              ORDER BY attribute_ordinal_position, attribute_id LIMIT 5001) AS attribute
 ) AS columns
 ORDER BY tenant.tenant_code, system.system_code, connection.connection_code,
          object.object_schema, object.object_name
"""


class MappingEditChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    object_mapping: MappingObjectCandidate | None = None
    attribute_mappings: list[MappingAttributeCandidate] = Field(
        default_factory=list[MappingAttributeCandidate], max_length=5000
    )

    @model_validator(mode="after")
    def separate_edits(self) -> Self:
        if (self.object_mapping is not None) == bool(self.attribute_mappings):
            raise ValueError("Save Object Mapping or Attribute Mapping separately")
        return self


def _reference_key(reference: Mapping[str, Any]) -> tuple[str, ...]:
    kind = reference.get("entity_type")
    if kind in {"logical_entity", "dimensional_entity"}:
        fields = ("entity_type", "entity_schema_name", "entity_name")
    elif "logical_entity_name" in reference:
        reference = {
            **reference,
            "entity_type": "logical_entity",
            "entity_schema_name": reference.get("logical_entity_schema_name"),
            "entity_name": reference.get("logical_entity_name"),
        }
        fields = ("entity_type", "entity_schema_name", "entity_name")
    elif "dimensional_entity_name" in reference:
        reference = {
            **reference,
            "entity_type": "dimensional_entity",
            "entity_schema_name": reference.get("dimensional_entity_schema_name"),
            "entity_name": reference.get("dimensional_entity_name"),
        }
        fields = ("entity_type", "entity_schema_name", "entity_name")
    elif kind is None:
        fields = OBJECT_FIELDS
    else:
        raise InvalidRequestError("Choose an eligible source table.")
    if any(not isinstance(reference.get(key), str) or not reference[key].strip() for key in fields):
        raise InvalidRequestError("A source reference needs its complete identity.")
    return tuple(normalize_model_key_value(reference[key]) for key in fields)


def mapping_record_editor(
    review: ModelReviewSnapshot,
    command: ModelRecordEditorRequest,
    sources: Sequence[Mapping[str, Any]],
) -> ModelRecordEditor:
    parent = review.records_by_id.get("mapping_object", {}).get(command.record_id)
    if not isinstance(parent, MappingObjectRecord):
        raise WorkbenchError("model_record_not_found", "This Mapping is unavailable.")
    layer = parent.modeled_entity_type.removesuffix("_entity")
    entity_key = (
        normalize_model_key_value(parent.modeled_entity_schema_name),
        normalize_model_key_value(parent.modeled_entity_name),
    )
    entity = next(
        (
            row
            for row in review.records_by_id.get(f"{layer}_entity", {}).values()
            if (
                normalize_model_key_value(getattr(row, f"{layer}_entity_schema_name")),
                normalize_model_key_value(getattr(row, f"{layer}_entity_name")),
            )
            == entity_key
        ),
        None,
    )
    if entity is None:
        raise WorkbenchError("model_record_not_found", "This modeled Entity is unavailable.")
    entity_locked = bool(getattr(entity, f"{layer}_entity_is_locked"))
    children = {
        normalize_model_key_value(row.modeled_attribute_name): row
        for row in review.records_by_id.get("mapping_attribute", {}).values()
        if isinstance(row, MappingAttributeRecord) and _same_pair(parent, row)
    }
    attributes: list[dict[str, Any]] = []
    protected_child = any(row.attribute_mapping_is_locked for row in children.values())
    for row in review.records_by_id.get(f"{layer}_attribute", {}).values():
        if (
            normalize_model_key_value(getattr(row, f"{layer}_entity_schema_name")),
            normalize_model_key_value(getattr(row, f"{layer}_entity_name")),
        ) != entity_key:
            continue
        protected_child = protected_child or bool(getattr(row, f"{layer}_attribute_is_locked"))
        if getattr(row, f"{layer}_attribute_status") != "active":
            continue
        name = getattr(row, f"{layer}_attribute_name")
        child = children.get(normalize_model_key_value(name))
        attributes.append(
            {
                "name": name,
                "data_type": getattr(row, f"{layer}_attribute_data_type"),
                "ordinal": getattr(row, f"{layer}_attribute_ordinal_position"),
                "is_locked": entity_locked
                or parent.object_mapping_is_locked
                or bool(getattr(row, f"{layer}_attribute_is_locked"))
                or bool(child and child.attribute_mapping_is_locked),
                "document": deepcopy(child.attribute_mapping_transformation_document)
                if child
                else None,
                "structured": child is None
                or child.output_template_code is None
                or child.output_template_code.casefold()
                in MAPPING_REFERENCE_TEMPLATE_CODES["mapping_attribute"],
            }
        )
    tables: list[dict[str, Any]] = []
    for source in sources:
        obj = source["source"]["object"]
        modeled = "entity_type" in obj
        fields = ("entity_type", "entity_schema_name", "entity_name") if modeled else OBJECT_FIELDS
        reference = {key: obj[key] for key in fields}
        columns = [
            {
                "name": column["attribute_name"],
                "data_type": column["attribute_data_type"],
                "reference": {**reference, "attribute_name": column["attribute_name"]},
            }
            for column in obj["attributes"]
            if column.get("is_active", True) and column.get("status", "active") == "active"
        ]
        label = (
            f"{obj['entity_schema_name']}.{obj['entity_name']}"
            if modeled
            else (
                f"{obj['system_code']} · {obj['connection_code']} · "
                f"{obj['object_schema']}.{obj['object_name']}"
            )
        )
        tables.append({"reference": reference, "label": label, "columns": columns})
    return ModelRecordEditor(
        model_revision=review.snapshot.model_revision,
        label=(
            f"{parent.modeled_entity_schema_name}.{parent.modeled_entity_name} · "
            f"{parent.source_system_code}"
        ),
        fields=[],
        is_locked=entity_locked or parent.object_mapping_is_locked,
        mapping={
            "object_document": deepcopy(parent.mapping_transformation_document),
            "dependency_order": parent.object_dependency_order,
            "object_is_locked": entity_locked or parent.object_mapping_is_locked or protected_child,
            "structured": parent.output_template_code is None
            or parent.output_template_code.casefold()
            in MAPPING_REFERENCE_TEMPLATE_CODES["mapping_object"],
            "attributes": sorted(attributes, key=lambda item: (item["ordinal"], item["name"])),
            "source_tables": tables,
        },
    )


def _same_pair(parent: MappingObjectRecord, child: MappingAttributeRecord) -> bool:
    return all(
        normalize_model_key_value(getattr(parent, field))
        == normalize_model_key_value(getattr(child, field))
        for field in (
            "modeled_entity_type",
            "modeled_entity_schema_name",
            "modeled_entity_name",
            "source_system_code",
        )
    )


def prepare_mapping_edit(
    review: ModelReviewSnapshot,
    command: SaveModelRecordRequest,
    editor: ModelRecordEditor,
    physical_scope: PhysicalModelCatalog,
) -> ValidatedModelChangeSet:
    if editor.is_locked:
        raise WorkbenchError("record_locked", "Unlock this Mapping and Entity before editing.")
    try:
        changes = MappingEditChanges.model_validate(command.changes, strict=True)
    except ValidationError:
        raise InvalidRequestError(
            "The Mapping edit has invalid fields or exceeds document limits."
        ) from None
    data = editor.mapping
    assert data is not None
    parent = review.records_by_id["mapping_object"][command.record_id]
    assert isinstance(parent, MappingObjectRecord)
    object_document = (
        changes.object_mapping.mapping_transformation_document
        if changes.object_mapping is not None
        else parent.mapping_transformation_document
    )
    dependency_order = (
        changes.object_mapping.object_dependency_order
        if changes.object_mapping is not None
        else parent.object_dependency_order
    )
    if data["object_is_locked"] and (
        object_document != parent.mapping_transformation_document
        or dependency_order != parent.object_dependency_order
    ):
        raise WorkbenchError("record_locked", "Object logic is protected by a locked Attribute.")
    targets = {normalize_model_key_value(item["name"]): item for item in data["attributes"]}
    names = [
        normalize_model_key_value(item.modeled_attribute_name)
        for item in changes.attribute_mappings
    ]
    if len(names) != len(set(names)) or not set(names) <= targets.keys():
        raise InvalidRequestError("Choose each active target Attribute at most once.")
    existing = {
        normalize_model_key_value(row.modeled_attribute_name): row
        for row in review.records_by_id.get("mapping_attribute", {}).values()
        if isinstance(row, MappingAttributeRecord) and _same_pair(parent, row)
    }
    future = {name: item["document"] for name, item in targets.items()}
    children: list[dict[str, Any]] = []
    for item, name in zip(changes.attribute_mappings, names, strict=True):
        document = item.attribute_mapping_transformation_document
        if document == future[name]:
            continue
        if targets[name]["is_locked"]:
            raise WorkbenchError(
                "record_locked", "Unlock the target Attribute and its Mapping before editing."
            )
        future[name] = document
        child = existing.get(name)
        if child is None and document is None:
            continue
        values = (
            child.model_dump(mode="json")
            if child
            else {
                "modeled_entity_type": parent.modeled_entity_type,
                "modeled_entity_schema_name": parent.modeled_entity_schema_name,
                "modeled_entity_name": parent.modeled_entity_name,
                "modeled_attribute_name": targets[name]["name"],
                "source_system_code": parent.source_system_code,
                "output_template_code": None,
                "attribute_mapping_status": "active",
                "attribute_mapping_is_locked": False,
            }
        )
        values["attribute_mapping_transformation_document"] = document
        children.append(values)

    # Only the standard templates declare this source hierarchy. Custom JSON remains opaque.
    if data["structured"]:
        available = {_reference_key(table["reference"]): table for table in data["source_tables"]}
        selected: set[tuple[str, ...]] = set()
        for field in (
            "source_tables",
            "source_objects",
            "source_logical_entities",
            "source_dimensional_entities",
        ):
            refs = (object_document or {}).get(field, [])
            if not isinstance(refs, list):
                raise InvalidRequestError("Object source tables must be an array.")
            for reference in cast(list[Any], refs):
                if not isinstance(reference, dict):
                    raise InvalidRequestError("Choose an eligible source table.")
                key = _reference_key(cast(dict[str, Any], reference))
                if key not in available:
                    raise InvalidRequestError(
                        "A selected source table is outside this Mapping's eligible scope."
                    )
                selected.add(key)
        for name, document in future.items():
            if not document or not targets[name]["structured"]:
                continue
            for field in (
                "source_columns",
                "source_attributes",
                "source_logical_attributes",
                "source_dimensional_attributes",
            ):
                refs: Any = document.get(field) or []
                if not isinstance(refs, list):
                    raise InvalidRequestError("Attribute source columns must be an array.")
                for reference in cast(list[Any], refs):
                    if not isinstance(reference, dict):
                        raise InvalidRequestError("Choose an eligible source column.")
                    key = _reference_key(cast(dict[str, Any], reference))
                    reference = cast(dict[str, Any], reference)
                    column = reference.get(
                        "attribute_name",
                        reference.get(
                            "logical_attribute_name", reference.get("dimensional_attribute_name")
                        ),
                    )
                    if key not in selected:
                        raise InvalidRequestError(
                            "Select the source table on the Object before using its columns. "
                            "Remove affected Attribute references before removing a table."
                        )
                    if not isinstance(column, str) or normalize_model_key_value(column) not in {
                        normalize_model_key_value(item["name"])
                        for item in available[key]["columns"]
                    }:
                        raise InvalidRequestError("A selected source column is no longer eligible.")
    edited = parent.model_copy(
        update={
            "mapping_transformation_document": object_document,
            "object_dependency_order": dependency_order,
        }
    )
    staged: dict[ModelChangeSetDataset, list[dict[str, Any]]] = {}
    if command.mapping_target is not None or edited != parent:
        staged["mapping_object"] = [edited.model_dump(mode="json")]
    if children:
        staged["mapping_attribute"] = children
    validation = validate_future_graph(
        snapshot=review.snapshot, staged_documents=staged, physical_scope=physical_scope
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "This Mapping edit conflicts with model references or protected records."
        )
    return validation
