"""Atomic successful SQL artifact replacement and Workflow Run completion."""

from __future__ import annotations

import hashlib
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal, LiteralString, Protocol
from uuid import UUID

from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import AuthorizationDeniedError, DependencyUnavailableError
from gds_etl_workbench.domain.modeling_records import GeneratedCodeRecord
from pydantic import BaseModel, ConfigDict, Field

from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)

from .candidate import GeneratedSqlArtifact

type ModeledEntityType = Literal["logical_entity", "dimensional_entity"]

_STORE_SQL: LiteralString = """
SELECT stored.generated_sql_artifact_id,
       stored.object_id,
       stored.generated_sql_digest
  FROM application.store_generated_sql_artifact(
       %s, %s, %s, %s, %s, %s, %s, %s,
       %s, %s, %s, %s, %s, %s, %s
  ) AS stored
"""

_COMPLETE_SQL: LiteralString = """
SELECT completed.workflow_run_state
  FROM application.complete_workflow_run(%s, %s, %s, %s, %s, %s) AS completed
"""


class SqlStorageTransaction(Protocol):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None: ...


class SqlStorageDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[SqlStorageTransaction]: ...


class SqlGeneratorIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")


class CodeGenerationArtifactContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    object_id: int = Field(gt=0, repr=False)
    mapping_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sql_generation_guide_version_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    applied_generated_code: GeneratedCodeRecord | None = None


class StoredGeneratedSqlArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    generated_sql_artifact_id: int = Field(gt=0)
    object_id: int = Field(gt=0)
    generated_sql_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class GeneratedSqlStorageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workflow_run_id: int = Field(gt=0)
    workflow_run_state: Literal["completed", "completed_with_repair"]
    artifact_count: int = Field(gt=0, le=50_000)
    items: tuple[StoredGeneratedSqlArtifact, ...] = Field(min_length=1, max_length=50_000)


class GeneratedSqlStorageError(DependencyUnavailableError):
    """Stable failure that never includes SQL or database diagnostics."""


class DatabaseGeneratedSqlStorage:
    """Store all successful artifacts and complete the run in one transaction."""

    def __init__(
        self,
        *,
        database: SqlStorageDatabase,
        generator: SqlGeneratorIdentity,
    ) -> None:
        self._database = database
        self._generator = generator

    async def store(
        self,
        principal: RequestPrincipal,
        *,
        model_id: int,
        modeled_entity_type: ModeledEntityType,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        artifacts: tuple[GeneratedSqlArtifact, ...],
        contexts: tuple[CodeGenerationArtifactContext, ...],
    ) -> GeneratedSqlStorageResult:
        by_ref = {context.target_ref: context for context in contexts}
        artifact_refs = [artifact.target_ref for artifact in artifacts]
        if (
            not artifacts
            or len(artifact_refs) != len(set(artifact_refs))
            or set(artifact_refs) != set(by_ref)
            or any(
                artifact.object_id != by_ref[artifact.target_ref].object_id
                for artifact in artifacts
            )
        ):
            raise ValueError("Code Generation candidate and context coverage differ")

        identity = _identity_triple(principal)
        stored: list[StoredGeneratedSqlArtifact] = []
        try:
            async with self._database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=workflow_run_id,
                    workflow_run_claim_token=workflow_run_claim_token,
                )
                for artifact in artifacts:
                    context = by_ref[artifact.target_ref]
                    digest = hashlib.sha256(artifact.generated_sql.encode("utf-8")).hexdigest()
                    row = await transaction.fetch_one(
                        _STORE_SQL,
                        identity
                        + (
                            model_id,
                            expected_model_revision,
                            modeled_entity_type,
                            context.object_id,
                            context.mapping_context_digest,
                            context.source_context_digest,
                            context.sql_generation_guide_version_id,
                            workflow_run_id,
                            self._generator.code,
                            self._generator.version,
                            artifact.generated_sql,
                            digest,
                        ),
                    )
                    if row is None:
                        raise GeneratedSqlStorageError()
                    stored.append(StoredGeneratedSqlArtifact.model_validate(row, strict=True))
                completed = await transaction.fetch_one(
                    _COMPLETE_SQL,
                    identity
                    + (
                        workflow_run_id,
                        expected_model_revision,
                        len(stored),
                    ),
                )
                if completed is None:
                    raise GeneratedSqlStorageError()
        except AuthorizationDeniedError:
            raise
        except Exception:
            raise GeneratedSqlStorageError() from None

        state = completed.get("workflow_run_state")
        if state not in {"completed", "completed_with_repair"}:
            raise GeneratedSqlStorageError()
        return GeneratedSqlStorageResult(
            workflow_run_id=workflow_run_id,
            workflow_run_state=state,
            artifact_count=len(stored),
            items=tuple(stored),
        )


def _identity_triple(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    principal_type = "service_principal" if principal.actor_kind is ActorKind.WORKLOAD else "user"
    return principal.entra_tenant_id, principal.entra_object_id, principal_type
