"""Deterministic DBML projection from the shared ID-free Model Snapshot."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from gds_etl_workbench.domain.modeling_records import ModelingRecord
from gds_etl_workbench.tools.snapshots.archive import SnapshotContractError
from gds_etl_workbench.tools.snapshots.model.contracts import ModelSnapshot

type DbmlModelType = Literal["full", "conceptual", "logical", "dimensional"]
type DbmlLayer = Literal["conceptual", "logical", "dimensional"]
type DbmlView = Literal["complete", "submodel", "default"]

MAX_DBML_FILE_COUNT = 1_002
MAX_DBML_FILE_BYTES = 12 * 1024 * 1024
MAX_DBML_TOTAL_BYTES = 16 * 1024 * 1024

_EFFECTIVE_STATUSES = frozenset({"active", "needs_review"})
_CARDINALITY_OPERATORS = {
    "one_to_one": "-",
    "one_to_many": "<",
    "many_to_one": ">",
    "many_to_many": "<>",
}
_COLORS = (
    "#4E79A7",
    "#F28E2B",
    "#59A14F",
    "#E15759",
    "#B07AA1",
    "#76B7B2",
    "#EDC948",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
)
_TYPE_PARAMETER = r"(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?)"
_SAFE_DBML_TYPE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
    rf"(?:\({_TYPE_PARAMETER}(?: *, *{_TYPE_PARAMETER})*\))?"
)
_MAX_FILENAME_STEM = 250


@dataclass(frozen=True, slots=True)
class DbmlDocument:
    path: str
    layer: DbmlLayer
    view: DbmlView
    submodel_name: str | None
    content: bytes
    table_count: int
    relationship_count: int


@dataclass(frozen=True, slots=True)
class _Submodel:
    name: str
    definition: str


@dataclass(frozen=True, slots=True)
class _Entity:
    name: str
    dependency_order: int
    color_group: str
    notes: tuple[tuple[str, object | None], ...]
    submodel_keys: frozenset[str]


@dataclass(frozen=True, slots=True)
class _Attribute:
    entity_key: str
    name: str
    data_type: str
    ordinal: int
    nullable: bool
    primary_key: bool
    natural_key: bool
    surrogate_key: bool
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Relationship:
    name: str
    definition: str
    from_entity_key: str
    from_attribute_key: str
    to_entity_key: str
    to_attribute_key: str
    cardinality: str
    notes: tuple[tuple[str, object | None], ...]


@dataclass(frozen=True, slots=True)
class _ModeledLayer:
    layer: Literal["logical", "dimensional"]
    submodels: tuple[_Submodel, ...]
    entities: tuple[_Entity, ...]
    attributes_by_entity: Mapping[str, tuple[_Attribute, ...]]
    relationships: tuple[_Relationship, ...]


def render_dbml_documents(
    snapshot: ModelSnapshot,
    *,
    model_type: DbmlModelType,
    include_submodels: bool,
) -> tuple[DbmlDocument, ...]:
    """Render complete and optional submodel DBML documents with fixed bounds."""
    if model_type not in {"full", "conceptual", "logical", "dimensional"}:
        raise SnapshotContractError("DBML model_type is invalid")
    if type(include_submodels) is not bool:
        raise SnapshotContractError("DBML include_submodels must be a boolean")

    documents: list[DbmlDocument] = []
    if model_type in {"full", "conceptual"}:
        documents.append(_render_conceptual(snapshot))
    if model_type in {"full", "logical"}:
        documents.extend(
            _render_modeled_documents(
                snapshot,
                _logical_layer(snapshot),
                include_submodels=include_submodels,
            )
        )
    if model_type in {"full", "dimensional"}:
        documents.extend(
            _render_modeled_documents(
                snapshot,
                _dimensional_layer(snapshot),
                include_submodels=include_submodels,
            )
        )

    documents.sort(key=lambda item: item.path)
    paths = [document.path.casefold() for document in documents]
    if not documents or len(documents) > MAX_DBML_FILE_COUNT:
        raise SnapshotContractError("DBML Snapshot file count is invalid")
    if len(paths) != len(set(paths)):
        raise SnapshotContractError("DBML Snapshot contains colliding filenames")
    if any(not _safe_filename(document.path) for document in documents):
        raise SnapshotContractError("DBML Snapshot contains an unsafe filename")
    if any(
        not document.content or len(document.content) > MAX_DBML_FILE_BYTES
        for document in documents
    ):
        raise SnapshotContractError("A DBML file exceeds its byte limit")
    if sum(len(document.content) for document in documents) > MAX_DBML_TOTAL_BYTES:
        raise SnapshotContractError("DBML files exceed their aggregate byte limit")
    return tuple(documents)


def _render_conceptual(snapshot: ModelSnapshot) -> DbmlDocument:
    objects = tuple(
        sorted(
            (
                record
                for record in snapshot.conceptual.objects
                if _effective(record.conceptual_object_status)
            ),
            key=lambda record: _sort_text(record.conceptual_object_name),
        )
    )
    object_by_key = _unique_records(
        objects,
        lambda record: record.conceptual_object_name,
        "Conceptual Object",
    )
    colors = _color_map(
        {
            _normalize(record.conceptual_object_name): record.conceptual_object_type
            for record in objects
        }
    )
    relationships = tuple(
        sorted(
            (
                record
                for record in snapshot.conceptual.relationships
                if _effective(record.conceptual_relationship_status)
            ),
            key=lambda record: (
                _sort_text(record.from_conceptual_object_name),
                _sort_text(record.to_conceptual_object_name),
                _sort_text(record.conceptual_relationship_name),
            ),
        )
    )
    lines = _project_lines(snapshot, "conceptual", "Complete conceptual model")
    for record in objects:
        object_key = _normalize(record.conceptual_object_name)
        lines.extend(
            [
                _table_header(record.conceptual_object_name, colors[object_key]),
                '  "__conceptual_key" conceptual_key [pk, not null, '
                "note: 'Visualization-only endpoint; not a modeled Attribute.']",
                *_note_lines(
                    (
                        ("Type", record.conceptual_object_type),
                        ("Grain", record.conceptual_object_grain),
                        ("Definition", record.conceptual_object_definition),
                        ("Aliases", record.conceptual_object_aliases),
                        ("Confidence", record.conceptual_object_confidence),
                    )
                ),
                "}",
                "",
            ]
        )
    for index, record in enumerate(relationships, start=1):
        from_key = _normalize(record.from_conceptual_object_name)
        to_key = _normalize(record.to_conceptual_object_name)
        if from_key not in object_by_key or to_key not in object_by_key:
            raise SnapshotContractError(
                "An effective Conceptual Relationship has an inactive or missing endpoint"
            )
        cardinality_operator = _CARDINALITY_OPERATORS.get(
            record.conceptual_relationship_cardinality,
            "-",
        )
        lines.extend(
            [
                _comment(
                    (
                        ("Relationship", record.conceptual_relationship_name),
                        ("Type", record.conceptual_relationship_type),
                        ("Definition", record.conceptual_relationship_definition),
                        ("Basis", record.conceptual_relationship_basis),
                    )
                ),
                *(
                    ["// Cardinality is unknown; rendered as one-to-one fallback."]
                    if record.conceptual_relationship_cardinality == "unknown"
                    else []
                ),
                (
                    f"Ref conceptual_relationship_{index}: "
                    f"{_identifier(object_by_key[from_key].conceptual_object_name)}."
                    '"__conceptual_key" '
                    f"{cardinality_operator} "
                    f"{_identifier(object_by_key[to_key].conceptual_object_name)}."
                    '"__conceptual_key"'
                ),
                "",
            ]
        )
    return _document(
        path="conceptual.dbml",
        layer="conceptual",
        view="complete",
        submodel_name=None,
        lines=lines,
        table_count=len(objects),
        relationship_count=len(relationships),
    )


def _logical_layer(snapshot: ModelSnapshot) -> _ModeledLayer:
    submodels = _submodels(
        (
            (record.logical_submodel_name, record.logical_submodel_definition)
            for record in snapshot.logical.submodels
            if _effective(record.logical_submodel_status)
        ),
        "Logical Submodel",
    )
    submodel_keys = {_normalize(item.name) for item in submodels}
    entities: list[_Entity] = []
    entity_records = tuple(
        record for record in snapshot.logical.entities if _effective(record.logical_entity_status)
    )
    _unique_records(entity_records, lambda record: record.logical_entity_name, "Logical Entity")
    for record in entity_records:
        memberships = _effective_memberships(record.submodels, submodel_keys, "Logical Entity")
        entities.append(
            _Entity(
                name=record.logical_entity_name,
                dependency_order=record.logical_entity_dependency_order,
                color_group=str(record.logical_entity_dependency_order),
                notes=(
                    ("Type", record.logical_entity_type),
                    ("Type detail", record.logical_entity_type_detail),
                    ("Grain", record.logical_entity_grain),
                    ("Dependency order", record.logical_entity_dependency_order),
                    ("Definition", record.logical_entity_definition),
                    ("Confidence", record.logical_entity_confidence),
                ),
                submodel_keys=memberships,
            )
        )

    attributes: list[_Attribute] = []
    for record in snapshot.logical.attributes:
        if not _effective(record.logical_attribute_status):
            continue
        notes = [record.logical_attribute_definition]
        if record.logical_attribute_is_surrogate_key:
            notes.append("Surrogate key.")
        elif record.logical_attribute_is_natural_key:
            notes.append("Natural key.")
        if record.logical_attribute_is_audit_column:
            notes.append("Audit Attribute.")
        attributes.append(
            _Attribute(
                entity_key=_normalize(record.logical_entity_name),
                name=record.logical_attribute_name,
                data_type=record.logical_attribute_data_type,
                ordinal=record.logical_attribute_ordinal_position,
                nullable=record.logical_attribute_is_nullable,
                primary_key=record.logical_attribute_is_primary_key,
                natural_key=record.logical_attribute_is_natural_key,
                surrogate_key=record.logical_attribute_is_surrogate_key,
                notes=tuple(notes),
            )
        )
    relationships = tuple(
        _Relationship(
            name=record.logical_relationship_name,
            definition=record.logical_relationship_definition,
            from_entity_key=_normalize(record.from_logical_entity_name),
            from_attribute_key=_normalize(record.from_logical_attribute_name),
            to_entity_key=_normalize(record.to_logical_entity_name),
            to_attribute_key=_normalize(record.to_logical_attribute_name),
            cardinality=record.logical_relationship_cardinality,
            notes=(
                ("Basis", record.logical_relationship_basis),
                ("Confidence", record.logical_relationship_confidence),
            ),
        )
        for record in snapshot.logical.relationships
        if _effective(record.logical_relationship_status)
    )
    return _prepare_modeled_layer(
        layer="logical",
        submodels=submodels,
        entities=entities,
        attributes=attributes,
        relationships=relationships,
    )


def _dimensional_layer(snapshot: ModelSnapshot) -> _ModeledLayer:
    submodels = _submodels(
        (
            (record.dimensional_submodel_name, record.dimensional_submodel_definition)
            for record in snapshot.dimensional.submodels
            if _effective(record.dimensional_submodel_status)
        ),
        "Dimensional Submodel",
    )
    submodel_keys = {_normalize(item.name) for item in submodels}
    entities: list[_Entity] = []
    entity_records = tuple(
        record
        for record in snapshot.dimensional.entities
        if _effective(record.dimensional_entity_status)
    )
    _unique_records(
        entity_records,
        lambda record: record.dimensional_entity_name,
        "Dimensional Entity",
    )
    for record in entity_records:
        memberships = _effective_memberships(
            record.submodels,
            submodel_keys,
            "Dimensional Entity",
        )
        entities.append(
            _Entity(
                name=record.dimensional_entity_name,
                dependency_order=record.dimensional_entity_dependency_order,
                color_group=record.dimensional_entity_type,
                notes=(
                    ("Type", record.dimensional_entity_type),
                    ("Fact type", record.dimensional_fact_type),
                    ("Grain", record.dimensional_entity_grain_definition),
                    ("Dependency order", record.dimensional_entity_dependency_order),
                    ("Definition", record.dimensional_entity_definition),
                    ("Confidence", record.dimensional_entity_confidence),
                ),
                submodel_keys=memberships,
            )
        )

    attributes: list[_Attribute] = []
    for record in snapshot.dimensional.attributes:
        if not _effective(record.dimensional_attribute_status):
            continue
        key_role = record.dimensional_attribute_key_role
        notes = [
            record.dimensional_attribute_definition,
            f"Role: {record.dimensional_attribute_role}.",
        ]
        if key_role != "none":
            notes.append(f"Key role: {key_role}.")
        if record.dimensional_attribute_is_grain_component:
            notes.append("Grain component.")
        if record.dimensional_attribute_additivity is not None:
            notes.append(f"Additivity: {record.dimensional_attribute_additivity}.")
        if record.dimensional_attribute_default_aggregation is not None:
            notes.append(
                f"Default aggregation: {record.dimensional_attribute_default_aggregation}."
            )
        if record.dimensional_attribute_aggregation_basis is not None:
            notes.append(f"Aggregation basis: {record.dimensional_attribute_aggregation_basis}")
        if record.dimensional_attribute_change_behavior is not None:
            notes.append(f"Change behavior: {record.dimensional_attribute_change_behavior}.")
        attributes.append(
            _Attribute(
                entity_key=_normalize(record.dimensional_entity_name),
                name=record.dimensional_attribute_name,
                data_type=record.dimensional_attribute_data_type,
                ordinal=record.dimensional_attribute_ordinal_position,
                nullable=record.dimensional_attribute_is_nullable,
                primary_key=key_role == "surrogate",
                natural_key=key_role == "business",
                surrogate_key=False,
                notes=tuple(notes),
            )
        )
    relationships = tuple(
        _Relationship(
            name=record.dimensional_relationship_name,
            definition=record.dimensional_relationship_definition,
            from_entity_key=_normalize(record.from_dimensional_entity_name),
            from_attribute_key=_normalize(record.from_dimensional_attribute_name),
            to_entity_key=_normalize(record.to_dimensional_entity_name),
            to_attribute_key=_normalize(record.to_dimensional_attribute_name),
            cardinality=record.dimensional_relationship_cardinality,
            notes=(
                ("Kind", record.dimensional_relationship_kind),
                ("Role", record.dimensional_relationship_role_name),
                (
                    "Optional",
                    "yes" if record.dimensional_relationship_is_optional else "no",
                ),
                ("Basis", record.dimensional_relationship_basis),
                ("Confidence", record.dimensional_relationship_confidence),
            ),
        )
        for record in snapshot.dimensional.relationships
        if _effective(record.dimensional_relationship_status)
    )
    return _prepare_modeled_layer(
        layer="dimensional",
        submodels=submodels,
        entities=entities,
        attributes=attributes,
        relationships=relationships,
    )


def _prepare_modeled_layer(
    *,
    layer: Literal["logical", "dimensional"],
    submodels: tuple[_Submodel, ...],
    entities: list[_Entity],
    attributes: list[_Attribute],
    relationships: tuple[_Relationship, ...],
) -> _ModeledLayer:
    entities.sort(key=lambda item: (item.dependency_order, _sort_text(item.name)))
    entity_by_key = {_normalize(entity.name): entity for entity in entities}
    attributes_by_entity: dict[str, list[_Attribute]] = defaultdict(list)
    attribute_keys: set[tuple[str, str]] = set()
    for attribute in attributes:
        key = (attribute.entity_key, _normalize(attribute.name))
        if attribute.entity_key not in entity_by_key:
            raise SnapshotContractError(
                f"An effective {layer.title()} Attribute has an inactive or missing Entity"
            )
        if key in attribute_keys:
            raise SnapshotContractError(f"Effective {layer.title()} Attribute names are not unique")
        attribute_keys.add(key)
        attributes_by_entity[attribute.entity_key].append(attribute)
    for entity_attributes in attributes_by_entity.values():
        entity_attributes.sort(key=lambda item: (item.ordinal, _sort_text(item.name)))

    ordered_relationships = tuple(
        sorted(
            relationships,
            key=lambda item: (
                item.from_entity_key,
                item.to_entity_key,
                _sort_text(item.name),
            ),
        )
    )
    for relationship in ordered_relationships:
        endpoints = (
            (relationship.from_entity_key, relationship.from_attribute_key),
            (relationship.to_entity_key, relationship.to_attribute_key),
        )
        if any(endpoint not in attribute_keys for endpoint in endpoints):
            raise SnapshotContractError(
                f"An effective {layer.title()} Relationship has an inactive or missing endpoint"
            )
    return _ModeledLayer(
        layer=layer,
        submodels=submodels,
        entities=tuple(entities),
        attributes_by_entity={key: tuple(value) for key, value in attributes_by_entity.items()},
        relationships=ordered_relationships,
    )


def _render_modeled_documents(
    snapshot: ModelSnapshot,
    data: _ModeledLayer,
    *,
    include_submodels: bool,
) -> tuple[DbmlDocument, ...]:
    documents = [
        _render_modeled(
            snapshot,
            data,
            entity_keys=None,
            path=f"{data.layer}_complete.dbml",
            view="complete",
            submodel_name=None,
            description=f"Complete {data.layer} model",
        )
    ]
    if not include_submodels:
        return tuple(documents)

    filenames = _submodel_filenames(data.layer, data.submodels)
    assigned: set[str] = set()
    for submodel in data.submodels:
        submodel_key = _normalize(submodel.name)
        members = frozenset(
            _normalize(entity.name)
            for entity in data.entities
            if submodel_key in entity.submodel_keys
        )
        assigned.update(members)
        documents.append(
            _render_modeled(
                snapshot,
                data,
                entity_keys=members,
                path=filenames[submodel_key],
                view="submodel",
                submodel_name=submodel.name,
                description=(
                    f"{data.layer.title()} Submodel: {submodel.name}. {submodel.definition}"
                ),
            )
        )
    all_entities = {_normalize(entity.name) for entity in data.entities}
    default_entities = frozenset(all_entities - assigned)
    if default_entities:
        documents.append(
            _render_modeled(
                snapshot,
                data,
                entity_keys=default_entities,
                path=f"{data.layer}_default.dbml",
                view="default",
                submodel_name=None,
                description=(
                    f"{data.layer.title()} Entities without an active Submodel membership"
                ),
            )
        )
    return tuple(documents)


def _render_modeled(
    snapshot: ModelSnapshot,
    data: _ModeledLayer,
    *,
    entity_keys: frozenset[str] | None,
    path: str,
    view: DbmlView,
    submodel_name: str | None,
    description: str,
) -> DbmlDocument:
    included = (
        frozenset(_normalize(entity.name) for entity in data.entities)
        if entity_keys is None
        else entity_keys
    )
    colors = _color_map({_normalize(entity.name): entity.color_group for entity in data.entities})
    lines = _project_lines(snapshot, _token(description), description)
    table_count = 0
    for entity in data.entities:
        entity_key = _normalize(entity.name)
        if entity_key not in included:
            continue
        table_count += 1
        lines.append(_table_header(entity.name, colors[entity_key]))
        attributes = data.attributes_by_entity.get(entity_key, ())
        inline, indexes = _key_settings(attributes)
        for attribute in attributes:
            settings = list(inline.get(_normalize(attribute.name), ()))
            settings.append("null" if attribute.nullable else "not null")
            if attribute.notes:
                settings.append(f"note: {_single_quoted(' '.join(attribute.notes))}")
            lines.append(
                f"  {_identifier(attribute.name)} {_dbml_type(attribute.data_type)} "
                f"[{', '.join(settings)}]"
            )
        if indexes:
            lines.append("  indexes {")
            for names, setting in indexes:
                columns = ", ".join(_identifier(name) for name in names)
                lines.append(f"    ({columns}) [{setting}]")
            lines.append("  }")
        lines.extend([*_note_lines(entity.notes), "}", ""])

    relationship_count = 0
    entity_by_key = {_normalize(entity.name): entity for entity in data.entities}
    attribute_by_key = {
        (entity_key, _normalize(attribute.name)): attribute
        for entity_key, attributes in data.attributes_by_entity.items()
        for attribute in attributes
    }
    for relationship in data.relationships:
        if (
            relationship.from_entity_key not in included
            or relationship.to_entity_key not in included
        ):
            continue
        relationship_count += 1
        from_entity = entity_by_key[relationship.from_entity_key]
        to_entity = entity_by_key[relationship.to_entity_key]
        from_attribute = attribute_by_key[
            (relationship.from_entity_key, relationship.from_attribute_key)
        ]
        to_attribute = attribute_by_key[(relationship.to_entity_key, relationship.to_attribute_key)]
        lines.extend(
            [
                _comment(
                    (
                        ("Relationship", relationship.name),
                        ("Definition", relationship.definition),
                        *relationship.notes,
                    )
                ),
                (
                    f"Ref {data.layer}_relationship_{relationship_count}: "
                    f"{_identifier(from_entity.name)}.{_identifier(from_attribute.name)} "
                    f"{_CARDINALITY_OPERATORS[relationship.cardinality]} "
                    f"{_identifier(to_entity.name)}.{_identifier(to_attribute.name)}"
                ),
                "",
            ]
        )
    return _document(
        path=path,
        layer=data.layer,
        view=view,
        submodel_name=submodel_name,
        lines=lines,
        table_count=table_count,
        relationship_count=relationship_count,
    )


def _submodels(
    values: Iterable[tuple[str, str]],
    label: str,
) -> tuple[_Submodel, ...]:
    result = tuple(
        sorted(
            (_Submodel(name=name, definition=definition) for name, definition in values),
            key=lambda item: _sort_text(item.name),
        )
    )
    keys = [_normalize(item.name) for item in result]
    if len(keys) != len(set(keys)):
        raise SnapshotContractError(f"Effective {label} names are not unique")
    return result


def _effective_memberships(
    memberships: Iterable[ModelingRecord],
    active_submodel_keys: set[str],
    label: str,
) -> frozenset[str]:
    result: set[str] = set()
    for membership in memberships:
        status = getattr(membership, "membership_status", None)
        if not isinstance(status, str) or not _effective(status):
            continue
        name = getattr(membership, "submodel_name", None)
        if not isinstance(name, str) or _normalize(name) not in active_submodel_keys:
            raise SnapshotContractError(
                f"An effective {label} membership has an inactive or missing Submodel"
            )
        result.add(_normalize(name))
    return frozenset(result)


def _unique_records[RecordT: ModelingRecord](
    records: Iterable[RecordT],
    name_of: Callable[[RecordT], str],
    label: str,
) -> dict[str, RecordT]:
    result: dict[str, RecordT] = {}
    for record in records:
        name = name_of(record)
        key = _normalize(name)
        if key in result:
            raise SnapshotContractError(f"Effective {label} names are not unique")
        result[key] = record
    return result


def _key_settings(
    attributes: Iterable[_Attribute],
) -> tuple[dict[str, tuple[str, ...]], list[tuple[tuple[str, ...], str]]]:
    rows = tuple(attributes)
    primary = tuple(item for item in rows if item.primary_key)
    natural = tuple(item for item in rows if item.natural_key and not item.primary_key)
    surrogate = tuple(item for item in rows if item.surrogate_key and not item.primary_key)
    inline: dict[str, list[str]] = defaultdict(list)
    indexes: list[tuple[tuple[str, ...], str]] = []
    if len(primary) == 1:
        inline[_normalize(primary[0].name)].append("pk")
    elif primary:
        indexes.append((tuple(item.name for item in primary), "pk"))
    if len(natural) == 1:
        inline[_normalize(natural[0].name)].append("unique")
    elif natural:
        indexes.append((tuple(item.name for item in natural), "unique"))
    for attribute in surrogate:
        inline[_normalize(attribute.name)].append("unique")
    return {key: tuple(value) for key, value in inline.items()}, indexes


def _submodel_filenames(
    layer: Literal["logical", "dimensional"],
    submodels: Iterable[_Submodel],
) -> dict[str, str]:
    rows = tuple(submodels)
    stems = {
        _normalize(item.name): f"{layer}_{_slug(item.name, fallback='submodel')}" for item in rows
    }
    base_names = {key: f"{stem[:_MAX_FILENAME_STEM]}.dbml" for key, stem in stems.items()}
    counts = Counter(name.casefold() for name in base_names.values())
    reserved = {
        "conceptual.dbml",
        "logical_complete.dbml",
        "logical_default.dbml",
        "dimensional_complete.dbml",
        "dimensional_default.dbml",
    }
    used = set(reserved)
    result: dict[str, str] = {}
    for item in rows:
        key = _normalize(item.name)
        base = base_names[key]
        if counts[base.casefold()] == 1 and base.casefold() not in reserved:
            candidate = base
        else:
            marker = "_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
            candidate = _filename_with_marker(stems[key], marker)
        if candidate.casefold() in used:
            raise SnapshotContractError("DBML Submodel filenames collide")
        used.add(candidate.casefold())
        result[key] = candidate
    return result


def _document(
    *,
    path: str,
    layer: DbmlLayer,
    view: DbmlView,
    submodel_name: str | None,
    lines: list[str],
    table_count: int,
    relationship_count: int,
) -> DbmlDocument:
    content = ("\n".join(lines).rstrip() + "\n").encode("utf-8")
    return DbmlDocument(
        path=path,
        layer=layer,
        view=view,
        submodel_name=submodel_name,
        content=content,
        table_count=table_count,
        relationship_count=relationship_count,
    )


def _effective(status: str) -> bool:
    return status in _EFFECTIVE_STATUSES


def _color_map(groups: Mapping[str, str]) -> dict[str, str]:
    normalized_groups = sorted({_normalize(value) for value in groups.values()})
    colors = {value: _COLORS[index % len(_COLORS)] for index, value in enumerate(normalized_groups)}
    return {key: colors[_normalize(group)] for key, group in groups.items()}


def _one_line(value: object) -> str:
    if isinstance(value, (list, tuple)):
        rendered = ", ".join(_one_line(item) for item in cast(Sequence[object], value))
    else:
        rendered = str(value)
    normalized = unicodedata.normalize("NFC", rendered)
    without_controls = "".join(
        " " if unicodedata.category(character) in {"Cc", "Cf", "Cs"} else character
        for character in normalized
    )
    return " ".join(without_controls.split())


def _normalize(value: str) -> str:
    return _one_line(value).casefold()


def _sort_text(value: str) -> str:
    return _normalize(value)


def _token(value: object, *, fallback: str = "item", limit: int = 128) -> str:
    token = re.sub(r"[^A-Za-z0-9_]+", "_", _one_line(value)).strip("_")
    if not token:
        token = fallback
    if token[0].isdigit():
        token = f"_{token}"
    return token[:limit]


def _slug(value: object, *, fallback: str) -> str:
    return _token(value, fallback=fallback, limit=_MAX_FILENAME_STEM).lower()


def _identifier(value: object) -> str:
    escaped = _one_line(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _single_quoted(value: object) -> str:
    escaped = _one_line(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _note_lines(values: Iterable[tuple[str, object | None]]) -> list[str]:
    content = [
        f"{label}: {_one_line(value)}"
        for label, value in values
        if value is not None and _one_line(value)
    ]
    if not content:
        return []
    escaped = [line.replace("\\", "\\\\").replace("'", "\\'") for line in content]
    return ["  Note: '''", *(f"  {line}" for line in escaped), "  '''"]


def _comment(values: Iterable[tuple[str, object | None]]) -> str:
    content = [
        f"{label}: {_one_line(value)}"
        for label, value in values
        if value is not None and _one_line(value)
    ]
    return f"// {' | '.join(content)}"


def _table_header(name: str, color: str) -> str:
    return f"Table {_identifier(name)} [headercolor: {color}] {{"


def _project_lines(snapshot: ModelSnapshot, suffix: str, description: str) -> list[str]:
    project_name = _token(f"{snapshot.model_name}_{suffix}", fallback="model")
    return [
        f"Project {project_name} {{",
        *_note_lines(
            (
                ("Model", snapshot.model_name),
                ("Model ID", snapshot.model_id),
                ("Model revision", snapshot.model_revision),
                ("View", description),
            )
        ),
        "}",
        "",
    ]


def _dbml_type(value: object) -> str:
    data_type = _one_line(value).strip() or "unknown"
    return data_type if _SAFE_DBML_TYPE.fullmatch(data_type) else _identifier(data_type)


def _filename_with_marker(stem: str, marker: str) -> str:
    available = _MAX_FILENAME_STEM - len(marker)
    if available < 1:
        raise SnapshotContractError("A DBML filename cannot be represented safely")
    return f"{stem[:available]}{marker}.dbml"


def _safe_filename(value: str) -> bool:
    return bool(len(value) <= 255 and re.fullmatch(r"[a-z0-9][a-z0-9_]{0,249}\.dbml", value))
