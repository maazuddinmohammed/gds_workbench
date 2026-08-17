"""Read-only MCP projection of the shared Metadata Snapshot contract registry."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.tools.snapshots.dataset_description import (
    DatasetColumnDescription,
)

from .archive import build_dataset_document
from .contracts import DATASETS, DATASETS_BY_NAME, MetadataDataset


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MetadataDatasetReference(ContractModel):
    columns: list[str]
    target_record_type: str
    target_columns: list[str]
    nullable: bool


class MetadataDatasetDependency(ContractModel):
    record_type: str
    datasets: list[str]


class DescribeMetadataDatasetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset: MetadataDataset
    record_type: str
    section: Literal["foundational", "reference", "operational"]
    change_set_eligible: bool
    natural_key: list[str]
    references: list[MetadataDatasetReference]
    dependencies: list[MetadataDatasetDependency]
    population_rules: tuple[str, ...]
    columns: tuple[DatasetColumnDescription, ...]
    dataset_schema: dict[str, object]


class MetadataDatasetToolError(Exception):
    """A bounded contract-description failure safe for MCP serialization."""


def register_describe_metadata_dataset_tool(
    server: MCPServer[None],
    *,
    identity_provider: IdentityProvider,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Describe one Metadata Snapshot dataset from the server's shared contract. "
            "Returns each column's meaning, population guidance, accepted values or "
            "reference source, examples, and its exact JSON Schema; never returns "
            "physical rows."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": ToolPolicy.TENANT_READ.value},
        structured_output=True,
    )
    async def describe_metadata_dataset(
        ctx: Context[None],
        dataset: MetadataDataset,
        schema_version: Literal["1.0"] = "1.0",
    ) -> DescribeMetadataDatasetResult:
        del schema_version
        try:
            identity_provider.request_principal(ctx.request_context.request)
            definition = DATASETS_BY_NAME.get(dataset)
            if definition is None:
                raise InvalidRequestError("The Metadata Snapshot dataset is unknown.")
            dependency_record_types = tuple(
                dict.fromkeys(reference.target_record_type for reference in definition.references)
            )
            dataset_document = build_dataset_document(definition)
            return DescribeMetadataDatasetResult(
                dataset=definition.name,
                record_type=definition.record_type,
                section=definition.section.value,
                change_set_eligible=definition.change_set_eligible,
                natural_key=list(definition.canonical_key),
                references=[
                    MetadataDatasetReference(
                        columns=list(reference.columns),
                        target_record_type=reference.target_record_type,
                        target_columns=list(reference.target_columns),
                        nullable=reference.nullable,
                    )
                    for reference in definition.references
                ],
                dependencies=[
                    MetadataDatasetDependency(
                        record_type=record_type,
                        datasets=[
                            candidate.name
                            for candidate in DATASETS
                            if candidate.record_type == record_type
                        ],
                    )
                    for record_type in dependency_record_types
                ],
                population_rules=dataset_document.description.population_rules,
                columns=dataset_document.description.columns,
                dataset_schema=dataset_document.schema,
            )
        except AuthenticationError as error:
            raise MetadataDatasetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataDatasetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataDatasetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "describe_metadata_dataset",
        policy=ToolPolicy.TENANT_READ,
        summarize_input=_audit_input,
        retain_arguments={"dataset", "schema_version"},
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str]:
    raw_dataset = arguments.get("dataset")
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "dataset": (
            raw_dataset
            if isinstance(raw_dataset, str) and raw_dataset in DATASETS_BY_NAME
            else "invalid"
        ),
    }
