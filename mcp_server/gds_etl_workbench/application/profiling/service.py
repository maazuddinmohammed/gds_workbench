"""MCP-owned durable profiling runs, independent of the web deployment."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.application.profiling.execution import (
    ProfileAttribute,
    ProfileObject,
    ProfileQuery,
    ProfilingExecutor,
    build_profile_queries,
    load_default_profiling_policy,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.errors import AuthorizationDeniedError, InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import WriteDatabase


class ProfilingStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    state: Literal["queued", "running", "completed", "cancelled", "failed"]
    selected_object_count: int = Field(ge=1)
    completed_object_count: int = Field(ge=0)
    saved_profile_count: int = Field(ge=0)
    failure_code: str | None
    failure_message: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class PlannedObject:
    object_id: int
    connection_id: int
    queries: tuple[ProfileQuery, ...]
    context_digests: dict[int, str]


def plan_context(payload: dict[str, Any]) -> tuple[PlannedObject, ...]:
    """Validate every target before any external query can start."""
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in payload["context"]:
        grouped.setdefault(row["object_id"], []).append(row)
    policy = load_default_profiling_policy()
    batches = payload.get("batch_ids")
    result: list[PlannedObject] = []
    for object_id, rows in grouped.items():
        header = rows[0]
        if len(rows) > policy.max_attributes_per_object:
            raise InvalidRequestError("Profiling Object exceeds the Attribute limit.")
        batch = next((row["relation_attribute"] for row in rows if row["is_batch_attribute"]), None)
        if header["batch_attribute_name"] is not None and batch is None:
            raise InvalidRequestError("Batch Attribute metadata is incomplete.")
        target = ProfileObject(
            object_id=object_id,
            connection_id=header["gds_connection_id"],
            catalog=header["relation_catalog"],
            schema=header["relation_schema"],
            table=header["relation_object"],
            batch_attribute_name=batch,
            attributes=tuple(
                ProfileAttribute(
                    attribute_id=row["attribute_id"],
                    name=row["relation_attribute"],
                    data_type=row["attribute_data_type"],
                )
                for row in rows
            ),
        )
        queries = build_profile_queries(
            target,
            batch_ids=None if batches is None else tuple(batches),
            require_batch_ids=True,
            attributes_per_query=policy.attributes_per_query,
        )
        result.append(
            PlannedObject(
                object_id,
                target.connection_id,
                queries,
                {row["attribute_id"]: row["source_context_digest"] for row in rows},
            )
        )
    if not result:
        raise InvalidRequestError("Profiling requires eligible Objects and Attributes.")
    return tuple(result)


def identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    return (
        principal.entra_tenant_id,
        principal.entra_object_id,
        "user" if principal.actor_kind is ActorKind.HUMAN else "service_principal",
    )


class ProfilingService:
    def __init__(self, database: WriteDatabase) -> None:
        self.database = database

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        model_id: int,
        expected_model_revision: int,
        selected_object_ids: list[int],
        batch_ids: list[str] | None,
        environment_code: str,
        request_id: UUID,
    ) -> ProfilingStatus:
        async with self.database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                "SELECT mcp.start_mcp_profiling_run(%s,%s,%s,%s,%s,%s,%s,%s,%s) AS result",
                (
                    *identity_arguments(principal),
                    model_id,
                    expected_model_revision,
                    selected_object_ids,
                    batch_ids,
                    environment_code,
                    request_id,
                ),
            )
            assert row is not None
            payload = row["result"]
            if payload["context"] is not None:
                plan_context(payload)
            return ProfilingStatus.model_validate(payload["status"])

    async def status(self, principal: RequestPrincipal, run_id: int) -> ProfilingStatus:
        async with self.database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                "SELECT mcp.get_mcp_profiling_status(%s,%s,%s,%s) AS result",
                (*identity_arguments(principal), run_id),
            )
        assert row is not None
        return ProfilingStatus.model_validate(row["result"])

    async def cancel(self, principal: RequestPrincipal, run_id: int) -> ProfilingStatus:
        async with self.database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                "SELECT mcp.cancel_mcp_profiling_run(%s,%s,%s,%s) AS result",
                (*identity_arguments(principal), run_id),
            )
        assert row is not None
        return ProfilingStatus.model_validate(row["result"])

    async def worker_operation(
        self,
        operation: str,
        run_id: int | None = None,
        claim: UUID | None = None,
        payload: object = None,
    ) -> Any:
        async with self.database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                "SELECT mcp.mcp_profiling_worker(%s,%s,%s,%s) AS result",
                (operation, run_id, claim, Jsonb(payload)),
            )
        assert row is not None
        return row["result"]


class ProfilingWorker:
    """Claims survive process loss; expired claims are recovered by another worker."""

    def __init__(self, service: ProfilingService, executor: ProfilingExecutor) -> None:
        self.service = service
        self.executor = executor

    async def run_forever(self) -> None:
        while True:
            try:
                claim = await self.service.worker_operation("claim")
                if claim is not None:
                    await self.run_claim(claim)
                    continue
            except Exception:
                # PostgreSQL and connector exception text may contain sensitive values.
                pass
            await asyncio.sleep(2)

    async def run_claim(self, claim: dict[str, Any]) -> None:
        run_id = int(claim["workflow_run_id"])
        token = UUID(str(claim["workflow_run_claim_token"]))
        execution = asyncio.create_task(self.execute(run_id, token))
        heartbeat = asyncio.create_task(self.heartbeat(run_id, token))
        release_on_shutdown = False
        try:
            done, _ = await asyncio.wait(
                {execution, heartbeat}, return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat in done:
                # Cancellation or claim loss: stop connector work and never persist.
                execution.cancel()
            with suppress(asyncio.CancelledError):
                await execution
            if heartbeat in done:
                await heartbeat
        except asyncio.CancelledError:
            release_on_shutdown = True
            execution.cancel()
            raise
        except Exception:
            with suppress(Exception):
                await self.service.worker_operation("fail", run_id, token)
        finally:
            execution.cancel()
            heartbeat.cancel()
            await asyncio.gather(execution, heartbeat, return_exceptions=True)
            if release_on_shutdown:
                with suppress(Exception):
                    await self.service.worker_operation("release", run_id, token)

    async def heartbeat(self, run_id: int, token: UUID) -> None:
        while True:
            await asyncio.sleep(2)
            await self.service.worker_operation("heartbeat", run_id, token)

    async def execute(self, run_id: int, token: UUID) -> None:
        payload = await self.service.worker_operation("context", run_id, token)
        targets = plan_context(payload)
        connections: dict[int, DatabricksSqlConnection] = {}
        for row in payload["connections"]:
            if row["failure_code"] is not None:
                raise InvalidRequestError("Profiling GDS connection is unavailable.")
            connections[row["gds_connection_id"]] = DatabricksSqlConnection(
                server_hostname=row["databricks_host_name"],
                http_path=row["databricks_http_path"],
                access_token=row["databricks_token"],
            )
        policy = load_default_profiling_policy()
        profiles: list[dict[str, object]] = []
        for completed, target in enumerate(targets, 1):
            row_count: int | None = None
            for query in target.queries:
                # Recheck the live claim immediately before each external query.
                await self.service.worker_operation("heartbeat", run_id, token)
                metrics = await self.executor.execute(
                    connection=connections[target.connection_id],
                    query=query,
                    timeout_seconds=policy.statement_timeout_seconds,
                )
                if tuple(metric.attribute_id for metric in metrics) != query.attribute_ids:
                    raise InvalidRequestError("Profiling returned incomplete Attribute coverage.")
                for metric in metrics:
                    if row_count is not None and metric.row_count != row_count:
                        raise InvalidRequestError("Profiling Object changed during measurement.")
                    row_count = metric.row_count
                    profile = metric.model_dump(mode="json")
                    profile.update(
                        object_id=target.object_id,
                        source_context_digest=target.context_digests[metric.attribute_id],
                    )
                    profiles.append(profile)
            await self.service.worker_operation("progress", run_id, token, completed)
        await self.service.worker_operation("complete", run_id, token, profiles)
