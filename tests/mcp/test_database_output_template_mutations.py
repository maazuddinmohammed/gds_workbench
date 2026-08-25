from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import psycopg
import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres


@dataclass(frozen=True, slots=True)
class PrincipalIdentity:
    entra_tenant_id: UUID
    entra_object_id: UUID
    principal_id: int


CREATE_OUTPUT_TEMPLATE_SQL = """
    SELECT *
      FROM application.create_output_template(
          %s::UUID,
          %s::UUID,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::JSONB
      )
"""

UPDATE_OUTPUT_TEMPLATE_SQL = """
    SELECT *
      FROM application.update_output_template(
          %s::UUID,
          %s::UUID,
          %s::VARCHAR,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::BOOLEAN,
          %s::TIMESTAMPTZ
      )
"""


def _field(
    *,
    name: str,
    description: str,
    data_type: str,
    order: int,
    array_item_type: str | None = None,
    example: object | None = None,
    required: bool = True,
) -> dict[str, object]:
    field: dict[str, object] = {
        "output_template_field_name": name,
        "output_template_field_description": description,
        "output_template_field_data_type": data_type,
        "output_template_field_is_required": required,
        "output_template_field_order": order,
    }
    if array_item_type is not None:
        field["output_template_field_array_item_type"] = array_item_type
    if example is not None:
        field["output_template_field_example"] = example
    return field


def _valid_string_field(
    *,
    name: str = "mapping_summary",
    order: int = 10,
) -> dict[str, object]:
    return _field(
        name=name,
        description="Mapping summary.",
        data_type="string",
        order=order,
    )


def test_create_output_template_is_atomic_canonical_and_idempotent(
    postgres_database: DisposablePostgres,
) -> None:
    identity = _seed_identity(
        postgres_database,
        is_super_admin=True,
        label="template_create",
    )
    code = f"mapping_object_{uuid4().hex}"
    fields = [
        _field(
            name="business_keys",
            description="Ordered business keys.",
            data_type="array",
            array_item_type="string",
            example=["customer_id"],
            required=True,
            order=20,
        ),
        _field(
            name="target_grain",
            description="Target row grain.",
            data_type="string",
            example="one row per customer",
            order=10,
        ),
    ]

    with postgres_database.connect_owner() as connection:
        created = _create_template(
            connection,
            identity=identity,
            code=code,
            name="Standard Mapping Object",
            description="Normalized Mapping Object output.",
            target_type="mapping_object",
            fields=fields,
        )

    with postgres_database.connect_owner() as connection:
        replayed = _create_template(
            connection,
            identity=identity,
            code=code,
            name="Standard Mapping Object",
            description="Normalized Mapping Object output.",
            target_type="mapping_object",
            fields=list(reversed(fields)),
        )
        stored_fields = connection.execute(
            """
            SELECT output_template_field_name,
                   output_template_field_description,
                   output_template_field_data_type,
                   output_template_field_array_item_type,
                   output_template_field_example,
                   output_template_field_is_required,
                   output_template_field_order
              FROM application.output_template_field
             WHERE output_template_id = %s
             ORDER BY output_template_field_order
            """,
            (created["output_template_id"],),
        ).fetchall()

    assert replayed == created
    assert created["created_by_principal_id"] == identity.principal_id
    assert created["updated_by_principal_id"] == identity.principal_id
    assert len(created["output_template_schema_digest"]) == 64
    assert set(created["output_template_schema_digest"]) <= set("0123456789abcdef")
    assert stored_fields == [
        {
            "output_template_field_name": "target_grain",
            "output_template_field_description": "Target row grain.",
            "output_template_field_data_type": "string",
            "output_template_field_array_item_type": None,
            "output_template_field_example": "one row per customer",
            "output_template_field_is_required": True,
            "output_template_field_order": 10,
        },
        {
            "output_template_field_name": "business_keys",
            "output_template_field_description": "Ordered business keys.",
            "output_template_field_data_type": "array",
            "output_template_field_array_item_type": "string",
            "output_template_field_example": ["customer_id"],
            "output_template_field_is_required": True,
            "output_template_field_order": 20,
        },
    ]

    with pytest.raises(psycopg.Error, match="idempot|conflict"):
        with postgres_database.connect_owner() as connection:
            _create_template(
                connection,
                identity=identity,
                code=code,
                name="Conflicting Template Name",
                description="Normalized Mapping Object output.",
                target_type="mapping_object",
                fields=fields,
            )

    conflicting_fields = [dict(field) for field in fields]
    conflicting_fields[0]["output_template_field_description"] = "Changed schema."
    with pytest.raises(psycopg.Error, match="idempot|conflict"):
        with postgres_database.connect_owner() as connection:
            _create_template(
                connection,
                identity=identity,
                code=code,
                name="Standard Mapping Object",
                description="Normalized Mapping Object output.",
                target_type="mapping_object",
                fields=conflicting_fields,
            )

    with postgres_database.connect_owner() as connection:
        count = connection.execute(
            """
            SELECT count(*) AS count
              FROM application.output_template
             WHERE lower(output_template_code) = lower(%s)
            """,
            (code,),
        ).fetchone()
    assert count == {"count": 1}


def test_concurrent_exact_output_template_create_is_idempotent(
    postgres_database: DisposablePostgres,
) -> None:
    identity = _seed_identity(
        postgres_database,
        is_super_admin=True,
        label="template_concurrent",
    )
    code = f"concurrent_template_{uuid4().hex}"
    fields = [_valid_string_field()]

    with (
        postgres_database.connect_owner() as first_connection,
        postgres_database.connect_owner() as second_connection,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        first_template = _create_template(
            first_connection,
            identity=identity,
            code=code,
            name="Concurrent Output Template",
            description=None,
            target_type="mapping_object",
            fields=fields,
        )
        second_future = executor.submit(
            _create_template,
            second_connection,
            identity=identity,
            code=code,
            name="Concurrent Output Template",
            description=None,
            target_type="mapping_object",
            fields=fields,
        )
        try:
            _wait_for_lock_wait(
                postgres_database,
                second_connection.info.backend_pid,
            )
        finally:
            first_connection.commit()
        second_template = second_future.result(timeout=5)

    assert second_template["output_template_id"] == first_template["output_template_id"]


def test_create_output_template_derives_a_super_admin_actor(
    postgres_database: DisposablePostgres,
) -> None:
    ordinary_identity = _seed_identity(
        postgres_database,
        is_super_admin=False,
        label="template_ordinary",
    )
    code = f"ordinary_template_{uuid4().hex}"

    with pytest.raises(psycopg.Error, match="authoriz|Super Admin"):
        with postgres_database.connect_owner() as connection:
            _create_template(
                connection,
                identity=ordinary_identity,
                code=code,
                name="Unauthorized Template",
                description=None,
                target_type="mapping_object",
                fields=[_valid_string_field()],
            )

    with pytest.raises(psycopg.Error, match="identity|authoriz"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                CREATE_OUTPUT_TEMPLATE_SQL,
                (
                    ordinary_identity.entra_tenant_id,
                    ordinary_identity.entra_object_id,
                    "service_principal",
                    code,
                    "Spoofed Template",
                    None,
                    "mapping_object",
                    json.dumps([_valid_string_field()]),
                ),
            )

    with postgres_database.connect_owner() as connection:
        count = connection.execute(
            """
            SELECT count(*) AS count
              FROM application.output_template
             WHERE lower(output_template_code) = lower(%s)
            """,
            (code,),
        ).fetchone()
    assert count == {"count": 0}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            [
                _valid_string_field(name="duplicate_name", order=10),
                _valid_string_field(name="duplicate_name", order=20),
            ],
            "duplicate",
        ),
        (
            [
                _valid_string_field(name="first_field", order=10),
                _valid_string_field(name="second_field", order=10),
            ],
            "duplicate",
        ),
        ([_valid_string_field(name="schema_version")], "reserved"),
        ([_valid_string_field(name="transformation_kind")], "reserved"),
        (
            [
                _field(
                    name="invalid_type",
                    description="Unsupported type.",
                    data_type="date",
                    order=10,
                )
            ],
            "data type",
        ),
        (
            [
                _field(
                    name="array_without_item_type",
                    description="Array item type is required.",
                    data_type="array",
                    order=10,
                )
            ],
            "array",
        ),
        (
            [
                _field(
                    name="scalar_with_item_type",
                    description="Scalar cannot declare an array item type.",
                    data_type="string",
                    array_item_type="string",
                    order=10,
                )
            ],
            "array",
        ),
    ],
    ids=(
        "duplicate-name",
        "duplicate-order",
        "reserved-schema-version",
        "reserved-transformation-kind",
        "unsupported-data-type",
        "array-item-type-required",
        "array-item-type-only-for-arrays",
    ),
)
def test_create_output_template_rejects_invalid_field_schemas_atomically(
    postgres_database: DisposablePostgres,
    fields: list[dict[str, object]],
    message: str,
) -> None:
    identity = _seed_identity(
        postgres_database,
        is_super_admin=True,
        label="template_invalid",
    )
    code = f"invalid_template_{uuid4().hex}"

    with pytest.raises(psycopg.Error) as captured:
        with postgres_database.connect_owner() as connection:
            _create_template(
                connection,
                identity=identity,
                code=code,
                name="Invalid Template",
                description=None,
                target_type="mapping_object",
                fields=fields,
            )
    assert message.lower() in str(captured.value).lower()

    with postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT count(*) AS template_count,
                   count(field.output_template_field_id) AS field_count
              FROM application.output_template AS template
              LEFT JOIN application.output_template_field AS field
                ON field.output_template_id = template.output_template_id
             WHERE lower(template.output_template_code) = lower(%s)
            """,
            (code,),
        ).fetchone()
    assert stored == {"template_count": 0, "field_count": 0}


def test_update_output_template_changes_only_metadata_with_an_optimistic_fence(
    postgres_database: DisposablePostgres,
) -> None:
    creator = _seed_identity(
        postgres_database,
        is_super_admin=True,
        label="template_creator",
    )
    updater = _seed_identity(
        postgres_database,
        is_super_admin=True,
        label="template_updater",
    )
    code = f"updatable_template_{uuid4().hex}"

    with postgres_database.connect_owner() as connection:
        created = _create_template(
            connection,
            identity=creator,
            code=code,
            name="Original Template",
            description="Original metadata.",
            target_type="mapping_attribute",
            fields=[_valid_string_field()],
        )

    with postgres_database.connect_owner() as connection:
        updated = connection.execute(
            UPDATE_OUTPUT_TEMPLATE_SQL,
            (
                updater.entra_tenant_id,
                updater.entra_object_id,
                "user",
                created["output_template_id"],
                "Renamed Template",
                "Updated metadata only.",
                False,
                created["updated_time"],
            ),
        ).fetchone()
        fields_after_update = connection.execute(
            """
            SELECT output_template_field_name,
                   output_template_field_description,
                   output_template_field_data_type,
                   output_template_field_array_item_type,
                   output_template_field_example,
                   output_template_field_is_required,
                   output_template_field_order
              FROM application.output_template_field
             WHERE output_template_id = %s
             ORDER BY output_template_field_order
            """,
            (created["output_template_id"],),
        ).fetchall()

    assert updated is not None
    assert updated["output_template_name"] == "Renamed Template"
    assert updated["output_template_description"] == "Updated metadata only."
    assert updated["is_active"] is False
    assert updated["created_by_principal_id"] == creator.principal_id
    assert updated["updated_by_principal_id"] == updater.principal_id
    assert (
        updated["output_template_schema_digest"]
        == created["output_template_schema_digest"]
    )
    assert updated["updated_time"] > created["updated_time"]
    assert fields_after_update == [
        {
            "output_template_field_name": "mapping_summary",
            "output_template_field_description": "Mapping summary.",
            "output_template_field_data_type": "string",
            "output_template_field_array_item_type": None,
            "output_template_field_example": None,
            "output_template_field_is_required": True,
            "output_template_field_order": 10,
        }
    ]

    with pytest.raises(psycopg.Error, match="stale|conflict"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                UPDATE_OUTPUT_TEMPLATE_SQL,
                (
                    updater.entra_tenant_id,
                    updater.entra_object_id,
                    "user",
                    created["output_template_id"],
                    "Stale Rename",
                    None,
                    True,
                    created["updated_time"],
                ),
            )


def test_output_template_schema_and_fields_remain_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    identity = _seed_identity(
        postgres_database,
        is_super_admin=True,
        label="template_immutable",
    )
    with postgres_database.connect_owner() as connection:
        template = _create_template(
            connection,
            identity=identity,
            code=f"immutable_template_{uuid4().hex}",
            name="Immutable Template",
            description=None,
            target_type="mapping_object",
            fields=[_valid_string_field()],
        )

    with pytest.raises(psycopg.Error, match="schema is immutable"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.output_template
                   SET output_template_schema_digest = repeat('f', 64)
                 WHERE output_template_id = %s
                """,
                (template["output_template_id"],),
            )

    with pytest.raises(
        psycopg.Error,
        match="identity column|schema is immutable",
    ):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.output_template
                   SET output_template_id = output_template_id + 1000000000
                 WHERE output_template_id = %s
                """,
                (template["output_template_id"],),
            )

    with pytest.raises(psycopg.Error, match="fields are immutable"):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE application.output_template_field
                   SET output_template_field_description = 'Changed directly.'
                 WHERE output_template_id = %s
                """,
                (template["output_template_id"],),
            )


def test_output_template_mutations_are_web_only_security_definer_functions(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        functions = connection.execute(
            """
            SELECT procedure.proname AS function_name,
                   procedure.prosecdef AS is_security_definer,
                   procedure.proconfig @>
                       ARRAY['search_path=pg_catalog']::TEXT[] AS fixed_search_path,
                   procedure.proretset AS returns_set,
                   procedure.prorettype =
                       'application.output_template'::REGTYPE AS returns_template,
                   has_function_privilege(
                       'gds_web_write', procedure.oid, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', procedure.oid, 'EXECUTE'
                   ) AS mcp_can_execute,
                   NOT EXISTS (
                       SELECT 1
                         FROM aclexplode(
                                  coalesce(
                                      procedure.proacl,
                                      acldefault('f', procedure.proowner)
                                  )
                              ) AS acl
                        WHERE acl.grantee = 0
                          AND acl.privilege_type = 'EXECUTE'
                   ) AS public_cannot_execute
              FROM pg_catalog.pg_proc AS procedure
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'application'
               AND procedure.proname IN (
                   'create_output_template',
                   'update_output_template'
               )
             ORDER BY procedure.proname
            """
        ).fetchall()
        table_privileges = connection.execute(
            """
            SELECT table_name,
                   has_table_privilege(
                       'gds_web_write',
                       'application.' || quote_ident(table_name),
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate,
                   has_table_privilege(
                       'gds_app_write',
                       'application.' || quote_ident(table_name),
                       'SELECT,INSERT,UPDATE,DELETE'
                   ) AS mcp_can_access
              FROM unnest(
                       ARRAY['output_template', 'output_template_field']
                   ) AS output_table(table_name)
             ORDER BY table_name
            """
        ).fetchall()

    assert functions == [
        {
            "function_name": "create_output_template",
            "is_security_definer": True,
            "fixed_search_path": True,
            "returns_set": True,
            "returns_template": True,
            "web_can_execute": True,
            "mcp_can_execute": False,
            "public_cannot_execute": True,
        },
        {
            "function_name": "update_output_template",
            "is_security_definer": True,
            "fixed_search_path": True,
            "returns_set": True,
            "returns_template": True,
            "web_can_execute": True,
            "mcp_can_execute": False,
            "public_cannot_execute": True,
        },
    ]
    assert table_privileges == [
        {
            "table_name": "output_template",
            "web_can_mutate": False,
            "mcp_can_access": False,
        },
        {
            "table_name": "output_template_field",
            "web_can_mutate": False,
            "mcp_can_access": False,
        },
    ]


def _seed_identity(
    postgres_database: DisposablePostgres,
    *,
    is_super_admin: bool,
    label: str,
) -> PrincipalIdentity:
    suffix = uuid4().hex
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email,
                is_super_admin
            ) VALUES ('user', %s, %s, %s)
            RETURNING principal_id
            """,
            (
                f"{label} {suffix}",
                f"{label}_{suffix}@example.test",
                is_super_admin,
            ),
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal["principal_id"], entra_tenant_id, entra_object_id),
        )
    return PrincipalIdentity(
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        principal_id=principal["principal_id"],
    )


def _wait_for_lock_wait(
    postgres_database: DisposablePostgres,
    backend_process_id: int,
) -> None:
    deadline = time.monotonic() + 5
    with postgres_database.connect_owner() as observer:
        while time.monotonic() < deadline:
            activity = observer.execute(
                """
                SELECT wait_event_type
                  FROM pg_catalog.pg_stat_activity
                 WHERE pid = %s
                """,
                (backend_process_id,),
            ).fetchone()
            if activity and activity["wait_event_type"] == "Lock":
                return
            time.sleep(0.02)
    pytest.fail("concurrent Output Template request did not reach a lock wait")


def _create_template(
    connection: psycopg.Connection[Any],
    *,
    identity: PrincipalIdentity,
    code: str,
    name: str,
    description: str | None,
    target_type: str,
    fields: list[dict[str, object]],
) -> dict[str, Any]:
    row = connection.execute(
        CREATE_OUTPUT_TEMPLATE_SQL,
        (
            identity.entra_tenant_id,
            identity.entra_object_id,
            "user",
            code,
            name,
            description,
            target_type,
            json.dumps(fields),
        ),
    ).fetchone()
    assert row is not None
    return row
