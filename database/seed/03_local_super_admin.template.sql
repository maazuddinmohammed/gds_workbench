-- Manual local-development seed only. Never run this in production.
-- Replace every __REPLACE_...__ placeholder before execution.

DO $local_super_admin_guard$
DECLARE
    expected_database TEXT := '__REPLACE_WITH_EXPECTED_DATABASE_NAME__';
    entra_tenant_text TEXT := '__REPLACE_WITH_ENTRA_TENANT_ID__';
    local_object_text TEXT := '__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__';
BEGIN
    IF expected_database LIKE '%__REPLACE_%'
       OR entra_tenant_text LIKE '%__REPLACE_%'
       OR local_object_text LIKE '%__REPLACE_%' THEN
        RAISE EXCEPTION 'replace every local Super Admin seed placeholder';
    END IF;

    IF current_database() <> expected_database THEN
        RAISE EXCEPTION 'refusing unexpected database: %', current_database();
    END IF;

    IF entra_tenant_text::UUID = '00000000-0000-0000-0000-000000000000'::UUID
       OR local_object_text::UUID =
          '00000000-0000-0000-0000-000000000000'::UUID THEN
        RAISE EXCEPTION 'local identity UUIDs must be nonzero';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM security.principal
         WHERE lower(btrim(principal_email)) =
               'local.developer@local.invalid'
    ) THEN
        RAISE EXCEPTION 'Local Developer Principal already exists';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM security.entra_principal_identity
         WHERE entra_tenant_id = entra_tenant_text::UUID
           AND entra_object_id = local_object_text::UUID
    ) THEN
        RAISE EXCEPTION 'configured local identity already exists';
    END IF;
END;
$local_super_admin_guard$;

WITH local_principal AS (
    INSERT INTO security.principal (
        principal_type,
        principal_display_name,
        principal_description,
        principal_email,
        is_super_admin
    )
    VALUES (
        'user',
        'Local Developer',
        'Dedicated local-mode Super Admin; never use in production',
        'local.developer@local.invalid',
        TRUE
    )
    RETURNING principal_id, principal_type
)
INSERT INTO security.entra_principal_identity (
    principal_id,
    principal_type,
    entra_tenant_id,
    entra_object_id
)
SELECT principal_id,
       principal_type,
       '__REPLACE_WITH_ENTRA_TENANT_ID__'::UUID,
       '__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__'::UUID
  FROM local_principal;
