-- GDS ETL Workbench Release 1: Subject Area Section.
--
-- A Subject Area is a named focus window over Project Input Scope tables, such as
-- Sales or Support. It keeps each modeling call small; it is not a separate model,
-- and a table may belong to several areas. Unassigned tables are worked out, not
-- stored: active Scope tables with no active membership.

CREATE TABLE workflow.subject_area (
    subject_area_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    subject_area_name VARCHAR(255) NOT NULL,
    subject_area_definition TEXT NOT NULL,
    subject_area_status VARCHAR(20) NOT NULL DEFAULT 'active',
    subject_area_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_subject_area_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT uq_subject_area_id_project UNIQUE (subject_area_id, project_id),
    CONSTRAINT ck_subject_area_name CHECK (
        reference.is_nonblank(subject_area_name)
    ),
    CONSTRAINT ck_subject_area_definition CHECK (
        reference.is_nonblank(subject_area_definition)
    ),
    CONSTRAINT ck_subject_area_status CHECK (
        subject_area_status IN ('active', 'inactive', 'deprecated')
    )
);

CREATE UNIQUE INDEX ux_subject_area_project_name
    ON workflow.subject_area (
        project_id,
        lower(btrim(subject_area_name))
    );

-- One row per (area, table). The table must be in this Project's Input Scope.
CREATE TABLE workflow.subject_area_table (
    subject_area_table_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    subject_area_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    subject_area_table_status VARCHAR(20) NOT NULL DEFAULT 'active',
    subject_area_table_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_subject_area_table_project FOREIGN KEY (project_id)
        REFERENCES project.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT fk_subject_area_table_area FOREIGN KEY (
        subject_area_id,
        project_id
    ) REFERENCES workflow.subject_area (
        subject_area_id,
        project_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_subject_area_table_scope FOREIGN KEY (
        project_id,
        object_id
    ) REFERENCES project.project_input_scope (project_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_subject_area_table_member UNIQUE (
        project_id,
        subject_area_id,
        object_id
    ),
    CONSTRAINT ck_subject_area_table_status CHECK (
        subject_area_table_status IN ('active', 'inactive', 'deprecated')
    )
);

CREATE INDEX ix_subject_area_project_status
    ON workflow.subject_area (project_id, subject_area_status);
CREATE INDEX ix_subject_area_table_object
    ON workflow.subject_area_table (project_id, object_id);
