"""Fixed SQL boundaries for metadata evidence and atomic enrichment completion."""

from __future__ import annotations

import json
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.errors import DependencyUnavailableError, InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, WriteTransaction
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from gds_workbench_api.features.workflows.authoring.context_contracts import (
    workflow_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    raise_workflow_lifecycle_error,
    workflow_identity_triple,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    PostgresAgentRunPlanRepository,
)
from gds_workbench_api.features.workflows.execution.fence import assert_workflow_run_claim

from .contracts import (
    EnrichmentFieldResult,
    MetadataEnrichmentCompletion,
    MetadataEnrichmentContext,
)


class EnrichmentDatabase(Protocol):
    def write_transaction(
        self, *, isolation: ReadIsolation = ReadIsolation.READ_COMMITTED
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class MetadataEnrichmentRepository:
    def __init__(self, database: EnrichmentDatabase, *, environment_code: str) -> None:
        self._database = database
        self._environment_code = environment_code

    async def load(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> tuple[AgentRunPlan, MetadataEnrichmentContext]:
        try:
            async with self._database.write_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                row = await transaction.fetch_one(
                    "SELECT application.get_metadata_enrichment_execution_context"
                    "(%s,%s,%s,%s,%s) AS context",
                    workflow_identity_triple(principal)
                    + (workflow_run_id, expected_model_revision),
                )
                plan = await PostgresAgentRunPlanRepository().load(
                    transaction,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    workflow_run_id=workflow_run_id,
                )
        except Exception as error:
            raise_workflow_lifecycle_error(error)
        if row is None:
            raise DependencyUnavailableError()
        try:
            raw = json.dumps(row["context"], ensure_ascii=False, allow_nan=False)
            if len(raw.encode("utf-8")) > 16 * 1024 * 1024:
                raise InvalidRequestError(
                    "The selected metadata exceeds the enrichment context limit."
                )
            context = MetadataEnrichmentContext.model_validate_json(raw, strict=True)
        except (KeyError, TypeError, ValueError, ValidationError):
            raise DependencyUnavailableError() from None
        if (
            context.workflow_run_id != workflow_run_id
            or context.model_id != model_id
            or context.model_revision != expected_model_revision
            or plan.model_workflow != "metadata_enrichment"
            or plan.workflow_execution_mode != "one_shot"
            or plan.model_revision != expected_model_revision
            or set(plan.selected_object_ids) != {item.object_id for item in context.objects}
            or any(item.source_tenant_id != tenant_id for item in context.objects)
            or sum(len(item.attributes) for item in context.objects) > 5_000
        ):
            raise InvalidRequestError("The selected metadata enrichment context is unavailable.")
        input_contracts = workflow_input_contracts("metadata_enrichment_object")
        for item in context.objects:
            if set(item.prompt_inputs) != set(input_contracts) or any(
                not Draft202012Validator(spec["schema"]).is_valid(item.prompt_inputs[name])  # pyright: ignore[reportUnknownMemberType]
                for name, spec in input_contracts.items()
            ):
                raise DependencyUnavailableError()
        return plan, context

    async def connection(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        connection_id: int,
    ) -> DatabricksSqlConnection | None:
        try:
            async with self._database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    "SELECT * FROM application.get_metadata_enrichment_connection_values"
                    "(%s,%s,%s,%s,%s,%s,%s)",
                    workflow_identity_triple(principal)
                    + (
                        workflow_run_id,
                        expected_model_revision,
                        connection_id,
                        self._environment_code,
                    ),
                )
        except Exception as error:
            raise_workflow_lifecycle_error(error)
        if row is None or row.get("failure_code") is not None:
            return None
        if (
            row.get("workflow_run_id") != workflow_run_id
            or row.get("model_revision") != expected_model_revision
            or row.get("gds_connection_id") != connection_id
        ):
            raise DependencyUnavailableError()
        values = [
            row.get(key)
            for key in ("databricks_host_name", "databricks_http_path", "databricks_token")
        ]
        if not all(isinstance(value, str) and value.strip() for value in values):
            return None
        return DatabricksSqlConnection(
            server_hostname=str(values[0]),
            http_path=str(values[1]),
            access_token=str(values[2]),
        )

    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        context: MetadataEnrichmentContext,
        workflow_run_claim_token: UUID,
        results: tuple[EnrichmentFieldResult, ...],
    ) -> MetadataEnrichmentCompletion:
        documents = [item.model_dump(mode="json") for item in results]
        if (
            len(results) > 10_200
            or len(json.dumps(documents, ensure_ascii=False).encode("utf-8")) > 24 * 1024 * 1024
        ):
            raise InvalidRequestError("The metadata enrichment result limit was exceeded.")
        try:
            async with self._database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    "SELECT application.complete_metadata_enrichment"
                    "(%s,%s,%s,%s,%s,%s,%s,%s) AS result",
                    workflow_identity_triple(principal)
                    + (
                        context.workflow_run_id,
                        context.model_revision,
                        workflow_run_claim_token,
                        context.baseline_digest,
                        Jsonb(documents),
                    ),
                )
        except Exception as error:
            raise_workflow_lifecycle_error(error)
        if row is None:
            raise DependencyUnavailableError()
        try:
            return MetadataEnrichmentCompletion.model_validate(row["result"], strict=True)
        except (KeyError, ValidationError):
            raise DependencyUnavailableError() from None
