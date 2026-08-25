"""Validated Mapping preparation models and repository seams."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Literal, Protocol, Self
from uuid import UUID

from gds_etl_workbench.application.authorization import TenantAuthorization
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from gds_workbench_api.features.mapping.profile_registry import MappingProfileRegistration
from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan

type MappingOperation = Literal["build", "extend"]
type MappingRoute = Literal["logical_to_silver", "dimensional_to_gold"]
type ModeledEntityType = Literal["logical_entity", "dimensional_entity"]
type ArtifactType = Literal["sql_file", "python_file", "python_notebook"]
type LifecycleStatus = Literal["active", "needs_review", "inactive", "deprecated"]
type ReadinessAction = Literal["author", "extend", "preserve", "blocked"]
type JsonObject = dict[str, JsonValue]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingPairIdentity(_FrozenModel):
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)


class MappingProfileIdentity(_FrozenModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class MappingOutputTemplateSelection(_FrozenModel):
    output_template_id: int = Field(gt=0)
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class MappingOutputTemplateSelections(_FrozenModel):
    mapping_object: MappingOutputTemplateSelection | None
    mapping_attribute: MappingOutputTemplateSelection | None


class MappingRunPlan(_FrozenModel):
    """Mapping-specific request frozen beside the common prompt/agent plan."""

    agent_plan: AgentRunPlan = Field(repr=False)
    actor_principal_id: int = Field(gt=0)
    pair: MappingPairIdentity
    operation: MappingOperation
    coverage_mode: Literal["selected_targets"]
    artifact_type: ArtifactType
    route: MappingRoute
    profile: MappingProfileIdentity
    output_template_selections: MappingOutputTemplateSelections

    @model_validator(mode="after")
    def validate_exact_pair(self) -> Self:
        common = self.agent_plan
        expected_route: MappingRoute | None = None
        if common.modeled_entity_type == "logical_entity":
            expected_route = "logical_to_silver"
        elif common.modeled_entity_type == "dimensional_entity":
            expected_route = "dimensional_to_gold"
        if (
            common.model_workflow != "mapping"
            or common.workflow_execution_mode is None
            or common.selected_object_ids != (self.pair.target_object_id,)
            or expected_route != self.route
        ):
            raise ValueError("The Mapping Run must freeze one inferred target/System pair")
        return self

    @property
    def workflow_run_id(self) -> int:
        return self.agent_plan.workflow_run_id

    @property
    def model_id(self) -> int:
        return self.agent_plan.model_id

    @property
    def model_revision(self) -> int:
        return self.agent_plan.model_revision

    @property
    def correlation_id(self) -> UUID:
        return self.agent_plan.correlation_id

    @property
    def modeled_entity_type(self) -> ModeledEntityType:
        value = self.agent_plan.modeled_entity_type
        if value is None:  # Guarded by validate_exact_pair.
            raise ValueError("The Mapping modeled Entity type is unavailable")
        return value


class MappingPhysicalAttribute(_FrozenModel):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    attribute_data_type: str = Field(min_length=1, max_length=100)
    attribute_nullability: bool
    attribute_ordinal_position: int = Field(gt=0)
    attribute_description: str | None = Field(default=None, max_length=2_000)
    is_active: bool


class MappingPhysicalObject(_FrozenModel):
    object_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_catalog: str = Field(min_length=1, max_length=255)
    tenant_is_active: bool
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_is_active: bool
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_is_active: bool
    is_global_data_store: bool
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_description: str | None = Field(default=None, max_length=2_000)
    batch_attribute_name: str | None = Field(default=None, max_length=400)
    zone_code: Literal["source", "bronze", "silver", "gold"]
    scope_is_locked: bool
    scope_is_active: bool
    is_locked: bool
    is_active: bool
    attributes: tuple[MappingPhysicalAttribute, ...] = Field(max_length=5_000)

    @model_validator(mode="after")
    def validate_attributes(self) -> Self:
        attribute_ids = [item.attribute_id for item in self.attributes]
        ordinals = [item.attribute_ordinal_position for item in self.attributes]
        if len(attribute_ids) != len(set(attribute_ids)) or len(ordinals) != len(set(ordinals)):
            raise ValueError("Physical Mapping Attributes must be unique")
        return self


class MappingSourceSystem(_FrozenModel):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    system_description: str | None = Field(default=None, max_length=2_000)
    is_active: bool


class MappingDependency(_FrozenModel):
    mapping_source_system_dependency_id: int = Field(gt=0)
    dependency_order: int = Field(ge=0)
    status: LifecycleStatus
    is_locked: bool


class MappingDependencyNode(_FrozenModel):
    mapping_source_system_dependency_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    dependency_order: int = Field(ge=0)
    status: LifecycleStatus
    is_locked: bool


class MappingDependencyEdge(_FrozenModel):
    predecessor_source_system_id: int = Field(gt=0)
    successor_source_system_id: int = Field(gt=0)


class MappingDependencyGraph(_FrozenModel):
    nodes: tuple[MappingDependencyNode, ...] = Field(max_length=1_000)
    edges: tuple[MappingDependencyEdge, ...] = Field(max_length=10_000)
    malformed_reference_count: int = Field(ge=0, le=10_001)

    @model_validator(mode="after")
    def validate_deterministic_identity(self) -> Self:
        node_ids = [item.source_system_id for item in self.nodes]
        dependency_ids = [item.mapping_source_system_dependency_id for item in self.nodes]
        edge_ids = [
            (
                item.successor_source_system_id,
                item.predecessor_source_system_id,
            )
            for item in self.edges
        ]
        if (
            len(node_ids) != len(set(node_ids))
            or len(dependency_ids) != len(set(dependency_ids))
            or len(edge_ids) != len(set(edge_ids))
            or node_ids != sorted(node_ids)
            or edge_ids != sorted(edge_ids)
        ):
            raise ValueError("Mapping dependency graph identities must be unique and sorted")
        return self


class MappingTargetDependencyNode(_FrozenModel):
    target_object_id: int = Field(gt=0)
    dependency_order: int = Field(ge=0)
    status: LifecycleStatus
    has_locked_headers: bool
    has_unlocked_headers: bool


class MappingTargetDependencyEdge(_FrozenModel):
    predecessor_target_object_id: int = Field(gt=0)
    successor_target_object_id: int = Field(gt=0)


class MappingTargetDependencyGraph(_FrozenModel):
    nodes: tuple[MappingTargetDependencyNode, ...] = Field(max_length=1_000)
    edges: tuple[MappingTargetDependencyEdge, ...] = Field(max_length=10_000)
    malformed_reference_count: int = Field(ge=0, le=10_001)
    mixed_order_target_count: int = Field(ge=0, le=1_001)

    @model_validator(mode="after")
    def validate_deterministic_identity(self) -> Self:
        node_ids = [item.target_object_id for item in self.nodes]
        edge_ids = [
            (
                item.successor_target_object_id,
                item.predecessor_target_object_id,
            )
            for item in self.edges
        ]
        if node_ids != sorted(set(node_ids)) or edge_ids != sorted(set(edge_ids)):
            raise ValueError("Mapping target dependency graph identities must be unique and sorted")
        return self


class MappingOutputTemplateField(_FrozenModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    description: str = Field(min_length=1, max_length=2_000)
    data_type: Literal["string", "integer", "number", "boolean", "object", "array"]
    array_item_type: Literal["string", "integer", "number", "boolean", "object"] | None
    example: JsonValue | None = Field(default=None, repr=False)
    is_required: bool
    order: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_array_type(self) -> Self:
        if (self.data_type == "array") != (self.array_item_type is not None):
            raise ValueError("Only array output-template fields declare an item type")
        return self


class MappingOutputTemplate(_FrozenModel):
    output_template_id: int = Field(gt=0)
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    target_type: Literal["mapping_object", "mapping_attribute"]
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_digest_is_valid: bool
    is_active: bool
    fields: tuple[MappingOutputTemplateField, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_ordered_fields(self) -> Self:
        names = [field.name for field in self.fields]
        orders = [field.order for field in self.fields]
        if (
            len(names) != len(set(names))
            or len(orders) != len(set(orders))
            or orders != sorted(orders)
        ):
            raise ValueError("Output-template fields must have unique sorted orders")
        return self


class MappingOutputTemplateInventory(_FrozenModel):
    ids: tuple[int, ...] = Field(max_length=20_066)
    definitions: tuple[MappingOutputTemplate, ...] = Field(max_length=20_066)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        definition_ids = [item.output_template_id for item in self.definitions]
        if (
            list(self.ids) != sorted(set(self.ids))
            or definition_ids != sorted(set(definition_ids))
            or not set(definition_ids) <= set(self.ids)
        ):
            raise ValueError("Mapping output-template inventory must be unique and sorted")
        return self


class MappingModeledAttribute(_FrozenModel):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=255)
    attribute_definition: str = Field(min_length=1, max_length=2_000)
    attribute_data_type: str = Field(min_length=1, max_length=100)
    is_nullable: bool
    ordinal_position: int = Field(gt=0)
    is_audit_column: bool
    status: LifecycleStatus
    is_locked: bool


class MappingModeledEntity(_FrozenModel):
    entity_id: int = Field(gt=0)
    entity_name: str = Field(min_length=1, max_length=255)
    entity_definition: str = Field(min_length=1, max_length=2_000)
    entity_kind: str = Field(min_length=1, max_length=50)
    grain: str | None = Field(default=None, max_length=2_000)
    dependency_order: int = Field(ge=0)
    status: LifecycleStatus
    is_locked: bool
    attributes: tuple[MappingModeledAttribute, ...] = Field(max_length=5_000)

    @model_validator(mode="after")
    def validate_attributes(self) -> Self:
        identifiers = [item.attribute_id for item in self.attributes]
        ordinals = [item.ordinal_position for item in self.attributes]
        if len(identifiers) != len(set(identifiers)) or len(ordinals) != len(set(ordinals)):
            raise ValueError("Modeled Mapping Attributes must be unique")
        return self


class ExistingMappingAttribute(_FrozenModel):
    mapping_attribute_id: int = Field(gt=0)
    modeled_attribute_id: int = Field(gt=0)
    target_attribute_id: int = Field(gt=0)
    transformation_document: JsonObject | None = Field(default=None, repr=False)
    status: LifecycleStatus
    is_locked: bool
    agent_run_id: str | None = Field(default=None, max_length=500)
    workflow_run_id: int | None = Field(default=None, gt=0)
    output_template_id: int | None = Field(default=None, gt=0)


class ExistingMappingHeader(_FrozenModel):
    mapping_object_id: int = Field(gt=0)
    modeled_entity: MappingModeledEntity
    object_dependency_order: int = Field(ge=0)
    artifact_type: ArtifactType | None
    artifact_generation_instructions: str | None = Field(
        default=None,
        max_length=32_768,
        repr=False,
    )
    profile: MappingProfileIdentity | None
    mapping_package_document: JsonObject | None = Field(default=None, repr=False)
    mapping_package_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    transformation_document: JsonObject | None = Field(default=None, repr=False)
    status: LifecycleStatus
    is_locked: bool
    agent_run_id: str | None = Field(default=None, max_length=500)
    workflow_run_id: int | None = Field(default=None, gt=0)
    output_template_id: int | None = Field(default=None, gt=0)
    attribute_mappings: tuple[ExistingMappingAttribute, ...] = Field(max_length=20_000)

    @model_validator(mode="after")
    def validate_authored_group_and_children(self) -> Self:
        authored = (
            self.artifact_type,
            self.artifact_generation_instructions,
            self.profile,
            self.mapping_package_document,
            self.mapping_package_digest,
            self.transformation_document,
        )
        if any(value is None for value in authored) and any(
            value is not None for value in authored
        ):
            raise ValueError("Mapping header authored fields must be complete or absent")
        child_ids = [item.mapping_attribute_id for item in self.attribute_mappings]
        target_bindings = [
            (item.modeled_attribute_id, item.target_attribute_id)
            for item in self.attribute_mappings
        ]
        if len(child_ids) != len(set(child_ids)) or len(target_bindings) != len(
            set(target_bindings)
        ):
            raise ValueError("Existing Mapping Attribute bindings must be unique")
        return self

    @property
    def is_authored(self) -> bool:
        return self.mapping_package_document is not None


class MappingSource(_FrozenModel):
    source_mapping_id: int = Field(gt=0)
    modeled_entity_id: int = Field(gt=0)
    role: str = Field(min_length=1, max_length=2_000)
    rationale: str = Field(min_length=1, max_length=2_000)
    mapping_order: int | None = Field(default=None, gt=0)
    is_locked: bool
    object: MappingPhysicalObject


class MappingAuthoringPolicy(_FrozenModel):
    model_name: str = Field(min_length=1, max_length=255)
    naming_instructions: str | None = Field(default=None, max_length=32_768, repr=False)
    audit_columns_template: JsonObject | None = Field(default=None, repr=False)
    technical_columns_template: JsonObject | None = Field(default=None, repr=False)


class MappingRunContext(_FrozenModel):
    """Complete repository-owned business context; no secret or physical rows."""

    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    correlation_id: UUID
    pair: MappingPairIdentity
    modeled_entity_type: ModeledEntityType
    route: MappingRoute
    output_template_selections: MappingOutputTemplateSelections
    source_system: MappingSourceSystem
    dependency: MappingDependency
    dependency_graph: MappingDependencyGraph = Field(repr=False)
    target_dependency_graph: MappingTargetDependencyGraph = Field(repr=False)
    output_templates: MappingOutputTemplateInventory = Field(repr=False)
    target: MappingPhysicalObject = Field(repr=False)
    sources: tuple[MappingSource, ...] = Field(max_length=128, repr=False)
    headers: tuple[ExistingMappingHeader, ...] = Field(min_length=1, max_length=64, repr=False)
    authoring: MappingAuthoringPolicy = Field(repr=False)

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        expected_route = {
            "logical_entity": "logical_to_silver",
            "dimensional_entity": "dimensional_to_gold",
        }[self.modeled_entity_type]
        if (
            self.route != expected_route
            or self.target.object_id != self.pair.target_object_id
            or self.source_system.system_id != self.pair.source_system_id
        ):
            raise ValueError("The Mapping context does not match its frozen pair")
        header_ids = [item.mapping_object_id for item in self.headers]
        entity_ids = [item.modeled_entity.entity_id for item in self.headers]
        source_ids = [item.source_mapping_id for item in self.sources]
        if (
            len(header_ids) != len(set(header_ids))
            or len(entity_ids) != len(set(entity_ids))
            or len(source_ids) != len(set(source_ids))
        ):
            raise ValueError("Mapping context identities must be unique")
        known_entities = set(entity_ids)
        if any(source.modeled_entity_id not in known_entities for source in self.sources):
            raise ValueError("Mapping sources must belong to a selected header Entity")
        target_attributes = {item.attribute_id for item in self.target.attributes}
        referenced_template_ids = {
            selection.output_template_id
            for selection in (
                self.output_template_selections.mapping_object,
                self.output_template_selections.mapping_attribute,
            )
            if selection is not None
        }
        for header in self.headers:
            if header.output_template_id is not None:
                referenced_template_ids.add(header.output_template_id)
            modeled_attributes = {item.attribute_id for item in header.modeled_entity.attributes}
            referenced_template_ids.update(
                child.output_template_id
                for child in header.attribute_mappings
                if child.output_template_id is not None
            )
            if any(
                child.modeled_attribute_id not in modeled_attributes
                or child.target_attribute_id not in target_attributes
                for child in header.attribute_mappings
            ):
                raise ValueError("Mapping Attribute bindings must resolve in context")
        if self.output_templates.ids != tuple(sorted(referenced_template_ids)):
            raise ValueError("Mapping output-template inventory must cover every frozen reference")
        return self


class MappingReadinessIssue(_FrozenModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    message: str = Field(min_length=1, max_length=500)
    mapping_object_id: int | None = Field(default=None, gt=0)
    mapping_attribute_id: int | None = Field(default=None, gt=0)


class MappingAttributeReadiness(_FrozenModel):
    mapping_attribute_id: int = Field(gt=0)
    action: ReadinessAction


class MappingHeaderReadiness(_FrozenModel):
    mapping_object_id: int = Field(gt=0)
    action: ReadinessAction
    attribute_actions: tuple[MappingAttributeReadiness, ...]


class MappingReadiness(_FrozenModel):
    ready: bool
    operation: MappingOperation
    package_action: ReadinessAction
    headers: tuple[MappingHeaderReadiness, ...]
    issues: tuple[MappingReadinessIssue, ...]


class MappingPreparation(_FrozenModel):
    plan: MappingRunPlan
    context: MappingRunContext = Field(repr=False)
    registration: MappingProfileRegistration | None = Field(default=None, repr=False)
    readiness: MappingReadiness


class MappingProfileResolver(Protocol):
    """Adapter seam implemented by the separately-owned profile registry."""

    def resolve(
        self,
        *,
        key: str,
        version: str,
        schema_digest: str,
    ) -> MappingProfileRegistration | None: ...


class MappingPreparationDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class MappingAuthorizer(Protocol):
    async def authorize_tenant(
        self,
        transaction: ReadTransaction,
        request_principal: RequestPrincipal,
        *,
        tenant_id: int,
        policy: ToolPolicy,
    ) -> TenantAuthorization: ...


class MappingRunPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        actor_principal_id: int,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> MappingRunPlan: ...


class CommonAgentPlanRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan: ...


class MappingRunPlanUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="mapping_run_plan_unavailable",
            message="The revision-fenced Mapping Run plan is unavailable.",
        )


class MappingRunContextRepository(Protocol):
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: MappingRunPlan,
    ) -> MappingRunContext: ...


class MappingRunContextUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="mapping_run_context_unavailable",
            message="The revision-fenced Mapping Run context is unavailable.",
        )
