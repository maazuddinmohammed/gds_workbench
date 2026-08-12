-- Human Entra identity and Tenant Read access template.
-- Copy this file outside the repository and replace every placeholder.
-- This file contains no password; email is identity metadata, not a credential.

DO $validate_seed_input$
DECLARE
    v_entra_tenant_id TEXT := '__REPLACE_WITH_ENTRA_TENANT_ID__';
    v_entra_object_id TEXT := '__REPLACE_WITH_ENTRA_OBJECT_ID__';
    v_display_name TEXT := '__REPLACE_WITH_DISPLAY_NAME__';
    v_login_email TEXT := '__REPLACE_WITH_LOGIN_EMAIL__';
    v_tenant_code TEXT := '__REPLACE_WITH_TENANT_CODE__';
BEGIN
    IF v_entra_tenant_id LIKE '__REPLACE_WITH_%'
       OR v_entra_object_id LIKE '__REPLACE_WITH_%'
       OR v_display_name LIKE '__REPLACE_WITH_%'
       OR v_login_email LIKE '__REPLACE_WITH_%'
       OR v_tenant_code LIKE '__REPLACE_WITH_%' THEN
        RAISE EXCEPTION 'replace every seed placeholder before execution';
    END IF;

    PERFORM v_entra_tenant_id::UUID;
    PERFORM v_entra_object_id::UUID;

    IF NOT reference.is_nonblank(v_display_name)
       OR NOT reference.is_nonblank(v_login_email)
       OR position('@' IN v_login_email) <= 1 THEN
        RAISE EXCEPTION 'display name or login email is invalid';
    END IF;

    IF (
        SELECT count(*)
          FROM core.tenant AS tenant
         WHERE lower(btrim(tenant.tenant_code)) = lower(btrim(v_tenant_code))
           AND tenant.is_active
    ) <> 1 THEN
        RAISE EXCEPTION 'target Tenant must resolve to one active row';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM security.principal AS principal
         WHERE lower(btrim(principal.principal_email)) = lower(btrim(v_login_email))
    ) THEN
        RAISE EXCEPTION 'a Principal with this email already exists';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM security.entra_principal_identity AS identity_record
         WHERE identity_record.entra_tenant_id = v_entra_tenant_id::UUID
           AND identity_record.entra_object_id = v_entra_object_id::UUID
    ) THEN
        RAISE EXCEPTION 'this Entra identity already exists';
    END IF;
END;
$validate_seed_input$;

WITH seed_input AS (
    SELECT 'cb8ce8f6-afec-44b2-8764-f227c4f8ce08'::UUID AS entra_tenant_id,
           '432c2e34-e294-4063-92c3-67c54b762b8c'::UUID AS entra_object_id,
           'Maaz'::VARCHAR(200) AS display_name,
           'maazuddinmohammed01@gmail.com'::VARCHAR(320) AS login_email,
           'DEMO_TENANT'::VARCHAR(100) AS tenant_code
),
target_tenant AS (
    SELECT tenant.tenant_id
      FROM core.tenant AS tenant
      JOIN seed_input
        ON lower(btrim(tenant.tenant_code)) = lower(btrim(seed_input.tenant_code))
     WHERE tenant.is_active
),
new_principal AS (
    INSERT INTO security.principal (
        principal_type,
        principal_display_name,
        principal_description,
        principal_email,
        is_super_admin
    )
    SELECT 'user',
           seed_input.display_name,
           'Initial deployment Tenant reader',
           seed_input.login_email,
           FALSE
      FROM seed_input
    RETURNING principal_id, principal_type
),
new_identity AS (
    INSERT INTO security.entra_principal_identity (
        principal_id,
        principal_type,
        entra_tenant_id,
        entra_object_id
    )
    SELECT new_principal.principal_id,
           new_principal.principal_type,
           seed_input.entra_tenant_id,
           seed_input.entra_object_id
      FROM new_principal
     CROSS JOIN seed_input
    RETURNING principal_id
)
INSERT INTO security.tenant_principal_access (
    tenant_id,
    principal_id,
    tenant_role,
    granted_by_principal_id
)
SELECT target_tenant.tenant_id,
       new_identity.principal_id,
       'viewer',
       new_identity.principal_id
  FROM target_tenant
 CROSS JOIN new_identity;

SELECT principal.principal_id,
       principal.principal_display_name,
       principal.principal_email,
       tenant.tenant_id,
       tenant.tenant_code,
       access_record.tenant_role
  FROM security.principal AS principal
  JOIN security.tenant_principal_access AS access_record
    ON access_record.principal_id = principal.principal_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = access_record.tenant_id
 WHERE lower(btrim(principal.principal_email)) =
       lower(btrim('maazuddinmohammed01@gmail.com'));
