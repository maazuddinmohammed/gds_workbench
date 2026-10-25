"""Fixed, typed Prompt inputs projected from already-bounded stage evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import cache
from typing import Annotated, Any, Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ProfilingProfileRecord,
    ProjectSchemaDefinition,
)
from gds_etl_workbench.domain.snapshots.project import (
    ContextSection,
    DimensionalSection,
    LogicalSection,
    MappingSection,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    ValidationError,
    create_model,
    model_validator,
)

from gds_workbench_api.features.metadata_enrichment.contracts import EvidenceMethod
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates

from .agent_execution import LocalAgentToolDefinition
from .context import SelectedLogicalEntityContext, SelectedObjectContext
from .context_contracts import workflow_input_contracts
from .plan import AgentRunPlan, FrozenAgentStage
from .tool_configuration import registered_tool_definitions

_PREFIX = "workflow.metadata_enrichment.one_shot.candidate_authoring.inputs."


class _PromptInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)


class _ProjectBrief(_PromptInput):
    project_name: str = Field(min_length=1, max_length=255, pattern=r"\S", repr=False)
    project_revision: int = Field(gt=0)
    project_description: str | None = Field(
        min_length=1, max_length=2_000, pattern=r"\S", repr=False
    )


class _AuthoringProjectIdentity(_PromptInput):
    project_name: str = Field(min_length=1, max_length=255, pattern=r"\S", repr=False)
    project_revision: int = Field(gt=0)
    project_workflow: Literal["analysis", "logical", "dimensional"]
    workflow_execution_mode: Literal["tool_assisted"]
    selected_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


type _ContextDataset = Literal[
    "project_details",
    "selected_object",
    "selected_attribute",
    "selected_logical_entity",
    "profiling_profile",
    "analysis_result",
    "context_type",
    "context_group",
    "context_record",
    "subject_area",
    "subject_area_table",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "mapping_object",
    "mapping_attribute",
    "read_only_mapping_object",
    "read_only_mapping_attribute",
    "read_only_generated_code",
    "read_only_generated_code_source_system",
]
type _Count = Annotated[int, Field(ge=0)]


class _EvidenceDataset(_PromptInput):
    dataset: _ContextDataset
    source_record_count: _Count
    retrieval_item_count: _Count
    fragmented_record_count: _Count

    @model_validator(mode="after")
    def validate_counts(self) -> _EvidenceDataset:
        if (
            self.fragmented_record_count > self.source_record_count
            or self.retrieval_item_count < self.source_record_count
            or (
                not self.fragmented_record_count
                and self.retrieval_item_count != self.source_record_count
            )
        ):
            raise ValueError("The evidence counts are inconsistent")
        return self


class _DatasetCountSemantics(_PromptInput):
    dataset_counts: Literal["retrieval_items_and_page_total_count"]
    dataset_record_counts: Literal["source_records"]


class _EvidenceManifest(_PromptInput):
    dataset_counts: dict[_ContextDataset, _Count]
    dataset_record_counts: dict[_ContextDataset, _Count]
    fragmented_record_counts: dict[_ContextDataset, _Count]
    dataset_count_semantics: _DatasetCountSemantics


_AUTHORING_ADAPTERS: dict[str, TypeAdapter[Any]] = {
    "project_brief": TypeAdapter(_ProjectBrief),
    "selected_metadata": TypeAdapter(list[SelectedObjectContext]),
    "selected_logical_entities": TypeAdapter(list[SelectedLogicalEntityContext]),
    "logical_schemas": TypeAdapter(list[ProjectSchemaDefinition]),
    "dimensional_schemas": TypeAdapter(list[ProjectSchemaDefinition]),
    "profile_evidence": TypeAdapter(list[ProfilingProfileRecord]),
    "applied_relationships": TypeAdapter(list[AnalysisResultRecord]),
    "context_records": TypeAdapter(ContextSection),
    "project_identity": TypeAdapter(_AuthoringProjectIdentity),
    "evidence_datasets": TypeAdapter(list[_EvidenceDataset]),
    "analysis_evidence": TypeAdapter(list[AnalysisResultRecord]),
    "applied_logical": TypeAdapter(LogicalSection | None),
    "applied_dimensional": TypeAdapter(DimensionalSection | None),
    "applied_mapping": TypeAdapter(MappingSection | None),
}


@cache
def _authoring_input_adapter(name: str) -> TypeAdapter[Any]:
    if name in _AUTHORING_ADAPTERS:
        return _AUTHORING_ADAPTERS[name]
    # Gold policy initialization imports the workflow runner; load its real
    # schemas only when a registered policy input is needed.
    from gds_workbench_api.features.dimensional.policy import GoldAuditPolicy, GoldTechnicalPolicy

    return {
        "gold_technical_policy": TypeAdapter(GoldTechnicalPolicy),
        "gold_audit_policy": TypeAdapter(GoldAuditPolicy),
    }[name]


_ANALYSIS_INPUTS: dict[str, tuple[str, str, str, JsonValue]] = {
    "project_brief": (
        "one_shot",
        "",
        "Project name, current revision and business description for interpreting the selection.",
        {"project_name": "Customer Project", "project_revision": 7, "project_description": None},
    ),
    "selected_metadata": (
        "one_shot",
        "selected_objects",
        "Selected Objects with their exact Attribute identities, descriptions, storage types "
        "and inferred types. This is metadata; it contains no physical sample rows.",
        [
            {
                "selection_order": 1,
                "object": {
                    "tenant_code": "NWA",
                    "source_tenant_code": "NWA",
                    "system_code": "CRM",
                    "connection_code": "SOURCE",
                    "object_schema": "bronze",
                    "object_name": "orders",
                    "fc_object_schema": None,
                    "fc_object_name": None,
                    "object_transformation": None,
                    "object_description": "Customer orders.",
                    "batch_attribute_name": None,
                    "object_type_code": "table",
                    "zone_code": "bronze",
                    "is_locked": False,
                    "is_active": True,
                },
                "attributes": [
                    {
                        "tenant_code": "NWA",
                        "system_code": "CRM",
                        "connection_code": "SOURCE",
                        "object_schema": "bronze",
                        "object_name": "orders",
                        "attribute_name": "customer_id",
                        "fc_attribute_name": None,
                        "attribute_ordinal_position": 1,
                        "attribute_description": "Customer placing the order.",
                        "attribute_data_type": "STRING",
                        "attribute_inferred_data_type": "BIGINT",
                        "attribute_nullability": False,
                        "attribute_custom_code": None,
                        "is_surrogate_key": False,
                        "is_natural_key": False,
                        "is_meta_data": False,
                        "is_masking_required": False,
                        "is_mapped": False,
                        "is_purge": False,
                        "is_locked": False,
                        "is_active": True,
                    }
                ],
            }
        ],
    ),
    "profile_evidence": (
        "one_shot",
        "profiles",
        "Previously recorded Attribute profiling measurements. Missing records or null "
        "measurements mean unknown; never substitute zero or claim newly measured evidence.",
        [],
    ),
    "applied_relationships": (
        "one_shot",
        "analysis_relationships",
        "Applied Analysis hypotheses, lifecycle state and any recorded validation evidence. "
        "A hypothesis is not proof of referential integrity; preserve exact endpoint keys.",
        [],
    ),
    "context_records": (
        "one_shot",
        "context",
        "Applicable saved Context groups and records, with source references. "
        "Distinguish explicit business rules from weaker naming or type clues.",
        {"types": [], "groups": [], "records": []},
    ),
    "project_identity": (
        "tool_assisted",
        "",
        "Frozen Project and selection identity for bounded evidence retrieval. The scope digest "
        "identifies the selection; it does not contain its records.",
        {
            "project_name": "Customer Project",
            "project_revision": 7,
            "project_workflow": "analysis",
            "workflow_execution_mode": "tool_assisted",
            "selected_scope_digest": "a" * 64,
        },
    ),
    "evidence_datasets": (
        "tool_assisted",
        "",
        "Available dataset counts. Retrieval items include fragments and can exceed source "
        "records. Retrieve records through get_agent_context_dataset using the manifest's "
        "pagination and fragment contract; a count is not relationship evidence.",
        [
            {
                "dataset": "selected_attribute",
                "source_record_count": 2,
                "retrieval_item_count": 4,
                "fragmented_record_count": 1,
            }
        ],
    ),
}


_LOGICAL_INPUTS: dict[str, tuple[str, str, str, JsonValue]] = {
    name: _ANALYSIS_INPUTS[name]
    for name in (
        "project_brief",
        "selected_metadata",
        "profile_evidence",
        "context_records",
        "project_identity",
        "evidence_datasets",
    )
}
_LOGICAL_INPUTS["analysis_evidence"] = _ANALYSIS_INPUTS["applied_relationships"]
_LOGICAL_INPUTS["project_identity"] = (
    "tool_assisted",
    "",
    _ANALYSIS_INPUTS["project_identity"][2],
    {
        **cast(dict[str, JsonValue], _ANALYSIS_INPUTS["project_identity"][3]),
        "project_workflow": "logical",
    },
)
_LOGICAL_INPUTS["applied_logical"] = (
    "one_shot",
    "applied.logical",
    "Applied Logical Submodels, Entities, Attributes and Relationships, including nested source "
    "mappings, memberships, lifecycle state and locks. Preserve compatible history and explicit "
    "audit columns. read_only_dependencies separately constrains their existing downstream "
    "Mapping and Code outputs; this stage cannot modify those records. Null means no applied "
    "Logical section is available.",
    {"submodels": [], "entities": [], "attributes": [], "relationships": []},
)
_LOGICAL_INPUTS["logical_schemas"] = (
    "one_shot",
    "project_details.logical_schemas",
    "Allowed Logical schema names with placement descriptions. Every Entity must use one.",
    [{"schema_name": "silver", "description": "Operational entities."}],
)
_DIMENSIONAL_INPUTS = dict(_LOGICAL_INPUTS)
_DIMENSIONAL_INPUTS.pop("logical_schemas", None)
_DIMENSIONAL_INPUTS["dimensional_schemas"] = (
    "one_shot",
    "project_details.dimensional_schemas",
    "Allowed Dimensional schema names with placement descriptions. Every Entity must use one.",
    [{"schema_name": "gold", "description": "Analytical entities."}],
)
_DIMENSIONAL_INPUTS.pop("selected_metadata", None)
_DIMENSIONAL_INPUTS["selected_logical_entities"] = (
    "one_shot",
    "selected_logical_entities",
    "Frozen selected Logical Entities and active Attributes, including schema, data types, "
    "grain, source lineage and lifecycle. Reference these exact schema-qualified identities "
    "when generating Dimensional sources.",
    cast(
        JsonValue, workflow_input_contracts("dimensional")["selected_logical_entities"]["example"]
    ),
)
_DIMENSIONAL_INPUTS["project_identity"] = (
    "tool_assisted",
    "",
    _ANALYSIS_INPUTS["project_identity"][2],
    {
        **cast(dict[str, JsonValue], _ANALYSIS_INPUTS["project_identity"][3]),
        "project_workflow": "dimensional",
    },
)
_DIMENSIONAL_INPUTS["applied_logical"] = (
    "one_shot",
    "applied.logical",
    "Applied upstream Logical Entities, Attributes, Relationships and source supports. "
    "Use them to understand selected Logical meaning and grain. This stage cannot alter the "
    "Logical layer or infer that every Logical Entity is eligible for this selection.",
    _LOGICAL_INPUTS["applied_logical"][3],
)
_DIMENSIONAL_INPUTS["applied_dimensional"] = (
    "one_shot",
    "applied.dimensional",
    "Applied Dimensional Submodels, Entities, Attributes and Relationships with exact sources, "
    "lifecycle and locks. Preserve compatible history; read_only_dependencies constrains "
    "current downstream Mapping and Code. The candidate cannot change those dependencies.",
    {"submodels": [], "entities": [], "attributes": [], "relationships": []},
)
_DIMENSIONAL_INPUTS["applied_mapping"] = (
    "one_shot",
    "applied.mapping",
    "Applied Mapping Object and Attribute transformations. Inspect the "
    "modeled_entity_type before interpreting upstream Logical versus downstream Dimensional "
    "records. Mapping gives lineage and transformation meaning, not newly measured values. "
    "It is evidence only; this workflow does not author Mapping.",
    {"objects": [], "attributes": []},
)
_DIMENSIONAL_INPUTS["gold_technical_policy"] = (
    "one_shot",
    "project_details.gold_model_technical_columns_template",
    "Frozen required Gold technical policy: dimension surrogate-key naming/type, role-aware "
    "fact/bridge foreign-key names, and Type2 validity columns. Follow these exact templates "
    "and nullability rules. Required columns must remain compatible with saved Entities and "
    "their Mapping and Code outputs.",
    {
        "schema_version": "1.0",
        "dimension_surrogate_key": {
            "semantic_name_template": "{entity_name} key",
            "data_type": "BIGINT",
            "nullable": False,
            "definition_template": "Surrogate key for {entity_name}.",
        },
        "fact_bridge_foreign_key": {
            "with_role_semantic_name_template": "{role_name} key",
            "without_role_semantic_name_template": "{entity_name} key",
            "definition_template": "Foreign key to {entity_name}.",
        },
        "type_2": {
            "effective_from": {
                "semantic_name": "Effective From",
                "data_type": "TIMESTAMP",
                "nullable": False,
                "definition": "Type2 validity start.",
            },
            "effective_to": {
                "semantic_name": "Effective To",
                "data_type": "TIMESTAMP",
                "nullable": True,
                "definition": "Type2 validity end; null for current row.",
            },
            "is_current": {
                "semantic_name": "Is Current",
                "data_type": "BOOLEAN",
                "nullable": False,
                "definition": "Current Type2 row.",
            },
        },
    },
)
_DIMENSIONAL_INPUTS["gold_audit_policy"] = (
    "one_shot",
    "project_details.gold_model_audit_columns_template",
    "Frozen required audit columns with exact semantic names, types, nullability and "
    "definitions. Keep these distinct from source business Attributes and represent them "
    "explicitly. This policy does not establish source mappings or measured source values.",
    {
        "schema_version": "1.0",
        "columns": [
            {
                "semantic_name": "Loaded At",
                "data_type": "TIMESTAMP",
                "nullable": False,
                "definition": "Warehouse load time.",
            }
        ],
    },
)
_AUTHORING_STAGES = {
    "analysis": "relationship_inference",
    "subject_area": "candidate_authoring",
    "logical": "candidate_authoring",
    "dimensional": "candidate_authoring",
    "metadata_enrichment_object": "candidate_authoring",
    "metadata_enrichment_attribute": "candidate_authoring",
}
_AUTHORING_INPUTS = {
    "analysis": _ANALYSIS_INPUTS,
    # Subject Area prompts use only the compact workflow inputs.
    "subject_area": {},
    "logical": _LOGICAL_INPUTS,
    "dimensional": _DIMENSIONAL_INPUTS,
}


class _DescriptionAttributeEvidence(_PromptInput):
    name: str = Field(repr=False)
    storage_type: str
    inferred_type: str | None
    description: str | None = Field(repr=False)


class _ObjectDescriptionRequest(_PromptInput):
    target_ref: str = Field(pattern=r"^object:[1-9][0-9]{0,18}$")
    kind: Literal["object"]
    name: str = Field(repr=False)
    schema_name: str = Field(alias="schema", repr=False)
    system: str = Field(repr=False)
    current_description: str | None = Field(default=None, repr=False)
    attributes: list[_DescriptionAttributeEvidence] = Field(repr=False)


class _AttributeDescriptionRequest(_PromptInput):
    target_ref: str = Field(pattern=r"^attribute:[1-9][0-9]{0,18}$")
    kind: Literal["attribute"]
    name: str = Field(repr=False)
    object_name: str = Field(repr=False)
    object_description: str | None = Field(repr=False)
    current_description: str | None = Field(default=None, repr=False)
    system: str = Field(repr=False)
    storage_type: str
    inferred_type: str | None
    type_evidence_method: EvidenceMethod
    source_attribute: str | None = Field(repr=False)
    source_description: str | None = Field(repr=False)
    source_object_description: str | None = Field(repr=False)


type _DescriptionRequest = Annotated[
    _ObjectDescriptionRequest | _AttributeDescriptionRequest, Field(discriminator="kind")
]
type _DescriptionRequests = Annotated[list[_DescriptionRequest], Field(min_length=1, max_length=25)]
type _DescriptionRefs = Annotated[
    list[Annotated[str, Field(pattern=r"^(object|attribute):[1-9][0-9]{0,18}$")]],
    Field(min_length=1, max_length=25, json_schema_extra={"uniqueItems": True}),
]
_REQUESTS: TypeAdapter[_DescriptionRequests] = TypeAdapter(_DescriptionRequests)
_REFS: TypeAdapter[_DescriptionRefs] = TypeAdapter(_DescriptionRefs)


class PromptInputContract(BaseModel):
    """Fixed documentation; SQL retains registration, required flags and ordering."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str
    resolver_key: str
    data_type: Literal["json", "text"]
    description: str
    example: JsonValue
    value_schema: dict[str, JsonValue]
    source: str
    availability: str
    delivery: Literal["inline_value", "structured_context", "tool_dataset"]
    context_path: str | None


@cache
def _mapping_inputs(
    mode: str, stage_code: str
) -> dict[str, tuple[TypeAdapter[Any], str, str, JsonValue]]:
    from gds_workbench_api.features.mapping.preparation_contracts import (
        ExistingMappingHeader,
        MappingAuthoringPolicy,
        MappingModeledEntity,
        MappingOperation,
        MappingOutputTemplateInventory,
        MappingPairIdentity,
        MappingReadiness,
        MappingRoute,
        MappingSource,
        MappingSourceSystem,
        MappingTargetDependencyGraph,
    )

    if stage_code != "mapping_authoring":
        return {}
    if mode == "tool_assisted":
        identity = create_model(
            "MappingToolIdentity",
            __base__=_PromptInput,
            workflow_run_id=(Annotated[int, Field(gt=0)], ...),
            project_id=(Annotated[int, Field(gt=0)], ...),
            project_revision=(Annotated[int, Field(gt=0)], ...),
            pair=(MappingPairIdentity, ...),
        )
        dataset = create_model(
            "MappingEvidenceDataset",
            __base__=_PromptInput,
            name=(
                Literal[
                    "run",
                    "source_system",
                    "target_dependency_node",
                    "target_dependency_edge",
                    "target",
                    "target_attribute",
                    "source",
                    "source_attribute",
                    "header",
                    "modeled_entity",
                    "modeled_attribute",
                    "existing_mapping_attribute",
                    "output_template",
                    "authoring",
                    "readiness_header",
                    "readiness_issue",
                ],
                ...,
            ),
            record_count=(_Count, ...),
            retrieval_item_count=(_Count, ...),
            fragmented_record_count=(_Count, ...),
        )
        return {
            "run_identity": (
                TypeAdapter(identity),
                "",
                "Frozen Project revision and target/System pair for this tool-assisted run. "
                "Retrieve the run dataset for route, operation and template selections.",
                {
                    "workflow_run_id": 1048,
                    "project_id": 18,
                    "project_revision": 7,
                    "pair": {"modeled_entity_id": 201, "source_system_id": 31},
                },
            ),
            "evidence_datasets": (
                TypeAdapter(list[dataset]),
                "datasets",
                "Available bounded local tool datasets. record_count counts complete records; "
                "retrieval_item_count includes fragments. Retrieve all relevant pages and "
                "reassemble fragments by dataset/record_index/record_sha256 in index order, "
                "verify UTF-8 SHA-256, then parse JSON. Join records using their exact IDs. "
                "A manifest count or partial fragment is not business evidence.",
                [
                    {
                        "name": "target_attribute",
                        "record_count": 1,
                        "retrieval_item_count": 1,
                        "fragmented_record_count": 0,
                    }
                ],
            ),
        }
    if mode != "one_shot":
        return {}
    examples: dict[str, JsonValue] = {
        "authoring_policy": {
            "audit_columns_template": None,
            "project_name": "Customer Project",
            "naming_instructions": "Use PascalCase names.",
            "technical_columns_template": None,
        },
        "existing_mapping": [
            {
                "agent_run_id": None,
                "attribute_mappings": [
                    {
                        "agent_run_id": None,
                        "is_locked": False,
                        "mapping_attribute_id": None,
                        "modeled_attribute_id": 701,
                        "output_template_id": None,
                        "status": "active",
                        "transformation_document": None,
                        "workflow_run_id": None,
                    }
                ],
                "is_locked": False,
                "mapping_object_id": None,
                "modeled_entity": {
                    "attributes": [
                        {
                            "attribute_data_type": "BIGINT",
                            "attribute_definition": "Stable customer key.",
                            "attribute_id": 701,
                            "attribute_name": "CustomerID",
                            "is_audit_column": False,
                            "is_locked": False,
                            "is_nullable": False,
                            "ordinal_position": 1,
                            "status": "active",
                        }
                    ],
                    "dependency_order": 0,
                    "entity_definition": "A customer.",
                    "entity_id": 201,
                    "entity_kind": "core",
                    "entity_name": "Customer",
                    "grain": "One row per customer.",
                    "is_locked": False,
                    "status": "active",
                    "entity_type": "logical_entity",
                    "entity_schema_name": "silver_crm",
                },
                "object_dependency_order": 0,
                "output_template_id": None,
                "status": "active",
                "transformation_document": None,
                "workflow_run_id": None,
                "modeled_entity_id": 201,
            }
        ],
        "mapping_route": "logical_to_silver",
        "operation": "build",
        "pair_identity": {"source_system_id": 31, "modeled_entity_id": 201},
        "readiness": {
            "headers": [
                {
                    "action": "author",
                    "attribute_actions": [
                        {
                            "action": "author",
                            "mapping_attribute_id": None,
                            "modeled_attribute_id": 701,
                        }
                    ],
                    "mapping_object_id": None,
                    "modeled_entity_id": 201,
                }
            ],
            "issues": [],
            "operation": "build",
            "ready": True,
        },
        "source_evidence": [
            {
                "is_locked": False,
                "mapping_order": 1,
                "modeled_entity_id": 201,
                "object": {
                    "attributes": [
                        {
                            "attribute_data_type": "BIGINT",
                            "attribute_description": None,
                            "attribute_id": 801,
                            "attribute_inferred_data_type": None,
                            "attribute_name": "customer_id",
                            "attribute_nullability": False,
                            "attribute_ordinal_position": 1,
                            "is_active": True,
                        }
                    ],
                    "batch_attribute_name": None,
                    "connection_code": "crm_bronze",
                    "connection_id": 51,
                    "connection_is_active": True,
                    "is_active": True,
                    "is_global_data_store": False,
                    "is_locked": False,
                    "object_description": None,
                    "object_id": 401,
                    "object_name": "customer",
                    "object_schema": "bronze_crm",
                    "scope_is_active": True,
                    "scope_is_locked": False,
                    "source_tenant_id": 7,
                    "system_code": "CRM",
                    "system_id": 31,
                    "system_is_active": True,
                    "tenant_catalog": "northwind",
                    "tenant_code": "NWA",
                    "tenant_id": 7,
                    "tenant_is_active": True,
                    "zone_code": "bronze",
                },
                "rationale": "Authoritative CRM feed.",
                "role": "support",
                "source_mapping_id": 301,
            }
        ],
        "source_system": {
            "is_active": True,
            "system_code": "CRM",
            "system_description": None,
            "system_id": 31,
            "system_name": "CRM",
        },
        "target_dependencies": {
            "edges": [],
            "malformed_reference_count": 0,
            "mixed_order_target_count": 0,
            "nodes": [
                {
                    "dependency_order": 0,
                    "has_locked_headers": False,
                    "has_unlocked_headers": True,
                    "status": "active",
                    "modeled_entity_id": 201,
                }
            ],
        },
        "target_metadata": {
            "attributes": [
                {
                    "attribute_data_type": "BIGINT",
                    "attribute_definition": "Stable customer key.",
                    "attribute_id": 701,
                    "attribute_name": "CustomerID",
                    "is_audit_column": False,
                    "is_locked": False,
                    "is_nullable": False,
                    "ordinal_position": 1,
                    "status": "active",
                }
            ],
            "dependency_order": 0,
            "entity_definition": "A customer.",
            "entity_id": 201,
            "entity_kind": "core",
            "entity_name": "Customer",
            "grain": "One row per customer.",
            "is_locked": False,
            "status": "active",
            "entity_type": "logical_entity",
            "entity_schema_name": "silver_crm",
        },
        "template_guidance": {"definitions": [], "ids": []},
    }
    return {
        "pair_identity": (
            TypeAdapter(MappingPairIdentity),
            "run.pair",
            "Frozen modeled Entity and source System IDs. They identify this call, "
            "not editable output fields.",
            examples["pair_identity"],
        ),
        "mapping_route": (
            TypeAdapter(MappingRoute),
            "run.route",
            "logical_to_silver or dimensional_to_gold. Source and target layers are fixed by "
            "this route; do not invent intermediate targets.",
            examples["mapping_route"],
        ),
        "operation": (
            TypeAdapter(MappingOperation),
            "run.operation",
            "build authors a new pair; extend regenerates selected, unlocked "
            "transformations in an existing pair. Omitted or null selected output clears "
            "saved documents; locked and unselected content is preserved. generate selects "
            "the effective operation per pair. Read readiness for the exact per-record action.",
            examples["operation"],
        ),
        "target_metadata": (
            TypeAdapter(MappingModeledEntity),
            "target",
            "Selected modeled Entity, schema and Attributes. Preserve the schema-qualified "
            "Entity identity, Attribute names, types and nullability.",
            examples["target_metadata"],
        ),
        "source_evidence": (
            TypeAdapter(Annotated[list[MappingSource], Field(max_length=128)]),
            "sources",
            "Eligible physical sources for Logical Mapping or Logical Entity/Attribute "
            "sources for Dimensional Mapping, including descriptions, roles and rationale. "
            "Use their complete natural keys; IDs are not business joins.",
            examples["source_evidence"],
        ),
        "existing_mapping": (
            TypeAdapter(Annotated[list[ExistingMappingHeader], Field(min_length=1, max_length=1)]),
            "headers",
            "Existing header, owning modeled Entity/Attributes and their "
            "transformation documents. Preserve locked/preserved records. A null document is "
            "unauthored, not an empty executable transformation.",
            examples["existing_mapping"],
        ),
        "authoring_policy": (
            TypeAdapter(MappingAuthoringPolicy),
            "authoring",
            "Project name, naming instructions and audit/technical templates. Apply only "
            "recorded policy to transformation content; use existing modeled Attributes.",
            examples["authoring_policy"],
        ),
        "readiness": (
            TypeAdapter(MappingReadiness),
            "readiness",
            "Backend-computed action for the Object and each modeled Attribute. author/extend "
            "are actionable; preserve means omit from authored output. blocked is not "
            "permission to force a mapping.",
            examples["readiness"],
        ),
        "template_guidance": (
            TypeAdapter(MappingOutputTemplateInventory),
            "output_templates",
            "Available selected template definitions, typed fields, required flags and "
            "examples. The separate object_output_template and attribute_output_template "
            "variables resolve the frozen selection. Write concrete transformation documents, "
            "not copies of examples or the template metadata.",
            examples["template_guidance"],
        ),
        "source_system": (
            TypeAdapter(MappingSourceSystem),
            "source_system",
            "Exact source System for this pair. Its name/description supplies context, never "
            "a SQL credential or connection string.",
            examples["source_system"],
        ),
        "target_dependencies": (
            TypeAdapter(MappingTargetDependencyGraph),
            "target_dependency_graph",
            "Existing Entity dependency order and edges. Respect locked headers and "
            "exact target IDs; do not infer an edge solely from similar names.",
            examples["target_dependencies"],
        ),
    }


def get_prompt_input_contract(
    *,
    project_workflow: str,
    workflow_execution_mode: str | None,
    stage_code: str,
    resolver_key: str,
) -> PromptInputContract | None:
    """Return a known stage contract; never infer a resolver from a dotted path."""

    prefix = f"workflow.{project_workflow}.common.{stage_code}.inputs."
    if project_workflow in {"mapping", "code_generation", "validation"} and resolver_key.startswith(
        prefix
    ):
        from .downstream_inputs import downstream_input_contracts

        entry = downstream_input_contracts(project_workflow).get(resolver_key.removeprefix(prefix))
        if entry is not None:
            schema, description, example = entry
            return PromptInputContract(
                name=resolver_key.removeprefix(prefix),
                resolver_key=resolver_key,
                data_type="text" if schema.get("type") == "string" else "json",
                description=description,
                example=example,
                value_schema=schema,
                source="Authorized frozen workflow-local evidence.",
                availability="Included only when referenced by this saved template.",
                delivery="inline_value",
                context_path=None,
            )
    if stage_code == _AUTHORING_STAGES.get(project_workflow) and resolver_key.startswith(prefix):
        name = resolver_key.removeprefix(prefix)
        spec = workflow_input_contracts(project_workflow).get(name)
        if spec is not None:
            return PromptInputContract(
                name=name,
                resolver_key=resolver_key,
                data_type="text" if name == "naming_instructions" else "json",
                description=spec["description"],
                example=spec["example"],
                value_schema=spec["schema"],
                source="Authorized frozen workflow-local evidence.",
                availability="Both modes. Included only when referenced by this saved template. "
                "Empty arrays mean known empty; null means unavailable. Natural keys only.",
                delivery="inline_value",
                context_path=None,
            )
    if (
        resolver_key == "workflow.tools.available"
        and workflow_execution_mode == "tool_assisted"
        and (
            stage_code == _AUTHORING_STAGES.get(project_workflow)
            or (project_workflow == "mapping" and stage_code == "mapping_authoring")
        )
    ):
        return PromptInputContract(
            name="available_tools",
            resolver_key=resolver_key,
            data_type="json",
            description="Enabled read-only tools: names, descriptions and JSON input schemas. "
            "Use only these tools; dataset names and counts come from the context manifest.",
            example=[
                tool.model_dump(mode="json")
                for tool in registered_tool_definitions(project_workflow)
            ],
            value_schema=cast(
                dict[str, JsonValue], TypeAdapter(list[LocalAgentToolDefinition]).json_schema()
            ),
            source="Backend catalog filtered by the frozen Prompt version tool selection.",
            availability="Tool-assisted runs only. This example shows the registered defaults; "
            "the runtime value contains the actual enabled tools and enforced page limits.",
            delivery="inline_value",
            context_path=None,
        )

    if project_workflow == "mapping":
        for name, (adapter, path, description, example) in _mapping_inputs(
            workflow_execution_mode or "", stage_code
        ).items():
            if (
                resolver_key
                != f"workflow.mapping.{workflow_execution_mode}.{stage_code}.inputs.{name}"
            ):
                continue
            return PromptInputContract(
                name=name,
                resolver_key=resolver_key,
                data_type="json",
                description=description,
                example=example,
                value_schema=cast(dict[str, JsonValue], adapter.json_schema()),
                source="Backend frozen Mapping target/System preparation and readiness.",
                availability="Current target/System pair; tool mode retrieves documented datasets.",
                delivery="structured_context" if path else "inline_value",
                context_path=f"context.original_context.{path}" if path else None,
            )
        return None

    if project_workflow in _AUTHORING_STAGES and stage_code == _AUTHORING_STAGES[project_workflow]:
        for name, (mode, path, description, example) in _AUTHORING_INPUTS[project_workflow].items():
            if mode != workflow_execution_mode or resolver_key != (
                f"workflow.{project_workflow}.{mode}.{stage_code}.inputs.{name}"
            ):
                continue
            value_schema = _authoring_input_adapter(name).json_schema()
            if name == "project_identity":
                value_schema["properties"]["project_workflow"] = {
                    "type": "string",
                    "const": project_workflow,
                }
            return PromptInputContract(
                name=name,
                resolver_key=resolver_key,
                data_type="json",
                description=description,
                example=example,
                value_schema=cast(dict[str, JsonValue], value_schema),
                source=(
                    (
                        "Immutable Project selection and applicable metadata, "
                        "profiles and Context records."
                    )
                    if mode == "one_shot"
                    else "Immutable bounded context-tool manifest for this Project selection."
                ),
                availability=(
                    "Complete frozen selection. Empty collections mean no applicable evidence "
                    "was available when context was assembled; null measurements remain unknown."
                    if mode == "one_shot"
                    else "Available in full and compact tool manifests. Records are retrieved "
                    "separately; this input contains no record bodies."
                ),
                delivery="structured_context" if path else "inline_value",
                context_path=f"context.original_context.{path}" if path else None,
            )
        return None

    if (project_workflow, workflow_execution_mode, stage_code) != (
        "metadata_enrichment",
        "one_shot",
        "candidate_authoring",
    ):
        return None
    availability = (
        "Current nonempty description batch only, containing 1–25 requests. "
        "A later batch has different assigned references."
    )
    if resolver_key == f"{_PREFIX}assigned_description_refs":
        return PromptInputContract(
            name="assigned_description_refs",
            resolver_key=resolver_key,
            data_type="json",
            description=(
                "Exact ordered references requiring one description or null each. "
                "Do not add references from other batches or infer a data type in the output."
            ),
            example=["object:101", "attribute:201"],
            value_schema=cast(dict[str, JsonValue], _REFS.json_schema()),
            source=(
                "Assigned unlocked descriptions: missing values, or one explicit "
                "regeneration with current_description."
            ),
            availability=availability,
            delivery="inline_value",
            context_path=None,
        )
    if resolver_key == f"{_PREFIX}description_requests":
        return PromptInputContract(
            name="description_requests",
            resolver_key=resolver_key,
            data_type="json",
            description=(
                "Metadata evidence for the assigned descriptions. Object requests include active "
                "Attribute metadata; Attribute requests include registered storage type, backend "
                "type inference and available source descriptions. Null evidence is unavailable. "
                "The structured request already contains these records; inline only when needed."
            ),
            example=[
                {
                    "target_ref": "object:101",
                    "kind": "object",
                    "name": "orders",
                    "schema": "bronze",
                    "system": "CRM",
                    "attributes": [],
                },
                {
                    "target_ref": "attribute:201",
                    "kind": "attribute",
                    "name": "order_id",
                    "object_name": "orders",
                    "object_description": None,
                    "system": "CRM",
                    "storage_type": "STRING",
                    "inferred_type": "BIGINT",
                    "type_evidence_method": "source_schema",
                    "source_attribute": "OrderID",
                    "source_description": None,
                    "source_object_description": None,
                },
            ],
            value_schema=cast(dict[str, JsonValue], _REQUESTS.json_schema()),
            source=(
                "Selected physical metadata and bounded backend source/type evidence; no samples."
            ),
            availability=availability,
            delivery="structured_context",
            context_path="context.original_context.description_requests",
        )
    return None


def project_prompt_input_values(
    *,
    plan: AgentRunPlan,
    stage: FrozenAgentStage,
    context: JsonValue,
    resolver_values: Mapping[str, object],
    tool_definitions: tuple[LocalAgentToolDefinition, ...] = (),
    precomputed_values: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Add registered named inputs without changing legacy values or stage evidence."""

    values = dict(resolver_values)
    prompt_workflow = stage.prompt_workflow or plan.project_workflow
    requested: set[str] = set()
    for variable in stage.variables:
        descriptor = get_prompt_input_contract(
            project_workflow=prompt_workflow,
            workflow_execution_mode=plan.workflow_execution_mode,
            stage_code=stage.stage_code,
            resolver_key=variable.resolver_key,
        )
        if descriptor is None:
            continue
        if variable.name != descriptor.name or variable.data_type != descriptor.data_type:
            raise InvalidRequestError("The registered Prompt input definition is inconsistent.")
        requested.add(variable.resolver_key)
    if "workflow.tools.available" in requested:
        tools_value = [tool.model_dump(mode="json") for tool in tool_definitions]
        if (
            "workflow.tools.available" in values
            and values["workflow.tools.available"] != tools_value
        ):
            raise InvalidRequestError("The Prompt tool definitions are inconsistent.")
        values["workflow.tools.available"] = tools_value
        requested.remove("workflow.tools.available")
    prefix = f"workflow.{prompt_workflow}.common.{stage.stage_code}.inputs."
    new_inputs = workflow_input_contracts(prompt_workflow)
    if prompt_workflow in {"mapping", "code_generation", "validation"}:
        from .downstream_inputs import downstream_input_contracts, project_downstream_inputs

        new_inputs = {
            name: {"schema": schema}
            for name, (schema, _, _) in downstream_input_contracts(prompt_workflow).items()
        }
        if precomputed_values is None and isinstance(context, dict) and requested:
            precomputed_values = project_downstream_inputs(prompt_workflow, context)
    if any(key == prefix + name for name in new_inputs for key in requested):
        from jsonschema import Draft202012Validator

        supplied = precomputed_values
        if supplied is None and isinstance(context, dict):
            embedded_inputs = context.get("prompt_inputs")
            if isinstance(embedded_inputs, dict):
                supplied = embedded_inputs
            elif "selected_objects" in context and "profiles" in context:
                from .context_inputs import project_context_inputs

                supplied = project_context_inputs(context)
        if supplied is None:
            raise InvalidRequestError("The frozen workflow Prompt inputs are unavailable.")
        for name, spec in new_inputs.items():
            key = prefix + name
            if key not in requested:
                continue
            if name not in supplied or not cast(Any, Draft202012Validator(spec["schema"])).is_valid(
                supplied[name]
            ):
                raise InvalidRequestError("The frozen workflow Prompt input is invalid.")
            if key in values and values[key] != supplied[name]:
                raise InvalidRequestError("The frozen workflow Prompt input is inconsistent.")
            values[key] = supplied[name]
            requested.remove(key)
    if not requested:
        return values

    if plan.project_workflow == "mapping":
        try:
            if not isinstance(context, dict):
                raise ValueError
            inputs = _mapping_inputs(plan.workflow_execution_mode or "", stage.stage_code)
            for name, (adapter, path, _, _) in inputs.items():
                key = (
                    f"workflow.mapping.{plan.workflow_execution_mode}."
                    f"{stage.stage_code}.inputs.{name}"
                )
                if key not in requested:
                    continue
                mapping_value: JsonValue = context
                if name == "run_identity":
                    mapping_value = {
                        field: context[field]
                        for field in ("workflow_run_id", "project_id", "project_revision", "pair")
                    }
                else:
                    for component in path.split("."):
                        if not isinstance(mapping_value, dict):
                            raise ValueError
                        mapping_value = mapping_value[component]
                adapter.validate_json(
                    json.dumps(mapping_value, ensure_ascii=False, allow_nan=False), strict=True
                )
                if key in values and values[key] != mapping_value:
                    raise ValueError
                values.setdefault(key, mapping_value)
            return values
        except KeyError, TypeError, ValueError:
            raise InvalidRequestError("The Mapping Prompt inputs are inconsistent.") from None

    if plan.project_workflow in _AUTHORING_STAGES:
        try:
            if not isinstance(context, dict):
                raise ValueError
            projected: dict[str, object] = {}
            for name, (mode, path, _, _) in _AUTHORING_INPUTS[plan.project_workflow].items():
                key = f"workflow.{plan.project_workflow}.{mode}.{stage.stage_code}.inputs.{name}"
                if key not in requested:
                    continue
                if name == "project_brief":
                    details = context["project_details"]
                    if not isinstance(details, dict):
                        raise ValueError
                    value: object = {
                        "project_name": context["project_name"],
                        "project_revision": context["project_revision"],
                        "project_description": details["project_description"],
                    }
                elif name == "project_identity":
                    value = {
                        field: context[field] for field in _AuthoringProjectIdentity.model_fields
                    }
                    if value["project_workflow"] != plan.project_workflow:
                        raise ValueError
                elif name == "evidence_datasets":
                    manifest = _EvidenceManifest.model_validate(
                        {
                            field: context.get(field, {})
                            if field == "fragmented_record_counts"
                            else context[field]
                            for field in _EvidenceManifest.model_fields
                        },
                        strict=True,
                    )
                    names = set(manifest.dataset_counts)
                    if names != set(manifest.dataset_record_counts) or not (
                        set(manifest.fragmented_record_counts) <= names
                    ):
                        raise ValueError
                    value = [
                        {
                            "dataset": dataset,
                            "source_record_count": manifest.dataset_record_counts[dataset],
                            "retrieval_item_count": manifest.dataset_counts[dataset],
                            "fragmented_record_count": manifest.fragmented_record_counts.get(
                                dataset, 0
                            ),
                        }
                        for dataset in sorted(names)
                    ]
                elif name in {
                    "applied_logical",
                    "applied_dimensional",
                    "applied_mapping",
                }:
                    applied = context["applied"]
                    if not isinstance(applied, dict):
                        raise ValueError
                    value = applied[path.removeprefix("applied.")]
                elif name in {
                    "gold_technical_policy",
                    "gold_audit_policy",
                    "logical_schemas",
                    "dimensional_schemas",
                }:
                    project_details = context["project_details"]
                    if not isinstance(project_details, dict):
                        raise ValueError
                    value = project_details[path.removeprefix("project_details.")]
                    if name in {"gold_technical_policy", "gold_audit_policy"}:
                        raw_technical = project_details["gold_model_technical_columns_template"]
                        raw_audit = project_details["gold_model_audit_columns_template"]
                        if (raw_technical is not None and not isinstance(raw_technical, dict)) or (
                            raw_audit is not None and not isinstance(raw_audit, dict)
                        ):
                            raise ValueError
                        technical, audit = effective_gold_templates(raw_technical, raw_audit)
                        value = technical if name == "gold_technical_policy" else audit
                else:
                    value = context[path]
                # Existing canonical Pydantic models contain tuples and Decimal values whose
                # strict wire representation is JSON, as supplied to the provider.
                _authoring_input_adapter(name).validate_json(
                    json.dumps(value, ensure_ascii=False, allow_nan=False), strict=True
                )
                projected[key] = value
            for key, value in projected.items():
                if key in values and values[key] != value:
                    raise ValueError
                values.setdefault(key, value)
            return values
        except KeyError, TypeError, ValueError:
            raise InvalidRequestError(
                "The authoring Prompt inputs are invalid or inconsistent."
            ) from None

    try:
        if not isinstance(context, dict):
            raise ValueError
        requests = _REQUESTS.validate_python(context.get("description_requests"), strict=True)
        refs = [item.target_ref for item in requests]
        if len(refs) != len(set(refs)):
            raise ValueError
    except ValidationError, ValueError:
        raise InvalidRequestError("The Metadata description Prompt inputs are invalid.") from None

    projected = {
        f"{_PREFIX}assigned_description_refs": refs,
        f"{_PREFIX}description_requests": _REQUESTS.dump_python(
            requests, mode="json", by_alias=True, exclude_unset=True
        ),
    }
    for key in requested:
        if key in values and values[key] != projected[key]:
            raise InvalidRequestError("The Metadata description Prompt inputs are inconsistent.")
        values.setdefault(key, projected[key])
    return values


def list_prompt_input_contracts(
    *,
    project_workflow: str,
    workflow_execution_mode: str | None,
    stage_code: str,
) -> tuple[PromptInputContract, ...]:
    """Canonical workflow-local author choices; compatibility aliases are not advertised."""
    names = tuple(workflow_input_contracts(project_workflow))
    if project_workflow in {"mapping", "code_generation", "validation"}:
        from .downstream_inputs import downstream_input_contracts

        names = tuple(downstream_input_contracts(project_workflow))
    contracts: list[PromptInputContract] = []
    for name in names:
        descriptor = get_prompt_input_contract(
            project_workflow=project_workflow,
            workflow_execution_mode=workflow_execution_mode,
            stage_code=stage_code,
            resolver_key=f"workflow.{project_workflow}.common.{stage_code}.inputs.{name}",
        )
        if descriptor is not None:
            contracts.append(descriptor)
    return tuple(contracts)
