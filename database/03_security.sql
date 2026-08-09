-- GDS ETL Workbench Release 1: Principal identity, Tenant RBAC, and dormant Tenant Lease.

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

-- Retained as dormant data for a future demonstrated Tenant-wide operation.
-- Release 1 application workflows do not acquire or expose this Lease.
CREATE TABLE security.tenant_lock (
    tenant_lock_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    tenant_lock_token VARCHAR(128) NOT NULL,
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
    CONSTRAINT uq_tenant_lock_token UNIQUE (tenant_lock_token),
    CONSTRAINT ck_tenant_lock_token CHECK (
        reference.is_nonblank(tenant_lock_token)
    ),
    CONSTRAINT ck_tenant_lock_purpose CHECK (
        tenant_lock_purpose IS NULL
        OR reference.is_nonblank(tenant_lock_purpose)
    ),
    CONSTRAINT ck_tenant_lock_interval CHECK (
        tenant_lock_expires_time > tenant_lock_acquired_time
    )
);

CREATE TABLE security.tenant_lock_event (
    tenant_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    tenant_lock_token VARCHAR(128) NOT NULL,
    tenant_lock_event_type VARCHAR(50) NOT NULL,
    lock_owner_principal_id BIGINT NOT NULL,
    lock_acted_by_principal_id BIGINT,
    tenant_lock_acquired_time TIMESTAMPTZ NOT NULL,
    tenant_lock_expires_time TIMESTAMPTZ NOT NULL,
    tenant_lock_event_reason TEXT,
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

CREATE FUNCTION security.reject_append_only_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION USING
        ERRCODE = '55000',
        MESSAGE = format('%s is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME);
END;
$$;

CREATE TRIGGER guard_tenant_lock_event_append_only
BEFORE UPDATE OR DELETE ON security.tenant_lock_event
FOR EACH ROW EXECUTE FUNCTION security.reject_append_only_change();

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
CREATE INDEX ix_tenant_lock_event_tenant_created
    ON security.tenant_lock_event (tenant_id, created_time);
