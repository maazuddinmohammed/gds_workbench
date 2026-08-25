from collections.abc import Mapping
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from psycopg import Connection
from psycopg.types.json import Jsonb
from tests.mcp.conftest import DisposablePostgres

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.output_templates import DatabaseOutputTemplateService


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    if row is None:
        raise AssertionError(f"expected database ID field {field}")
    value = row.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID field {field}")
    return value


def _create_template(
    connection: Connection[dict[str, object]],
    *,
    entra_tenant_id: object,
    entra_object_id: object,
    code: str,
    target_type: str,
    fields: list[dict[str, object]],
) -> int:
    return _required_id(
        connection.execute(
            """
            SELECT created.output_template_id
              FROM application.create_output_template(
                   %s::UUID,
                   %s::UUID,
                   'user'::VARCHAR,
                   %s::VARCHAR,
                   %s::VARCHAR,
                   %s::VARCHAR,
                   %s::VARCHAR,
                   %s::JSONB
              ) AS created
            """,
            (
                entra_tenant_id,
                entra_object_id,
                code,
                code.replace("_", " ").title(),
                "Safe structured Mapping output.",
                target_type,
                Jsonb(fields),
            ),
        ).fetchone(),
        "output_template_id",
    )


@pytest.mark.asyncio
async def test_output_template_catalog_round_trips_through_the_web_runtime_role(
    web_postgres_database: DisposablePostgres,
) -> None:
    super_tenant_id = uuid4()
    super_object_id = uuid4()
    viewer_tenant_id = uuid4()
    viewer_object_id = uuid4()
    suffix = uuid4().hex

    with web_postgres_database.connect_owner() as connection:
        project_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"output_template_{suffix}", f"Output Template Project {suffix}"),
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
                    f"OUTPUT_{suffix}",
                    f"Output Template Tenant {suffix}",
                    f"output_catalog_{suffix}",
                    f"output_admin_{suffix}",
                ),
            ).fetchone(),
            "tenant_id",
        )
        super_principal_id = _required_id(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email,
                    is_super_admin
                ) VALUES ('user', %s, %s, TRUE)
                RETURNING principal_id
                """,
                (
                    f"Output Template Admin {suffix}",
                    f"output_admin_{suffix}@example.test",
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
            (super_principal_id, super_tenant_id, super_object_id),
        )
        viewer_principal_id = _required_id(
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
                    f"Output Template Viewer {suffix}",
                    f"output_viewer_{suffix}@example.test",
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
            (viewer_principal_id, viewer_tenant_id, viewer_object_id),
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
            (tenant_id, viewer_principal_id, super_principal_id),
        )

        object_code = f"catalog_object_{suffix}"
        object_template_id = _create_template(
            connection,
            entra_tenant_id=super_tenant_id,
            entra_object_id=super_object_id,
            code=object_code,
            target_type="mapping_object",
            fields=[
                {
                    "output_template_field_name": "transformation_logic",
                    "output_template_field_description": "Transformation logic.",
                    "output_template_field_data_type": "string",
                    "output_template_field_array_item_type": None,
                    "output_template_field_example": {
                        "secret_token": "MUST_NOT_LEAVE_DATABASE"
                    },
                    "output_template_field_is_required": False,
                    "output_template_field_order": 10,
                },
                {
                    "output_template_field_name": "source_objects",
                    "output_template_field_description": "Source object names.",
                    "output_template_field_data_type": "array",
                    "output_template_field_array_item_type": "string",
                    "output_template_field_example": ["crm.customer_raw"],
                    "output_template_field_is_required": True,
                    "output_template_field_order": 2,
                },
            ],
        )
        attribute_code = f"catalog_attribute_{suffix}"
        attribute_template_id = _create_template(
            connection,
            entra_tenant_id=super_tenant_id,
            entra_object_id=super_object_id,
            code=attribute_code,
            target_type="mapping_attribute",
            fields=[
                {
                    "output_template_field_name": "transformation_logic",
                    "output_template_field_description": "Column transformation logic.",
                    "output_template_field_data_type": "string",
                    "output_template_field_array_item_type": None,
                    "output_template_field_example": None,
                    "output_template_field_is_required": True,
                    "output_template_field_order": 1,
                }
            ],
        )
        connection.execute(
            """
            UPDATE application.output_template
               SET is_active = FALSE,
                   updated_by_principal_id = %s,
                   updated_time = clock_timestamp()
             WHERE output_template_id = %s
            """,
            (super_principal_id, attribute_template_id),
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=viewer_tenant_id,
        entra_object_id=viewer_object_id,
    )
    await database.open()
    try:
        service = DatabaseOutputTemplateService(
            database=database,
            authorizer=AuthorizationService(),
            cursor_signing_key=b"development-only-key-32-bytes-long",
        )
        active_objects = await service.list_templates(
            principal,
            tenant_id=tenant_id,
            target_type="mapping_object",
            active=True,
            page_size=200,
            cursor=None,
        )
        inactive_attributes = await service.list_templates(
            principal,
            tenant_id=tenant_id,
            target_type="mapping_attribute",
            active=False,
            page_size=200,
            cursor=None,
        )
        detail = await service.read_template(
            principal,
            tenant_id=tenant_id,
            output_template_id=object_template_id,
        )
    finally:
        await database.close()

    object_summary = next(
        item
        for item in active_objects.items
        if item.output_template_code == object_code
    )
    assert object_summary.output_template_schema_digest_is_valid is True
    assert object_summary.field_count == 2
    assert any(
        item.output_template_code == attribute_code
        for item in inactive_attributes.items
    )
    assert [field.output_template_field_order for field in detail.fields] == [2, 10]
    serialized = detail.model_dump_json()
    assert "MUST_NOT_LEAVE_DATABASE" not in serialized
    assert "output_template_field_example" not in serialized
