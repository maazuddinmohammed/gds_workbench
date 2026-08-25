"""Tenant-authorized read service for globally reusable Output Templates."""

from contextlib import AbstractAsyncContextManager
from typing import LiteralString, Protocol

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
)

from gds_workbench_api.features.output_templates.contracts import (
    OutputTemplateDetail,
    OutputTemplateField,
    OutputTemplatePage,
    OutputTemplateSummary,
    OutputTemplateTargetType,
)

_OUTPUT_TEMPLATE_LIST_SQL: LiteralString = """
SELECT template.output_template_id,
       template.output_template_code,
       template.output_template_name,
       left(template.output_template_description, 2000)
           AS output_template_description,
       template.output_template_target_type,
       template.output_template_schema_digest,
       template.output_template_schema_digest = encode(
           sha256(
               convert_to(
                   jsonb_build_object(
                       'output_template_target_type',
                           template.output_template_target_type,
                       'fields', field_document.digest_items
                   )::TEXT,
                   'UTF8'
               )
           ),
           'hex'
       ) AS output_template_schema_digest_is_valid,
       template.is_active,
       field_document.item_count AS field_count
  FROM application.output_template AS template
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS item_count,
              jsonb_agg(
                  jsonb_build_object(
                      'output_template_field_name',
                          item.output_template_field_name,
                      'output_template_field_description',
                          item.output_template_field_description,
                      'output_template_field_data_type',
                          item.output_template_field_data_type,
                      'output_template_field_array_item_type',
                          item.output_template_field_array_item_type,
                      'output_template_field_example', coalesce(
                          item.output_template_field_example,
                          'null'::JSONB
                      ),
                      'output_template_field_is_required',
                          item.output_template_field_is_required,
                      'output_template_field_order',
                          item.output_template_field_order
                  ) ORDER BY item.output_template_field_order
              ) AS digest_items
         FROM (
             SELECT field.output_template_field_name,
                    field.output_template_field_description,
                    field.output_template_field_data_type,
                    field.output_template_field_array_item_type,
                    field.output_template_field_example,
                    field.output_template_field_is_required,
                    field.output_template_field_order
               FROM application.output_template_field AS field
              WHERE field.output_template_id = template.output_template_id
              ORDER BY field.output_template_field_order
              LIMIT 501
         ) AS item
  ) AS field_document
 WHERE (%s::VARCHAR IS NULL OR template.output_template_target_type = %s)
   AND (%s::BOOLEAN IS NULL OR template.is_active = %s)
   AND field_document.item_count BETWEEN 1 AND 500
 ORDER BY lower(template.output_template_name),
          template.output_template_id
 LIMIT %s OFFSET %s
"""

_OUTPUT_TEMPLATE_DETAIL_SQL: LiteralString = """
SELECT template.output_template_id,
       template.output_template_code,
       template.output_template_name,
       left(template.output_template_description, 2000)
           AS output_template_description,
       template.output_template_target_type,
       template.output_template_schema_digest,
       template.output_template_schema_digest = encode(
           sha256(
               convert_to(
                   jsonb_build_object(
                       'output_template_target_type',
                           template.output_template_target_type,
                       'fields', field_document.digest_items
                   )::TEXT,
                   'UTF8'
               )
           ),
           'hex'
       ) AS output_template_schema_digest_is_valid,
       template.is_active,
       field_document.item_count AS field_count
  FROM application.output_template AS template
 CROSS JOIN LATERAL (
       SELECT count(*)::INTEGER AS item_count,
              jsonb_agg(
                  jsonb_build_object(
                      'output_template_field_name',
                          item.output_template_field_name,
                      'output_template_field_description',
                          item.output_template_field_description,
                      'output_template_field_data_type',
                          item.output_template_field_data_type,
                      'output_template_field_array_item_type',
                          item.output_template_field_array_item_type,
                      'output_template_field_example', coalesce(
                          item.output_template_field_example,
                          'null'::JSONB
                      ),
                      'output_template_field_is_required',
                          item.output_template_field_is_required,
                      'output_template_field_order',
                          item.output_template_field_order
                  ) ORDER BY item.output_template_field_order
              ) AS digest_items
         FROM (
             SELECT field.output_template_field_name,
                    field.output_template_field_description,
                    field.output_template_field_data_type,
                    field.output_template_field_array_item_type,
                    field.output_template_field_example,
                    field.output_template_field_is_required,
                    field.output_template_field_order
               FROM application.output_template_field AS field
              WHERE field.output_template_id = template.output_template_id
              ORDER BY field.output_template_field_order
              LIMIT 501
         ) AS item
  ) AS field_document
 WHERE template.output_template_id = %s
   AND field_document.item_count BETWEEN 1 AND 500
"""

_OUTPUT_TEMPLATE_FIELDS_SQL: LiteralString = """
SELECT field.output_template_field_name,
       left(field.output_template_field_description, 2000)
           AS output_template_field_description,
       field.output_template_field_data_type,
       field.output_template_field_array_item_type,
       field.output_template_field_is_required,
       field.output_template_field_order
  FROM application.output_template_field AS field
 WHERE field.output_template_id = %s
 ORDER BY field.output_template_field_order
 LIMIT 501
"""


class OutputTemplateNotFoundError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="output_template_not_found",
            message="The requested Output Template was not found.",
        )


class OutputTemplateDatabase(Protocol):
    def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[ReadTransaction]: ...


class OutputTemplateService(Protocol):
    async def list_templates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        target_type: OutputTemplateTargetType | None,
        active: bool | None,
        page_size: int,
        cursor: str | None,
    ) -> OutputTemplatePage: ...

    async def read_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        output_template_id: int,
    ) -> OutputTemplateDetail: ...


class DatabaseOutputTemplateService:
    def __init__(
        self,
        *,
        database: OutputTemplateDatabase,
        authorizer: AuthorizationService,
        cursor_signing_key: bytes,
    ) -> None:
        self._database = database
        self._authorizer = authorizer
        self._cursors = CursorCodec(cursor_signing_key)

    async def list_templates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        target_type: OutputTemplateTargetType | None,
        active: bool | None,
        page_size: int,
        cursor: str | None,
    ) -> OutputTemplatePage:
        target_token = target_type or "all"
        active_token = "all" if active is None else str(active).lower()
        collection = ":".join(
            (
                "web_output_templates",
                str(tenant_id),
                target_token,
                active_token,
                str(page_size),
            )
        )
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
                _OUTPUT_TEMPLATE_LIST_SQL,
                (
                    target_type,
                    target_type,
                    active,
                    active,
                    page_size + 1,
                    offset,
                ),
            )

        next_cursor = None
        if len(rows) > page_size:
            next_cursor = self._cursors.encode(
                collection=collection,
                offset=offset + page_size,
            )
        return OutputTemplatePage(
            tenant_id=tenant_id,
            items=tuple(OutputTemplateSummary.model_validate(row) for row in rows[:page_size]),
            next_cursor=next_cursor,
        )

    async def read_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        output_template_id: int,
    ) -> OutputTemplateDetail:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            template_row = await transaction.fetch_one(
                _OUTPUT_TEMPLATE_DETAIL_SQL,
                (output_template_id,),
            )
            if template_row is None:
                raise OutputTemplateNotFoundError()
            field_rows = await transaction.fetch_all(
                _OUTPUT_TEMPLATE_FIELDS_SQL,
                (output_template_id,),
            )

        return OutputTemplateDetail(
            tenant_id=tenant_id,
            template=OutputTemplateSummary.model_validate(template_row),
            fields=tuple(OutputTemplateField.model_validate(row) for row in field_rows),
        )
