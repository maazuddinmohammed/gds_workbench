"""Model Snapshot registry and its MCP-writable Model Change Set subset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ConceptualObjectRecord,
    ConceptualRelationshipRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    DimensionalSubmodelRecord,
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
    LogicalSubmodelRecord,
    MappingAttributeRecord,
    MappingDependencyRecord,
    MappingObjectRecord,
    ModelAttributeBindingRecord,
    ModelDetailsRecord,
    ModelingAssertionDocumentRecord,
    ModelingAssertionRecordRecord,
    ModelingRecord,
    ModelInputScopeRecord,
    ModelObjectBindingRecord,
    ProfilingProfileRecord,
    ValidationCheckRecord,
    ValidationGroupRecord,
)
from gds_etl_workbench.domain.portable_validation import (
    MODEL_RECORD_VALIDATIONS,
    record_validation_contract,
)

from .guidance import enrich_model_dataset_schema

type ModelSection = Literal[
    "model_input_scope",
    "profiling",
    "analysis",
    "assertion",
    "conceptual",
    "logical",
    "dimensional",
    "model_binding",
    "mapping",
    "code_generation",
    "validation",
]

type ModelDataset = Literal[
    "model_details",
    "model_input_scope",
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
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
    "model_object_binding",
    "model_attribute_binding",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
    "generated_code",
    "generated_code_source_system",
    "validation_group",
    "validation_check",
]

type ModelChangeSetDataset = Literal[
    "model_details",
    "model_input_scope",
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
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
    "model_object_binding",
    "model_attribute_binding",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
    "generated_code",
    "generated_code_source_system",
    "validation_group",
    "validation_check",
]

MODEL_SECTIONS: tuple[ModelSection, ...] = (
    "model_input_scope",
    "profiling",
    "analysis",
    "assertion",
    "conceptual",
    "logical",
    "dimensional",
    "model_binding",
    "mapping",
    "code_generation",
    "validation",
)


@dataclass(frozen=True, slots=True)
class ModelingDatasetDefinition:
    name: ModelDataset
    section: ModelSection
    row_model: type[ModelingRecord]
    canonical_key: tuple[str, ...]
    change_set_eligible: bool = True

    @property
    def rows_path(self) -> str:
        return f"data/{self.section}/{self.name}/rows.jsonl"

    @property
    def schema_path(self) -> str:
        return f"schemas/model/{self.name}.schema.json"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ModelInputScopeSection(ContractModel):
    details: ModelDetailsRecord
    objects: tuple[ModelInputScopeRecord, ...]


class ProfilingSection(ContractModel):
    profiles: tuple[ProfilingProfileRecord, ...]


class AnalysisSection(ContractModel):
    relationships: tuple[AnalysisResultRecord, ...]


class AssertionSection(ContractModel):
    documents: tuple[ModelingAssertionDocumentRecord, ...]
    records: tuple[ModelingAssertionRecordRecord, ...]


class ConceptualSection(ContractModel):
    objects: tuple[ConceptualObjectRecord, ...]
    relationships: tuple[ConceptualRelationshipRecord, ...]


class LogicalSection(ContractModel):
    submodels: tuple[LogicalSubmodelRecord, ...]
    entities: tuple[LogicalEntityRecord, ...]
    attributes: tuple[LogicalAttributeRecord, ...]
    relationships: tuple[LogicalRelationshipRecord, ...]


class DimensionalSection(ContractModel):
    submodels: tuple[DimensionalSubmodelRecord, ...]
    entities: tuple[DimensionalEntityRecord, ...]
    attributes: tuple[DimensionalAttributeRecord, ...]
    relationships: tuple[DimensionalRelationshipRecord, ...]


class ModelBindingSection(ContractModel):
    objects: tuple[ModelObjectBindingRecord, ...]
    attributes: tuple[ModelAttributeBindingRecord, ...]


class MappingSection(ContractModel):
    dependencies: tuple[MappingDependencyRecord, ...]
    objects: tuple[MappingObjectRecord, ...]
    attributes: tuple[MappingAttributeRecord, ...]


class CodeGenerationSection(ContractModel):
    artifacts: tuple[GeneratedCodeRecord, ...]
    source_systems: tuple[GeneratedCodeSourceSystemRecord, ...]


class ValidationSection(ContractModel):
    groups: tuple[ValidationGroupRecord, ...]
    checks: tuple[ValidationCheckRecord, ...]


class ModelSnapshot(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int
    model_name: str
    model_revision: int
    model_tenant_code: str | None = None
    other_active_model_names: tuple[str, ...] = ()
    model_input_scope: ModelInputScopeSection
    profiling: ProfilingSection
    analysis: AnalysisSection
    assertion: AssertionSection
    conceptual: ConceptualSection
    logical: LogicalSection
    dimensional: DimensionalSection
    model_binding: ModelBindingSection
    mapping: MappingSection
    code_generation: CodeGenerationSection = CodeGenerationSection(
        artifacts=(),
        source_systems=(),
    )
    validation: ValidationSection = ValidationSection(groups=(), checks=())


def model_snapshot_records(
    snapshot: ModelSnapshot,
) -> dict[str, tuple[ModelingRecord, ...]]:
    """Flatten one Model Snapshot into its shared dataset registry."""
    return {
        "model_details": (snapshot.model_input_scope.details,),
        "model_input_scope": snapshot.model_input_scope.objects,
        "profiling_profile": snapshot.profiling.profiles,
        "analysis_result": snapshot.analysis.relationships,
        "modeling_assertion_document": snapshot.assertion.documents,
        "modeling_assertion_record": snapshot.assertion.records,
        "conceptual_object": snapshot.conceptual.objects,
        "conceptual_relationship": snapshot.conceptual.relationships,
        "logical_submodel": snapshot.logical.submodels,
        "logical_entity": snapshot.logical.entities,
        "logical_attribute": snapshot.logical.attributes,
        "logical_relationship": snapshot.logical.relationships,
        "dimensional_submodel": snapshot.dimensional.submodels,
        "dimensional_entity": snapshot.dimensional.entities,
        "dimensional_attribute": snapshot.dimensional.attributes,
        "dimensional_relationship": snapshot.dimensional.relationships,
        "model_object_binding": snapshot.model_binding.objects,
        "model_attribute_binding": snapshot.model_binding.attributes,
        "mapping_dependency": snapshot.mapping.dependencies,
        "mapping_object": snapshot.mapping.objects,
        "mapping_attribute": snapshot.mapping.attributes,
        "generated_code": snapshot.code_generation.artifacts,
        "generated_code_source_system": snapshot.code_generation.source_systems,
        "validation_group": snapshot.validation.groups,
        "validation_check": snapshot.validation.checks,
    }


def build_model_dataset_schema(
    definition: ModelingDatasetDefinition,
) -> dict[str, object]:
    # Validation mode includes every JSON representation accepted when staging records.
    # Snapshot-serialized values remain a valid subset of this contract.
    generated = definition.row_model.model_json_schema(mode="validation")
    properties = generated.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(f"{definition.name} generated an invalid JSON Schema")
    schema: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": definition.schema_path,
        "title": definition.row_model.__name__,
        "description": (
            f"One exact ID-free {definition.name} record "
            + (
                "shared by Model Snapshots and Model Change Sets."
                if definition.change_set_eligible
                else "available only through Model Snapshot and read tools."
            )
        ),
        "type": "object",
        "additionalProperties": False,
        "$defs": generated.get("$defs", {}),
        "properties": cast(dict[str, object], properties),
        "required": generated.get("required", []),
        "x-gds-dataset": definition.name,
        "x-gds-section": definition.section,
        "x-gds-canonical-key": list(definition.canonical_key),
        "x-gds-database-ids-included": False,
        "x-gds-change-set-eligible": definition.change_set_eligible,
    }
    enrich_model_dataset_schema(definition.name, schema)
    rules = MODEL_RECORD_VALIDATIONS.get(definition.name)
    if rules is not None:
        schema["x-gds-record-validation"] = record_validation_contract(rules)
    return schema


DATASETS = (
    ModelingDatasetDefinition(
        name="model_details",
        section="model_input_scope",
        row_model=ModelDetailsRecord,
        canonical_key=(),
    ),
    ModelingDatasetDefinition(
        name="model_input_scope",
        section="model_input_scope",
        row_model=ModelInputScopeRecord,
        canonical_key=(
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="profiling_profile",
        section="profiling",
        row_model=ProfilingProfileRecord,
        canonical_key=(
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="analysis_result",
        section="analysis",
        row_model=AnalysisResultRecord,
        canonical_key=(
            "from_tenant_code",
            "from_system_code",
            "from_connection_code",
            "from_object_schema",
            "from_object_name",
            "from_attribute_name",
            "to_tenant_code",
            "to_system_code",
            "to_connection_code",
            "to_object_schema",
            "to_object_name",
            "to_attribute_name",
            "relationship_kind",
        ),
    ),
    ModelingDatasetDefinition(
        name="modeling_assertion_document",
        section="assertion",
        row_model=ModelingAssertionDocumentRecord,
        canonical_key=("modeling_assertion_document_name",),
    ),
    ModelingDatasetDefinition(
        name="modeling_assertion_record",
        section="assertion",
        row_model=ModelingAssertionRecordRecord,
        canonical_key=("modeling_assertion_record_key",),
    ),
    ModelingDatasetDefinition(
        name="conceptual_object",
        section="conceptual",
        row_model=ConceptualObjectRecord,
        canonical_key=("conceptual_object_name",),
    ),
    ModelingDatasetDefinition(
        name="conceptual_relationship",
        section="conceptual",
        row_model=ConceptualRelationshipRecord,
        canonical_key=(
            "from_conceptual_object_name",
            "to_conceptual_object_name",
            "conceptual_relationship_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="logical_submodel",
        section="logical",
        row_model=LogicalSubmodelRecord,
        canonical_key=("logical_submodel_name",),
    ),
    ModelingDatasetDefinition(
        name="logical_entity",
        section="logical",
        row_model=LogicalEntityRecord,
        canonical_key=("logical_entity_name",),
    ),
    ModelingDatasetDefinition(
        name="logical_attribute",
        section="logical",
        row_model=LogicalAttributeRecord,
        canonical_key=("logical_entity_name", "logical_attribute_name"),
    ),
    ModelingDatasetDefinition(
        name="logical_relationship",
        section="logical",
        row_model=LogicalRelationshipRecord,
        canonical_key=(
            "from_logical_entity_name",
            "from_logical_attribute_name",
            "to_logical_entity_name",
            "to_logical_attribute_name",
            "logical_relationship_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="dimensional_submodel",
        section="dimensional",
        row_model=DimensionalSubmodelRecord,
        canonical_key=("dimensional_submodel_name",),
    ),
    ModelingDatasetDefinition(
        name="dimensional_entity",
        section="dimensional",
        row_model=DimensionalEntityRecord,
        canonical_key=("dimensional_entity_name",),
    ),
    ModelingDatasetDefinition(
        name="dimensional_attribute",
        section="dimensional",
        row_model=DimensionalAttributeRecord,
        canonical_key=("dimensional_entity_name", "dimensional_attribute_name"),
    ),
    ModelingDatasetDefinition(
        name="dimensional_relationship",
        section="dimensional",
        row_model=DimensionalRelationshipRecord,
        canonical_key=(
            "from_dimensional_entity_name",
            "from_dimensional_attribute_name",
            "to_dimensional_entity_name",
            "to_dimensional_attribute_name",
            "dimensional_relationship_kind",
            "dimensional_relationship_role_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="model_object_binding",
        section="model_binding",
        row_model=ModelObjectBindingRecord,
        canonical_key=("modeled_entity_type", "modeled_entity_name"),
    ),
    ModelingDatasetDefinition(
        name="model_attribute_binding",
        section="model_binding",
        row_model=ModelAttributeBindingRecord,
        canonical_key=(
            "modeled_entity_type",
            "modeled_entity_name",
            "modeled_attribute_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="mapping_dependency",
        section="mapping",
        row_model=MappingDependencyRecord,
        canonical_key=("modeled_entity_type", "source_system_code"),
    ),
    ModelingDatasetDefinition(
        name="mapping_object",
        section="mapping",
        row_model=MappingObjectRecord,
        canonical_key=(
            "modeled_entity_type",
            "modeled_entity_name",
            "source_system_code",
        ),
    ),
    ModelingDatasetDefinition(
        name="mapping_attribute",
        section="mapping",
        row_model=MappingAttributeRecord,
        canonical_key=(
            "modeled_entity_type",
            "modeled_entity_name",
            "modeled_attribute_name",
            "source_system_code",
        ),
    ),
    ModelingDatasetDefinition(
        name="generated_code",
        section="code_generation",
        row_model=GeneratedCodeRecord,
        canonical_key=(
            "modeled_entity_type",
            "modeled_entity_name",
            "artifact_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="generated_code_source_system",
        section="code_generation",
        row_model=GeneratedCodeSourceSystemRecord,
        canonical_key=(
            "modeled_entity_type",
            "modeled_entity_name",
            "artifact_name",
            "source_system_code",
        ),
    ),
    ModelingDatasetDefinition(
        name="validation_group",
        section="validation",
        row_model=ValidationGroupRecord,
        canonical_key=(
            "tenant_code",
            "system_code",
            "validation_group_name",
        ),
    ),
    ModelingDatasetDefinition(
        name="validation_check",
        section="validation",
        row_model=ValidationCheckRecord,
        canonical_key=(
            "tenant_code",
            "system_code",
            "validation_group_name",
            "validation_check_name",
        ),
    ),
)

DATASETS_BY_NAME = {definition.name: definition for definition in DATASETS}
CHANGE_SET_DATASETS = tuple(definition for definition in DATASETS if definition.change_set_eligible)
CHANGE_SET_DATASETS_BY_NAME = {definition.name: definition for definition in CHANGE_SET_DATASETS}
