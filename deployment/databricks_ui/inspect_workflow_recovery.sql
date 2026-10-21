-- Run this entire script in a fresh SQL session with SELECT access to the two tables.
-- Change only the three IDs below to inspect a different Run, Tenant and Project.
-- Reads one Run and event counts; calls no application functions and makes no writes.
-- No credentials, tokens, digests, reference IDs, messages or event bodies are returned.
-- Terminal Runs normally clear their claim timestamps; NULL lease intervals are expected.
-- Usage markers show recorded initialization, not model use or successful execution.
-- A missing usage marker on an older Run does not prove initialization never happened.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '2s';

WITH requested(workflow_run_id, tenant_id, project_id) AS (
    VALUES (18::BIGINT, 2::BIGINT, 4::BIGINT)
),
observed AS (
    SELECT run.workflow_run_id, run.project_id, run.project_workflow,
           run.workflow_run_state, run.failure_code, run.workflow_run_recovery_count,
           run.started_time, run.completed_time, run.workflow_run_claimed_time,
           run.workflow_run_claim_heartbeat_time, run.workflow_run_claim_expires_time,
           run.usage_tracking_version, run.usage_tracked_recovery_count,
           run.usage_history_incomplete,
           statement_timestamp() AS observed_time
      FROM requested
      LEFT JOIN application.workflow_run AS run
        ON run.workflow_run_id = requested.workflow_run_id
       AND run.tenant_id = requested.tenant_id
       AND run.project_id = requested.project_id
)
SELECT current_setting('transaction_read_only') = 'on' AS read_only_transaction,
       run.workflow_run_id IS NOT NULL AS run_found,
       run.project_workflow AS workflow,
       run.workflow_run_state AS state,
       run.failure_code = 'workflow_run_recovery_exhausted' AS recovery_exhausted,
       run.workflow_run_recovery_count AS recovery_count,
       round(extract(epoch FROM (
           coalesce(run.completed_time, run.observed_time) - run.started_time
       )), 3) AS run_seconds,
       run.workflow_run_claimed_time IS NOT NULL AS claim_present,
       run.workflow_run_claim_expires_time > run.observed_time AS claim_unexpired,
       round(extract(epoch FROM (
           run.observed_time - run.workflow_run_claimed_time
       )), 3) AS seconds_since_claim,
       round(extract(epoch FROM (
           run.workflow_run_claim_heartbeat_time - run.workflow_run_claimed_time
       )), 3) AS heartbeat_seconds_after_claim,
       round(extract(epoch FROM (
           run.observed_time - run.workflow_run_claim_heartbeat_time
       )), 3) AS seconds_since_heartbeat,
       round(extract(epoch FROM (
           run.workflow_run_claim_expires_time - run.observed_time
       )), 3) AS lease_seconds_remaining,
       run.usage_tracking_version,
       run.usage_tracked_recovery_count,
       run.usage_history_incomplete,
       events.total_event_count,
       events.lifecycle_event_count,
       events.profiling_prepare_event_count,
       events.profiling_execute_event_count,
       events.other_stage_event_count
  FROM observed AS run
 CROSS JOIN LATERAL (
       SELECT count(*) AS total_event_count,
              count(*) FILTER (WHERE project_event_log_stage = 'workflow_run')
                  AS lifecycle_event_count,
              count(*) FILTER (WHERE project_event_log_stage = 'profiling.prepare')
                  AS profiling_prepare_event_count,
              count(*) FILTER (WHERE project_event_log_stage = 'profiling.execute')
                  AS profiling_execute_event_count,
              count(*) FILTER (WHERE project_event_log_stage NOT IN (
                  'workflow_run', 'profiling.prepare', 'profiling.execute'
              )) AS other_stage_event_count
         FROM project.project_event_log
        WHERE workflow_run_id = run.workflow_run_id
          AND project_id = run.project_id
 ) AS events;

ROLLBACK;
