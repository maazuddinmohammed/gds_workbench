-- GDS ETL Workbench Release 1: identity, membership, and dormant Tenant Lease.

CREATE SCHEMA core_security;

CREATE ROLE gds_migration NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE gds_app_read NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE gds_app_write NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

CREATE TABLE core_security.user_account (
    user_account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_email VARCHAR(320) NOT NULL,
    user_display_name VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_user_account_email CHECK (
        user_email = btrim(user_email)
        AND length(user_email) > 3
        AND position('@' IN user_email) > 1
    ),
    CONSTRAINT ck_user_account_display_name CHECK (
        user_display_name IS NULL OR core.is_nonblank(user_display_name)
    )
);

CREATE TABLE core_security.user_entra_identity (
    user_entra_identity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_account_id BIGINT NOT NULL,
    entra_tenant_id UUID NOT NULL,
    entra_object_id UUID NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_user_entra_identity_account FOREIGN KEY (user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_user_entra_identity UNIQUE (entra_tenant_id, entra_object_id),
    CONSTRAINT uq_user_entra_identity_id_account
        UNIQUE (user_entra_identity_id, user_account_id),
    CONSTRAINT uq_user_entra_identity_account_tenant
        UNIQUE (user_account_id, entra_tenant_id)
);

CREATE TABLE core_security.tenant_user_access (
    tenant_user_access_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    user_account_id BIGINT NOT NULL,
    tenant_access_level VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_user_access_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_user_access_account FOREIGN KEY (user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_tenant_user_access UNIQUE (tenant_id, user_account_id),
    CONSTRAINT ck_tenant_access_level CHECK (
        tenant_access_level IN ('admin', 'architect', 'developer')
    )
);

-- Retained as dormant data for a future demonstrated Tenant-wide operation.
-- Release 1 application workflows do not acquire or expose this Lease.
CREATE TABLE core_security.tenant_lock (
    tenant_lock_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    tenant_lock_token VARCHAR(128) NOT NULL,
    locked_by_user_account_id BIGINT NOT NULL,
    tenant_lock_purpose VARCHAR(500),
    tenant_lock_acquired_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tenant_lock_expires_time TIMESTAMPTZ NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_lock_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_lock_owner FOREIGN KEY (locked_by_user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_tenant_lock_tenant UNIQUE (tenant_id),
    CONSTRAINT uq_tenant_lock_token UNIQUE (tenant_lock_token),
    CONSTRAINT ck_tenant_lock_token CHECK (
        core.is_nonblank(tenant_lock_token)
    ),
    CONSTRAINT ck_tenant_lock_purpose CHECK (
        tenant_lock_purpose IS NULL OR core.is_nonblank(tenant_lock_purpose)
    ),
    CONSTRAINT ck_tenant_lock_interval CHECK (
        tenant_lock_expires_time > tenant_lock_acquired_time
    )
);

CREATE TABLE core_security.tenant_lock_event (
    tenant_lock_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    tenant_lock_token VARCHAR(128) NOT NULL,
    tenant_lock_event_type VARCHAR(50) NOT NULL,
    lock_owner_user_account_id BIGINT NOT NULL,
    lock_acted_by_user_account_id BIGINT,
    tenant_lock_acquired_time TIMESTAMPTZ NOT NULL,
    tenant_lock_expires_time TIMESTAMPTZ NOT NULL,
    tenant_lock_event_reason TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_lock_event_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_lock_event_owner FOREIGN KEY (lock_owner_user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_tenant_lock_event_actor FOREIGN KEY (lock_acted_by_user_account_id)
        REFERENCES core_security.user_account (user_account_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_tenant_lock_event_type CHECK (
        tenant_lock_event_type IN (
            'acquired', 'renewed', 'released', 'force_unlocked', 'expired'
        )
    ),
    CONSTRAINT ck_tenant_lock_event_actor CHECK (
        tenant_lock_event_type = 'expired'
        OR lock_acted_by_user_account_id IS NOT NULL
    ),
    CONSTRAINT ck_tenant_lock_event_interval CHECK (
        tenant_lock_expires_time > tenant_lock_acquired_time
    ),
    CONSTRAINT ck_tenant_lock_force_reason CHECK (
        tenant_lock_event_type <> 'force_unlocked'
        OR core.is_nonblank(tenant_lock_event_reason)
    )
);

CREATE FUNCTION core_security.reject_append_only_change()
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
BEFORE UPDATE OR DELETE ON core_security.tenant_lock_event
FOR EACH ROW EXECUTE FUNCTION core_security.reject_append_only_change();

CREATE UNIQUE INDEX ux_user_account_email_ci
    ON core_security.user_account (lower(btrim(user_email)));

CREATE INDEX ix_user_entra_identity_account_active
    ON core_security.user_entra_identity (user_account_id, is_active);
CREATE INDEX ix_tenant_user_access_account_active
    ON core_security.tenant_user_access (user_account_id, is_active, tenant_id);
CREATE INDEX ix_tenant_user_access_tenant_role_active
    ON core_security.tenant_user_access (
        tenant_id,
        tenant_access_level,
        is_active
    );
CREATE INDEX ix_tenant_lock_owner_expires
    ON core_security.tenant_lock (
        locked_by_user_account_id,
        tenant_lock_expires_time
    );
CREATE INDEX ix_tenant_lock_event_tenant_created
    ON core_security.tenant_lock_event (tenant_id, created_time);
