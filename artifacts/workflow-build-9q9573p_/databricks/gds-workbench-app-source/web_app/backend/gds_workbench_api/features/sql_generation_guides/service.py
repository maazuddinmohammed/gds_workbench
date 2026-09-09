"""Authorized database service for SQL Generation Guide management."""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Literal, Never, Protocol
from uuid import UUID

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    WorkbenchError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from gds_workbench_api.features.sql_generation_guides.contracts import (
    SaveSqlGenerationGuideDraftRequest,
    SqlGenerationGuideDetail,
    SqlGenerationGuidePage,
    SqlGenerationGuideSummary,
    SqlGenerationGuideVersionDetail,
    SqlGenerationGuideVersionState,
)

_GUIDE_LIST_SQL = """
SELECT guide.sql_generation_guide_id,
       guide.sql_generation_guide_code,
       guide.sql_generation_guide_name,
       left(guide.sql_generation_guide_description, 2000)
           AS sql_generation_guide_description,
       guide.is_default,
       guide.is_active,
       latest.sql_generation_guide_version_id AS latest_version_id,
       latest.sql_generation_guide_version_number AS latest_version_number,
       latest.sql_generation_guide_version_status AS latest_version_status,
       latest.sql_generation_guide_digest AS latest_version_digest,
       latest.updated_time AS latest_version_updated_at,
       guide.updated_time AS updated_at
  FROM application.sql_generation_guide AS guide
  LEFT JOIN LATERAL (
       SELECT version.sql_generation_guide_version_id,
              version.sql_generation_guide_version_number,
              version.sql_generation_guide_version_status,
              version.sql_generation_guide_digest,
              version.updated_time
         FROM application.sql_generation_guide_version AS version
        WHERE version.sql_generation_guide_id = guide.sql_generation_guide_id
        ORDER BY version.sql_generation_guide_version_number DESC,
                 version.sql_generation_guide_version_id DESC
        LIMIT 1
  ) AS latest ON TRUE
 ORDER BY guide.is_default DESC,
          lower(guide.sql_generation_guide_name),
          guide.sql_generation_guide_id
 LIMIT %s OFFSET %s
"""

_GUIDE_DETAIL_SQL = """
SELECT guide.sql_generation_guide_id,
       guide.sql_generation_guide_code,
       guide.sql_generation_guide_name,
       left(guide.sql_generation_guide_description, 2000)
           AS sql_generation_guide_description,
       guide.is_default,
       guide.is_active,
       latest.sql_generation_guide_version_id AS latest_version_id,
       latest.sql_generation_guide_version_number AS latest_version_number,
       latest.sql_generation_guide_version_status AS latest_version_status,
       latest.sql_generation_guide_digest AS latest_version_digest,
       latest.updated_time AS latest_version_updated_at,
       guide.updated_time AS updated_at
  FROM application.sql_generation_guide AS guide
  LEFT JOIN LATERAL (
       SELECT version.sql_generation_guide_version_id,
              version.sql_generation_guide_version_number,
              version.sql_generation_guide_version_status,
              version.sql_generation_guide_digest,
              version.updated_time
         FROM application.sql_generation_guide_version AS version
        WHERE version.sql_generation_guide_id = guide.sql_generation_guide_id
        ORDER BY version.sql_generation_guide_version_number DESC,
                 version.sql_generation_guide_version_id DESC
        LIMIT 1
  ) AS latest ON TRUE
 WHERE guide.sql_generation_guide_id = %s
"""

_GUIDE_VERSIONS_SQL = """
SELECT version.sql_generation_guide_version_id,
       version.sql_generation_guide_id,
       version.sql_generation_guide_version_number,
       left(version.sql_generation_guide_content, 262144)
           AS sql_generation_guide_content,
       version.sql_generation_guide_digest,
       version.sql_generation_guide_version_status,
       version.published_time AS published_at,
       version.retired_time AS retired_at,
       version.created_time AS created_at,
       version.updated_time AS updated_at
  FROM application.sql_generation_guide_version AS version
 WHERE version.sql_generation_guide_id = %s
 ORDER BY version.sql_generation_guide_version_number DESC,
          version.sql_generation_guide_version_id DESC
 LIMIT %s OFFSET %s
"""

_GUIDE_MUTATION_BINDING_SQL = """
SELECT guide.sql_generation_guide_id
  FROM application.sql_generation_guide AS guide
 WHERE guide.sql_generation_guide_id = %s
   AND guide.is_active
"""

_SAVE_GUIDE_DRAFT_SQL = """
SELECT saved.sql_generation_guide_version_id,
       saved.sql_generation_guide_id,
       saved.sql_generation_guide_version_number,
       saved.sql_generation_guide_digest,
       saved.sql_generation_guide_version_status,
       saved.published_time AS published_at,
       saved.retired_time AS retired_at,
       saved.created_time AS created_at,
       saved.updated_time AS updated_at
  FROM application.save_sql_generation_guide_draft(
       %s::UUID,
       %s::UUID,
       %s::VARCHAR,
       %s::BIGINT,
       %s::BIGINT,
       %s::TEXT,
       %s::TIMESTAMPTZ
  ) AS saved
"""

_GUIDE_VERSION_MUTATION_BINDING_SQL = """
SELECT version.sql_generation_guide_version_id
  FROM application.sql_generation_guide_version AS version
  JOIN application.sql_generation_guide AS guide
    ON guide.sql_generation_guide_id = version.sql_generation_guide_id
   AND guide.is_active
 WHERE version.sql_generation_guide_version_id = %s
   AND version.sql_generation_guide_id = %s
"""

_TRANSITION_GUIDE_VERSION_SQL = """
SELECT saved.sql_generation_guide_version_id,
       saved.sql_generation_guide_id,
       saved.sql_generation_guide_version_number,
       saved.sql_generation_guide_digest,
       saved.sql_generation_guide_version_status,
       saved.published_time AS published_at,
       saved.retired_time AS retired_at,
       saved.created_time AS created_at,
       saved.updated_time AS updated_at
  FROM application.transition_sql_generation_guide_version(
       %s::UUID,
       %s::UUID,
       %s::VARCHAR,
       %s::BIGINT,
       %s::VARCHAR,
       %s::VARCHAR
  ) AS saved
"""


class SqlGenerationGuideNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="sql_generation_guide_not_found",
            message="The requested SQL Generation Guide was not found.",
        )


class SqlGenerationGuideConflictError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="sql_generation_guide_conflict",
            message=(
                "SQL Generation Guide state changed; inspect the current state before retrying."
            ),
        )


class SqlGenerationGuideDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class SqlGenerationGuideService(Protocol):
    async def list_guides(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        page_size: int,
        cursor: str | None,
    ) -> SqlGenerationGuidePage: ...

    async def read_guide(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        history_page_size: int,
        history_cursor: str | None,
    ) -> SqlGenerationGuideDetail: ...

    async def save_draft(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        body: SaveSqlGenerationGuideDraftRequest,
    ) -> SqlGenerationGuideVersionState: ...

    async def publish_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        sql_generation_guide_version_id: int,
    ) -> SqlGenerationGuideVersionState: ...

    async def retire_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        sql_generation_guide_version_id: int,
    ) -> SqlGenerationGuideVersionState: ...


class DatabaseSqlGenerationGuideService:
    def __init__(
        self,
        *,
        database: SqlGenerationGuideDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_guides(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        page_size: int,
        cursor: str | None,
    ) -> SqlGenerationGuidePage:
        collection = f"web_sql_generation_guides:{tenant_id}:{page_size}"
        offset = self._cursors.decode(cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            rows = await transaction.fetch_all(
                _GUIDE_LIST_SQL,
                (page_size + 1, offset),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return SqlGenerationGuidePage(
            tenant_id=tenant_id,
            items=tuple(SqlGenerationGuideSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_guide(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        history_page_size: int,
        history_cursor: str | None,
    ) -> SqlGenerationGuideDetail:
        collection = ":".join(
            (
                "web_sql_generation_guide_history",
                str(tenant_id),
                str(sql_generation_guide_id),
                str(history_page_size),
            )
        )
        offset = self._cursors.decode(history_cursor, collection=collection)
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            guide_row = await transaction.fetch_one(
                _GUIDE_DETAIL_SQL,
                (sql_generation_guide_id,),
            )
            if guide_row is None:
                raise SqlGenerationGuideNotFoundError()
            version_rows = await transaction.fetch_all(
                _GUIDE_VERSIONS_SQL,
                (sql_generation_guide_id, history_page_size + 1, offset),
            )

        next_cursor = None
        if len(version_rows) > history_page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + history_page_size,
            )
        return SqlGenerationGuideDetail(
            tenant_id=tenant_id,
            guide=SqlGenerationGuideSummary.model_validate(guide_row),
            versions=tuple(
                SqlGenerationGuideVersionDetail.model_validate(row)
                for row in version_rows[:history_page_size]
            ),
            history_next_cursor=next_cursor,
        )

    async def save_draft(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        body: SaveSqlGenerationGuideDraftRequest,
    ) -> SqlGenerationGuideVersionState:
        identity = _identity_arguments(principal)
        async with self._write_transaction() as transaction:
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            if not authorization.principal.is_super_admin:
                raise AuthorizationDeniedError()
            guide_row = await transaction.fetch_one(
                _GUIDE_MUTATION_BINDING_SQL,
                (sql_generation_guide_id,),
            )
            if guide_row is None:
                raise SqlGenerationGuideNotFoundError()
            row = await transaction.fetch_one(
                _SAVE_GUIDE_DRAFT_SQL,
                (
                    *identity,
                    sql_generation_guide_id,
                    body.expected_sql_generation_guide_version_id,
                    body.sql_generation_guide_content,
                    body.expected_updated_at,
                ),
            )
        if row is None:
            raise InvalidRequestError("The SQL Generation Guide draft could not be saved.")
        return SqlGenerationGuideVersionState.model_validate(row)

    async def publish_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        sql_generation_guide_version_id: int,
    ) -> SqlGenerationGuideVersionState:
        return await self._transition_version(
            principal,
            tenant_id=tenant_id,
            sql_generation_guide_id=sql_generation_guide_id,
            sql_generation_guide_version_id=sql_generation_guide_version_id,
            expected_status="draft",
            target_status="published",
        )

    async def retire_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        sql_generation_guide_version_id: int,
    ) -> SqlGenerationGuideVersionState:
        return await self._transition_version(
            principal,
            tenant_id=tenant_id,
            sql_generation_guide_id=sql_generation_guide_id,
            sql_generation_guide_version_id=sql_generation_guide_version_id,
            expected_status="published",
            target_status="retired",
        )

    async def _transition_version(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        sql_generation_guide_id: int,
        sql_generation_guide_version_id: int,
        expected_status: Literal["draft", "published"],
        target_status: Literal["published", "retired"],
    ) -> SqlGenerationGuideVersionState:
        identity = _identity_arguments(principal)
        async with self._write_transaction() as transaction:
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            if not authorization.principal.is_super_admin:
                raise AuthorizationDeniedError()
            version_row = await transaction.fetch_one(
                _GUIDE_VERSION_MUTATION_BINDING_SQL,
                (sql_generation_guide_version_id, sql_generation_guide_id),
            )
            if version_row is None:
                raise SqlGenerationGuideNotFoundError()
            row = await transaction.fetch_one(
                _TRANSITION_GUIDE_VERSION_SQL,
                (
                    *identity,
                    sql_generation_guide_version_id,
                    expected_status,
                    target_status,
                ),
            )
        if row is None:
            raise InvalidRequestError("The SQL Generation Guide version could not be changed.")
        return SqlGenerationGuideVersionState.model_validate(row)

    @asynccontextmanager
    async def _write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        try:
            async with self._database.write_transaction() as transaction:
                yield transaction
        except DependencyUnavailableError as error:
            _raise_database_error(error)


def _identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    if principal.actor_kind is ActorKind.HUMAN:
        expected_type = "user"
    elif principal.actor_kind is ActorKind.WORKLOAD:
        expected_type = "service_principal"
    else:
        raise AuthorizationDeniedError()
    return principal.entra_tenant_id, principal.entra_object_id, expected_type


def _raise_database_error(error: DependencyUnavailableError) -> Never:
    cause = error.__cause__
    diagnostic = getattr(cause, "diag", None)
    message = getattr(diagnostic, "message_primary", None)
    if not isinstance(message, str):
        raise error
    if "requires Super Admin" in message or " denied:" in message:
        raise AuthorizationDeniedError() from error
    if "unavailable" in message:
        raise SqlGenerationGuideNotFoundError() from error
    if (
        "stale_sql_generation_guide" in message
        or "draft already exists" in message
        or "draft does not exist" in message
        or "version status" in message
    ):
        raise SqlGenerationGuideConflictError() from error
    if "content is invalid" in message or "transition is invalid" in message:
        raise InvalidRequestError() from error
    raise error
