-- GDS ETL Workbench Release 1: Principal identity, Tenant RBAC, and governed Tenant Locks.

CREATE SCHEMA security;

CREATE ROLE gds_migration NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE gds_app_read NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE gds_app_write NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

CREATE TABLE security.principal (
    principal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal_type VARCHAR(30) NOT NULL,
    principal_display_name VARCHAR(200) NOT NULL,
    principal_description TEXT,
    principal_email VARCHAR(320),
    service_principal_application_id UUID,
    service_principal_type VARCHAR(30),
    is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT uq_principal_id_type UNIQUE (principal_id, principal_type),
    CONSTRAINT ck_principal_type CHECK (
        principal_type IN ('user', 'service_principal')
    ),
    CONSTRAINT ck_principal_display_name CHECK (
        reference.is_nonblank(principal_display_name)
    ),
    CONSTRAINT ck_principal_description CHECK (
        principal_description IS NULL
        OR reference.is_nonblank(principal_description)
    ),
    CONSTRAINT ck_principal_shape CHECK (
        (
            principal_type = 'user'
            AND principal_email IS NOT NULL
            AND principal_email = btrim(principal_email)
            AND length(principal_email) > 3
            AND position('@' IN principal_email) > 1
            AND service_principal_application_id IS NULL
            AND service_principal_type IS NULL
        )
        OR
        (
            principal_type = 'service_principal'
            AND principal_email IS NULL
            AND service_principal_application_id IS NOT NULL
            AND service_principal_type IN ('application', 'managed_identity')
        )
    )
);

CREATE TABLE security.entra_principal_identity (
    entra_principal_identity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    principal_id BIGINT NOT NULL,
    principal_type VARCHAR(30) NOT NULL,
    entra_tenant_id UUID NOT NULL,
    entra_object_id UUID NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_entra_principal_identity_principal FOREIGN KEY (
        principal_id,
        principal_type
    ) REFERENCES security.principal (
        principal_id,
        principal_type
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_entra_principal_identity
        UNIQUE (entra_tenant_id, entra_object_id),
    CONSTRAINT uq_entra_identity_principal
        UNIQUE (
            entra_principal_identity_id,
            principal_id,
            principal_type
        ),
    CONSTRAINT uq_principal_entra_tenant
        UNIQUE (principal_id, entra_tenant_id)
);

CREATE TABLE security.tenant_principal_access (
    tenant_principal_access_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    principal_id BIGINT NOT NULL,
    tenant_role VARCHAR(30) NOT NULL,
    granted_by_principal_id BIGINT NOT NULL,
    granted_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    access_expires_time TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_principal_access_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_principal_access_principal FOREIGN KEY (principal_id)
        REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_principal_access_grantor FOREIGN KEY (
        granted_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_tenant_principal_access UNIQUE (tenant_id, principal_id),
    CONSTRAINT ck_tenant_principal_role CHECK (
        tenant_role IN ('viewer', 'developer', 'architect', 'tenant_admin')
    ),
    CONSTRAINT ck_tenant_principal_access_expiry CHECK (
        access_expires_time IS NULL
        OR access_expires_time > granted_time
    )
);

-- One active database-time lock per Tenant. Ordinary write policies require
-- exact ownership; lock-management functions are the only runtime mutation path.
CREATE TABLE security.tenant_lock (
    tenant_lock_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    locked_by_principal_id BIGINT NOT NULL,
    tenant_lock_purpose VARCHAR(500),
    tenant_lock_acquired_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tenant_lock_expires_time TIMESTAMPTZ NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_lock_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_lock_owner FOREIGN KEY (locked_by_principal_id)
        REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT uq_tenant_lock_tenant UNIQUE (tenant_id),
    CONSTRAINT ck_tenant_lock_purpose CHECK (
        tenant_lock_purpose IS NULL
        OR reference.is_nonblank(tenant_lock_purpose)
    ),
    CONSTRAINT ck_tenant_lock_interval CHECK (
        tenant_lock_expires_time > tenant_lock_acquired_time
        AND tenant_lock_expires_time
            <= tenant_lock_acquired_time + INTERVAL '4 hours'
    )
);

CREATE TABLE security.tenant_lock_event (
    tenant_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    tenant_lock_id BIGINT NOT NULL,
    tenant_lock_event_type VARCHAR(50) NOT NULL,
    lock_owner_principal_id BIGINT NOT NULL,
    lock_acted_by_principal_id BIGINT,
    tenant_lock_acquired_time TIMESTAMPTZ NOT NULL,
    tenant_lock_expires_time TIMESTAMPTZ NOT NULL,
    tenant_lock_event_reason VARCHAR(2000),
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_lock_event_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_lock_event_owner FOREIGN KEY (
        lock_owner_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_lock_event_actor FOREIGN KEY (
        lock_acted_by_principal_id
    ) REFERENCES security.principal (principal_id) ON DELETE NO ACTION,
    CONSTRAINT ck_tenant_lock_event_type CHECK (
        tenant_lock_event_type IN (
            'acquired', 'renewed', 'released', 'force_unlocked', 'expired'
        )
    ),
    CONSTRAINT ck_tenant_lock_event_actor CHECK (
        tenant_lock_event_type = 'expired'
        OR lock_acted_by_principal_id IS NOT NULL
    ),
    CONSTRAINT ck_tenant_lock_event_interval CHECK (
        tenant_lock_expires_time > tenant_lock_acquired_time
    ),
    CONSTRAINT ck_tenant_lock_force_reason CHECK (
        tenant_lock_event_type <> 'force_unlocked'
        OR reference.is_nonblank(tenant_lock_event_reason)
    )
);

CREATE UNIQUE INDEX ux_principal_email_ci
    ON security.principal (lower(btrim(principal_email)))
    WHERE principal_type = 'user';

CREATE INDEX ix_entra_principal_identity_principal_active
    ON security.entra_principal_identity (principal_id, is_active);
CREATE INDEX ix_tenant_principal_access_principal_active
    ON security.tenant_principal_access (principal_id, is_active, tenant_id);
CREATE INDEX ix_tenant_principal_access_tenant_role_active
    ON security.tenant_principal_access (
        tenant_id,
        tenant_role,
        is_active
    );
CREATE INDEX ix_tenant_lock_owner_expires
    ON security.tenant_lock (
        locked_by_principal_id,
        tenant_lock_expires_time
    );
CREATE INDEX ix_tenant_lock_expires
    ON security.tenant_lock (tenant_lock_expires_time, tenant_id);
CREATE INDEX ix_tenant_lock_event_tenant_created
    ON security.tenant_lock_event (tenant_id, created_time);

-- Resolve one exact active Entra identity and evaluate one server-selected
-- Tenant operation policy. Callers must normalize tenant_not_found responses;
-- the function intentionally returns no row for an unknown or inactive Principal.
CREATE FUNCTION security.authorize_tenant_operation(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_policy VARCHAR(50)
)
RETURNS TABLE (
    principal_id BIGINT,
    principal_type VARCHAR(30),
    principal_display_name VARCHAR(200),
    is_super_admin BOOLEAN,
    effective_role VARCHAR(30),
    authorized BOOLEAN,
    denial_code VARCHAR(50),
    lock_owner_display_name VARCHAR(200),
    lock_expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, security, core
AS $authorize_tenant_operation$
DECLARE
    v_principal_id BIGINT;
    v_principal_type VARCHAR(30);
    v_principal_display_name VARCHAR(200);
    v_is_super_admin BOOLEAN;
    v_tenant_visibility VARCHAR(20);
    v_tenant_role VARCHAR(30);
    v_effective_role VARCHAR(30);
    v_effective_role_rank INTEGER;
    v_required_role_rank INTEGER;
    v_lock_owner_principal_id BIGINT;
    v_lock_owner_display_name VARCHAR(200);
    v_lock_expires_time TIMESTAMPTZ;
BEGIN
    IF p_expected_principal_type NOT IN ('user', 'service_principal') THEN
        RAISE EXCEPTION 'unsupported Principal type' USING ERRCODE = '22023';
    END IF;
    IF p_policy NOT IN (
        'tenant_read',
        'tenant_metadata_write',
        'tenant_model_write',
        'tenant_lock_manage',
        'super_admin_only'
    ) THEN
        RAISE EXCEPTION 'unsupported authorization policy' USING ERRCODE = '22023';
    END IF;

    SELECT principal.principal_id,
           principal.principal_type,
           principal.principal_display_name,
           principal.is_super_admin
      INTO v_principal_id,
           v_principal_type,
           v_principal_display_name,
           v_is_super_admin
      FROM security.entra_principal_identity AS identity
      JOIN security.principal AS principal
        ON principal.principal_id = identity.principal_id
       AND principal.principal_type = identity.principal_type
     WHERE identity.entra_tenant_id = p_entra_tenant_id
       AND identity.entra_object_id = p_entra_object_id
       AND identity.principal_type = p_expected_principal_type
       AND identity.is_active
       AND principal.is_active
     FOR SHARE OF identity, principal;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    IF v_principal_type = 'service_principal' AND NOT v_is_super_admin THEN
        RETURN QUERY SELECT
            v_principal_id,
            v_principal_type,
            v_principal_display_name,
            v_is_super_admin,
            NULL::VARCHAR(30),
            FALSE,
            'authorization_denied'::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT tenant.tenant_visibility
      INTO v_tenant_visibility
     FROM core.tenant AS tenant
     WHERE tenant.tenant_id = p_tenant_id
       AND tenant.is_active
     FOR SHARE OF tenant;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            v_principal_id,
            v_principal_type,
            v_principal_display_name,
            v_is_super_admin,
            NULL::VARCHAR(30),
            FALSE,
            'tenant_not_found'::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT access.tenant_role
      INTO v_tenant_role
      FROM security.tenant_principal_access AS access
     WHERE access.tenant_id = p_tenant_id
       AND access.principal_id = v_principal_id
       AND access.is_active
       AND (
           access.access_expires_time IS NULL
           OR access.access_expires_time > CURRENT_TIMESTAMP
       )
     FOR SHARE OF access;

    v_effective_role := CASE
        WHEN v_is_super_admin THEN 'super_admin'
        WHEN v_tenant_role IS NOT NULL THEN v_tenant_role
        WHEN v_tenant_visibility = 'global' THEN 'viewer'
        ELSE NULL
    END;
    v_effective_role_rank := CASE v_effective_role
        WHEN 'viewer' THEN 1
        WHEN 'developer' THEN 2
        WHEN 'architect' THEN 3
        WHEN 'tenant_admin' THEN 4
        WHEN 'super_admin' THEN 4
        ELSE 0
    END;
    v_required_role_rank := CASE p_policy
        WHEN 'tenant_read' THEN 1
        WHEN 'tenant_metadata_write' THEN 2
        WHEN 'tenant_model_write' THEN 3
        WHEN 'tenant_lock_manage' THEN 2
        WHEN 'super_admin_only' THEN 4
    END;

    IF v_effective_role_rank < v_required_role_rank
       OR (p_policy = 'super_admin_only' AND NOT v_is_super_admin) THEN
        RETURN QUERY SELECT
            v_principal_id,
            v_principal_type,
            v_principal_display_name,
            v_is_super_admin,
            v_effective_role,
            FALSE,
            CASE
                WHEN p_policy = 'tenant_read' THEN 'tenant_not_found'
                ELSE 'authorization_denied'
            END::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    IF p_policy IN ('tenant_metadata_write', 'tenant_model_write') THEN
        SELECT tenant_lock.locked_by_principal_id,
               lock_owner.principal_display_name,
               tenant_lock.tenant_lock_expires_time
          INTO v_lock_owner_principal_id,
               v_lock_owner_display_name,
               v_lock_expires_time
          FROM security.tenant_lock AS tenant_lock
          JOIN security.principal AS lock_owner
            ON lock_owner.principal_id = tenant_lock.locked_by_principal_id
         WHERE tenant_lock.tenant_id = p_tenant_id
           AND tenant_lock.tenant_lock_expires_time > CURRENT_TIMESTAMP
         FOR SHARE OF tenant_lock, lock_owner;
        IF NOT FOUND THEN
            RETURN QUERY SELECT
                v_principal_id,
                v_principal_type,
                v_principal_display_name,
                v_is_super_admin,
                v_effective_role,
                FALSE,
                'tenant_lock_required'::VARCHAR(50),
                NULL::VARCHAR(200),
                NULL::TIMESTAMPTZ;
            RETURN;
        END IF;
        IF v_lock_owner_principal_id <> v_principal_id THEN
            RETURN QUERY SELECT
                v_principal_id,
                v_principal_type,
                v_principal_display_name,
                v_is_super_admin,
                v_effective_role,
                FALSE,
                'tenant_locked'::VARCHAR(50),
                v_lock_owner_display_name,
                v_lock_expires_time;
            RETURN;
        END IF;
    END IF;

    RETURN QUERY SELECT
        v_principal_id,
        v_principal_type,
        v_principal_display_name,
        v_is_super_admin,
        v_effective_role,
        TRUE,
        NULL::VARCHAR(50),
        NULL::VARCHAR(200),
        NULL::TIMESTAMPTZ;
END;
$authorize_tenant_operation$;

-- Acquire is retry-safe for the current owner. A caller-selected duration is
-- bounded to 1..240 minutes; omission uses the server-owned 60-minute default.
CREATE FUNCTION security.acquire_tenant_lock(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_requested_duration_minutes INTEGER,
    p_purpose VARCHAR(500)
)
RETURNS TABLE (
    acquired BOOLEAN,
    denial_code VARCHAR(50),
    owner_display_name VARCHAR(200),
    purpose VARCHAR(500),
    acquired_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, security, core
AS $acquire_tenant_lock$
DECLARE
    v_decision RECORD;
    v_duration_minutes INTEGER;
    v_existing_lock RECORD;
    v_new_lock RECORD;
BEGIN
    v_duration_minutes := coalesce(p_requested_duration_minutes, 60);
    IF v_duration_minutes NOT BETWEEN 1 AND 240 THEN
        RAISE EXCEPTION 'lock duration must be between 1 and 240 minutes'
            USING ERRCODE = '22023';
    END IF;
    IF p_purpose IS NOT NULL AND NOT reference.is_nonblank(p_purpose) THEN
        RAISE EXCEPTION 'lock purpose must be nonblank when provided'
            USING ERRCODE = '22023';
    END IF;

    PERFORM 1
      FROM core.tenant AS tenant
     WHERE tenant.tenant_id = p_tenant_id
       AND tenant.is_active
     FOR UPDATE;

    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_lock_manage'
      );
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE,
            'authorization_denied'::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::VARCHAR(500),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            v_decision.denial_code::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::VARCHAR(500),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT tenant_lock.tenant_lock_id,
           tenant_lock.locked_by_principal_id,
           lock_owner.principal_display_name,
           tenant_lock.tenant_lock_purpose,
           tenant_lock.tenant_lock_acquired_time,
           tenant_lock.tenant_lock_expires_time
      INTO v_existing_lock
      FROM security.tenant_lock AS tenant_lock
      JOIN security.principal AS lock_owner
        ON lock_owner.principal_id = tenant_lock.locked_by_principal_id
     WHERE tenant_lock.tenant_id = p_tenant_id
     FOR UPDATE OF tenant_lock;

    IF FOUND AND v_existing_lock.tenant_lock_expires_time <= CURRENT_TIMESTAMP THEN
        INSERT INTO security.tenant_lock_event (
            tenant_id,
            tenant_lock_id,
            tenant_lock_event_type,
            lock_owner_principal_id,
            lock_acted_by_principal_id,
            tenant_lock_acquired_time,
            tenant_lock_expires_time
        ) VALUES (
            p_tenant_id,
            v_existing_lock.tenant_lock_id,
            'expired',
            v_existing_lock.locked_by_principal_id,
            NULL,
            v_existing_lock.tenant_lock_acquired_time,
            v_existing_lock.tenant_lock_expires_time
        );
        DELETE FROM security.tenant_lock AS tenant_lock
         WHERE tenant_lock.tenant_lock_id = v_existing_lock.tenant_lock_id;
        v_existing_lock := NULL;
    END IF;

    IF v_existing_lock IS NOT NULL THEN
        IF v_existing_lock.locked_by_principal_id = v_decision.principal_id THEN
            RETURN QUERY SELECT
                TRUE,
                NULL::VARCHAR(50),
                v_existing_lock.principal_display_name::VARCHAR(200),
                v_existing_lock.tenant_lock_purpose::VARCHAR(500),
                v_existing_lock.tenant_lock_acquired_time::TIMESTAMPTZ,
                v_existing_lock.tenant_lock_expires_time::TIMESTAMPTZ;
        ELSE
            RETURN QUERY SELECT
                FALSE,
                'tenant_locked'::VARCHAR(50),
                v_existing_lock.principal_display_name::VARCHAR(200),
                v_existing_lock.tenant_lock_purpose::VARCHAR(500),
                v_existing_lock.tenant_lock_acquired_time::TIMESTAMPTZ,
                v_existing_lock.tenant_lock_expires_time::TIMESTAMPTZ;
        END IF;
        RETURN;
    END IF;

    INSERT INTO security.tenant_lock (
        tenant_id,
        locked_by_principal_id,
        tenant_lock_purpose,
        tenant_lock_acquired_time,
        tenant_lock_expires_time
    ) VALUES (
        p_tenant_id,
        v_decision.principal_id,
        p_purpose,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP + make_interval(mins => v_duration_minutes)
    )
    RETURNING tenant_lock_id,
              tenant_lock_purpose,
              tenant_lock_acquired_time,
              tenant_lock_expires_time
         INTO v_new_lock;

    INSERT INTO security.tenant_lock_event (
        tenant_id,
        tenant_lock_id,
        tenant_lock_event_type,
        lock_owner_principal_id,
        lock_acted_by_principal_id,
        tenant_lock_acquired_time,
        tenant_lock_expires_time
    ) VALUES (
        p_tenant_id,
        v_new_lock.tenant_lock_id,
        'acquired',
        v_decision.principal_id,
        v_decision.principal_id,
        v_new_lock.tenant_lock_acquired_time,
        v_new_lock.tenant_lock_expires_time
    );

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        v_decision.principal_display_name::VARCHAR(200),
        v_new_lock.tenant_lock_purpose::VARCHAR(500),
        v_new_lock.tenant_lock_acquired_time::TIMESTAMPTZ,
        v_new_lock.tenant_lock_expires_time::TIMESTAMPTZ;
END;
$acquire_tenant_lock$;

-- Override is an explicit lock-management operation. It never changes the
-- displaced Principal's Tenant Role; it replaces only the active lock and
-- preserves the reason in the append-only lock event stream.
CREATE FUNCTION security.override_tenant_lock(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_requested_duration_minutes INTEGER,
    p_purpose VARCHAR(500),
    p_reason VARCHAR(2000)
)
RETURNS TABLE (
    acquired BOOLEAN,
    denial_code VARCHAR(50),
    owner_display_name VARCHAR(200),
    purpose VARCHAR(500),
    acquired_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, security, core
AS $override_tenant_lock$
DECLARE
    v_decision RECORD;
    v_existing_lock RECORD;
BEGIN
    IF NOT reference.is_nonblank(p_reason) THEN
        RAISE EXCEPTION 'lock override reason is required' USING ERRCODE = '22023';
    END IF;
    IF coalesce(p_requested_duration_minutes, 60) NOT BETWEEN 1 AND 240 THEN
        RAISE EXCEPTION 'lock duration must be between 1 and 240 minutes'
            USING ERRCODE = '22023';
    END IF;
    IF p_purpose IS NOT NULL AND NOT reference.is_nonblank(p_purpose) THEN
        RAISE EXCEPTION 'lock purpose must be nonblank when provided'
            USING ERRCODE = '22023';
    END IF;

    PERFORM 1
      FROM core.tenant AS tenant
     WHERE tenant.tenant_id = p_tenant_id
       AND tenant.is_active
     FOR UPDATE;
    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_lock_manage'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(
                v_decision.denial_code,
                'authorization_denied'
            )::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::VARCHAR(500),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT tenant_lock.tenant_lock_id,
           tenant_lock.locked_by_principal_id,
           tenant_lock.tenant_lock_acquired_time,
           tenant_lock.tenant_lock_expires_time
      INTO v_existing_lock
      FROM security.tenant_lock AS tenant_lock
     WHERE tenant_lock.tenant_id = p_tenant_id
     FOR UPDATE;

    IF FOUND AND v_existing_lock.locked_by_principal_id <> v_decision.principal_id THEN
        INSERT INTO security.tenant_lock_event (
            tenant_id,
            tenant_lock_id,
            tenant_lock_event_type,
            lock_owner_principal_id,
            lock_acted_by_principal_id,
            tenant_lock_acquired_time,
            tenant_lock_expires_time,
            tenant_lock_event_reason
        ) VALUES (
            p_tenant_id,
            v_existing_lock.tenant_lock_id,
            CASE
                WHEN v_existing_lock.tenant_lock_expires_time <= CURRENT_TIMESTAMP
                    THEN 'expired'
                ELSE 'force_unlocked'
            END,
            v_existing_lock.locked_by_principal_id,
            CASE
                WHEN v_existing_lock.tenant_lock_expires_time <= CURRENT_TIMESTAMP
                    THEN NULL
                ELSE v_decision.principal_id
            END,
            v_existing_lock.tenant_lock_acquired_time,
            v_existing_lock.tenant_lock_expires_time,
            CASE
                WHEN v_existing_lock.tenant_lock_expires_time <= CURRENT_TIMESTAMP
                    THEN NULL
                ELSE p_reason
            END
        );
        DELETE FROM security.tenant_lock AS tenant_lock
         WHERE tenant_lock.tenant_lock_id = v_existing_lock.tenant_lock_id;
    END IF;

    RETURN QUERY
    SELECT result.acquired,
           result.denial_code,
           result.owner_display_name,
           result.purpose,
           result.acquired_time,
           result.expires_time
      FROM security.acquire_tenant_lock(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          p_requested_duration_minutes,
          p_purpose
      ) AS result;
END;
$override_tenant_lock$;

CREATE FUNCTION security.renew_tenant_lock(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT,
    p_requested_duration_minutes INTEGER
)
RETURNS TABLE (
    renewed BOOLEAN,
    denial_code VARCHAR(50),
    owner_display_name VARCHAR(200),
    purpose VARCHAR(500),
    acquired_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, security, core
AS $renew_tenant_lock$
DECLARE
    v_decision RECORD;
    v_duration_minutes INTEGER;
    v_existing_lock RECORD;
    v_renewed_lock RECORD;
BEGIN
    v_duration_minutes := coalesce(p_requested_duration_minutes, 60);
    IF v_duration_minutes NOT BETWEEN 1 AND 240 THEN
        RAISE EXCEPTION 'lock duration must be between 1 and 240 minutes'
            USING ERRCODE = '22023';
    END IF;

    PERFORM 1
      FROM core.tenant AS tenant
     WHERE tenant.tenant_id = p_tenant_id
       AND tenant.is_active
     FOR UPDATE;
    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_lock_manage'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(
                v_decision.denial_code,
                'authorization_denied'
            )::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::VARCHAR(500),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT tenant_lock.tenant_lock_id,
           tenant_lock.locked_by_principal_id,
           lock_owner.principal_display_name,
           tenant_lock.tenant_lock_purpose,
           tenant_lock.tenant_lock_acquired_time,
           tenant_lock.tenant_lock_expires_time
      INTO v_existing_lock
      FROM security.tenant_lock AS tenant_lock
      JOIN security.principal AS lock_owner
        ON lock_owner.principal_id = tenant_lock.locked_by_principal_id
     WHERE tenant_lock.tenant_id = p_tenant_id
     FOR UPDATE OF tenant_lock;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE,
            'tenant_lock_required'::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::VARCHAR(500),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    IF v_existing_lock.tenant_lock_expires_time <= CURRENT_TIMESTAMP THEN
        INSERT INTO security.tenant_lock_event (
            tenant_id,
            tenant_lock_id,
            tenant_lock_event_type,
            lock_owner_principal_id,
            lock_acted_by_principal_id,
            tenant_lock_acquired_time,
            tenant_lock_expires_time
        ) VALUES (
            p_tenant_id,
            v_existing_lock.tenant_lock_id,
            'expired',
            v_existing_lock.locked_by_principal_id,
            NULL,
            v_existing_lock.tenant_lock_acquired_time,
            v_existing_lock.tenant_lock_expires_time
        );
        DELETE FROM security.tenant_lock AS tenant_lock
         WHERE tenant_lock.tenant_lock_id = v_existing_lock.tenant_lock_id;
        RETURN QUERY SELECT
            FALSE,
            'tenant_lock_required'::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::VARCHAR(500),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_existing_lock.locked_by_principal_id <> v_decision.principal_id THEN
        RETURN QUERY SELECT
            FALSE,
            'tenant_locked'::VARCHAR(50),
            v_existing_lock.principal_display_name::VARCHAR(200),
            v_existing_lock.tenant_lock_purpose::VARCHAR(500),
            v_existing_lock.tenant_lock_acquired_time::TIMESTAMPTZ,
            v_existing_lock.tenant_lock_expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    UPDATE security.tenant_lock AS tenant_lock
       SET tenant_lock_acquired_time = CURRENT_TIMESTAMP,
           tenant_lock_expires_time =
               CURRENT_TIMESTAMP + make_interval(mins => v_duration_minutes),
           updated_time = CURRENT_TIMESTAMP,
           updated_by = CURRENT_USER
     WHERE tenant_lock.tenant_lock_id = v_existing_lock.tenant_lock_id
    RETURNING tenant_lock.tenant_lock_id,
              tenant_lock.tenant_lock_purpose,
              tenant_lock.tenant_lock_acquired_time,
              tenant_lock.tenant_lock_expires_time
         INTO v_renewed_lock;

    INSERT INTO security.tenant_lock_event (
        tenant_id,
        tenant_lock_id,
        tenant_lock_event_type,
        lock_owner_principal_id,
        lock_acted_by_principal_id,
        tenant_lock_acquired_time,
        tenant_lock_expires_time
    ) VALUES (
        p_tenant_id,
        v_renewed_lock.tenant_lock_id,
        'renewed',
        v_decision.principal_id,
        v_decision.principal_id,
        v_renewed_lock.tenant_lock_acquired_time,
        v_renewed_lock.tenant_lock_expires_time
    );

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        v_decision.principal_display_name::VARCHAR(200),
        v_renewed_lock.tenant_lock_purpose::VARCHAR(500),
        v_renewed_lock.tenant_lock_acquired_time::TIMESTAMPTZ,
        v_renewed_lock.tenant_lock_expires_time::TIMESTAMPTZ;
END;
$renew_tenant_lock$;

CREATE FUNCTION security.release_tenant_lock(
    p_entra_tenant_id UUID,
    p_entra_object_id UUID,
    p_expected_principal_type VARCHAR(30),
    p_tenant_id BIGINT
)
RETURNS TABLE (
    released BOOLEAN,
    denial_code VARCHAR(50),
    owner_display_name VARCHAR(200),
    acquired_time TIMESTAMPTZ,
    expires_time TIMESTAMPTZ
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, security, core
AS $release_tenant_lock$
DECLARE
    v_decision RECORD;
    v_existing_lock RECORD;
BEGIN
    PERFORM 1
      FROM core.tenant AS tenant
     WHERE tenant.tenant_id = p_tenant_id
       AND tenant.is_active
     FOR UPDATE;
    SELECT *
      INTO v_decision
      FROM security.authorize_tenant_operation(
          p_entra_tenant_id,
          p_entra_object_id,
          p_expected_principal_type,
          p_tenant_id,
          'tenant_lock_manage'
      );
    IF NOT FOUND OR NOT v_decision.authorized THEN
        RETURN QUERY SELECT
            FALSE,
            coalesce(
                v_decision.denial_code,
                'authorization_denied'
            )::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    SELECT tenant_lock.tenant_lock_id,
           tenant_lock.locked_by_principal_id,
           lock_owner.principal_display_name,
           tenant_lock.tenant_lock_acquired_time,
           tenant_lock.tenant_lock_expires_time
      INTO v_existing_lock
      FROM security.tenant_lock AS tenant_lock
      JOIN security.principal AS lock_owner
        ON lock_owner.principal_id = tenant_lock.locked_by_principal_id
     WHERE tenant_lock.tenant_id = p_tenant_id
     FOR UPDATE OF tenant_lock;
    IF NOT FOUND THEN
        RETURN QUERY SELECT
            FALSE,
            'tenant_lock_required'::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;

    IF v_existing_lock.tenant_lock_expires_time <= CURRENT_TIMESTAMP THEN
        INSERT INTO security.tenant_lock_event (
            tenant_id,
            tenant_lock_id,
            tenant_lock_event_type,
            lock_owner_principal_id,
            lock_acted_by_principal_id,
            tenant_lock_acquired_time,
            tenant_lock_expires_time
        ) VALUES (
            p_tenant_id,
            v_existing_lock.tenant_lock_id,
            'expired',
            v_existing_lock.locked_by_principal_id,
            NULL,
            v_existing_lock.tenant_lock_acquired_time,
            v_existing_lock.tenant_lock_expires_time
        );
        DELETE FROM security.tenant_lock AS tenant_lock
         WHERE tenant_lock.tenant_lock_id = v_existing_lock.tenant_lock_id;
        RETURN QUERY SELECT
            FALSE,
            'tenant_lock_required'::VARCHAR(50),
            NULL::VARCHAR(200),
            NULL::TIMESTAMPTZ,
            NULL::TIMESTAMPTZ;
        RETURN;
    END IF;
    IF v_existing_lock.locked_by_principal_id <> v_decision.principal_id THEN
        RETURN QUERY SELECT
            FALSE,
            'tenant_locked'::VARCHAR(50),
            v_existing_lock.principal_display_name::VARCHAR(200),
            v_existing_lock.tenant_lock_acquired_time::TIMESTAMPTZ,
            v_existing_lock.tenant_lock_expires_time::TIMESTAMPTZ;
        RETURN;
    END IF;

    INSERT INTO security.tenant_lock_event (
        tenant_id,
        tenant_lock_id,
        tenant_lock_event_type,
        lock_owner_principal_id,
        lock_acted_by_principal_id,
        tenant_lock_acquired_time,
        tenant_lock_expires_time
    ) VALUES (
        p_tenant_id,
        v_existing_lock.tenant_lock_id,
        'released',
        v_decision.principal_id,
        v_decision.principal_id,
        v_existing_lock.tenant_lock_acquired_time,
        v_existing_lock.tenant_lock_expires_time
    );
    DELETE FROM security.tenant_lock AS tenant_lock
     WHERE tenant_lock.tenant_lock_id = v_existing_lock.tenant_lock_id;

    RETURN QUERY SELECT
        TRUE,
        NULL::VARCHAR(50),
        v_decision.principal_display_name::VARCHAR(200),
        v_existing_lock.tenant_lock_acquired_time::TIMESTAMPTZ,
        v_existing_lock.tenant_lock_expires_time::TIMESTAMPTZ;
END;
$release_tenant_lock$;

-- PostgreSQL has no time-based trigger. The App Service calls this bounded,
-- concurrency-safe function periodically; interaction paths also treat an
-- expired row as inactive and write the same event before replacing it.
CREATE FUNCTION security.expire_tenant_locks(p_limit INTEGER DEFAULT 100)
RETURNS INTEGER
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, security
AS $expire_tenant_locks$
DECLARE
    v_lock RECORD;
    v_expired_count INTEGER := 0;
BEGIN
    IF p_limit NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'expiry batch limit must be between 1 and 1000'
            USING ERRCODE = '22023';
    END IF;

    FOR v_lock IN
        SELECT tenant_lock.tenant_lock_id,
               tenant_lock.tenant_id,
               tenant_lock.locked_by_principal_id,
               tenant_lock.tenant_lock_acquired_time,
               tenant_lock.tenant_lock_expires_time
          FROM security.tenant_lock AS tenant_lock
         WHERE tenant_lock.tenant_lock_expires_time <= CURRENT_TIMESTAMP
         ORDER BY tenant_lock.tenant_lock_expires_time, tenant_lock.tenant_lock_id
         FOR UPDATE SKIP LOCKED
         LIMIT p_limit
    LOOP
        INSERT INTO security.tenant_lock_event (
            tenant_id,
            tenant_lock_id,
            tenant_lock_event_type,
            lock_owner_principal_id,
            lock_acted_by_principal_id,
            tenant_lock_acquired_time,
            tenant_lock_expires_time
        ) VALUES (
            v_lock.tenant_id,
            v_lock.tenant_lock_id,
            'expired',
            v_lock.locked_by_principal_id,
            NULL,
            v_lock.tenant_lock_acquired_time,
            v_lock.tenant_lock_expires_time
        );
        DELETE FROM security.tenant_lock AS tenant_lock
         WHERE tenant_lock.tenant_lock_id = v_lock.tenant_lock_id;
        v_expired_count := v_expired_count + 1;
    END LOOP;
    RETURN v_expired_count;
END;
$expire_tenant_locks$;
