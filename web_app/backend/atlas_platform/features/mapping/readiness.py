"""Mapping authorization, immutable preparation, and integrity readiness."""

from __future__ import annotations

from atlas_mcp.application.change_sets.project import load_project_physical_scope
from atlas_mcp.application.project_read import ProjectReadContext
from atlas_mcp.application.project_snapshot import build_project_snapshot
from atlas_mcp.domain.authorization import RequestPrincipal, ToolPolicy
from atlas_mcp.domain.errors import AuthorizationDeniedError
from atlas_mcp.infrastructure.postgres import ReadIsolation

from atlas_platform.features.workflows.authoring.context import (
    AgentContextUnavailableError,
    reject_forbidden_provider_json,
)
from atlas_platform.features.workflows.authoring.dependency_order import (
    resolve_mapping_dependency_order,
)
from atlas_platform.features.workflows.execution.contracts import WorkflowExecutionDatabase

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
        project_id: int,
        workflow_run_id: int,
        expected_project_revision: int,
    ) -> tuple[MappingPreparation, ...]:
        async with self._database.write_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            source_tenants = authorization.readable_source_tenant_ids
            actor_principal_id = authorization.principal.principal_id
            if actor_principal_id is None:
                raise AuthorizationDeniedError()
            plans = await self._plan_repository.load(
                transaction,
                actor_principal_id=actor_principal_id,
                tenant_id=tenant_id,
                project_id=project_id,
                workflow_run_id=workflow_run_id,
                expected_project_revision=expected_project_revision,
            )
            contexts = [
                await self._context_repository.load(transaction, tenant_id=tenant_id, plan=plan)
                for plan in plans
            ]
            project = ProjectReadContext(
                tenant_id=tenant_id,
                project_id=project_id,
                project_name=contexts[0].authoring.project_name,
                project_revision=expected_project_revision,
                readable_source_tenant_ids=source_tenants,
            )
            snapshot = await build_project_snapshot(transaction, project, enforce_row_limits=False)
            physical_scope = await load_project_physical_scope(transaction, project)
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
                    item.readiness.headers[0].required_dependency_order,
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
        or context.project_id != plan.project_id
        or context.project_revision != plan.project_revision
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
                and not (
                    source.role == "lookup"
                    and any(
                        edge.successor_modeled_entity_id
                        == edge.predecessor_modeled_entity_id
                        == target.entity_id
                        for edge in context.target_dependency_graph.edges
                    )
                )
            ):
                issue(
                    "source.self_reference", "A self lookup requires an active self-relationship."
                )
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
    orders = {
        node.modeled_entity_id: node.dependency_order
        for node in context.target_dependency_graph.nodes
        if node.status == "active"
    }
    orders[target.entity_id] = max(
        orders.get(target.entity_id, 0), target.dependency_order, header.object_dependency_order
    )
    required_order, deferred_edges, cycle = resolve_mapping_dependency_order(
        orders,
        {
            (edge.successor_modeled_entity_id, edge.predecessor_modeled_entity_id)
            for edge in context.target_dependency_graph.edges
        },
        target.entity_id,
    )
    deferred_attributes = {
        name
        for edge in context.target_dependency_graph.edges
        if edge.successor_modeled_entity_id == target.entity_id
        and (target.entity_id, edge.predecessor_modeled_entity_id) in deferred_edges
        for name in edge.child_attribute_names
    }
    if header.is_locked and header.object_dependency_order < required_order:
        issue(
            "dependency.locked_order",
            "The locked Mapping must load after its parent. Review its dependency order first.",
        )
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
            or template.modeled_entity_type not in (None, plan.modeled_entity_type)
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
                modeled_attributes[modeled_id].attribute_name in deferred_attributes
                and child.mapping_attribute_id is not None
                and child.transformation_document is not None
            )
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
        required_dependency_order=required_order,
        attribute_actions=tuple(attribute_actions),
    )
    return MappingReadiness(
        ready=not issues,
        operation=plan.operation,
        headers=(readiness_header,),
        issues=tuple(issues),
        warnings=(_cycle_warning(context, cycle, deferred_attributes),) if cycle else (),
        deferred_dependency_attributes=tuple(sorted(deferred_attributes)),
        deferred_dependency_parent_ids=tuple(
            sorted(parent for child, parent in deferred_edges if child == target.entity_id)
        ),
    )


def _cycle_warning(
    context: MappingRunContext, cycle: tuple[int, ...], deferred_attributes: set[str]
) -> MappingReadinessIssue:
    """Bound event text and show only safe modeled identifiers from the frozen Project."""
    target = context.target
    nodes = {node.modeled_entity_id: node for node in context.target_dependency_graph.nodes}

    def safe_name(name: str) -> bool:
        if not name.isprintable() or len(name) > 48:
            return False
        try:
            reject_forbidden_provider_json(name, reject_sensitive_values=True)
        except AgentContextUnavailableError:
            return False
        return True

    def label(entity_id: int) -> str:
        node = target if entity_id == target.entity_id else nodes[entity_id]
        schema, name = node.entity_schema_name, node.entity_name
        if (
            schema
            and name
            and safe_name(schema)
            and safe_name(name)
            and safe_name(f"{schema}.{name}")
        ):
            return f"{schema}.{name}"
        return "the selected Entity" if entity_id == target.entity_id else "an upstream Entity"

    cycle_target = cycle[0]
    labels = [label(entity_id) for entity_id in cycle[:3]]
    if len(cycle) > 4:
        labels.append(f"… ({len(cycle) - 4} more)")
    if len(cycle) > 3:
        labels.append(label(cycle[-1]))
    path = " → ".join(labels)
    if cycle_target != target.entity_id:
        message = (
            f"{label(target.entity_id)} depends on the upstream cycle {path}. "
            "Its own fields remain eligible for Mapping. Resolve the parent keys in a later pass."
        )
    elif len(cycle) == 2:
        message = f"{label(target.entity_id)} references itself. "
    else:
        message = f"Dependency cycle {path}. "
    if cycle_target == target.entity_id:
        fields = [
            name if safe_name(name) else "a modeled field"
            for name in sorted(deferred_attributes)[:3]
        ]
        listed = ", ".join(fields)
        if len(deferred_attributes) > 3:
            listed += f" and {len(deferred_attributes) - 3} more"
        foreign_keys = f"foreign keys ({listed})" if listed else "circular foreign keys"
        message += f"Map the base row first and resolve its {foreign_keys} in a later load pass."
    return MappingReadinessIssue(code="dependency.cycle", message=message)
