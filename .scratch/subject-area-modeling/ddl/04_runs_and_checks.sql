-- PROPOSAL (draft, not installed). Small additions to database/13_application_workflow_runs.sql
-- and a results table for the new Validate runs.

-- ---------------------------------------------------------------------------
-- 1. Workflow names. These replace 'conceptual', 'logical' and 'dimensional' in
--    application.workflow_run.project_workflow (and its CHECK).
-- ---------------------------------------------------------------------------
--   'subject_areas'          group tables into subject areas (today's Conceptual run)
--   'logical_build'          AI, one call per selected subject area, one draft
--   'logical_optimize'       AI, whole Logical model, one draft
--   'logical_validate'       no AI, Databricks checks, results saved directly
--   'dimensional_build'      AI, one call per selected subject area, one draft
--   'dimensional_optimize'   AI, whole Dimensional model, one draft
--   'dimensional_validate'   no AI, Databricks checks, results saved directly

-- ---------------------------------------------------------------------------
-- 2. Which subject areas a Build run covers. Works like today's
--    application.workflow_run_object_selection, but with areas instead of tables.
-- ---------------------------------------------------------------------------
CREATE TABLE application.workflow_run_subject_area_selection (
    workflow_run_id  BIGINT NOT NULL,  -- backend
    project_id       BIGINT NOT NULL,  -- backend
    subject_area_id  BIGINT NOT NULL,  -- you, in the run dialog
    selection_order  INTEGER NOT NULL, -- the order Build processes the areas
    PRIMARY KEY (workflow_run_id, subject_area_id),
    FOREIGN KEY (workflow_run_id, project_id)
        REFERENCES application.workflow_run (workflow_run_id, project_id),
    FOREIGN KEY (subject_area_id, project_id)
        REFERENCES workflow.subject_area (subject_area_id, project_id),
    UNIQUE (workflow_run_id, selection_order)
);
-- The run also freezes each area's table list when it is created, so editing an area
-- during a run can't change what the run works on.

-- ---------------------------------------------------------------------------
-- 3. Validate results: Databricks measurements, saved directly (no draft), like
--    Analysis validation. A new Validate run replaces the earlier result of the same
--    check on the same record.
--    Rule checks (every table modeled, every entity has a key, ...) are cheap and are
--    computed when the screen loads, so they are not stored.
-- ---------------------------------------------------------------------------
CREATE TABLE workflow.model_check_result (
    model_check_result_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, -- backend
    project_id                   BIGINT NOT NULL,  -- backend
    workflow_run_id              BIGINT NOT NULL,  -- backend: the Validate run
    logical_entity_id            BIGINT,           -- one of these four is the checked record
    logical_relationship_id      BIGINT,
    dimensional_entity_id        BIGINT,
    dimensional_relationship_id  BIGINT,
    check_code                   VARCHAR(30) NOT NULL,  -- see the CHECK below
    check_result                 VARCHAR(20) NOT NULL,  -- passed | failed | inconclusive
    rows_checked                 BIGINT,           -- measured rows
    failing_rows                 BIGINT,           -- duplicates, orphans or nulls found
    checked_time                 TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (num_nonnulls(logical_entity_id, logical_relationship_id,
                        dimensional_entity_id, dimensional_relationship_id) = 1),
    CHECK (check_code IN (
        'key_unique',       -- natural key (or fact grain) has no duplicates in the real rows
        'parent_found',     -- every foreign-key value finds its parent row
        'required_filled'   -- non-nullable columns have no nulls
    )),
    CHECK (check_result IN ('passed', 'failed', 'inconclusive')),
    CHECK (rows_checked IS NULL OR rows_checked >= 0),
    CHECK (failing_rows IS NULL OR failing_rows >= 0)
);
-- Read by: Optimize and the next Build (fix failed checks), MAP (a non-unique key
-- means Mapping must deduplicate), the review screens.
-- Typed record columns follow the existing rule against one unchecked polymorphic id.
-- Foreign keys to each checked table are omitted here for brevity.
