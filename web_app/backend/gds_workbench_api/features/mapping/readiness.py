"""Mapping authorization, immutable preparation, and integrity readiness."""

from __future__ import annotations

from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import AuthorizationDeniedError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from .preparation_contracts import (
    MappingAttributeReadiness,
    MappingAuthorizer,
    MappingHeaderReadiness,
    MappingPreparation,
    MappingPreparationDatabase,
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
        database: MappingPreparationDatabase,
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
    ) -> MappingPreparation:
        async with self._database.write_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            actor_principal_id = authorization.principal.principal_id
            if actor_principal_id is None:
                raise AuthorizationDeniedError()
            plan = await self._plan_repository.load(
                transaction,
                actor_principal_id=actor_principal_id,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
            )
            context = await self._context_repository.load(
                transaction,
                tenant_id=tenant_id,
                plan=plan,
            )
        return MappingPreparation(
            plan=plan,
            context=context,
            readiness=assess_mapping_readiness(plan=plan, context=context),
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
    if context.dependency.status != "active":
        issue("dependency.inactive", "The selected source-System dependency is inactive.")
    _validate_source_dependency_graph(context, issues)

    expected_zone = "silver" if plan.route == "logical_to_silver" else "gold"
    target = context.target
    if (
        target.zone_code != expected_zone
        or not target.is_active
        or not target.scope_is_active
        or not target.tenant_is_active
        or not target.system_is_active
        or not target.connection_is_active
        or not target.is_global_data_store
    ):
        issue(
            "target.unavailable", "The selected target is inactive, unbound, or in the wrong zone."
        )
    if not target.attributes or any(not item.is_active for item in target.attributes):
        issue("target.attributes_unavailable", "Every bound target Attribute must be active.")

    if not context.sources:
        issue("source.objects_missing", "No executable source Object is available.")
    elif any(
        not source.object.is_active
        or not source.object.scope_is_active
        or not source.object.tenant_is_active
        or not source.object.system_is_active
        or not source.object.connection_is_active
        or not source.object.attributes
        for source in context.sources
    ):
        issue("source.objects_unavailable", "An executable source is inactive or incomplete.")

    header = context.headers[0]
    modeled_attributes = {
        item.attribute_id: item
        for item in header.modeled_entity.attributes
        if item.status == "active"
    }
    children = {item.modeled_attribute_id: item for item in header.attribute_mappings}
    if header.modeled_entity.status != "active" or not modeled_attributes:
        issue("binding.entity_unavailable", "The target has no active bound modeled Entity.")
    if set(children) != set(modeled_attributes):
        issue("binding.attribute_coverage", "Every active bound Attribute needs Mapping context.")

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

    if plan.operation == "build" and header.is_authored:
        issue("operation.requires_extend", "An existing Mapping requires the extend operation.")
    if plan.operation == "extend" and not header.is_authored:
        issue("operation.requires_build", "A new Mapping requires the build operation.")

    if header.is_locked:
        object_action = "preserve" if header.is_authored else "blocked"
    else:
        object_action = "extend" if header.is_authored else "author"
    attribute_actions: list[MappingAttributeReadiness] = []
    for modeled_id in sorted(modeled_attributes):
        child = children.get(modeled_id)
        if child is None:
            action = "blocked"
            mapping_attribute_id = None
        elif child.is_locked:
            action = (
                "preserve"
                if child.mapping_attribute_id is not None
                and child.transformation_document is not None
                else "blocked"
            )
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
    if object_action == "blocked" or any(item.action == "blocked" for item in attribute_actions):
        issue("mapping.locked_incomplete", "A locked Mapping record is incomplete.")

    readiness_header = MappingHeaderReadiness(
        model_object_binding_id=header.model_object_binding_id,
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


def _validate_source_dependency_graph(
    context: MappingRunContext,
    issues: list[MappingReadinessIssue],
) -> None:
    graph = context.dependency_graph
    if graph.malformed_reference_count:
        issues.append(
            MappingReadinessIssue(
                code="dependency.graph_malformed",
                message="The source-System dependency graph is malformed.",
            )
        )
        return
    nodes = {item.source_system_id: item for item in graph.nodes}
    selected = nodes.get(context.source_system.system_id)
    if selected is None or selected.dependency_order != context.dependency.dependency_order:
        issues.append(
            MappingReadinessIssue(
                code="dependency.graph_selected_drift",
                message="The selected source System differs from the dependency graph.",
            )
        )
    successors: dict[int, set[int]] = {key: set() for key in nodes}
    indegree = {key: 0 for key in nodes}
    for edge in graph.edges:
        predecessor = nodes.get(edge.predecessor_source_system_id)
        successor = nodes.get(edge.successor_source_system_id)
        if (
            predecessor is None
            or successor is None
            or predecessor.dependency_order >= successor.dependency_order
        ):
            issues.append(
                MappingReadinessIssue(
                    code="dependency.graph_order_invalid",
                    message="A dependency edge does not resolve to an earlier wave.",
                )
            )
            return
        successors[predecessor.source_system_id].add(successor.source_system_id)
        indegree[successor.source_system_id] += 1
    ready = sorted(key for key, value in indegree.items() if value == 0)
    visited = 0
    while ready:
        current = ready.pop(0)
        visited += 1
        for successor_id in sorted(successors[current]):
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                ready.append(successor_id)
                ready.sort()
    if visited != len(nodes):
        issues.append(
            MappingReadinessIssue(
                code="dependency.graph_cycle",
                message="The source-System dependency graph contains a cycle.",
            )
        )
