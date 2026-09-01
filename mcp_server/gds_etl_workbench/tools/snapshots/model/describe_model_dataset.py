"""Read-only projection of the shared Model dataset registry."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.tools.snapshots.dataset_description import (
    DatasetColumnDescription,
    compact_authoring_schema,
)

from ...modeling.common import POLICY, ContractModel
from .contracts import (
    DATASETS_BY_NAME,
    ModelDataset,
    ModelSection,
    build_model_dataset_schema,
)
from .guidance import model_dataset_population_rules


class DescribeModelDatasetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    detail: Literal["compact", "full"]
    dataset: ModelDataset
    section: ModelSection
    change_set_eligible: bool
    database_ids_included: Literal[False] = False
    canonical_key: tuple[str, ...]
    population_rules: tuple[str, ...]
    authoring_schema: dict[str, object]
    columns: tuple[DatasetColumnDescription, ...] | None
    record_schema: dict[str, object] | None
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
            "Describe one Model dataset for agent authoring. Compact detail is the default "
            "and omits duplicated column cards plus validator-owned nested schemas. Full "
            "detail additionally returns every column card and the exact ID-free JSON "
            "Schema. Both include canonical key and GDS population, digest, and assertion rules."
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
        detail: Literal["compact", "full"] = "compact",
        schema_version: Literal["1.0"] = "1.0",
    ) -> DescribeModelDatasetResult:
        del schema_version
        try:
            identity_provider.request_principal(ctx.request_context.request)
            definition = DATASETS_BY_NAME.get(dataset)
            if definition is None:
                raise InvalidRequestError("The Model dataset is unknown.")
            record_schema = build_model_dataset_schema(definition)
            raw_rules = record_schema.get("x-gds-population-rules", [])
            raw_columns = record_schema.get("x-gds-columns", [])
            if not isinstance(raw_rules, list) or not isinstance(raw_columns, list):
                raise ValueError("The Model dataset authoring guidance is invalid.")
            rule_documents = cast(list[object], raw_rules)
            column_documents = cast(list[object], raw_columns)
            if not all(isinstance(rule, str) for rule in rule_documents) or not all(
                isinstance(column, dict) for column in column_documents
            ):
                raise ValueError("The Model dataset authoring guidance is invalid.")
            usage = ("Use every required field and no unlisted field.",)
            if definition.change_set_eligible:
                usage += (
                    "Use canonical names, never database IDs, in Model Change Set records.",
                    "Each staged dataset completely replaces that pending dataset.",
                    "An empty staged record list clears that pending dataset.",
                )
            else:
                usage += ("This dataset is read-only through MCP; it cannot be staged or applied.",)
            usage += model_dataset_population_rules(definition.name)
            return DescribeModelDatasetResult(
                detail=detail,
                dataset=definition.name,
                section=definition.section,
                change_set_eligible=definition.change_set_eligible,
                canonical_key=definition.canonical_key,
                population_rules=tuple(cast(list[str], rule_documents)),
                authoring_schema=compact_authoring_schema(record_schema),
                columns=(
                    tuple(
                        DatasetColumnDescription.model_validate(column, strict=False)
                        for column in cast(list[dict[str, object]], column_documents)
                    )
                    if detail == "full"
                    else None
                ),
                record_schema=record_schema if detail == "full" else None,
                usage=usage,
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
        retain_arguments={"dataset", "detail", "schema_version"},
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str]:
    dataset = arguments.get("dataset")
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "detail": (
            arguments.get("detail", "compact")
            if arguments.get("detail", "compact") in {"compact", "full"}
            else "invalid"
        ),
        "dataset": (
            dataset if isinstance(dataset, str) and dataset in DATASETS_BY_NAME else "invalid"
        ),
    }
