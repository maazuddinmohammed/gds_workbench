from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.features.code_generation.candidate import GeneratedSqlArtifact
from gds_workbench_api.features.code_generation.storage import (
    CodeGenerationArtifactContext,
    DatabaseGeneratedSqlStorage,
    GeneratedSqlStorageError,
    SqlGeneratorIdentity,
)

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


class StorageTransaction:
    def __init__(self, *, fence_failure: Exception | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fence_failure = fence_failure

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "assert_workflow_run_claim" in query:
            if self.fence_failure is not None:
                raise self.fence_failure
            return {"asserted": None}
        if "store_generated_sql_artifact" in query:
            return {
                "generated_sql_artifact_id": 900 + len(self.calls),
                "object_id": parameters[6],
                "generated_sql_digest": parameters[-1],
            }
        if "complete_workflow_run" in query:
            return {"workflow_run_state": "completed"}
        raise AssertionError("unexpected storage query")


class StorageDatabase:
    def __init__(self, *, fence_failure: Exception | None = None) -> None:
        self.transaction = StorageTransaction(fence_failure=fence_failure)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[StorageTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_storage_atomically_upserts_exact_artifacts_then_completes_run() -> None:
    database = StorageDatabase()
    storage = DatabaseGeneratedSqlStorage(
        database=database,
        generator=SqlGeneratorIdentity(code="gds.web.sql", version="1.0.0"),
    )
    sql = "SELECT customer_id\nFROM silver.customer;\n"

    result = await storage.store(
        _principal(),
        model_id=18,
        modeled_entity_type="logical_entity",
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
        artifacts=(
            GeneratedSqlArtifact(
                target_ref="target_1",
                object_id=501,
                generated_sql=sql,
            ),
        ),
        contexts=(
            CodeGenerationArtifactContext(
                target_ref="target_1",
                object_id=501,
                mapping_context_digest="a" * 64,
                source_context_digest="b" * 64,
                sql_generation_guide_version_id=81,
            ),
        ),
    )

    assert result.workflow_run_state == "completed"
    assert result.artifact_count == 1
    assert len(result.items[0].generated_sql_digest) == 64
    assert sql not in repr(result)
    assert "assert_workflow_run_claim" in database.transaction.calls[0][0]
    assert database.transaction.calls[0][1] == (1048, _CLAIM_TOKEN)
    store_parameters = database.transaction.calls[1][1]
    assert store_parameters[:3] == (
        UUID("11111111-1111-1111-1111-111111111111"),
        UUID("22222222-2222-2222-2222-222222222222"),
        "user",
    )
    assert store_parameters[3:7] == (18, 7, "logical_entity", 501)
    assert store_parameters[10:14] == (1048, "gds.web.sql", "1.0.0", sql)
    assert "complete_workflow_run" in database.transaction.calls[2][0]


@pytest.mark.asyncio
async def test_storage_rejects_context_or_candidate_coverage_mismatch_before_write() -> None:
    database = StorageDatabase()
    storage = DatabaseGeneratedSqlStorage(
        database=database,
        generator=SqlGeneratorIdentity(code="gds.web.sql", version="1.0.0"),
    )

    with pytest.raises(ValueError, match="coverage"):
        await storage.store(
            _principal(),
            model_id=18,
            modeled_entity_type="logical_entity",
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
            artifacts=(
                GeneratedSqlArtifact(
                    target_ref="target_1",
                    object_id=501,
                    generated_sql="SELECT 1;",
                ),
            ),
            contexts=(),
        )

    assert database.transaction.calls == []


@pytest.mark.asyncio
async def test_storage_rejects_a_lost_claim_before_any_artifact_or_completion_write() -> None:
    diagnostic = "claim token=secret; SQL=SELECT raw_provider_output"
    database = StorageDatabase(fence_failure=RuntimeError(diagnostic))
    storage = DatabaseGeneratedSqlStorage(
        database=database,
        generator=SqlGeneratorIdentity(code="gds.web.sql", version="1.0.0"),
    )

    with pytest.raises(GeneratedSqlStorageError) as raised:
        await storage.store(
            _principal(),
            model_id=18,
            modeled_entity_type="logical_entity",
            workflow_run_id=1048,
            expected_model_revision=7,
            workflow_run_claim_token=_CLAIM_TOKEN,
            artifacts=(
                GeneratedSqlArtifact(
                    target_ref="target_1",
                    object_id=501,
                    generated_sql="SELECT 1;",
                ),
            ),
            contexts=(
                CodeGenerationArtifactContext(
                    target_ref="target_1",
                    object_id=501,
                    mapping_context_digest="a" * 64,
                    source_context_digest="b" * 64,
                    sql_generation_guide_version_id=81,
                ),
            ),
        )

    assert len(database.transaction.calls) == 1
    assert "assert_workflow_run_claim" in database.transaction.calls[0][0]
    assert diagnostic not in str(raised.value)
    assert diagnostic not in repr(raised.value)
