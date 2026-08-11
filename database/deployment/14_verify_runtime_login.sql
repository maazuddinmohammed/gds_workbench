-- Verify the fixed production runtime login after provisioning it.

DO $verify_runtime_login$
DECLARE
    v_membership_count INTEGER;
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_roles AS role_record
         WHERE role_record.rolname = 'gds_mcp_runtime'
           AND role_record.rolcanlogin
           AND NOT role_record.rolsuper
           AND NOT role_record.rolinherit
           AND NOT role_record.rolcreatedb
           AND NOT role_record.rolcreaterole
           AND NOT role_record.rolreplication
           AND NOT role_record.rolbypassrls
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime posture is invalid';
    END IF;

    SELECT count(*)
      INTO v_membership_count
      FROM pg_catalog.pg_auth_members AS membership
      JOIN pg_catalog.pg_roles AS member_role
        ON member_role.oid = membership.member
      JOIN pg_catalog.pg_roles AS granted_role
        ON granted_role.oid = membership.roleid
     WHERE member_role.rolname = 'gds_mcp_runtime';

    IF v_membership_count <> 1 OR NOT pg_has_role(
        'gds_mcp_runtime',
        'gds_app_write',
        'MEMBER'
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime must have exactly one direct membership';
    END IF;

    IF NOT has_database_privilege(
        'gds_mcp_runtime',
        current_database(),
        'CONNECT'
    ) THEN
        RAISE EXCEPTION 'gds_mcp_runtime cannot connect to this database';
    END IF;
END;
$verify_runtime_login$;

SELECT 'gds_mcp_runtime' AS runtime_login,
       'gds_app_write' AS activated_role,
       'passed' AS verification_status;
