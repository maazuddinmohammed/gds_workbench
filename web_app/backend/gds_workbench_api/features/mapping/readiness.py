"""Mapping authorization, preparation, and readiness rules."""

from __future__ import annotations

import json

from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import AuthorizationDeniedError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.mapping.preparation_contracts import (
    JsonObject,
    MappingAttributeReadiness,
    MappingAuthorizer,
    MappingHeaderReadiness,
    MappingPreparation,
    MappingPreparationDatabase,
    MappingProfileResolver,
    MappingReadiness,
    MappingReadinessIssue,
    MappingRunContext,
    MappingRunContextRepository,
    MappingRunPlan,
    MappingRunPlanRepository,
    ReadinessAction,
)
from gds_workbench_api.features.mapping.profile_registry import MappingProfileRegistration


class MappingReadinessService:
    """Authorize and load one immutable Mapping preparation snapshot."""

    def __init__(
        self,
        *,
        database: MappingPreparationDatabase,
        authorizer: MappingAuthorizer,
        plan_repository: MappingRunPlanRepository,
        context_repository: MappingRunContextRepository,
        profile_resolver: MappingProfileResolver,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._plan_repository = plan_repository
        self._context_repository = context_repository
        self._profile_resolver = profile_resolver

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
            registration = self._profile_resolver.resolve(
                key=plan.profile.key,
                version=plan.profile.version,
                schema_digest=plan.profile.schema_digest,
            )
        return MappingPreparation(
            plan=plan,
            context=context,
            registration=registration,
            readiness=assess_mapping_readiness(
                plan=plan,
                context=context,
                registration=registration,
            ),
        )


def assess_mapping_readiness(
    *,
    plan: MappingRunPlan,
    context: MappingRunContext,
    registration: MappingProfileRegistration | None,
) -> MappingReadiness:
    """Report all deterministic pre-agent blockers for the frozen package."""

    issues: list[MappingReadinessIssue] = []

    def add_issue(
        code: str,
        message: str,
        *,
        header_id: int | None = None,
        child_id: int | None = None,
    ) -> None:
        issues.append(
            MappingReadinessIssue(
                code=code,
                message=message,
                mapping_object_id=header_id,
                mapping_attribute_id=child_id,
            )
        )

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
        add_issue(
            "context.identity_drift",
            "The Mapping context no longer matches the frozen Run identity.",
        )

    if registration is None or (
        registration.key,
        registration.version,
        registration.schema_digest,
    ) != (plan.profile.key, plan.profile.version, plan.profile.schema_digest):
        add_issue(
            "profile.unavailable",
            "The exact frozen Mapping Pydantic profile is unavailable.",
        )
    if not context.source_system.is_active:
        add_issue("source_system.inactive", "The frozen source System is inactive.")
    if context.dependency.status != "active":
        add_issue("dependency.inactive", "The source System dependency is not active.")
    if context.dependency_graph.malformed_reference_count:
        add_issue(
            "dependency.graph_malformed",
            "An active Mapping package declares a malformed source-System dependency.",
        )
    dependency_nodes = {node.source_system_id: node for node in context.dependency_graph.nodes}
    selected_node = dependency_nodes.get(plan.pair.source_system_id)
    if context.dependency.status == "active" and (
        selected_node is None
        or selected_node.mapping_source_system_dependency_id
        != context.dependency.mapping_source_system_dependency_id
        or selected_node.dependency_order != context.dependency.dependency_order
        or selected_node.is_locked != context.dependency.is_locked
    ):
        add_issue(
            "dependency.graph_selected_drift",
            "The selected source-System dependency differs from the active graph node.",
        )
    successors: dict[int, set[int]] = {
        source_system_id: set() for source_system_id in dependency_nodes
    }
    indegree = {source_system_id: 0 for source_system_id in dependency_nodes}
    missing_graph_node = False
    invalid_graph_order = False
    for edge in context.dependency_graph.edges:
        predecessor = dependency_nodes.get(edge.predecessor_source_system_id)
        successor = dependency_nodes.get(edge.successor_source_system_id)
        if predecessor is None or successor is None:
            missing_graph_node = True
            continue
        if predecessor.dependency_order >= successor.dependency_order:
            invalid_graph_order = True
        successors[predecessor.source_system_id].add(successor.source_system_id)
        indegree[successor.source_system_id] += 1
    if missing_graph_node:
        add_issue(
            "dependency.graph_node_missing",
            "A declared source-System dependency does not resolve to active graph nodes.",
        )
    if invalid_graph_order:
        add_issue(
            "dependency.graph_order_invalid",
            "A predecessor source System is not in an earlier dependency wave.",
        )
    ready_nodes = sorted(
        source_system_id for source_system_id, count in indegree.items() if count == 0
    )
    visited_node_count = 0
    while ready_nodes:
        source_system_id = ready_nodes.pop(0)
        visited_node_count += 1
        for successor_id in sorted(successors[source_system_id]):
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                ready_nodes.append(successor_id)
                ready_nodes.sort()
    if visited_node_count != len(dependency_nodes):
        add_issue(
            "dependency.graph_cycle",
            "The active source-System dependency graph contains a cycle.",
        )
    target_graph = context.target_dependency_graph
    if target_graph.malformed_reference_count:
        add_issue(
            "target_dependency.graph_malformed",
            "An active Mapping package declares a malformed target dependency.",
        )
    if target_graph.mixed_order_target_count:
        add_issue(
            "target_dependency.graph_mixed_order",
            "Active Mapping headers disagree on a target dependency order.",
        )
    target_nodes = {node.target_object_id: node for node in target_graph.nodes}
    selected_target_node = target_nodes.get(plan.pair.target_object_id)
    selected_header_orders = {header.object_dependency_order for header in context.headers}
    if (
        selected_target_node is None
        or selected_target_node.status != "active"
        or len(selected_header_orders) != 1
        or selected_target_node.dependency_order not in selected_header_orders
    ):
        add_issue(
            "target_dependency.graph_selected_drift",
            "The selected target headers differ from their active dependency node.",
        )
    target_successors: dict[int, set[int]] = {
        target_object_id: set() for target_object_id in target_nodes
    }
    target_indegree = {target_object_id: 0 for target_object_id in target_nodes}
    missing_target_node = False
    invalid_target_order = False
    for edge in target_graph.edges:
        predecessor = target_nodes.get(edge.predecessor_target_object_id)
        successor = target_nodes.get(edge.successor_target_object_id)
        if predecessor is None or successor is None:
            missing_target_node = True
            continue
        if predecessor.dependency_order >= successor.dependency_order:
            invalid_target_order = True
        target_successors[predecessor.target_object_id].add(successor.target_object_id)
        target_indegree[successor.target_object_id] += 1
    if missing_target_node:
        add_issue(
            "target_dependency.graph_node_missing",
            "A target dependency does not resolve to active graph nodes.",
        )
    if invalid_target_order:
        add_issue(
            "target_dependency.graph_order_invalid",
            "A predecessor target is not in an earlier dependency wave.",
        )
    ready_targets = sorted(
        target_object_id for target_object_id, count in target_indegree.items() if count == 0
    )
    visited_target_count = 0
    while ready_targets:
        target_object_id = ready_targets.pop(0)
        visited_target_count += 1
        for successor_id in sorted(target_successors[target_object_id]):
            target_indegree[successor_id] -= 1
            if target_indegree[successor_id] == 0:
                ready_targets.append(successor_id)
                ready_targets.sort()
    if visited_target_count != len(target_nodes):
        add_issue(
            "target_dependency.graph_cycle",
            "The active target dependency graph contains a cycle.",
        )
    templates_by_id = {
        template.output_template_id: template for template in context.output_templates.definitions
    }
    selected_templates = (
        (
            "object",
            "mapping_object",
            plan.output_template_selections.mapping_object,
        ),
        (
            "attribute",
            "mapping_attribute",
            plan.output_template_selections.mapping_attribute,
        ),
    )
    for level, expected_target_type, selection in selected_templates:
        if selection is None:
            continue
        selected_template = templates_by_id.get(selection.output_template_id)
        if selected_template is None:
            add_issue(
                f"template.selected_{level}_missing",
                f"The frozen {level} output-template definition is unavailable.",
            )
        elif selected_template.target_type != expected_target_type:
            add_issue(
                f"template.selected_{level}_type_mismatch",
                f"The frozen {level} output template has the wrong target type.",
            )
        elif (
            selected_template.schema_digest != selection.schema_digest
            or not selected_template.schema_digest_is_valid
        ):
            add_issue(
                f"template.selected_{level}_digest_drift",
                f"The frozen {level} output-template digest or fields have drifted.",
            )
        elif not selected_template.is_active:
            add_issue(
                f"template.selected_{level}_inactive",
                f"The frozen {level} output template is inactive for future authoring.",
            )
    for header in context.headers:
        if header.output_template_id is not None:
            template = templates_by_id.get(header.output_template_id)
            if template is None:
                add_issue(
                    "template.header_missing",
                    "A referenced Mapping header output template is unavailable.",
                    header_id=header.mapping_object_id,
                )
            elif template.target_type != "mapping_object":
                add_issue(
                    "template.header_type_mismatch",
                    "A Mapping header output template has the wrong target type.",
                    header_id=header.mapping_object_id,
                )
            elif not template.schema_digest_is_valid:
                add_issue(
                    "template.header_digest_drift",
                    "A Mapping header output template digest does not match its fields.",
                    header_id=header.mapping_object_id,
                )
        for child in header.attribute_mappings:
            if child.output_template_id is not None:
                template = templates_by_id.get(child.output_template_id)
                if template is None:
                    add_issue(
                        "template.attribute_missing",
                        "A referenced Mapping Attribute output template is unavailable.",
                        header_id=header.mapping_object_id,
                        child_id=child.mapping_attribute_id,
                    )
                elif template.target_type != "mapping_attribute":
                    add_issue(
                        "template.attribute_type_mismatch",
                        "A Mapping Attribute output template has the wrong target type.",
                        header_id=header.mapping_object_id,
                        child_id=child.mapping_attribute_id,
                    )
                elif not template.schema_digest_is_valid:
                    add_issue(
                        "template.attribute_digest_drift",
                        "A Mapping Attribute output template digest does not match its fields.",
                        header_id=header.mapping_object_id,
                        child_id=child.mapping_attribute_id,
                    )
    if (
        not context.target.is_active
        or not context.target.scope_is_active
        or not context.target.tenant_is_active
        or not context.target.system_is_active
        or not context.target.connection_is_active
        or context.target.zone_code != ("silver" if plan.route == "logical_to_silver" else "gold")
    ):
        add_issue(
            "target.unavailable",
            "The frozen target Object is inactive, out of Scope, or in the wrong zone.",
        )
    active_target_attributes = tuple(
        attribute for attribute in context.target.attributes if attribute.is_active
    )
    if not active_target_attributes:
        add_issue("target.attributes_missing", "The target has no active Attributes.")
    if not context.sources:
        add_issue("source.objects_missing", "No active scoped executable source is available.")
    elif any(
        not source.object.is_active
        or not source.object.scope_is_active
        or not source.object.tenant_is_active
        or not source.object.system_is_active
        or not source.object.connection_is_active
        for source in context.sources
    ):
        add_issue(
            "source.objects_unavailable",
            "At least one frozen executable source is inactive or out of Scope.",
        )
    if context.sources and any(not source.object.attributes for source in context.sources):
        add_issue(
            "source.attributes_missing",
            "At least one executable source has no active Attributes.",
        )
    if sum(len(source.object.attributes) for source in context.sources) > 10_000:
        add_issue(
            "source.attributes_oversized",
            "Executable sources exceed the 10,000-Attribute context limit.",
        )
    completed_target_attribute_ids = {
        child.target_attribute_id
        for header in context.headers
        for child in header.attribute_mappings
        if child.status == "active" and child.transformation_document is not None
    }
    uncovered_target_attribute_ids = {
        attribute.attribute_id for attribute in active_target_attributes
    } - completed_target_attribute_ids
    package_requires_completion = (
        bool(uncovered_target_attribute_ids)
        or any(not header.is_authored for header in context.headers)
        or any(
            child.transformation_document is None
            for header in context.headers
            for child in header.attribute_mappings
        )
    )
    package_requires_extend_change = package_requires_completion or any(
        not header.is_locked for header in context.headers
    )
    if uncovered_target_attribute_ids and all(header.is_locked for header in context.headers):
        add_issue(
            "package.locked_change_required",
            "Locked headers cannot receive required target-Attribute bindings.",
        )
    authored_headers = [header for header in context.headers if header.is_authored]
    package_signatures = {
        (
            header.artifact_type,
            header.artifact_generation_instructions,
            header.profile,
            header.mapping_package_digest,
            _stable_json_key(header.mapping_package_document),
        )
        for header in authored_headers
    }
    if len(package_signatures) > 1:
        add_issue(
            "package.mixed_authored_context",
            "Existing authored headers do not share one package/profile context.",
        )

    header_readiness: list[MappingHeaderReadiness] = []
    for header in context.headers:
        header_blocked = False
        if header.status != "active" or header.modeled_entity.status != "active":
            add_issue(
                "header.unavailable",
                "A preregistered header or its modeled Entity is not active.",
                header_id=header.mapping_object_id,
            )
            header_blocked = True

        authored_matches_request = (
            header.is_authored
            and header.artifact_type == plan.artifact_type
            and header.profile == plan.profile
        )
        if plan.operation == "build":
            if package_requires_completion and header.is_authored and not authored_matches_request:
                add_issue(
                    "header.build_conflict",
                    "Build cannot revise an existing header with different frozen metadata.",
                    header_id=header.mapping_object_id,
                )
                header_blocked = True
            elif package_requires_completion and header.is_locked and not authored_matches_request:
                add_issue(
                    "header.locked_change_required",
                    "A locked header requires authoring and cannot be changed.",
                    header_id=header.mapping_object_id,
                )
                header_blocked = True
            header_action: ReadinessAction = (
                "blocked" if header_blocked else "preserve" if header.is_authored else "author"
            )
        else:
            if package_requires_extend_change and header.is_locked and not authored_matches_request:
                add_issue(
                    "header.locked_change_required",
                    "A locked header requires authoring or profile upgrade and cannot change.",
                    header_id=header.mapping_object_id,
                )
                header_blocked = True
            header_action = (
                "blocked" if header_blocked else "preserve" if header.is_locked else "extend"
            )

        child_readiness: list[MappingAttributeReadiness] = []
        modeled_by_id = {item.attribute_id: item for item in header.modeled_entity.attributes}
        target_by_id = {item.attribute_id: item for item in context.target.attributes}
        for child in header.attribute_mappings:
            child_blocked = False
            modeled = modeled_by_id[child.modeled_attribute_id]
            target = target_by_id[child.target_attribute_id]
            if child.status != "active" or modeled.status != "active" or not target.is_active:
                add_issue(
                    "attribute.unavailable",
                    "An existing Mapping Attribute binding is not fully active.",
                    header_id=header.mapping_object_id,
                    child_id=child.mapping_attribute_id,
                )
                child_blocked = True
            if child.transformation_document is None and (child.is_locked or header.is_locked):
                add_issue(
                    "attribute.locked_change_required",
                    "A locked Mapping Attribute binding requires authoring and cannot change.",
                    header_id=header.mapping_object_id,
                    child_id=child.mapping_attribute_id,
                )
                child_blocked = True
            if child_blocked:
                child_action: ReadinessAction = "blocked"
            elif plan.operation == "build":
                child_action = "preserve" if child.transformation_document is not None else "author"
            else:
                child_action = "preserve" if child.is_locked or header.is_locked else "extend"
            child_readiness.append(
                MappingAttributeReadiness(
                    mapping_attribute_id=child.mapping_attribute_id,
                    action=child_action,
                )
            )
        header_readiness.append(
            MappingHeaderReadiness(
                mapping_object_id=header.mapping_object_id,
                action=header_action,
                attribute_actions=tuple(child_readiness),
            )
        )

    ready = not issues
    actions = {header.action for header in header_readiness} | {
        child.action for header in header_readiness for child in header.attribute_actions
    }
    package_action: ReadinessAction
    if not ready or "blocked" in actions:
        package_action = "blocked"
    elif plan.operation == "build" and "author" in actions:
        package_action = "author"
    elif plan.operation == "extend" and "extend" in actions:
        package_action = "extend"
    else:
        package_action = "preserve"
    return MappingReadiness(
        ready=ready,
        operation=plan.operation,
        package_action=package_action,
        headers=tuple(header_readiness),
        issues=tuple(issues),
    )


def _stable_json_key(value: JsonObject | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
