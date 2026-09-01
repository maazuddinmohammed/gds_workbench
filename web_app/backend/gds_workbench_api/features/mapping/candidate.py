"""Validate one complete Header Mapper candidate against frozen Mapping context."""

from __future__ import annotations

from copy import deepcopy
from typing import Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.mapping_contracts import (
    MappingContractModel,
    MappingPackageDocumentV1,
)
from gds_etl_workbench.domain.mapping_profiles import mapping_package_digest
from pydantic import Field, JsonValue, ValidationError, field_validator

from gds_workbench_api.features.mapping.output_schema import (
    MappingTransformationDocumentError,
    compile_header_mapper_output_schema,
    validate_mapping_transformation_document,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingOutputTemplate,
    MappingPreparation,
    MappingSource,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    pydantic_validation_issues,
)


class _AgentHeader(MappingContractModel):
    mapping_object_id: int = Field(gt=0)
    transformation: JsonValue


class _AgentHeaderCoverage(MappingContractModel):
    expected_mapping_object_ids: list[int] = Field(min_length=1, max_length=64)
    returned_mapping_object_ids: list[int] = Field(min_length=1, max_length=64)

    @field_validator(
        "expected_mapping_object_ids",
        "returned_mapping_object_ids",
    )
    @classmethod
    def normalize_ids(cls, values: list[int]) -> list[int]:
        if any(value <= 0 for value in values) or len(values) != len(set(values)):
            raise ValueError("Header coverage IDs must be unique positive IDs")
        return sorted(values)


class _AgentHeaderEnvelope(MappingContractModel):
    schema_version: Literal["1.0"]
    package: MappingPackageDocumentV1
    headers: list[_AgentHeader] = Field(min_length=1, max_length=64)
    coverage: _AgentHeaderCoverage

    @field_validator("headers")
    @classmethod
    def normalize_headers(cls, values: list[_AgentHeader]) -> list[_AgentHeader]:
        identifiers = [item.mapping_object_id for item in values]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Header Mapper IDs must be unique")
        return sorted(values, key=lambda item: item.mapping_object_id)


class NormalizedMappingHeader(MappingContractModel):
    mapping_object_id: int = Field(gt=0)
    transformation: dict[str, JsonValue]


class NormalizedMappingHeaderCoverage(MappingContractModel):
    expected_mapping_object_ids: tuple[int, ...] = Field(min_length=1, max_length=64)
    returned_mapping_object_ids: tuple[int, ...] = Field(min_length=1, max_length=64)


class NormalizedMappingHeaderCandidate(MappingContractModel):
    schema_version: Literal["1.0"] = "1.0"
    package: MappingPackageDocumentV1
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    headers: tuple[NormalizedMappingHeader, ...] = Field(min_length=1, max_length=64)
    coverage: NormalizedMappingHeaderCoverage


class MappingHeaderCandidateValidator:
    """Keep Header Mapper output inside one immutable prepared Mapping pair."""

    def __init__(self, *, preparation: MappingPreparation) -> None:
        self._preparation = preparation
        self._template, self._template_identity_is_valid = _selected_object_template(preparation)

    def output_schema(self) -> dict[str, JsonValue]:
        if not self._template_identity_is_valid:
            raise InvalidRequestError("The frozen Mapping Object output template is unavailable.")
        return deepcopy(compile_header_mapper_output_schema(template=self._template))

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate)[1])

    def parse_validated(self, candidate: JsonValue) -> NormalizedMappingHeaderCandidate:
        normalized, issues = self._normalize(candidate)
        if normalized is None or issues:
            raise InvalidRequestError("The Mapping Header candidate is invalid.")
        return normalized

    def _normalize(
        self,
        candidate: JsonValue,
    ) -> tuple[
        NormalizedMappingHeaderCandidate | None,
        tuple[AgentValidationIssue, ...],
    ]:
        try:
            parsed = _AgentHeaderEnvelope.model_validate(candidate, strict=True)
        except ValidationError as error:
            return None, pydantic_validation_issues(error)

        issues: list[AgentValidationIssue] = []
        plan = self._preparation.plan
        context = self._preparation.context
        registration = self._preparation.registration
        package_json = parsed.package.model_dump(mode="json")
        candidate_package_digest = mapping_package_digest(package_json)
        if not self._preparation.readiness.ready:
            issues.append(
                _issue(
                    "candidate.preparation_not_ready",
                    (),
                    "Header Mapper validation requires one fully ready frozen preparation.",
                )
            )
        if not self._template_identity_is_valid:
            issues.append(
                _issue(
                    "candidate.template_identity_mismatch",
                    (),
                    "The frozen Mapping Object output-template identity is unavailable.",
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
            issues.append(
                _issue(
                    "candidate.context_identity_mismatch",
                    (),
                    "The Mapping context does not match the frozen Run identity.",
                )
            )
        package_profile = parsed.package.pydantic_profile
        if (
            registration is None
            or (
                registration.key,
                registration.version,
                registration.schema_digest,
            )
            != (plan.profile.key, plan.profile.version, plan.profile.schema_digest)
            or (
                package_profile.key,
                package_profile.version,
                package_profile.schema_digest,
            )
            != (plan.profile.key, plan.profile.version, plan.profile.schema_digest)
        ):
            issues.append(
                _issue(
                    "candidate.profile_mismatch",
                    ("package", "pydantic_profile"),
                    "The Mapping package must use the exact frozen deployed profile.",
                )
            )
        if (
            parsed.package.target_object_id != plan.pair.target_object_id
            or parsed.package.source_system_id != plan.pair.source_system_id
            or parsed.package.route != plan.route
            or parsed.package.artifact_type != plan.artifact_type
        ):
            issues.append(
                _issue(
                    "candidate.identity_mismatch",
                    ("package",),
                    "The Mapping package does not match the frozen pair, route, and artifact.",
                )
            )
        expected_source_predecessors = {
            edge.predecessor_source_system_id
            for edge in context.dependency_graph.edges
            if edge.successor_source_system_id == plan.pair.source_system_id
        }
        returned_source_predecessors = {
            dependency.predecessor_source_system_id
            for dependency in parsed.package.source_system_dependencies
        }
        if returned_source_predecessors != expected_source_predecessors:
            issues.append(
                _issue(
                    "candidate.source_dependency_mismatch",
                    ("package", "source_system_dependencies"),
                    "Source-System dependencies must equal the complete frozen graph.",
                )
            )
        expected_target_predecessors = {
            edge.predecessor_target_object_id
            for edge in context.target_dependency_graph.edges
            if edge.successor_target_object_id == plan.pair.target_object_id
        }
        returned_target_predecessors = {
            dependency.predecessor_target_object_id
            for dependency in parsed.package.target_dependencies
        }
        if returned_target_predecessors != expected_target_predecessors:
            issues.append(
                _issue(
                    "candidate.target_dependency_mismatch",
                    ("package", "target_dependencies"),
                    "Target dependencies must equal the complete frozen graph.",
                )
            )
        active_target_attribute_ids = {
            attribute.attribute_id for attribute in context.target.attributes if attribute.is_active
        }
        if not set(parsed.package.load.merge_keys) <= active_target_attribute_ids:
            issues.append(
                _issue(
                    "candidate.target_attribute_outside_context",
                    ("package", "load", "merge_keys"),
                    "Mapping load keys must resolve to active frozen target Attributes.",
                )
            )
        all_header_ids = sorted(
            header.mapping_object_id for header in self._preparation.context.headers
        )
        actions = {
            header.mapping_object_id: header.action
            for header in self._preparation.readiness.headers
        }
        actionable_ids = sorted(
            mapping_object_id
            for mapping_object_id, action in actions.items()
            if action in {"author", "extend"}
        )
        returned_ids = parsed.coverage.returned_mapping_object_ids
        candidate_header_ids = [header.mapping_object_id for header in parsed.headers]
        if (
            parsed.coverage.expected_mapping_object_ids != all_header_ids
            or returned_ids != sorted(set(returned_ids))
            or candidate_header_ids != sorted(set(candidate_header_ids))
            or returned_ids != candidate_header_ids
        ):
            issues.append(
                _issue(
                    "candidate.coverage_mismatch",
                    ("coverage",),
                    "Header coverage must exactly describe the frozen and returned headers.",
                )
            )
        if set(actionable_ids) - set(returned_ids):
            issues.append(
                _issue(
                    "candidate.coverage_incomplete",
                    ("coverage", "returned_mapping_object_ids"),
                    "Every actionable Mapping header must be returned in one complete candidate.",
                )
            )
        if set(returned_ids) - set(actionable_ids):
            issues.append(
                _issue(
                    "candidate.header_not_actionable",
                    ("headers",),
                    "Preserved, locked, and blocked Mapping headers cannot be agent-authored.",
                )
            )
        preserved_authored_headers = [
            header
            for header in context.headers
            if actions.get(header.mapping_object_id) == "preserve" and header.is_authored
        ]
        preservation_mismatch = False
        for header in preserved_authored_headers:
            try:
                stored_document_digest = mapping_package_digest(header.mapping_package_document)
            except ValueError:
                preservation_mismatch = True
                break
            if (
                header.mapping_package_digest != candidate_package_digest
                or stored_document_digest != candidate_package_digest
            ):
                preservation_mismatch = True
                break
        if preservation_mismatch:
            issues.append(
                _issue(
                    "candidate.package_preservation_required",
                    ("package",),
                    "The package must exactly match every preserved authored header.",
                )
            )
        sources_by_object_id: dict[int, list[MappingSource]] = {}
        for frozen_source in context.sources:
            sources_by_object_id.setdefault(frozen_source.object.object_id, []).append(
                frozen_source
            )
        for index, executable_source in enumerate(parsed.package.executable_sources):
            matching_sources = sources_by_object_id.get(executable_source.object_id, [])
            if not matching_sources:
                issues.append(
                    _issue(
                        "candidate.source_outside_context",
                        ("package", "executable_sources", index, "object_id"),
                        "Every executable source Object must belong to frozen Mapping context.",
                    )
                )
                continue
            batch_rule = executable_source.batch_rule
            if batch_rule is not None and not any(
                source.object.batch_attribute_name is not None
                and any(
                    attribute.is_active
                    and attribute.attribute_id == batch_rule.attribute_id
                    and attribute.attribute_name == source.object.batch_attribute_name
                    for attribute in source.object.attributes
                )
                for source in matching_sources
            ):
                issues.append(
                    _issue(
                        "candidate.batch_attribute_mismatch",
                        ("package", "executable_sources", index, "batch_rule"),
                        "A batch rule may use only the frozen Object batch Attribute.",
                    )
                )
        normalized_headers: list[NormalizedMappingHeader] = []
        frozen_headers = {header.mapping_object_id: header for header in context.headers}
        package_sources_by_alias = {
            source.alias: source for source in parsed.package.executable_sources
        }
        for index, header in enumerate(parsed.headers):
            try:
                transformation = validate_mapping_transformation_document(
                    target_type="mapping_object",
                    template=self._template,
                    document=header.transformation,
                )
            except MappingTransformationDocumentError:
                issues.append(
                    _issue(
                        "candidate.transformation_invalid",
                        ("headers", index, "transformation"),
                        "The header transformation does not match its frozen schema.",
                    )
                )
                continue
            raw_aliases = transformation.get("source_aliases")
            frozen_header = frozen_headers.get(header.mapping_object_id)
            if raw_aliases is not None:
                aliases_valid = (
                    isinstance(raw_aliases, list)
                    and bool(raw_aliases)
                    and all(isinstance(alias, str) for alias in raw_aliases)
                    and len(raw_aliases) == len(set(cast(list[str], raw_aliases)))
                )
                allowed_aliases: set[str] = set()
                if frozen_header is not None:
                    allowed_object_ids = {
                        source.object.object_id
                        for source in context.sources
                        if source.modeled_entity_id == frozen_header.modeled_entity.entity_id
                    }
                    allowed_aliases = {
                        alias
                        for alias, package_source in package_sources_by_alias.items()
                        if package_source.object_id in allowed_object_ids
                    }
                if not aliases_valid or not set(cast(list[str], raw_aliases)) <= (allowed_aliases):
                    issues.append(
                        _issue(
                            "candidate.source_alias_outside_context",
                            ("headers", index, "transformation", "source_aliases"),
                            "Header source aliases must resolve to that frozen Entity's sources.",
                        )
                    )
                elif aliases_valid:
                    transformation["source_aliases"] = [
                        cast(JsonValue, alias) for alias in sorted(cast(list[str], raw_aliases))
                    ]
            normalized_headers.append(
                NormalizedMappingHeader(
                    mapping_object_id=header.mapping_object_id,
                    transformation=transformation,
                )
            )

        normalized = (
            NormalizedMappingHeaderCandidate(
                package=parsed.package,
                package_digest=candidate_package_digest,
                headers=tuple(sorted(normalized_headers, key=lambda item: item.mapping_object_id)),
                coverage=NormalizedMappingHeaderCoverage(
                    expected_mapping_object_ids=tuple(all_header_ids),
                    returned_mapping_object_ids=tuple(returned_ids),
                ),
            )
            if len(normalized_headers) == len(parsed.headers)
            else None
        )
        return normalized, tuple(issues[:200])


def _selected_object_template(
    preparation: MappingPreparation,
) -> tuple[MappingOutputTemplate | None, bool]:
    selection = preparation.plan.output_template_selections.mapping_object
    if selection is None:
        return None, True
    template = next(
        (
            item
            for item in preparation.context.output_templates.definitions
            if item.output_template_id == selection.output_template_id
        ),
        None,
    )
    if (
        template is None
        or template.target_type != "mapping_object"
        or template.schema_digest != selection.schema_digest
        or not template.schema_digest_is_valid
        or not template.is_active
    ):
        return None, False
    return template, True


def _issue(
    code: str,
    path: tuple[str | int, ...],
    message: str,
) -> AgentValidationIssue:
    return AgentValidationIssue(code=code, path=path, message=message)
