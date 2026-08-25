from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.output_templates import (
    DatabaseOutputTemplateService,
    OutputTemplateDatabase,
    OutputTemplateDetail,
    OutputTemplateField,
    OutputTemplateNotFoundError,
    OutputTemplatePage,
    OutputTemplateService,
    OutputTemplateSummary,
    create_output_templates_router,
)


PRINCIPAL = RequestPrincipal(
    actor_kind=ActorKind.HUMAN,
    entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
    entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
)


def _authorization_row() -> dict[str, Any]:
    return {
        "principal_id": 41,
        "principal_display_name": "Template Reader",
        "is_super_admin": False,
        "effective_role": "viewer",
        "authorized": True,
        "denial_code": None,
        "lock_owner_display_name": None,
        "lock_expires_time": None,
    }


def _template_row(template_id: int, code: str) -> dict[str, Any]:
    return {
        "output_template_id": template_id,
        "output_template_code": code,
        "output_template_name": code.replace("_", " ").title(),
        "output_template_description": "Structured Mapping output.",
        "output_template_target_type": "mapping_object",
        "output_template_schema_digest": "a" * 64,
        "output_template_schema_digest_is_valid": True,
        "is_active": True,
        "field_count": 2,
    }


class OutputTemplateListTransaction:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append("authorize")
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
        return _authorization_row()

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append("list")
        assert "FROM application.output_template AS template" in query
        assert "application.output_template_field" in query
        assert "output_template_field_example AS" not in query
        target_type, repeated_target_type, active, repeated_active, limit, offset = (
            parameters
        )
        assert target_type == repeated_target_type == "mapping_object"
        assert active is repeated_active is True
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            _template_row(101, "standard_object"),
            _template_row(102, "strict_object"),
        ]
        return rows[offset : offset + limit]


class OutputTemplateListDatabase:
    def __init__(self) -> None:
        self.transaction = OutputTemplateListTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[OutputTemplateListTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_output_template_list_is_authorized_filtered_safe_and_signed_page_bounded() -> (
    None
):
    database = OutputTemplateListDatabase()
    service = DatabaseOutputTemplateService(
        database=cast(OutputTemplateDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    first = await service.list_templates(
        PRINCIPAL,
        tenant_id=7,
        target_type="mapping_object",
        active=True,
        page_size=1,
        cursor=None,
    )
    second = await service.list_templates(
        PRINCIPAL,
        tenant_id=7,
        target_type="mapping_object",
        active=True,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.output_template_code for item in first.items] == ["standard_object"]
    assert [item.output_template_code for item in second.items] == ["strict_object"]
    assert second.next_cursor is None
    assert database.transaction.calls == ["authorize", "list", "authorize", "list"]
    assert database.transaction.offsets == [0, 1]
    serialized = first.model_dump_json()
    assert "output_template_field_example" not in serialized
    assert "prompt" not in serialized
    assert "provider" not in serialized
    assert "secret" not in serialized

    with pytest.raises(InvalidRequestError):
        await service.list_templates(
            PRINCIPAL,
            tenant_id=7,
            target_type="mapping_attribute",
            active=True,
            page_size=1,
            cursor=first.next_cursor,
        )


class OutputTemplateDetailTransaction:
    def __init__(self, *, found: bool = True) -> None:
        self.calls: list[str] = []
        self.found = found

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize")
            assert parameters[-1] == 7
            return _authorization_row()
        self.calls.append("template")
        assert "FROM application.output_template AS template" in query
        assert parameters == (101,)
        if not self.found:
            return None
        return _template_row(101, "standard_object")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append("fields")
        assert "FROM application.output_template_field AS field" in query
        assert "output_template_field_example" not in query
        assert parameters == (101,)
        return [
            {
                "output_template_field_name": "source_objects",
                "output_template_field_description": "Governed source object names.",
                "output_template_field_data_type": "array",
                "output_template_field_array_item_type": "string",
                "output_template_field_is_required": True,
                "output_template_field_order": 2,
            },
            {
                "output_template_field_name": "filter_criteria",
                "output_template_field_description": "Optional source filter.",
                "output_template_field_data_type": "string",
                "output_template_field_array_item_type": None,
                "output_template_field_is_required": False,
                "output_template_field_order": 10,
            },
        ]


class OutputTemplateDetailDatabase:
    def __init__(self, *, found: bool = True) -> None:
        self.transaction = OutputTemplateDetailTransaction(found=found)

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[OutputTemplateDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_output_template_detail_returns_only_ordered_typed_fields() -> None:
    database = OutputTemplateDetailDatabase()
    service = DatabaseOutputTemplateService(
        database=cast(OutputTemplateDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    detail = await service.read_template(
        PRINCIPAL,
        tenant_id=7,
        output_template_id=101,
    )

    assert detail.template.output_template_code == "standard_object"
    assert [field.output_template_field_name for field in detail.fields] == [
        "source_objects",
        "filter_criteria",
    ]
    assert detail.fields[0].output_template_field_array_item_type == "string"
    assert detail.fields[1].output_template_field_array_item_type is None
    assert database.transaction.calls == ["authorize", "template", "fields"]
    serialized = detail.model_dump_json()
    assert "output_template_field_example" not in serialized
    assert "created_by" not in serialized
    assert "updated_by" not in serialized


@pytest.mark.asyncio
async def test_missing_output_template_stops_after_authorized_lookup() -> None:
    database = OutputTemplateDetailDatabase(found=False)
    service = DatabaseOutputTemplateService(
        database=cast(OutputTemplateDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    with pytest.raises(OutputTemplateNotFoundError):
        await service.read_template(
            PRINCIPAL,
            tenant_id=7,
            output_template_id=101,
        )

    assert database.transaction.calls == ["authorize", "template"]


class OutputTemplateRouterService:
    def __init__(self) -> None:
        self.list_filter: tuple[str | None, bool | None] | None = None

    async def list_templates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        target_type: str | None,
        active: bool | None,
        page_size: int,
        cursor: str | None,
    ) -> OutputTemplatePage:
        del principal, cursor
        assert tenant_id == 7
        assert page_size == 25
        self.list_filter = (target_type, active)
        return OutputTemplatePage(
            tenant_id=tenant_id,
            items=(
                OutputTemplateSummary.model_validate(
                    _template_row(101, "standard_object")
                ),
            ),
            next_cursor=None,
        )

    async def read_template(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        output_template_id: int,
    ) -> OutputTemplateDetail:
        del principal
        assert tenant_id == 7
        assert output_template_id == 101
        return OutputTemplateDetail(
            tenant_id=tenant_id,
            template=OutputTemplateSummary.model_validate(
                _template_row(101, "standard_object")
            ),
            fields=(
                OutputTemplateField(
                    output_template_field_name="transformation_logic",
                    output_template_field_description="Governed transformation logic.",
                    output_template_field_data_type="string",
                    output_template_field_array_item_type=None,
                    output_template_field_is_required=True,
                    output_template_field_order=1,
                ),
                OutputTemplateField(
                    output_template_field_name="source_objects",
                    output_template_field_description="Governed source objects.",
                    output_template_field_data_type="array",
                    output_template_field_array_item_type="string",
                    output_template_field_is_required=True,
                    output_template_field_order=2,
                ),
            ),
        )


def test_output_template_router_is_bounded_read_only_and_filter_validated() -> None:
    service = OutputTemplateRouterService()
    router = create_output_templates_router(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=PRINCIPAL.entra_tenant_id,
            local_principal_object_id=PRINCIPAL.entra_object_id,
        ),
        service=cast(OutputTemplateService, service),
    )
    api_routes = [route for route in router.routes if isinstance(route, APIRoute)]
    route_methods: set[tuple[str, str]] = set()
    for route in api_routes:
        assert route.methods is not None
        route_methods.update((route.path, method) for method in route.methods)
    base = "/api/v1/tenants/{tenant_id}/output-templates"
    assert route_methods == {
        (base, "GET"),
        (f"{base}/{{output_template_id}}", "GET"),
    }

    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        listed = client.get(
            "/api/v1/tenants/7/output-templates",
            params={
                "target_type": "mapping_object",
                "active": "true",
                "page_size": 25,
            },
        )
        detailed = client.get("/api/v1/tenants/7/output-templates/101")
        invalid = client.get(
            "/api/v1/tenants/7/output-templates",
            params={"target_type": "conceptual_object"},
        )

    assert listed.status_code == 200
    assert service.list_filter == ("mapping_object", True)
    assert detailed.status_code == 200
    assert detailed.json()["fields"][0]["output_template_field_order"] == 1
    assert invalid.status_code == 422
