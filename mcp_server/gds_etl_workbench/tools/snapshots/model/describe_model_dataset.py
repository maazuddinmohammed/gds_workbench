"""Read-only projection of the shared Model dataset registry."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError

from ...modeling.common import POLICY, ContractModel
from .contracts import (
    DATASETS_BY_NAME,
    ModelDataset,
    ModelSection,
    build_model_dataset_schema,
)


class DescribeModelDatasetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset: ModelDataset
    section: ModelSection
    change_set_eligible: Literal[True] = True
    database_ids_included: Literal[False] = False
    canonical_key: tuple[str, ...]
    record_schema: dict[str, object]
    usage: tuple[str, ...]


class ModelDatasetToolError(Exception):
    """A bounded contract-description failure safe for MCP serialization."""


def register_describe_model_dataset_tool(
    server: MCPServer[None],
    *,
    identity_provider: IdentityProvider,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Describe one shared Model Snapshot and Model Change Set dataset. Returns "
            "the exact ID-free JSON Schema, canonical key, and usage guidance."
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
    async def describe_model_dataset(
        ctx: Context[None],
        dataset: ModelDataset,
        schema_version: Literal["1.0"] = "1.0",
    ) -> DescribeModelDatasetResult:
        del schema_version
        try:
            identity_provider.request_principal(ctx.request_context.request)
            definition = DATASETS_BY_NAME.get(dataset)
            if definition is None:
                raise InvalidRequestError("The Model dataset is unknown.")
            return DescribeModelDatasetResult(
                dataset=definition.name,
                section=definition.section,
                canonical_key=definition.canonical_key,
                record_schema=build_model_dataset_schema(definition),
                usage=(
                    "Use every required field and no unlisted field.",
                    "Use canonical names, never database IDs, in Model Change Set records.",
                    "Each staged dataset is a complete replacement of that pending dataset.",
                    "An empty staged record list clears that pending dataset.",
                ),
            )
        except AuthenticationError as error:
            raise ModelDatasetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelDatasetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelDatasetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "describe_model_dataset",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"dataset", "schema_version"},
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str]:
    dataset = arguments.get("dataset")
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "dataset": (
            dataset if isinstance(dataset, str) and dataset in DATASETS_BY_NAME else "invalid"
        ),
    }
