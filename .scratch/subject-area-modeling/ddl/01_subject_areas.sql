-- PROPOSAL (draft, not installed). Replaces database/06_workflow_conceptual.sql.
--
-- Comment format:  filled by · read by
--   filled by: AI = the model writes it | backend = computed | you = set in review
--   read by:   BUILD = Logical/Dimensional Build calls (see README for all codes)
-- Nonblank text checks and the one-revision write guard stay as they are today.

-- One row per subject area, such as Sales or Support.
CREATE TABLE workflow.subject_area (
    subject_area_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id               BIGINT NOT NULL REFERENCES project.project,      -- backend
    subject_area_name        VARCHAR(255) NOT NULL,   -- AI · BUILD (run picker, prompt), diagrams
    subject_area_definition  TEXT NOT NULL,           -- AI · BUILD: tells the call what the area covers
    subject_area_is_active   BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (to retire) or you
    subject_area_is_locked   BOOLEAN NOT NULL DEFAULT FALSE,  -- you · AI can't change a locked area
    workflow_run_id          BIGINT,                  -- backend · audit: run that last changed it
    created_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (subject_area_id, project_id)
);

CREATE UNIQUE INDEX ux_subject_area_name
    ON workflow.subject_area (project_id, lower(btrim(subject_area_name)));

-- One row per (subject area, table). A table can sit in several areas.
CREATE TABLE workflow.subject_area_table (
    project_id                    BIGINT NOT NULL,  -- backend
    subject_area_id               BIGINT NOT NULL,  -- AI (by area name) · BUILD: which tables a call works on
    object_id                     BIGINT NOT NULL,  -- AI (by table id) · BUILD, Unassigned list
    subject_area_table_is_active  BOOLEAN NOT NULL DEFAULT TRUE,   -- AI (to remove) or you
    subject_area_table_is_locked  BOOLEAN NOT NULL DEFAULT FALSE,  -- you · pin a table to an area
    workflow_run_id               BIGINT,           -- backend · audit
    created_time                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, subject_area_id, object_id),
    FOREIGN KEY (subject_area_id, project_id)
        REFERENCES workflow.subject_area (subject_area_id, project_id),
    FOREIGN KEY (project_id, object_id)
        REFERENCES project.project_input_scope (project_id, object_id)  -- must be in scope
);

CREATE INDEX ix_subject_area_table_object
    ON workflow.subject_area_table (project_id, object_id);

-- Worked out, not stored:
--   Unassigned tables      = scope tables with no active row in subject_area_table.
--   An entity's areas      = the areas of the tables it is built from.

-- Dropped from today's 06_workflow_conceptual.sql:
--   conceptual_object: type, grain, aliases    no later step reads them
--   conceptual_relationship (whole table)       relationships are modeled in Logical
--   conceptual_support (whole table)            replaced by subject_area_table
--   membership reason                           only a reviewer would read it; the area
--                                               definition explains the grouping
--   agent_run_id, created_by, updated_by        see README
--   ConceptID DDL download                      nothing left to export
