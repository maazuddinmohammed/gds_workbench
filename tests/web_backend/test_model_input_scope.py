from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, LiteralString, Protocol, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata import ObjectAttribute
from gds_workbench_api.features.model_input_scope import (
    DatabaseModelInputScopeService,
    ModelInputScopeCandidate,
    ModelInputScopeCandidatePage,
    ModelInputScopeDetail,
    ModelInputScopeObject,
    ModelInputScopePage,
    ModelInputScopeService,
)
from gds_workbench_api.main import create_app


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Any: ...

    def web_runtime_dsn(self) -> str: ...


DEMO_METADATA_SEED = (
    Path(__file__).parents[2] / "database" / "seed" / "01_metadata_snapshot_demo.sql"
)


class StaticModelInputScopeService(ModelInputScopeService):
    async def list_candidates(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        zone_code: str | None,
        system_code: str | None,
        source_tenant_code: str | None,
        object_name: str | None,
        page_size: int,
        cursor: str | None,
    ) -> ModelInputScopeCandidatePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (
            tenant_id,
            model_id,
            zone_code,
            system_code,
            source_tenant_code,
            object_name,
            page_size,
            cursor,
        ) == (7, 18, "bronze", "crm", "grdm", "customer_raw", 25, None)
        return ModelInputScopeCandidatePage(
            model_id=18,
            model_revision=4,
            items=(
                ModelInputScopeCandidate(
                    object_id=501,
                    connection_id=21,
                    system_id=31,
                    system_code="CRM",
                    system_name="Customer Relationship Management",
                    source_tenant_id=8,
                    source_tenant_code="GRDM",
                    source_tenant_name="Global Reference Data",
                    object_schema="bronze_crm",
                    object_name="customer_raw",
                    zone_code="bronze",
                    batch_attribute_name="batch_id",
                    attribute_count=12,
                    is_in_active_scope=True,
                ),
            ),
            next_cursor=None,
        )

    async def list_input_scope(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        zone_code: str | None,
        system_code: str | None,
        source_tenant_code: str | None,
        object_name: str | None,
        page_size: int,
        cursor: str | None,
    ) -> ModelInputScopePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (
            tenant_id,
            model_id,
            zone_code,
            system_code,
            source_tenant_code,
            object_name,
            page_size,
            cursor,
        ) == (7, 18, "bronze", "crm", "grdm", None, 25, None)
        return ModelInputScopePage(
            model_id=18,
            model_revision=4,
            items=(
                ModelInputScopeObject(
                    model_input_scope_id=101,
                    object_id=501,
                    connection_id=21,
                    system_id=31,
                    system_code="CRM",
                    system_name="Customer Relationship Management",
                    source_tenant_id=8,
                    source_tenant_code="GRDM",
                    source_tenant_name="Global Reference Data",
                    object_schema="bronze_crm",
                    object_name="customer_raw",
                    zone_code="bronze",
                    batch_attribute_name="batch_id",
                    attribute_count=12,
                    is_model_input_eligible=True,
                    is_dimensional_source_eligible=False,
                    is_logical_mapping_target_eligible=False,
                    is_dimensional_mapping_target_eligible=False,
                    created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_input_scope_object(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        object_id: int,
    ) -> ModelInputScopeDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, object_id) == (7, 18, 501)
        return ModelInputScopeDetail(
            model_input_scope_id=101,
            object_id=501,
            connection_id=21,
            system_id=31,
            system_code="CRM",
            system_name="Customer Relationship Management",
            source_tenant_id=8,
            source_tenant_code="GRDM",
            source_tenant_name="Global Reference Data",
            object_schema="bronze_crm",
            object_name="customer_raw",
            zone_code="bronze",
            batch_attribute_name="batch_id",
            attribute_count=1,
            is_model_input_eligible=True,
            is_dimensional_source_eligible=False,
            is_logical_mapping_target_eligible=False,
            is_dimensional_mapping_target_eligible=False,
            created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            attributes=(
                ObjectAttribute(
                    attribute_id=601,
                    attribute_name="customer_id",
                    attribute_ordinal_position=1,
                    attribute_description="Customer identifier",
                    attribute_data_type="bigint",
                    attribute_nullability=False,
                    is_surrogate_key=False,
                    is_natural_key=True,
                    is_meta_data=False,
                    is_masking_required=False,
                    is_mapped=False,
                    is_purge=False,
                    is_active=True,
                ),
            ),
        )


def test_model_input_scope_returns_derived_eligibility_with_normalized_filters() -> (
    None
):
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        model_input_scope_service=StaticModelInputScopeService(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/input-scope"
            "?zone=Bronze&system_code=CRM&source_tenant_code=GRDM&page_size=25"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_revision"] == 4
    assert payload["items"][0]["object_name"] == "customer_raw"
    assert payload["items"][0]["source_tenant_code"] == "GRDM"
    assert payload["items"][0]["is_model_input_eligible"] is True
    assert "tenant_id" not in payload["items"][0]


def test_model_input_scope_candidates_are_exact_filtered_and_read_only() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        model_input_scope_service=StaticModelInputScopeService(),
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/input-scope/candidates"
            "?zone=Bronze&system_code=CRM&source_tenant_code=GRDM"
            "&object_name=Customer_Raw&page_size=25"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_revision"] == 4
    assert payload["items"] == [
        {
            "object_id": 501,
            "connection_id": 21,
            "system_id": 31,
            "system_code": "CRM",
            "system_name": "Customer Relationship Management",
            "source_tenant_id": 8,
            "source_tenant_code": "GRDM",
            "source_tenant_name": "Global Reference Data",
            "object_schema": "bronze_crm",
            "object_name": "customer_raw",
            "zone_code": "bronze",
            "batch_attribute_name": "batch_id",
            "attribute_count": 12,
            "is_in_active_scope": True,
        }
    ]
    assert "model_input_scope_id" not in payload["items"][0]


def test_model_input_scope_detail_opens_cross_source_object_through_model_authority() -> (
    None
):
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        model_input_scope_service=StaticModelInputScopeService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18/input-scope/501")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_tenant_id"] == 8
    assert payload["attributes"][0]["attribute_name"] == "customer_id"


class ScopeTransaction:
    def __init__(self) -> None:
        self.candidate_offsets: list[int] = []
        self.offsets: list[int] = []
        self.statements: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.statements.append(query)
        if "eligible_object.object_id = %s" in query:
            assert parameters == (7, 18, 501)
            return {
                "model_input_scope_id": 101,
                "object_id": 501,
                "connection_id": 21,
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "source_tenant_id": 8,
                "source_tenant_code": "GRDM",
                "source_tenant_name": "Global Reference Data",
                "object_schema": "bronze_crm",
                "object_name": "customer_raw",
                "zone_code": "bronze",
                "batch_attribute_name": "batch_id",
                "attribute_count": 1,
                "is_model_input_eligible": True,
                "is_dimensional_source_eligible": False,
                "is_logical_mapping_target_eligible": False,
                "is_dimensional_mapping_target_eligible": False,
                "created_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        if "FROM model.model" in query:
            assert parameters == (7, 18)
            return {"model_revision": 4}
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
        return {
            "principal_id": 41,
            "principal_display_name": "Maaz",
            "is_super_admin": False,
            "effective_role": "tenant_admin",
            "authorized": True,
            "denial_code": None,
            "lock_owner_display_name": None,
            "lock_expires_time": None,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.statements.append(query)
        if "SELECT attribute.attribute_id" in query:
            assert parameters == (501,)
            return [
                {
                    "attribute_id": 601,
                    "attribute_name": "customer_id",
                    "attribute_ordinal_position": 1,
                    "attribute_description": "Customer identifier",
                    "attribute_data_type": "bigint",
                    "attribute_nullability": False,
                    "is_surrogate_key": False,
                    "is_natural_key": True,
                    "is_meta_data": False,
                    "is_masking_required": False,
                    "is_mapped": False,
                    "is_purge": False,
                    "is_active": True,
                }
            ]
        if "is_in_active_scope" in query:
            assert "WITH RECURSIVE requested_tenant AS" in query
            assert "visible_objects AS" in query
            assert "workflow.list_tenant_visible_objects" in query
            assert "connection_value" not in query
            assert parameters[:2] == (7, 18)
            assert parameters[2:10] == (
                "bronze",
                "bronze",
                "crm",
                "crm",
                "grdm",
                "grdm",
                "customer_raw",
                "customer_raw",
            )
            limit, offset = parameters[-2:]
            assert limit == 2
            self.candidate_offsets.append(offset)
            rows = [
                {
                    "object_id": 501,
                    "connection_id": 21,
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                    "source_tenant_id": 8,
                    "source_tenant_code": "GRDM",
                    "source_tenant_name": "Global Reference Data",
                    "object_schema": "bronze_crm",
                    "object_name": "customer_raw",
                    "zone_code": "bronze",
                    "batch_attribute_name": "batch_id",
                    "attribute_count": 12,
                    "is_in_active_scope": True,
                },
                {
                    "object_id": 502,
                    "connection_id": 21,
                    "system_id": 31,
                    "system_code": "CRM",
                    "system_name": "Customer Relationship Management",
                    "source_tenant_id": 8,
                    "source_tenant_code": "GRDM",
                    "source_tenant_name": "Global Reference Data",
                    "object_schema": "bronze_crm_archive",
                    "object_name": "customer_raw",
                    "zone_code": "bronze",
                    "batch_attribute_name": "batch_id",
                    "attribute_count": 14,
                    "is_in_active_scope": False,
                },
            ]
            return rows[offset : offset + limit]
        assert "workflow.list_model_object_eligibility" in query
        assert "source_tenant.tenant_id = eligible_object.object_tenant_id" in query
        assert parameters[:2] == (7, 18)
        assert parameters[2:10] == (
            "bronze",
            "bronze",
            "crm",
            "crm",
            "grdm",
            "grdm",
            None,
            None,
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "model_input_scope_id": 101,
                "object_id": 501,
                "connection_id": 21,
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "source_tenant_id": 8,
                "source_tenant_code": "GRDM",
                "source_tenant_name": "Global Reference Data",
                "object_schema": "bronze_crm",
                "object_name": "customer_raw",
                "zone_code": "bronze",
                "batch_attribute_name": "batch_id",
                "attribute_count": 12,
                "is_model_input_eligible": True,
                "is_dimensional_source_eligible": False,
                "is_logical_mapping_target_eligible": False,
                "is_dimensional_mapping_target_eligible": False,
                "created_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "model_input_scope_id": 102,
                "object_id": 502,
                "connection_id": 21,
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "source_tenant_id": 8,
                "source_tenant_code": "GRDM",
                "source_tenant_name": "Global Reference Data",
                "object_schema": "bronze_crm",
                "object_name": "contact_raw",
                "zone_code": "bronze",
                "batch_attribute_name": "batch_id",
                "attribute_count": 11,
                "is_model_input_eligible": True,
                "is_dimensional_source_eligible": False,
                "is_logical_mapping_target_eligible": False,
                "is_dimensional_mapping_target_eligible": False,
                "created_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
                "updated_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class ScopeDatabase:
    def __init__(self) -> None:
        self.transaction = ScopeTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ScopeTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_scope_is_model_tenant_scoped_and_cursor_bound() -> None:
    database = ScopeDatabase()
    service = DatabaseModelInputScopeService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    first = await service.list_input_scope(
        principal,
        tenant_id=7,
        model_id=18,
        zone_code="bronze",
        system_code="crm",
        source_tenant_code="grdm",
        object_name=None,
        page_size=1,
        cursor=None,
    )
    second = await service.list_input_scope(
        principal,
        tenant_id=7,
        model_id=18,
        zone_code="bronze",
        system_code="crm",
        source_tenant_code="grdm",
        object_name=None,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert first.model_revision == 4
    assert [item.object_name for item in first.items] == ["customer_raw"]
    assert [item.object_name for item in second.items] == ["contact_raw"]
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]


@pytest.mark.asyncio
async def test_database_scope_candidates_use_authorized_visible_closure() -> None:
    database = ScopeDatabase()
    service = DatabaseModelInputScopeService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    first = await service.list_candidates(
        principal,
        tenant_id=7,
        model_id=18,
        zone_code="bronze",
        system_code="crm",
        source_tenant_code="grdm",
        object_name="customer_raw",
        page_size=1,
        cursor=None,
    )
    second = await service.list_candidates(
        principal,
        tenant_id=7,
        model_id=18,
        zone_code="bronze",
        system_code="crm",
        source_tenant_code="grdm",
        object_name="customer_raw",
        page_size=1,
        cursor=first.next_cursor,
    )

    assert first.model_revision == 4
    assert first.items[0].is_in_active_scope is True
    assert second.items[0].is_in_active_scope is False
    assert database.transaction.candidate_offsets == [0, 1]
    assert "security.entra_principal_identity" in database.transaction.statements[0]
    assert "FROM model.model" in database.transaction.statements[1]
    assert "WITH RECURSIVE requested_tenant AS" in database.transaction.statements[2]


@pytest.mark.asyncio
async def test_database_scope_detail_is_bound_to_active_model_input_scope() -> None:
    database = ScopeDatabase()
    service = DatabaseModelInputScopeService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_input_scope_object(
        principal,
        tenant_id=7,
        model_id=18,
        object_id=501,
    )

    assert detail.object_name == "customer_raw"
    assert detail.attributes[0].attribute_name == "customer_id"


@pytest.mark.asyncio
async def test_scope_reads_preserve_visibility_and_support_partial_object_name_search(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    suffix = uuid4().hex[:12]
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    hidden_object_name = f"hidden_customer_{suffix}"
    unassigned_object_name = f"unassigned_customer_{suffix}"
    with web_postgres_database.connect_owner() as connection:
        existing = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        if existing is None:
            connection.execute(
                cast(LiteralString, DEMO_METADATA_SEED.read_text(encoding="utf-8"))
            )
        tenant = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        assert tenant is not None
        tenant_id = tenant["tenant_id"]
        assert isinstance(tenant_id, int) and not isinstance(tenant_id, bool)

        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type, principal_display_name, principal_email
            ) VALUES ('user', %s, %s)
            RETURNING principal_id
            """,
            (f"Scope Candidate Reader {suffix}", f"scope_{suffix}@example.test"),
        ).fetchone()
        assert principal is not None
        principal_id = principal["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id, principal_type, entra_tenant_id, entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id, principal_id, tenant_role, granted_by_principal_id
            ) VALUES (%s, %s, 'viewer', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        target_model = connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id
            """,
            (tenant_id, f"Scope Candidate Model {suffix}"),
        ).fetchone()
        assert target_model is not None
        model_id = target_model["model_id"]
        assert isinstance(model_id, int) and not isinstance(model_id, bool)
        bronze_object = connection.execute(
            """
            SELECT object.object_id
              FROM core.object AS object
             WHERE object.object_schema = 'bronze_demo'
               AND object.object_name = 'customer'
            """
        ).fetchone()
        assert bronze_object is not None
        connection.execute(
            "INSERT INTO model.model_input_scope (model_id, object_id) VALUES (%s, %s)",
            (model_id, bronze_object["object_id"]),
        )

        hidden_tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id, tenant_code, tenant_name,
                tenant_catalog, gds_admin_catalog
            )
            SELECT project_id, %s, %s, %s, %s
              FROM core.project
             WHERE project_code = 'DEMO_PROJECT'
            RETURNING tenant_id
            """,
            (
                f"HIDDEN_SCOPE_{suffix}",
                f"Hidden Scope Tenant {suffix}",
                f"hidden_scope_{suffix}",
                f"hidden_scope_admin_{suffix}",
            ),
        ).fetchone()
        assert hidden_tenant is not None
        hidden_connection = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id
            )
            SELECT %s, system.system_id, %s, %s, connection_type.connection_type_id
              FROM core.system AS system
             CROSS JOIN reference.connection_type AS connection_type
             WHERE system.system_code = 'DEMO_CUSTOMER_SYSTEM'
               AND connection_type.connection_type_code = 'DEMO_POSTGRESQL'
            RETURNING connection_id
            """,
            (
                hidden_tenant["tenant_id"],
                f"HIDDEN_SCOPE_{suffix}",
                f"Hidden Scope Connection {suffix}",
            ),
        ).fetchone()
        assert hidden_connection is not None
        connection.execute(
            """
            INSERT INTO core.object (
                connection_id, source_tenant_id, object_schema, object_name,
                object_type_id, zone_id
            )
            SELECT %s, %s, %s, %s, object_type.object_type_id, zone.zone_id
              FROM reference.object_type AS object_type
             CROSS JOIN reference.zone AS zone
             WHERE object_type.object_type_code = 'TABLE'
               AND zone.zone_code = 'bronze'
            """,
            (
                hidden_connection["connection_id"],
                hidden_tenant["tenant_id"],
                f"hidden_scope_{suffix}",
                hidden_object_name,
            ),
        )
        connection.execute(
            """
            INSERT INTO core.object (
                connection_id, source_tenant_id, object_schema, object_name,
                object_type_id, zone_id
            )
            SELECT connection.connection_id,
                   connection.tenant_id,
                   %s,
                   %s,
                   object_type.object_type_id,
                   zone.zone_id
              FROM core.connection AS connection
             CROSS JOIN reference.object_type AS object_type
             CROSS JOIN reference.zone AS zone
             WHERE connection.connection_code = 'DEMO_GDS'
               AND object_type.object_type_code = 'TABLE'
               AND zone.zone_code = 'bronze'
            """,
            (f"unassigned_scope_{suffix}", unassigned_object_name),
        )

    principal_context = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseModelInputScopeService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    await database.open()
    try:
        candidates = await service.list_candidates(
            principal_context,
            tenant_id=tenant_id,
            model_id=model_id,
            zone_code=None,
            system_code=None,
            source_tenant_code=None,
            object_name=None,
            page_size=200,
            cursor=None,
        )
        exact = await service.list_candidates(
            principal_context,
            tenant_id=tenant_id,
            model_id=model_id,
            zone_code="bronze",
            system_code="demo_customer_system",
            source_tenant_code="demo_tenant",
            object_name="custom",
            page_size=20,
            cursor=None,
        )
        active_scope = await service.list_input_scope(
            principal_context,
            tenant_id=tenant_id,
            model_id=model_id,
            zone_code="bronze",
            system_code="demo_customer_system",
            source_tenant_code="demo_tenant",
            object_name="custom",
            page_size=20,
            cursor=None,
        )
    finally:
        await database.close()

    candidate_keys = {
        (item.object_schema, item.object_name) for item in candidates.items
    }
    assert ("source_demo", "customer") in candidate_keys
    assert ("bronze_demo", "customer") in candidate_keys
    assert ("silver_demo", "customer") not in candidate_keys
    assert ("gold_demo", "dim_customer") not in candidate_keys
    assert hidden_object_name not in {item.object_name for item in candidates.items}
    assert unassigned_object_name not in {item.object_name for item in candidates.items}
    assert len(exact.items) == 1
    assert exact.items[0].object_schema == "bronze_demo"
    assert exact.items[0].source_tenant_code == "DEMO_TENANT"
    assert exact.items[0].is_in_active_scope is True
    assert len(active_scope.items) == 1
    assert active_scope.items[0].object_name == "customer"
