"""Authorization, transaction, and cursor orchestration for Context reads."""

from contextlib import AbstractAsyncContextManager
from hashlib import sha256
from typing import Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction

from gds_workbench_api.features.context.contracts import (
    ContextGroupDetail,
    ContextGroupFilters,
    ContextGroupPage,
    ContextRecordDetail,
    ContextRecordFilters,
    ContextRecordPage,
    ContextSourceSystemPage,
    ContextTypeCollection,
)
from gds_workbench_api.features.context.repository import (
    ContextRepository,
    PostgresContextRepository,
)
from gds_workbench_api.features.projects import ProjectNotFoundError


class ContextService(Protocol):
    async def list_types(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> ContextTypeCollection: ...

    async def list_source_systems(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        page_size: int,
        cursor: str | None,
    ) -> ContextSourceSystemPage: ...

    async def list_groups(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextGroupFilters,
        page_size: int,
        cursor: str | None,
    ) -> ContextGroupPage: ...

    async def read_group(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        context_group_id: int,
    ) -> ContextGroupDetail: ...

    async def list_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextRecordFilters,
        page_size: int,
        cursor: str | None,
    ) -> ContextRecordPage: ...

    async def read_record(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        context_record_id: str,
    ) -> ContextRecordDetail: ...


class ContextReadDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class DatabaseContextService:
    def __init__(
        self,
        *,
        database: ContextReadDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
        repository: ContextRepository | None = None,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)
        self._repository = repository or PostgresContextRepository()

    async def list_types(
        self, principal: RequestPrincipal, *, tenant_id: int, project_id: int
    ) -> ContextTypeCollection:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            revision = await self._repository.read_project_revision(
                transaction, tenant_id=tenant_id, project_id=project_id
            )
            if revision is None:
                raise ProjectNotFoundError()
            items = await self._repository.list_types(transaction)
        return ContextTypeCollection(items=tuple(items))

    async def list_source_systems(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        page_size: int,
        cursor: str | None,
    ) -> ContextSourceSystemPage:
        collection = f"web_context_source_systems:{tenant_id}:{project_id}:{page_size}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            revision = await self._repository.read_project_revision(
                transaction, tenant_id=tenant_id, project_id=project_id
            )
            if revision is None:
                raise ProjectNotFoundError()
            # Context provenance names an active global System; it grants no
            # Connection or physical-data access. Match Context authoring's scope.
            items = await self._repository.list_source_systems(
                transaction, limit=page_size + 1, offset=offset
            )
        return ContextSourceSystemPage(
            items=tuple(items[:page_size]),
            next_cursor=_next_cursor(
                self._cursors,
                collection=collection,
                offset=offset,
                page_size=page_size,
                returned_count=len(items),
            ),
        )

    async def list_groups(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextGroupFilters,
        page_size: int,
        cursor: str | None,
    ) -> ContextGroupPage:
        collection = _cursor_collection(
            "groups",
            tenant_id=tenant_id,
            project_id=project_id,
            page_size=page_size,
            filters=filters,
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            revision = await self._repository.read_project_revision(
                transaction,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if revision is None:
                raise ProjectNotFoundError()
            items = await self._repository.list_groups(
                transaction,
                tenant_id=tenant_id,
                project_id=project_id,
                filters=filters,
                limit=page_size + 1,
                offset=offset,
            )
        return ContextGroupPage(
            project_id=project_id,
            project_revision=revision,
            items=tuple(items[:page_size]),
            next_cursor=_next_cursor(
                self._cursors,
                collection=collection,
                offset=offset,
                page_size=page_size,
                returned_count=len(items),
            ),
        )

    async def read_group(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        context_group_id: int,
    ) -> ContextGroupDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            return await self._repository.read_group(
                transaction,
                tenant_id=tenant_id,
                project_id=project_id,
                group_id=context_group_id,
            )

    async def list_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        filters: ContextRecordFilters,
        page_size: int,
        cursor: str | None,
    ) -> ContextRecordPage:
        collection = _cursor_collection(
            "records",
            tenant_id=tenant_id,
            project_id=project_id,
            page_size=page_size,
            filters=filters,
        )
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            revision = await self._repository.read_project_revision(
                transaction,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if revision is None:
                raise ProjectNotFoundError()
            items = await self._repository.list_records(
                transaction,
                tenant_id=tenant_id,
                project_id=project_id,
                filters=filters,
                limit=page_size + 1,
                offset=offset,
            )
        return ContextRecordPage(
            project_id=project_id,
            project_revision=revision,
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
        project_id: int,
        context_record_id: str,
    ) -> ContextRecordDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorize(transaction, principal, tenant_id=tenant_id)
            return await self._repository.read_record(
                transaction,
                tenant_id=tenant_id,
                project_id=project_id,
                record_id=context_record_id,
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
    project_id: int,
    page_size: int,
    filters: ContextGroupFilters | ContextRecordFilters,
) -> str:
    filter_digest = sha256(filters.model_dump_json().encode()).hexdigest()
    return f"web_context_{name}:{tenant_id}:{project_id}:{page_size}:{filter_digest}"


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
