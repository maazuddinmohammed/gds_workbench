"""Validated Mapping preparation models and repository seams.

Mapping authoring freezes one target/System pair and emits only flexible
transformation documents. Profile, package, artifact, and digest metadata are
not Mapping authoring inputs.
"""

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

from gds_workbench_api.features.workflows.authoring.plan import AgentRunPlan

type MappingOperation = Literal["build", "extend"]
type MappingRoute = Literal["logical_to_silver", "dimensional_to_gold"]
type ModeledEntityType = Literal["logical_entity", "dimensional_entity"]
type LifecycleStatus = Literal["active", "inactive", "deprecated"]
type ReadinessAction = Literal["author", "extend", "preserve", "blocked"]
type JsonObject = dict[str, JsonValue]


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingPairIdentity(_FrozenModel):
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)


class MappingOutputTemplateSelection(_FrozenModel):
    output_template_id: int = Field(gt=0)
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class MappingOutputTemplateSelections(_FrozenModel):
    mapping_object: MappingOutputTemplateSelection | None
    mapping_attribute: MappingOutputTemplateSelection | None


class MappingRunPlan(_FrozenModel):
    """Mapping-specific request frozen beside the common agent plan."""

    agent_plan: AgentRunPlan = Field(repr=False)
    actor_principal_id: int = Field(gt=0)
    pair: MappingPairIdentity
    operation: MappingOperation
    coverage_mode: Literal["selected_targets"]
    route: MappingRoute
    output_template_selections: MappingOutputTemplateSelections

    @model_validator(mode="after")
    def validate_exact_pair(self) -> Self:
        expected_route: MappingRoute | None = None
        if self.agent_plan.modeled_entity_type == "logical_entity":
            expected_route = "logical_to_silver"
        elif self.agent_plan.modeled_entity_type == "dimensional_entity":
            expected_route = "dimensional_to_gold"
        if (
            self.agent_plan.model_workflow != "mapping"
            or self.agent_plan.workflow_execution_mode is None
            or self.agent_plan.selected_object_ids != (self.pair.target_object_id,)
            or expected_route != self.route
        ):
            raise ValueError("The Mapping Run must freeze one target/System pair")
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
        if value is None:
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
        identifiers = [item.attribute_id for item in self.attributes]
        ordinals = [item.attribute_ordinal_position for item in self.attributes]
        if len(identifiers) != len(set(identifiers)) or len(ordinals) != len(set(ordinals)):
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


class MappingOutputTemplateInventory(_FrozenModel):
    ids: tuple[int, ...] = Field(max_length=20_066)
    definitions: tuple[MappingOutputTemplate, ...] = Field(max_length=20_066)


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


class ExistingMappingAttribute(_FrozenModel):
    mapping_attribute_id: int | None = Field(default=None, gt=0)
    modeled_attribute_id: int = Field(gt=0)
    target_attribute_id: int = Field(gt=0)
    transformation_document: JsonObject | None = Field(default=None, repr=False)
    status: LifecycleStatus = "active"
    is_locked: bool = False
    agent_run_id: str | None = Field(default=None, max_length=500)
    workflow_run_id: int | None = Field(default=None, gt=0)
    output_template_id: int | None = Field(default=None, gt=0)


class ExistingMappingHeader(_FrozenModel):
    model_object_binding_id: int = Field(gt=0)
    mapping_object_id: int | None = Field(default=None, gt=0)
    modeled_entity: MappingModeledEntity
    object_dependency_order: int = Field(ge=0)
    transformation_document: JsonObject | None = Field(default=None, repr=False)
    status: LifecycleStatus = "active"
    is_locked: bool = False
    agent_run_id: str | None = Field(default=None, max_length=500)
    workflow_run_id: int | None = Field(default=None, gt=0)
    output_template_id: int | None = Field(default=None, gt=0)
    attribute_mappings: tuple[ExistingMappingAttribute, ...] = Field(max_length=20_000)

    @property
    def is_authored(self) -> bool:
        return self.mapping_object_id is not None and self.transformation_document is not None


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
    headers: tuple[ExistingMappingHeader, ...] = Field(min_length=1, max_length=1, repr=False)
    authoring: MappingAuthoringPolicy = Field(repr=False)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        expected_route = {
            "logical_entity": "logical_to_silver",
            "dimensional_entity": "dimensional_to_gold",
        }[self.modeled_entity_type]
        header = self.headers[0]
        if (
            self.route != expected_route
            or self.target.object_id != self.pair.target_object_id
            or self.source_system.system_id != self.pair.source_system_id
            or any(
                source.modeled_entity_id != header.modeled_entity.entity_id
                for source in self.sources
            )
        ):
            raise ValueError("The Mapping context does not match its frozen pair")
        target_ids = {item.attribute_id for item in self.target.attributes}
        modeled_ids = {item.attribute_id for item in header.modeled_entity.attributes}
        if any(
            child.modeled_attribute_id not in modeled_ids
            or child.target_attribute_id not in target_ids
            for child in header.attribute_mappings
        ):
            raise ValueError("Mapping Attribute bindings must resolve in context")
        return self


class MappingReadinessIssue(_FrozenModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    message: str = Field(min_length=1, max_length=500)
    mapping_object_id: int | None = Field(default=None, gt=0)
    mapping_attribute_id: int | None = Field(default=None, gt=0)


class MappingAttributeReadiness(_FrozenModel):
    modeled_attribute_id: int = Field(gt=0)
    mapping_attribute_id: int | None = Field(default=None, gt=0)
    action: ReadinessAction


class MappingHeaderReadiness(_FrozenModel):
    model_object_binding_id: int = Field(gt=0)
    mapping_object_id: int | None = Field(default=None, gt=0)
    action: ReadinessAction
    attribute_actions: tuple[MappingAttributeReadiness, ...]


class MappingReadiness(_FrozenModel):
    ready: bool
    operation: MappingOperation
    headers: tuple[MappingHeaderReadiness, ...]
    issues: tuple[MappingReadinessIssue, ...]


class MappingPreparation(_FrozenModel):
    plan: MappingRunPlan
    context: MappingRunContext = Field(repr=False)
    readiness: MappingReadiness


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
