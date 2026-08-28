"""Deterministic first-stage Gold technical and audit policy projection."""

from __future__ import annotations

import json
from string import Formatter
from typing import Annotated, Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.change_sets.model_validation import validate_staged_records
from gds_etl_workbench.tools.snapshots.model.contracts import DimensionalSection
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

type _Nonblank255 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
]
type _Nonblank100 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"\S"),
]
type _Nonblank2000 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=2_000, pattern=r"\S"),
]


class GoldPolicyColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    semantic_name: _Nonblank255
    data_type: _Nonblank100
    nullable: bool
    definition: _Nonblank2000 | None


class _DimensionSurrogateKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    semantic_name_template: _Nonblank255
    data_type: _Nonblank100
    nullable: Literal[False]
    definition_template: _Nonblank2000

    @model_validator(mode="after")
    def validate_templates(self) -> _DimensionSurrogateKey:
        _validate_template(
            self.semantic_name_template,
            allowed={"entity_name"},
            required="entity_name",
        )
        _validate_template(self.definition_template, allowed={"entity_name"})
        return self


class _FactBridgeForeignKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    with_role_semantic_name_template: _Nonblank255
    without_role_semantic_name_template: _Nonblank255
    definition_template: _Nonblank2000

    @model_validator(mode="after")
    def validate_templates(self) -> _FactBridgeForeignKey:
        _validate_template(
            self.with_role_semantic_name_template,
            allowed={"role_name"},
            required="role_name",
        )
        _validate_template(
            self.without_role_semantic_name_template,
            allowed={"entity_name"},
            required="entity_name",
        )
        _validate_template(
            self.definition_template,
            allowed={"entity_name", "role_name"},
        )
        return self


class _Type2Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    effective_from: GoldPolicyColumn
    effective_to: GoldPolicyColumn
    is_current: GoldPolicyColumn

    @model_validator(mode="after")
    def validate_nullability(self) -> _Type2Policy:
        if (
            self.effective_from.nullable
            or not self.effective_to.nullable
            or self.is_current.nullable
        ):
            raise ValueError("Gold Type 2 policy nullability is invalid")
        names = [
            normalize_model_key_value(item.semantic_name)
            for item in (self.effective_from, self.effective_to, self.is_current)
        ]
        if len(names) != len(set(names)):
            raise ValueError("Gold Type 2 policy names must be unique")
        return self


class GoldTechnicalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    dimension_surrogate_key: _DimensionSurrogateKey
    fact_bridge_foreign_key: _FactBridgeForeignKey
    type_2: _Type2Policy


class GoldAuditPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    columns: tuple[GoldPolicyColumn, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_names(self) -> GoldAuditPolicy:
        names = [normalize_model_key_value(column.semantic_name) for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("Gold audit policy names must be unique")
        return self


def validate_dimensional_gold_policy(
    *,
    naming_instructions: str | None,
    raw_technical_template: dict[str, object] | None,
    raw_audit_template: dict[str, object] | None,
) -> None:
    """Require and parse the complete Gold policy group before agent work."""

    if naming_instructions is None or raw_technical_template is None or raw_audit_template is None:
        raise InvalidRequestError("Dimensional authoring requires the complete Gold policy group.")
    _parse_technical_policy(raw_technical_template)
    _parse_audit_policy(raw_audit_template)


def project_dimensional_gold_policy(
    *,
    changes: tuple[StageModelChange, ...],
    applied: DimensionalSection | None,
    raw_technical_template: dict[str, object] | None,
    raw_audit_template: dict[str, object] | None,
) -> tuple[StageModelChange, ...]:
    """Project Entity-local surrogate, Type 2, and audit Attributes.

    Relationship-derived Fact/Bridge foreign keys are applied separately after
    Relationships settle by ``project_dimensional_foreign_key_policy``.
    """

    if raw_technical_template is None and raw_audit_template is None:
        return changes
    if raw_technical_template is None or raw_audit_template is None:
        raise InvalidRequestError("The Gold policy template group is incomplete.")
    technical = _parse_technical_policy(raw_technical_template)
    audit = _parse_audit_policy(raw_audit_template)
    baseline = applied or DimensionalSection(
        submodels=(), entities=(), attributes=(), relationships=()
    )
    changes_by_dataset = {change.dataset: change for change in changes}
    if len(changes_by_dataset) != len(changes) or any(
        not change.dataset.startswith("dimensional_") for change in changes
    ):
        raise InvalidRequestError("Dimensional policy projection received invalid input.")

    changed_entities = _parse_records(
        changes_by_dataset.get("dimensional_entity"),
        dataset="dimensional_entity",
        record_type=DimensionalEntityRecord,
    )
    changed_attributes = _parse_records(
        changes_by_dataset.get("dimensional_attribute"),
        dataset="dimensional_attribute",
        record_type=DimensionalAttributeRecord,
    )
    entities = {_entity_key(record): record for record in baseline.entities}
    entities.update({_entity_key(record): record for record in changed_entities})
    attributes = {_attribute_key(record): record for record in baseline.attributes}
    attributes.update({_attribute_key(record): record for record in changed_attributes})

    projected: list[DimensionalAttributeRecord] = []
    for entity_key, entity in sorted(entities.items()):
        if entity.dimensional_entity_status not in ("active", "needs_review"):
            continue
        entity_attributes = [record for key, record in attributes.items() if key[0] == entity_key]
        business_ordinal = max(
            (
                record.dimensional_attribute_ordinal_position
                for record in entity_attributes
                if record.dimensional_attribute_role not in ("technical", "audit")
            ),
            default=0,
        )
        policy_ordinal_base = business_ordinal
        if entity.dimensional_entity_type in ("fact", "bridge"):
            policy_ordinal_base += sum(
                record.dimensional_attribute_key_role == "foreign"
                and record.dimensional_attribute_status in ("active", "needs_review")
                for record in entity_attributes
            )
        specifications: list[tuple[GoldPolicyColumn, Literal["technical", "audit"], str]] = []
        if entity.dimensional_entity_type == "dimension":
            try:
                surrogate = GoldPolicyColumn(
                    semantic_name=technical.dimension_surrogate_key.semantic_name_template.format(
                        entity_name=entity.dimensional_entity_name
                    ),
                    data_type=technical.dimension_surrogate_key.data_type,
                    nullable=False,
                    definition=technical.dimension_surrogate_key.definition_template.format(
                        entity_name=entity.dimensional_entity_name
                    ),
                )
            except ValidationError:
                raise InvalidRequestError(
                    "The Gold surrogate-key template produced an invalid column."
                ) from None
            specifications.append((surrogate, "technical", "surrogate"))
            if any(
                record.dimensional_attribute_change_behavior == "historize"
                and record.dimensional_attribute_role not in ("technical", "audit")
                and record.dimensional_attribute_status in ("active", "needs_review")
                for record in entity_attributes
            ):
                specifications.extend(
                    (column, "technical", "none")
                    for column in (
                        technical.type_2.effective_from,
                        technical.type_2.effective_to,
                        technical.type_2.is_current,
                    )
                )
        specifications.extend((column, "audit", "none") for column in audit.columns)
        normalized_names = [
            normalize_model_key_value(column.semantic_name) for column, _, _ in specifications
        ]
        if len(normalized_names) != len(set(normalized_names)):
            raise InvalidRequestError("Gold policy columns collide after normalization.")

        for offset, (column, role, key_role) in enumerate(specifications, start=1):
            key = (entity_key, normalize_model_key_value(column.semantic_name))
            existing = attributes.get(key)
            desired = _policy_attribute(
                entity=entity,
                column=column,
                role=role,
                key_role=key_role,
                ordinal=policy_ordinal_base + offset,
                existing=existing,
            )
            if existing != desired:
                projected.append(desired)
            attributes[key] = desired

    changed_attribute_by_key = {_attribute_key(record): record for record in changed_attributes}
    for record in projected:
        changed_attribute_by_key[_attribute_key(record)] = record

    output: list[StageModelChange] = []
    for dataset in (
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
    ):
        if dataset == "dimensional_attribute":
            records = [
                record.model_dump(mode="json")
                for record in sorted(
                    changed_attribute_by_key.values(),
                    key=lambda item: (
                        normalize_model_key_value(item.dimensional_entity_name),
                        item.dimensional_attribute_ordinal_position,
                        normalize_model_key_value(item.dimensional_attribute_name),
                    ),
                )
            ]
        else:
            change = changes_by_dataset.get(dataset)
            records = [] if change is None else change.records
        if records:
            output.append(StageModelChange(dataset=dataset, records=records))
    return tuple(output)


def project_dimensional_foreign_key_policy(
    *,
    changes: tuple[StageModelChange, ...],
    applied: DimensionalSection | None,
    raw_technical_template: dict[str, object] | None,
) -> tuple[StageModelChange, ...]:
    """Project Fact/Bridge foreign keys and bind their final Relationships."""

    if raw_technical_template is None:
        return changes
    technical = _parse_technical_policy(raw_technical_template)
    baseline = applied or DimensionalSection(
        submodels=(), entities=(), attributes=(), relationships=()
    )
    changes_by_dataset = {change.dataset: change for change in changes}
    if len(changes_by_dataset) != len(changes) or any(
        not change.dataset.startswith("dimensional_") for change in changes
    ):
        raise InvalidRequestError("Dimensional policy projection received invalid input.")

    changed_entities = _parse_records(
        changes_by_dataset.get("dimensional_entity"),
        dataset="dimensional_entity",
        record_type=DimensionalEntityRecord,
    )
    changed_attributes = _parse_records(
        changes_by_dataset.get("dimensional_attribute"),
        dataset="dimensional_attribute",
        record_type=DimensionalAttributeRecord,
    )
    changed_relationships = _parse_records(
        changes_by_dataset.get("dimensional_relationship"),
        dataset="dimensional_relationship",
        record_type=DimensionalRelationshipRecord,
    )
    entities = {_entity_key(record): record for record in baseline.entities}
    entities.update({_entity_key(record): record for record in changed_entities})
    attributes = {_attribute_key(record): record for record in baseline.attributes}
    attributes.update({_attribute_key(record): record for record in changed_attributes})
    applied_attributes = {_attribute_key(record): record for record in baseline.attributes}

    projected_relationships: list[DimensionalRelationshipRecord] = []
    projected_attributes: dict[tuple[str, str], DimensionalAttributeRecord] = {}
    projected_fk_keys: set[tuple[str, str]] = set()
    affected_entity_keys: set[str] = set()
    for relationship in changed_relationships:
        from_key = normalize_model_key_value(relationship.from_dimensional_entity_name)
        to_key = normalize_model_key_value(relationship.to_dimensional_entity_name)
        from_entity = entities.get(from_key)
        to_entity = entities.get(to_key)
        if from_entity is None or to_entity is None:
            raise InvalidRequestError("A Dimensional Relationship references an unknown Entity.")

        if from_entity.dimensional_entity_type in ("fact", "bridge"):
            if to_entity.dimensional_entity_type != "dimension":
                raise InvalidRequestError(
                    "Fact and Bridge Relationships must point to a Dimension."
                )
            surrogate_candidates = [
                attribute
                for attribute in attributes.values()
                if _entity_key_from_attribute(attribute) == to_key
                and attribute.dimensional_attribute_role == "technical"
                and attribute.dimensional_attribute_key_role == "surrogate"
                and attribute.dimensional_attribute_status in ("active", "needs_review")
            ]
            if len(surrogate_candidates) != 1:
                raise InvalidRequestError(
                    "A referenced Dimension must have exactly one effective surrogate key."
                )
            surrogate = surrogate_candidates[0]
            role_name = relationship.dimensional_relationship_role_name
            try:
                semantic_name = (
                    technical.fact_bridge_foreign_key.with_role_semantic_name_template.format(
                        role_name=role_name
                    )
                    if role_name is not None
                    else (
                        technical.fact_bridge_foreign_key.without_role_semantic_name_template.format(
                            entity_name=to_entity.dimensional_entity_name
                        )
                    )
                )
                definition = technical.fact_bridge_foreign_key.definition_template.format(
                    entity_name=to_entity.dimensional_entity_name,
                    role_name=(role_name or to_entity.dimensional_entity_name),
                )
                column = GoldPolicyColumn(
                    semantic_name=semantic_name,
                    data_type=surrogate.dimensional_attribute_data_type,
                    nullable=relationship.dimensional_relationship_is_optional,
                    definition=definition,
                )
            except (KeyError, ValidationError):
                raise InvalidRequestError(
                    "The Gold foreign-key template produced an invalid column."
                ) from None
            attribute_key = (
                from_key,
                normalize_model_key_value(column.semantic_name),
            )
            if attribute_key in projected_fk_keys:
                raise InvalidRequestError(
                    "Two Dimensional Relationships project the same foreign-key name."
                )
            projected_fk_keys.add(attribute_key)
            existing = attributes.get(attribute_key)
            desired = _policy_attribute(
                entity=from_entity,
                column=column,
                role="technical",
                key_role="foreign",
                ordinal=1,
                existing=existing,
            )
            attributes[attribute_key] = desired
            projected_attributes[attribute_key] = desired
            affected_entity_keys.add(from_key)
            projected_relationships.append(
                relationship.model_copy(
                    update={
                        "from_dimensional_attribute_name": desired.dimensional_attribute_name,
                        "to_dimensional_attribute_name": (surrogate.dimensional_attribute_name),
                    }
                )
            )
        elif to_entity.dimensional_entity_type in ("fact", "bridge"):
            raise InvalidRequestError("Fact and Bridge Relationships must use the from endpoint.")
        else:
            projected_relationships.append(relationship)

    for entity_key in sorted(affected_entity_keys):
        entity_attributes = [
            record
            for record in attributes.values()
            if _entity_key_from_attribute(record) == entity_key
        ]
        business = [
            record
            for record in entity_attributes
            if record.dimensional_attribute_role not in ("technical", "audit")
        ]
        technical_attributes = sorted(
            (
                record
                for record in entity_attributes
                if record.dimensional_attribute_role == "technical"
            ),
            key=lambda item: (
                0 if item.dimensional_attribute_key_role == "surrogate" else 1,
                normalize_model_key_value(item.dimensional_attribute_name),
            ),
        )
        audit_attributes = sorted(
            (
                record
                for record in entity_attributes
                if record.dimensional_attribute_role == "audit"
            ),
            key=lambda item: (
                item.dimensional_attribute_ordinal_position,
                normalize_model_key_value(item.dimensional_attribute_name),
            ),
        )
        next_ordinal = max(
            (item.dimensional_attribute_ordinal_position for item in business),
            default=0,
        )
        for offset, record in enumerate(
            (*technical_attributes, *audit_attributes),
            start=1,
        ):
            reordered = record.model_copy(
                update={"dimensional_attribute_ordinal_position": next_ordinal + offset}
            )
            key = _attribute_key(reordered)
            applied_record = applied_attributes.get(key)
            if (
                applied_record is not None
                and applied_record.dimensional_attribute_is_locked
                and applied_record != reordered
            ):
                raise InvalidRequestError("A locked Gold policy column cannot be projected.")
            attributes[key] = reordered
            if applied_record != reordered:
                projected_attributes[key] = reordered

    changed_attribute_by_key = {_attribute_key(record): record for record in changed_attributes}
    changed_attribute_by_key.update(projected_attributes)
    output: list[StageModelChange] = []
    for dataset in (
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
    ):
        if dataset == "dimensional_attribute":
            records = [
                record.model_dump(mode="json")
                for record in sorted(
                    changed_attribute_by_key.values(),
                    key=lambda item: (
                        _entity_key_from_attribute(item),
                        item.dimensional_attribute_ordinal_position,
                        normalize_model_key_value(item.dimensional_attribute_name),
                    ),
                )
            ]
        elif dataset == "dimensional_relationship":
            records = [record.model_dump(mode="json") for record in projected_relationships]
        else:
            change = changes_by_dataset.get(dataset)
            records = [] if change is None else change.records
        if records:
            output.append(StageModelChange(dataset=dataset, records=records))
    return tuple(output)


def _parse_technical_policy(raw_template: dict[str, object]) -> GoldTechnicalPolicy:
    try:
        return GoldTechnicalPolicy.model_validate_json(
            json.dumps(raw_template, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError):
        raise InvalidRequestError("The Gold technical-column template is invalid.") from None


def _parse_audit_policy(raw_template: dict[str, object]) -> GoldAuditPolicy:
    try:
        return GoldAuditPolicy.model_validate_json(
            json.dumps(raw_template, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError):
        raise InvalidRequestError("The Gold audit-column template is invalid.") from None


def _parse_records[T: BaseModel](
    change: StageModelChange | None,
    *,
    dataset: Literal[
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
    ],
    record_type: type[T],
) -> tuple[T, ...]:
    if change is None:
        return ()
    records, issues = validate_staged_records(dataset, change.records)
    if issues:
        raise InvalidRequestError("Dimensional policy projection received invalid input.")
    return tuple(cast(T, record) for record in records if isinstance(record, record_type))


def _policy_attribute(
    *,
    entity: DimensionalEntityRecord,
    column: GoldPolicyColumn,
    role: Literal["technical", "audit"],
    key_role: str,
    ordinal: int,
    existing: DimensionalAttributeRecord | None,
) -> DimensionalAttributeRecord:
    if existing is not None and (
        existing.dimensional_attribute_role != role
        or normalize_model_key_value(existing.dimensional_attribute_data_type)
        != normalize_model_key_value(column.data_type)
        or existing.dimensional_attribute_is_nullable != column.nullable
        or existing.dimensional_attribute_key_role != key_role
        or existing.sources
    ):
        raise InvalidRequestError(
            "A configured Gold policy column conflicts with an existing Attribute."
        )
    desired = DimensionalAttributeRecord(
        dimensional_entity_name=entity.dimensional_entity_name,
        dimensional_attribute_name=column.semantic_name,
        dimensional_attribute_definition=column.definition or column.semantic_name,
        dimensional_attribute_data_type=column.data_type,
        dimensional_attribute_is_nullable=column.nullable,
        dimensional_attribute_ordinal_position=ordinal,
        dimensional_attribute_role=role,
        dimensional_attribute_key_role=cast(
            Literal["none", "surrogate", "business", "foreign"], key_role
        ),
        dimensional_attribute_is_grain_component=key_role in ("surrogate", "foreign"),
        dimensional_attribute_additivity=None,
        dimensional_attribute_default_aggregation=None,
        dimensional_attribute_aggregation_basis=None,
        dimensional_attribute_change_behavior="fixed",
        dimensional_attribute_is_audit_column=role == "audit",
        dimensional_attribute_confidence="high",
        dimensional_attribute_status="active",
        dimensional_attribute_is_locked=(
            existing.dimensional_attribute_is_locked if existing is not None else False
        ),
        sources=(),
    )
    if existing is not None and existing.dimensional_attribute_is_locked and existing != desired:
        raise InvalidRequestError("A locked Gold policy column cannot be projected.")
    return desired


def _validate_template(
    value: str,
    *,
    allowed: set[str],
    required: str | None = None,
) -> None:
    try:
        parsed = tuple(Formatter().parse(value))
    except ValueError:
        raise ValueError("Gold policy template syntax is invalid") from None
    fields = [field for _, field, _, _ in parsed if field is not None]
    if (
        any(field not in allowed for field in fields)
        or (required is not None and required not in fields)
        or any(format_spec or conversion for _, _, format_spec, conversion in parsed)
    ):
        raise ValueError("Gold policy template placeholders are invalid")


def _entity_key(record: DimensionalEntityRecord) -> str:
    return normalize_model_key_value(record.dimensional_entity_name)


def _attribute_key(record: DimensionalAttributeRecord) -> tuple[str, str]:
    return (
        normalize_model_key_value(record.dimensional_entity_name),
        normalize_model_key_value(record.dimensional_attribute_name),
    )


def _entity_key_from_attribute(record: DimensionalAttributeRecord) -> str:
    return normalize_model_key_value(record.dimensional_entity_name)


__all__ = [
    "GoldAuditPolicy",
    "GoldPolicyColumn",
    "GoldTechnicalPolicy",
    "project_dimensional_foreign_key_policy",
    "project_dimensional_gold_policy",
    "validate_dimensional_gold_policy",
]
