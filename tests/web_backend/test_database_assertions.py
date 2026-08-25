from collections.abc import Mapping
from typing import Protocol
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from psycopg import Connection
from psycopg.types.json import Jsonb

from gds_workbench_api.features.assertions import (
    AssertionDocumentFilters,
    AssertionRecordFilters,
    DatabaseAssertionsService,
)
from gds_workbench_api.database import WebPostgresDatabase


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...

    def web_runtime_dsn(self) -> str: ...


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    if row is None or not isinstance(row.get(field), int):
        raise AssertionError(f"expected database ID field {field}")
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID field {field}")
    return value


@pytest.mark.asyncio
async def test_assertion_review_reads_round_trip_through_the_web_role(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    suffix = uuid4().hex
    with web_postgres_database.connect_owner() as connection:
        project_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"assertions_{suffix}", f"Assertions Project {suffix}"),
            ).fetchone(),
            "project_id",
        )
        tenant_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    f"ASSERTIONS_{suffix}",
                    f"Assertions Tenant {suffix}",
                    f"assertions_catalog_{suffix}",
                    f"assertions_admin_{suffix}",
                ),
            ).fetchone(),
            "tenant_id",
        )
        principal_id = _required_id(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email
                ) VALUES ('user', %s, %s)
                RETURNING principal_id
                """,
                (
                    f"Assertions Reviewer {suffix}",
                    f"assertions_{suffix}@example.test",
                ),
            ).fetchone(),
            "principal_id",
        )
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'viewer', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        system_type_id = _required_id(
            connection.execute(
                """
                INSERT INTO reference.system_type (
                    system_type_code,
                    system_type_name
                ) VALUES (%s, %s)
                RETURNING system_type_id
                """,
                (f"assertion_type_{suffix}", f"Assertion Type {suffix}"),
            ).fetchone(),
            "system_type_id",
        )
        system_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.system (
                    system_code,
                    system_name,
                    system_type_id
                ) VALUES (%s, %s, %s)
                RETURNING system_id
                """,
                (f"CRM_{suffix}", f"Customer System {suffix}", system_type_id),
            ).fetchone(),
            "system_id",
        )
        model_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s)
                RETURNING model_id
                """,
                (tenant_id, f"Assertions Review {suffix}"),
            ).fetchone(),
            "model_id",
        )
        other_model_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s)
                RETURNING model_id
                """,
                (tenant_id, f"Other Assertions Review {suffix}"),
            ).fetchone(),
            "model_id",
        )
        connection.execute(
            """
            INSERT INTO model.modeling_assertion_document (
                model_id,
                modeling_assertion_document_name
            ) VALUES (%s, %s)
            """,
            (other_model_id, f"Other model rules {suffix}"),
        )
        document_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.modeling_assertion_document (
                    model_id,
                    tenant_id,
                    system_id,
                    modeling_assertion_document_name,
                    modeling_assertion_file_pattern,
                    modeling_assertion_document_type,
                    modeling_assertion_document_description,
                    modeling_assertion_document_metadata
                ) VALUES (%s, %s, %s, %s, %s, 'business_rules', %s, %s)
                RETURNING modeling_assertion_document_id
                """,
                (
                    model_id,
                    tenant_id,
                    system_id,
                    f"Customer rules {suffix}",
                    "customer-rules-*.xlsx",
                    "Governed Customer rules.",
                    Jsonb({"source_kind": "workbook", "worksheet_count": 3}),
                ),
            ).fetchone(),
            "modeling_assertion_document_id",
        )
        record_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.modeling_assertion_record (
                    model_id,
                    modeling_assertion_document_id,
                    modeling_assertion_record_key,
                    modeling_assertion_record_type,
                    modeling_assertion_text,
                    modeling_assertion_details,
                    modeling_assertion_source_location,
                    modeling_assertion_applicable_layers,
                    modeling_assertion_confidence,
                    modeling_assertion_record_status,
                    modeling_assertion_record_is_locked
                ) VALUES (%s, %s, %s, 'grain_rule', %s, %s, %s,
                          ARRAY['conceptual', 'logical'], 'high',
                          'needs_review', TRUE)
                RETURNING modeling_assertion_record_id
                """,
                (
                    model_id,
                    document_id,
                    f"customer.rule-{suffix}",
                    "A Customer is one governed party.",
                    Jsonb({"subject": "customer", "grain": "governed_party"}),
                    Jsonb({"sheet": "Customer", "row": 12}),
                ),
            ).fetchone(),
            "modeling_assertion_record_id",
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        service = DatabaseAssertionsService(
            database=database,
            authorizer=AuthorizationService(),
            cursor_signing_key=b"development-only-key-32-bytes-long",
        )
        principal = RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
        )

        documents = await service.list_documents(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=AssertionDocumentFilters(
                source_system_code=f"crm_{suffix}",
                active=True,
                name_prefix="customer rules",
            ),
            page_size=25,
            cursor=None,
        )
        records = await service.list_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=AssertionRecordFilters(
                document_id=document_id,
                source_system_id=system_id,
                status="needs_review",
                locked=True,
                applicable_layer="conceptual",
                key_prefix="customer.",
            ),
            page_size=25,
            cursor=None,
        )
        document_detail = await service.read_document(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            modeling_assertion_document_id=document_id,
        )
        record_detail = await service.read_record(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            modeling_assertion_record_id=record_id,
        )
    finally:
        await database.close()

    assert [item.modeling_assertion_document_id for item in documents.items] == [
        document_id
    ]
    assert documents.items[0].workflow_run_id is None
    assert documents.items[0].record_count == 1
    assert documents.items[0].source_system is not None
    assert documents.items[0].source_system.system_id == system_id
    assert [item.modeling_assertion_record_id for item in records.items] == [record_id]
    assert records.items[0].workflow_run_id is None
    assert record_detail.modeling_assertion_details == {
        "subject": "customer",
        "grain": "governed_party",
    }
    assert record_detail.modeling_assertion_source_location == {
        "sheet": "Customer",
        "row": 12,
    }
    assert document_detail.modeling_assertion_document_metadata == {
        "source_kind": "workbook",
        "worksheet_count": 3,
    }
