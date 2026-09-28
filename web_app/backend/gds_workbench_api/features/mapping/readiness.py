"""Mapping authorization, immutable preparation, and integrity readiness."""

from __future__ import annotations

from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import AuthorizationDeniedError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionDatabase

from .preparation_contracts import (
    MappingAttributeReadiness,
    MappingAuthorizer,
    MappingHeaderReadiness,
    MappingModeledEntity,
    MappingPreparation,
    MappingReadiness,
    MappingReadinessIssue,
    MappingRunContext,
    MappingRunContextRepository,
    MappingRunPlan,
    MappingRunPlanRepository,
)


class MappingReadinessService:
    """Authorize and load one immutable Mapping preparation snapshot."""

    def __init__(
        self,
        *,
        database: WorkflowExecutionDatabase,
        authorizer: MappingAuthorizer,
        plan_repository: MappingRunPlanRepository,
        context_repository: MappingRunContextRepository,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository
        self._context_repository = context_repository

    async def prepare(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> tuple[MappingPreparation, ...]:
        async with self._database.write_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
                model_id=model_id,
            )
            source_tenants = authorization.readable_source_tenant_ids
            actor_principal_id = authorization.principal.principal_id
            if actor_principal_id is None:
                raise AuthorizationDeniedError()
            plans = await self._plan_repository.load(
                transaction,
                actor_principal_id=actor_principal_id,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            contexts = [
                await self._context_repository.load(transaction, tenant_id=tenant_id, plan=plan)
                for plan in plans
            ]
            model = ModelReadContext(
                tenant_id=tenant_id,
                model_id=model_id,
                model_name=contexts[0].authoring.model_name,
                model_revision=expected_model_revision,
                readable_source_tenant_ids=source_tenants,
            )
            snapshot = await build_model_snapshot(transaction, model, enforce_row_limits=False)
            physical_scope = await load_model_physical_scope(transaction, model)
        preparations = [
            MappingPreparation(
                plan=plan,
                context=context,
                readiness=assess_mapping_readiness(plan=plan, context=context),
                snapshot=snapshot,
                physical_scope=physical_scope,
            )
            for plan, context in zip(plans, contexts, strict=True)
        ]
        return tuple(
            sorted(
                preparations,
                key=lambda item: (
                    item.context.headers[0].object_dependency_order,
                    item.context.source_system.system_code.casefold(),
                    item.context.target.entity_schema_name.casefold(),
                    item.context.target.entity_name.casefold(),
                ),
            )
        )


def assess_mapping_readiness(
    *,
    plan: MappingRunPlan,
    context: MappingRunContext,
) -> MappingReadiness:
    """Enforce referential/state integrity, never subjective transformation quality."""

    issues: list[MappingReadinessIssue] = []

    def issue(code: str, message: str) -> None:
        issues.append(MappingReadinessIssue(code=code, message=message))

    if (
        context.workflow_run_id != plan.workflow_run_id
        or context.model_id != plan.model_id
        or context.model_revision != plan.model_revision
        or context.correlation_id != plan.correlation_id
        or context.pair != plan.pair
        or context.modeled_entity_type != plan.modeled_entity_type
        or context.route != plan.route
        or context.output_template_selections != plan.output_template_selections
    ):
        issue("context.identity_drift", "Mapping context differs from the frozen Run.")

    if not context.source_system.is_active:
        issue("source_system.inactive", "The selected source System is inactive.")

    target = context.target
    if target.status != "active":
        issue("target.unavailable", "The selected Entity is inactive.")
    if not target.attributes or any(item.status != "active" for item in target.attributes):
        issue("target.attributes_unavailable", "Every target Attribute must be active.")
    for source in context.sources:
        if isinstance(source.object, MappingModeledEntity):
            if plan.route == "logical_to_silver" and source.object.entity_type != "logical_entity":
                issue("source.layer_invalid", "Logical Mapping lookups must be Logical Entities.")
            if (
                source.object.entity_type == target.entity_type
                and source.object.entity_id == target.entity_id
            ):
                issue("source.self_reference", "An Entity cannot be its own Mapping lookup.")
            available = source.object.status == "active" and bool(source.object.attributes)
        else:
            if plan.route != "logical_to_silver" or source.object.zone_code not in {
                "source",
                "bronze",
            }:
                issue("source.zone_invalid", "Mapping source does not match the selected layer.")
            available = (
                source.object.is_active
                and source.object.scope_is_active
                and source.object.tenant_is_active
                and source.object.system_is_active
                and source.object.connection_is_active
                and bool(source.object.attributes)
            )
        if not available:
            issue("source.objects_unavailable", "A source is inactive or incomplete.")

    header = context.headers[0]
    modeled_attributes = {
        item.attribute_id: item
        for item in header.modeled_entity.attributes
        if item.status == "active"
    }
    children = {item.modeled_attribute_id: item for item in header.attribute_mappings}
    if header.modeled_entity.status != "active" or not modeled_attributes:
        issue("entity.unavailable", "The target has no active modeled Entity.")
    if set(children) != set(modeled_attributes):
        issue("entity.attribute_coverage", "Every active modeled Attribute needs Mapping context.")

    templates = {item.output_template_id: item for item in context.output_templates.definitions}
    for target_type, selection in (
        ("mapping_object", plan.output_template_selections.mapping_object),
        ("mapping_attribute", plan.output_template_selections.mapping_attribute),
    ):
        if selection is None:
            continue
        template = templates.get(selection.output_template_id)
        if (
            template is None
            or template.target_type != target_type
            or template.schema_digest != selection.schema_digest
            or not template.schema_digest_is_valid
            or not template.is_active
        ):
            issue("template.unavailable", "A selected Mapping output template is unavailable.")

    if plan.operation == "build" and header.mapping_object_id is not None:
        issue("operation.requires_extend", "An existing Mapping requires the extend operation.")
    if plan.operation == "extend" and header.mapping_object_id is None:
        issue("operation.requires_build", "A new Mapping requires the build operation.")

    object_action = "preserve" if header.is_locked else "extend" if header.is_authored else "author"
    attribute_actions: list[MappingAttributeReadiness] = []
    for modeled_id in sorted(modeled_attributes):
        child = children.get(modeled_id)
        if child is None:
            action = "blocked"
            mapping_attribute_id = None
        elif (
            header.is_locked
            or child.is_locked
            or (
                plan.selected_attribute_ids is not None
                and child.modeled_attribute_id not in plan.selected_attribute_ids
            )
        ):
            action = "preserve"
            mapping_attribute_id = child.mapping_attribute_id
        else:
            action = (
                "extend"
                if child.mapping_attribute_id is not None
                and child.transformation_document is not None
                else "author"
            )
            mapping_attribute_id = child.mapping_attribute_id
        attribute_actions.append(
            MappingAttributeReadiness(
                modeled_attribute_id=modeled_id,
                mapping_attribute_id=mapping_attribute_id,
                action=action,
            )
        )
    if plan.selected_attribute_ids is not None:
        eligible_ids = {
            child.modeled_attribute_id
            for child in header.attribute_mappings
            if not child.is_locked and not header.is_locked
        }
        if not set(plan.selected_attribute_ids) <= eligible_ids:
            issue(
                "selection.attributes_unavailable", "A selected Attribute is locked or unavailable."
            )
    if any(item.action == "blocked" for item in attribute_actions):
        issue(
            "mapping.locked_incomplete",
            "The selected Mapping context is incomplete or unavailable.",
        )

    readiness_header = MappingHeaderReadiness(
        modeled_entity_id=header.modeled_entity_id,
        mapping_object_id=header.mapping_object_id,
        action=object_action,
        attribute_actions=tuple(attribute_actions),
    )
    return MappingReadiness(
        ready=not issues,
        operation=plan.operation,
        headers=(readiness_header,),
        issues=tuple(issues),
    )
