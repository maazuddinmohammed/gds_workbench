"""Authorization, transaction, and cursor orchestration for Assertion reads."""

from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.assertions.contracts import (
    AssertionDocumentDetail,
    AssertionDocumentFilters,
    AssertionDocumentPage,
    AssertionRecordDetail,
    AssertionRecordFilters,
    AssertionRecordPage,
)
from gds_workbench_api.features.assertions.repository import (
    AssertionsRepository,
    PostgresAssertionsRepository,
)
from gds_workbench_api.features.models import ModelNotFoundError


class AssertionsService(Protocol):
    async def list_documents(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionDocumentFilters,
        page_size: int,
        cursor: str | None,
    ) -> AssertionDocumentPage: ...

    async def read_document(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        modeling_assertion_document_id: int,
    ) -> AssertionDocumentDetail: ...

    async def list_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionRecordFilters,
        page_size: int,
        cursor: str | None,
    ) -> AssertionRecordPage: ...

    async def read_record(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        modeling_assertion_record_id: int,
    ) -> AssertionRecordDetail: ...


class AssertionsReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseAssertionsService:
    def __init__(
        self,
        *,
        database: AssertionsReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
        repository: AssertionsRepository | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)
        self._repository = repository or PostgresAssertionsRepository()

    async def list_documents(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionDocumentFilters,
        page_size: int,
        cursor: str | None,
    ) -> AssertionDocumentPage:
        collection = _cursor_collection(
            "documents",
            tenant_id=tenant_id,
            model_id=model_id,
            page_size=page_size,
            filters=filters,
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            revision = await self._repository.read_model_revision(
                transaction,
                tenant_id=tenant_id,
                model_id=model_id,
            )
            if revision is None:
                raise ModelNotFoundError()
            items = await self._repository.list_documents(
                transaction,
                tenant_id=tenant_id,
                model_id=model_id,
                filters=filters,
                limit=page_size + 1,
                offset=offset,
            )
        return AssertionDocumentPage(
            model_id=model_id,
            model_revision=revision,
            items=tuple(items[:page_size]),
            next_cursor=_next_cursor(
                self._cursors,
                collection=collection,
                offset=offset,
                page_size=page_size,
                returned_count=len(items),
            ),
        )

    async def read_document(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        modeling_assertion_document_id: int,
    ) -> AssertionDocumentDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            return await self._repository.read_document(
                transaction,
                tenant_id=tenant_id,
                model_id=model_id,
                document_id=modeling_assertion_document_id,
            )

    async def list_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: AssertionRecordFilters,
        page_size: int,
        cursor: str | None,
    ) -> AssertionRecordPage:
        collection = _cursor_collection(
            "records",
            tenant_id=tenant_id,
            model_id=model_id,
            page_size=page_size,
            filters=filters,
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            revision = await self._repository.read_model_revision(
                transaction,
                tenant_id=tenant_id,
                model_id=model_id,
            )
            if revision is None:
                raise ModelNotFoundError()
            items = await self._repository.list_records(
                transaction,
                tenant_id=tenant_id,
                model_id=model_id,
                filters=filters,
                limit=page_size + 1,
                offset=offset,
            )
        return AssertionRecordPage(
            model_id=model_id,
            model_revision=revision,
            items=tuple(items[:page_size]),
            next_cursor=_next_cursor(
                self._cursors,
                collection=collection,
                offset=offset,
                page_size=page_size,
                returned_count=len(items),
            ),
        )

    async def read_record(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        modeling_assertion_record_id: int,
    ) -> AssertionRecordDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            return await self._repository.read_record(
                transaction,
                tenant_id=tenant_id,
                model_id=model_id,
                record_id=modeling_assertion_record_id,
            )

    async def _authorize(
        self,
        transaction: ReadTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> None:
        await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=ToolPolicy.TENANT_READ,
        )


def _cursor_collection(
    name: str,
    *,
    tenant_id: int,
    model_id: int,
    page_size: int,
    filters: AssertionDocumentFilters | AssertionRecordFilters,
) -> str:
    filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
    return f"web_assertions_{name}:{tenant_id}:{model_id}:{page_size}:{filter_digest}"


def _next_cursor(
    cursors: CursorCodec,
    *,
    collection: str,
    offset: int,
    page_size: int,
    returned_count: int,
) -> str | None:
    if returned_count <= page_size:
        return None
    return cursors.encode(collection=collection, offset=offset + page_size)
