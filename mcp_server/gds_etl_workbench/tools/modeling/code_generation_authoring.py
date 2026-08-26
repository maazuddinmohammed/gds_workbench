"""Server-derived, name-only Code Generation document authoring."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.mapping_contracts import (
    AttributeMappingTransformationDocumentV1,
    GeneratorDocumentV1,
    MappingPackageDocumentV1,
    ObjectMappingTransformationDocumentV1,
)
from gds_etl_workbench.domain.mapping_profiles import canonical_mapping_json_bytes
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .common import POLICY
from .mapping_authoring import (
    GetModelMappingAuthoringContextResult,
    MappingHeaderContext,
    ModeledEntityType,
    load_mapping_authoring_context,
)

_REFERENCE_CONTEXT_SQL: LiteralString = r"""
/* code_generation_reference_context_v1 */
WITH input AS MATERIALIZED (
    SELECT %s::BIGINT AS model_id,
           %s::VARCHAR(30) AS modeled_entity_type,
           %s::BIGINT AS target_object_id,
           %s::BIGINT AS source_system_id
), requested AS MATERIALIZED (
    SELECT input.*,
           target_model.tenant_id
      FROM input
      JOIN model.model AS target_model
        ON target_model.model_id = input.model_id
), active_mapping AS MATERIALIZED (
    SELECT mapping.mapping_package_document
      FROM requested
      JOIN workflow.mapping_object AS mapping
        ON mapping.model_id = requested.model_id
       AND mapping.modeled_entity_type = requested.modeled_entity_type
       AND mapping.object_id = requested.target_object_id
       AND mapping.source_system_id = requested.source_system_id
       AND mapping.object_mapping_status = 'active'
       AND mapping.mapping_package_document IS NOT NULL
), source_predecessor AS MATERIALIZED (
    SELECT DISTINCT predecessor.system_id,
           predecessor.system_code,
           predecessor.system_name
      FROM active_mapping AS mapping
      CROSS JOIN LATERAL jsonb_array_elements(
          mapping.mapping_package_document -> 'source_system_dependencies'
      ) AS item(value)
      JOIN core.system AS predecessor
        ON predecessor.system_id =
           (item.value ->> 'predecessor_source_system_id')::BIGINT
       AND predecessor.is_active
), target_predecessor AS MATERIALIZED (
    SELECT DISTINCT predecessor.object_id,
           predecessor_tenant.tenant_catalog AS catalog,
           predecessor.object_schema AS schema_name,
           predecessor.object_name
      FROM requested
      JOIN active_mapping AS mapping ON TRUE
      CROSS JOIN LATERAL jsonb_array_elements(
          mapping.mapping_package_document -> 'target_dependencies'
      ) AS item(value)
      JOIN core.object AS predecessor
        ON predecessor.object_id =
           (item.value ->> 'predecessor_target_object_id')::BIGINT
       AND predecessor.is_active
      JOIN core.connection AS predecessor_connection
        ON predecessor_connection.connection_id = predecessor.connection_id
       AND predecessor_connection.is_active
      JOIN core.tenant AS predecessor_tenant
        ON predecessor_tenant.tenant_id = CASE
               WHEN predecessor_connection.is_global_data_store
                   THEN requested.tenant_id
               ELSE predecessor_connection.tenant_id
           END
       AND predecessor_tenant.is_active
), package_provenance AS MATERIALIZED (
    SELECT provenance.value AS document
      FROM active_mapping AS mapping
      CROSS JOIN LATERAL jsonb_array_elements(
          mapping.mapping_package_document -> 'non_executable_provenance'
      ) AS provenance(value)
), original_provenance AS MATERIALIZED (
    SELECT DISTINCT
           'original_ingestion'::TEXT AS lineage_kind,
           ingestion.ingestion_object_mapping_id AS reference_id,
           original_system.system_id AS source_system_id,
           original_system.system_code AS source_system_code,
           original_system.system_name AS source_system_name,
           original_connection.connection_code,
           original_object.object_name AS source_object_name,
           jsonb_build_array(
               original_object.object_name || ' -> ' || executable_object.object_name
           ) AS lineage_path
      FROM package_provenance AS provenance
      CROSS JOIN LATERAL jsonb_array_elements_text(
          provenance.document -> 'ingestion_object_mapping_ids'
      ) AS reference(value)
      JOIN core.ingestion_object_mapping AS ingestion
        ON ingestion.ingestion_object_mapping_id = reference.value::BIGINT
       AND ingestion.is_active
      JOIN core.object AS original_object
        ON original_object.object_id = ingestion.source_object_id
       AND original_object.is_active
      JOIN core.connection AS original_connection
        ON original_connection.connection_id = original_object.connection_id
       AND original_connection.is_active
      JOIN core.system AS original_system
        ON original_system.system_id = original_connection.system_id
       AND original_system.system_id =
           (provenance.document ->> 'source_system_id')::BIGINT
       AND original_system.is_active
      JOIN core.object AS executable_object
        ON executable_object.object_id = ingestion.target_object_id
       AND executable_object.object_id =
           (provenance.document ->> 'source_object_id')::BIGINT
       AND executable_object.is_active
     WHERE provenance.document ->> 'lineage_kind' = 'original_ingestion'
), prior_provenance AS MATERIALIZED (
    SELECT DISTINCT
           'prior_mapping'::TEXT AS lineage_kind,
           prior.mapping_object_id AS reference_id,
           prior_system.system_id AS source_system_id,
           prior_system.system_code AS source_system_code,
           prior_system.system_name AS source_system_name,
           prior_connection.connection_code,
           prior_target.object_name AS source_object_name,
           jsonb_build_array(prior_target.object_name) AS lineage_path
      FROM package_provenance AS provenance
      CROSS JOIN LATERAL jsonb_array_elements_text(
          provenance.document -> 'prior_object_mapping_ids'
      ) AS reference(value)
      JOIN workflow.mapping_object AS prior
        ON prior.mapping_object_id = reference.value::BIGINT
       AND prior.object_mapping_status = 'active'
      JOIN core.system AS prior_system
        ON prior_system.system_id = prior.source_system_id
       AND prior_system.system_id =
           (provenance.document ->> 'source_system_id')::BIGINT
       AND prior_system.is_active
      JOIN core.object AS prior_target
        ON prior_target.object_id = prior.object_id
       AND prior_target.object_id =
           (provenance.document ->> 'source_object_id')::BIGINT
       AND prior_target.is_active
      JOIN core.connection AS prior_connection
        ON prior_connection.connection_id = prior_target.connection_id
       AND prior_connection.is_active
     WHERE provenance.document ->> 'lineage_kind' = 'prior_mapping'
)
SELECT jsonb_build_object(
           'source_predecessors', coalesce(
               (SELECT jsonb_agg(jsonb_build_object(
                           'system_id', system_id,
                           'code', system_code,
                           'name', system_name
                       ) ORDER BY system_id)
                  FROM source_predecessor),
               '[]'::JSONB
           ),
           'target_predecessors', coalesce(
               (SELECT jsonb_agg(jsonb_build_object(
                           'object_id', object_id,
                           'catalog', catalog,
                           'schema', schema_name,
                           'object_name', object_name
                       ) ORDER BY object_id)
                  FROM target_predecessor),
               '[]'::JSONB
           ),
           'provenance', coalesce(
               (SELECT jsonb_agg(document ORDER BY lineage_kind, reference_id)
                  FROM (
                      SELECT to_jsonb(original_provenance) AS document,
                             lineage_kind,
                             reference_id
                        FROM original_provenance
                      UNION ALL
                      SELECT to_jsonb(prior_provenance), lineage_kind, reference_id
                        FROM prior_provenance
                  ) AS combined),
               '[]'::JSONB
           )
       ) AS references
"""


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SourcePredecessorReference(_ContractModel):
    system_id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)


class TargetPredecessorReference(_ContractModel):
    object_id: int = Field(gt=0)
    catalog: str = Field(min_length=1, max_length=255)
    schema_name: str = Field(alias="schema", min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)


class ProvenanceReference(_ContractModel):
    lineage_kind: Literal["original_ingestion", "prior_mapping"]
    reference_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    source_system_code: str = Field(min_length=1, max_length=100)
    source_system_name: str = Field(min_length=1, max_length=200)
    connection_code: str = Field(min_length=1, max_length=100)
    source_object_name: str = Field(min_length=1, max_length=400)
    lineage_path: tuple[str, ...] = Field(min_length=1, max_length=32)


class CodeGenerationReferenceContext(_ContractModel):
    source_predecessors: tuple[SourcePredecessorReference, ...] = Field(max_length=64)
    target_predecessors: tuple[TargetPredecessorReference, ...] = Field(max_length=128)
    provenance: tuple[ProvenanceReference, ...] = Field(max_length=128)


class GeneratorDocumentProof(_ContractModel):
    contract: Literal["generator-document@1.0"] = "generator-document@1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    modeled_entity_type: ModeledEntityType
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    profile_schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class GetModelCodeGenerationDocumentResult(_ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    modeled_entity_type: ModeledEntityType
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    mapping_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proof: GeneratorDocumentProof
    document: GeneratorDocumentV1 = Field(repr=False)


class CodeGenerationAuthoringToolError(Exception):
    """A bounded Code Generation failure safe for MCP serialization."""


def register_code_generation_authoring_tools(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Derive one exact, name-only GeneratorDocumentV1 from applied Mapping for "
            "an exact target Object and source System pair."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_code_generation_document(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        modeled_entity_type: ModeledEntityType,
        target_object_id: Annotated[int, Field(gt=0)],
        source_system_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelCodeGenerationDocumentResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                prepared = await load_mapping_authoring_context(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    model_id=model_id,
                    modeled_entity_type=modeled_entity_type,
                    target_object_id=target_object_id,
                    source_system_id=source_system_id,
                )
                reference_row = await transaction.fetch_one(
                    _REFERENCE_CONTEXT_SQL,
                    (
                        prepared.model_id,
                        modeled_entity_type,
                        target_object_id,
                        source_system_id,
                    ),
                )
                if reference_row is None or reference_row.get("references") is None:
                    raise InvalidRequestError(
                        "The Code Generation reference context is unavailable."
                    )
                references = CodeGenerationReferenceContext.model_validate(
                    reference_row["references"],
                    strict=False,
                )
                document = _assemble_generator_document(prepared, references)
            document_digest = hashlib.sha256(
                canonical_mapping_json_bytes(document.model_dump(mode="json"))
            ).hexdigest()
            proof = GeneratorDocumentProof(
                model_id=prepared.model_id,
                model_revision=prepared.model_revision,
                modeled_entity_type=prepared.modeled_entity_type,
                target_object_id=target_object_id,
                source_system_id=source_system_id,
                profile_schema_digest=prepared.profile.schema_digest,
                mapping_context_digest=prepared.context_digest,
                document_digest=document_digest,
            )
            return GetModelCodeGenerationDocumentResult(
                model_id=prepared.model_id,
                model_revision=prepared.model_revision,
                modeled_entity_type=prepared.modeled_entity_type,
                target_object_id=target_object_id,
                source_system_id=source_system_id,
                mapping_context_digest=prepared.context_digest,
                document_digest=document_digest,
                proof=proof,
                document=document,
            )
        except AuthenticationError as error:
            raise CodeGenerationAuthoringToolError(
                f"{error.public_code}: {error.message}"
            ) from None
        except WorkbenchError as error:
            raise CodeGenerationAuthoringToolError(f"{error.code}: {error.message}") from None
        except TypeError, ValueError:
            raise CodeGenerationAuthoringToolError(
                "invalid_request: The applied Mapping cannot produce an exact GeneratorDocumentV1."
            ) from None
        except Exception:
            raise CodeGenerationAuthoringToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_code_generation_document",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={
            "model_id",
            "modeled_entity_type",
            "target_object_id",
            "source_system_id",
            "schema_version",
        },
    )


def _assemble_generator_document(
    prepared: GetModelMappingAuthoringContextResult,
    references: CodeGenerationReferenceContext,
) -> GeneratorDocumentV1:
    context = prepared.context
    packages: list[MappingPackageDocumentV1] = []
    header_documents: list[
        tuple[
            MappingHeaderContext,
            ObjectMappingTransformationDocumentV1,
            MappingPackageDocumentV1,
        ]
    ] = []
    for header in context.headers:
        existing = header.existing
        if (
            existing is None
            or existing.status != "active"
            or existing.mapping_package_document is None
            or existing.object_mapping_transformation_document is None
        ):
            raise InvalidRequestError("Applied Mapping headers are incomplete.")
        package = MappingPackageDocumentV1.model_validate(
            existing.mapping_package_document,
            strict=True,
        )
        transformation = ObjectMappingTransformationDocumentV1.model_validate(
            existing.object_mapping_transformation_document,
            strict=True,
        )
        if package.artifact_type != "sql_file":
            raise InvalidRequestError("Code Generation requires SQL-file Mapping artifacts.")
        packages.append(package)
        header_documents.append((header, transformation, package))
    canonical_packages = {
        canonical_mapping_json_bytes(item.model_dump(mode="json")) for item in packages
    }
    if len(canonical_packages) != 1:
        raise InvalidRequestError("Applied Mapping packages are inconsistent.")
    package = packages[0]
    if (
        package.target_object_id != context.target.object_id
        or package.source_system_id != context.source_system.system_id
        or package.route != prepared.route
        or package.pydantic_profile.key != prepared.profile.key
        or package.pydantic_profile.version != prepared.profile.version
        or package.pydantic_profile.schema_digest != prepared.profile.schema_digest
    ):
        raise InvalidRequestError("Applied Mapping package identity is inconsistent.")
    for header, _, _ in header_documents:
        existing = header.existing
        assert existing is not None
        if (
            existing.artifact_type != package.artifact_type
            or existing.artifact_generation_instructions != package.artifact_generation_instructions
            or existing.mapping_profile_key != package.pydantic_profile.key
            or existing.mapping_profile_version != package.pydantic_profile.version
        ):
            raise InvalidRequestError("Applied Mapping package metadata is inconsistent.")

    target_attributes = {item.attribute_id: item for item in context.target.attributes}
    source_objects = {
        source.object.object_id: source.object
        for header in context.headers
        for source in header.sources
    }
    package_sources = {item.alias: item for item in package.executable_sources}
    if len(package_sources) != len(package.executable_sources) or any(
        item.object_id not in source_objects for item in package_sources.values()
    ):
        raise InvalidRequestError("Applied Mapping source identity is incomplete.")

    target_bindings: dict[int, list[tuple[Any, Any, AttributeMappingTransformationDocumentV1]]] = {}
    used_attribute_ids: dict[str, set[int]] = {alias: set() for alias in package_sources}
    for header, _, _ in header_documents:
        existing = header.existing
        assert existing is not None
        modeled_attributes = {item.modeled_attribute_id: item for item in header.attributes}
        for binding in existing.attributes:
            if binding.status != "active" or binding.transformation is None:
                continue
            modeled_attribute = modeled_attributes.get(binding.modeled_attribute_id)
            if modeled_attribute is None or binding.target_attribute_id not in target_attributes:
                raise InvalidRequestError("Applied Mapping Attribute identity is incomplete.")
            transformation = AttributeMappingTransformationDocumentV1.model_validate(
                binding.transformation,
                strict=True,
            )
            for source_column in transformation.source_columns:
                executable = package_sources.get(source_column.source_alias)
                if executable is None:
                    raise InvalidRequestError("Applied Mapping source alias is incomplete.")
                source_object = source_objects[executable.object_id]
                if source_column.source_attribute_id not in {
                    item.attribute_id for item in source_object.attributes
                }:
                    raise InvalidRequestError("Applied Mapping source column is incomplete.")
                used_attribute_ids[source_column.source_alias].add(
                    source_column.source_attribute_id
                )
            target_bindings.setdefault(binding.target_attribute_id, []).append(
                (header, modeled_attribute, transformation)
            )
    if set(target_bindings) != set(target_attributes) or any(
        len(items) != 1 for items in target_bindings.values()
    ):
        raise InvalidRequestError(
            "GeneratorDocumentV1 requires one applied Mapping for every target column."
        )

    executable_sources: list[dict[str, object]] = []
    source_attribute_names: dict[tuple[str, int], str] = {}
    for alias, executable in package_sources.items():
        source = source_objects[executable.object_id]
        attributes = {
            item.attribute_id: item
            for item in source.attributes
            if item.attribute_id in used_attribute_ids[alias]
        }
        if not attributes:
            raise InvalidRequestError("Every executable source requires a used column.")
        for attribute_id, attribute in attributes.items():
            source_attribute_names[(alias, attribute_id)] = attribute.attribute_name
        batch_rule = executable.batch_rule
        batch_attribute = (
            None
            if batch_rule is None
            else next(
                (
                    item
                    for item in source.attributes
                    if item.attribute_id == batch_rule.attribute_id
                ),
                None,
            )
        )
        if batch_rule is not None and batch_attribute is None:
            raise InvalidRequestError("Applied Mapping batch column is incomplete.")
        executable_sources.append(
            {
                "alias": alias,
                "zone": source.zone,
                "catalog": source.tenant_catalog,
                "schema": source.object_schema,
                "object_name": source.object_name,
                "fqn": _fqn(
                    source.tenant_catalog,
                    source.object_schema,
                    source.object_name,
                ),
                "used_columns": [
                    {
                        "name": item.attribute_name,
                        "data_type": item.data_type,
                        "nullable": item.nullable,
                        "definition": item.definition,
                        "meaning": None,
                    }
                    for item in attributes.values()
                ],
                "batch_rule": (
                    None
                    if batch_rule is None or batch_attribute is None
                    else {
                        "attribute_name": batch_attribute.attribute_name,
                        "values": batch_rule.values,
                    }
                ),
            }
        )

    source_predecessors = {item.system_id: item for item in references.source_predecessors}
    target_predecessors = {item.object_id: item for item in references.target_predecessors}
    provenance_by_key = {
        (item.lineage_kind, item.reference_id): item for item in references.provenance
    }
    try:
        predecessor_documents = [
            {
                "code": source_predecessors[item.predecessor_source_system_id].code,
                "name": source_predecessors[item.predecessor_source_system_id].name,
                "reason": item.reason,
            }
            for item in package.source_system_dependencies
        ]
        target_predecessor_documents = [
            {
                "target_fqn": _fqn(
                    target_predecessors[item.predecessor_target_object_id].catalog,
                    target_predecessors[item.predecessor_target_object_id].schema_name,
                    target_predecessors[item.predecessor_target_object_id].object_name,
                ),
                "reason": item.reason,
            }
            for item in package.target_dependencies
        ]
    except KeyError:
        raise InvalidRequestError("Applied Mapping dependency names are incomplete.") from None

    provenance_documents: list[dict[str, object]] = []
    for provenance in package.non_executable_provenance:
        reference_ids = (
            provenance.ingestion_object_mapping_ids
            if provenance.lineage_kind == "original_ingestion"
            else provenance.prior_object_mapping_ids
        )
        for reference_id in reference_ids:
            reference = provenance_by_key.get((provenance.lineage_kind, reference_id))
            if reference is None or reference.source_system_id != provenance.source_system_id:
                raise InvalidRequestError("Applied Mapping provenance names are incomplete.")
            provenance_documents.append(
                {
                    "source_system_code": reference.source_system_code,
                    "source_system_name": reference.source_system_name,
                    "connection_code": reference.connection_code,
                    "source_object_name": reference.source_object_name,
                    "lineage_kind": reference.lineage_kind,
                    "lineage_path": list(reference.lineage_path),
                    "executable_source_aliases": provenance.executable_source_aliases,
                }
            )

    target_columns: list[dict[str, object]] = []
    for target_id, target in target_attributes.items():
        header, modeled_attribute, transformation = target_bindings[target_id][0]
        contributors = [
            {
                "entity_name": header.modeled_entity_name,
                "attribute_name": modeled_attribute.name,
                "source_alias": source.source_alias,
                "source_column_name": source_attribute_names[
                    (source.source_alias, source.source_attribute_id)
                ],
            }
            for source in transformation.source_columns
        ]
        target_columns.append(
            {
                "target_column_name": target.attribute_name,
                "disposition": "mapped",
                "reason": None,
                "contributors": contributors,
                "kind": transformation.transformation_kind,
                "step_output": transformation.step_output,
                "expression": transformation.expression,
                "logic": transformation.logic,
                "rationale": transformation.logic,
            }
        )

    merge_key_names = [target_attributes[item].attribute_name for item in package.load.merge_keys]
    layer: Literal["logical", "dimensional"] = (
        "logical" if prepared.modeled_entity_type == "logical_entity" else "dimensional"
    )
    document = {
        "schema": {
            "document_version": "1.0",
            "profile_key": prepared.profile.key,
            "profile_version": prepared.profile.version,
            "profile_schema_digest": prepared.profile.schema_digest,
        },
        "applied_model": {
            "model_name": prepared.model_name,
            "model_revision": prepared.model_revision,
            "source_context_digest": prepared.context_digest,
        },
        "route": prepared.route,
        "source_system": {
            "code": context.source_system.system_code,
            "name": context.source_system.system_name,
            "dependency_order": context.source_system.dependency_order,
            "predecessors": predecessor_documents,
        },
        "artifact": {
            "type": package.artifact_type,
            "generation_instructions": package.artifact_generation_instructions,
        },
        "dependency_waves": {
            "target_order": min(item[0].dependency_order for item in header_documents),
            "target_predecessors": target_predecessor_documents,
        },
        "target": {
            "catalog": context.target.tenant_catalog,
            "schema": context.target.object_schema,
            "object_name": context.target.object_name,
            "fqn": _fqn(
                context.target.tenant_catalog,
                context.target.object_schema,
                context.target.object_name,
            ),
            "zone": context.target.zone,
            "description": context.target.object_description,
            "grain_and_deduplication": package.grain_and_deduplication,
            "columns": [
                {
                    "name": item.attribute_name,
                    "data_type": item.data_type,
                    "nullable": item.nullable,
                    "ordinal": item.ordinal,
                    "definition": item.definition,
                }
                for item in target_attributes.values()
            ],
        },
        "executable_sources": executable_sources,
        "original_source_provenance": provenance_documents,
        "runtime_parameters": [item.model_dump(mode="json") for item in package.runtime_parameters],
        "named_steps": [item.model_dump(mode="json") for item in package.steps],
        "load": {
            "write_mode": package.load.write_mode,
            "merge_keys": merge_key_names,
            "partition_basis": package.load.partition_basis,
            "concurrent_system_write_mode": package.load.concurrent_system_write_mode,
            "concurrent_write_basis": package.load.concurrent_write_basis,
            "grain_and_deduplication": package.grain_and_deduplication,
        },
        "entity_contributions": [
            {
                "layer": layer,
                "entity_name": header.modeled_entity_name,
                "definition": header.modeled_entity_definition,
                **transformation.model_dump(mode="json", exclude={"schema_version"}),
            }
            for header, transformation, _ in header_documents
        ],
        "target_columns": target_columns,
    }
    return GeneratorDocumentV1.model_validate(document, strict=True)


def _fqn(catalog: str, schema_name: str, object_name: str) -> str:
    return ".".join((catalog, schema_name, object_name))


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    modeled_entity_type = arguments.get("modeled_entity_type")
    result: dict[str, str | int] = {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "modeled_entity_type": (
            cast(str, modeled_entity_type)
            if modeled_entity_type in {"logical_entity", "dimensional_entity"}
            else "invalid"
        ),
    }
    for name in ("model_id", "target_object_id", "source_system_id"):
        value = arguments.get(name)
        result[name] = value if type(value) is int and value > 0 else "invalid"
    return result
