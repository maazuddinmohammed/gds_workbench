# Existing Analysis review: Tenant fence race

Read-only production investigation, 2026-09-05. Only scratch tests and this design
were added. No production SQL, privileges, routes or record-family changes.

## Actual reproduction

`.scratch/test_model_review_tenant_fence_reproduction.py` uses only the existing
fixture-created disposable PostgreSQL container. It seeds two Models in one
Tenant, a real Analysis result in Model A and a properly created Profiling Run in
Model B. Calls use the real web runtime role, `DatabaseModelChangeSetService` and
`application.start_workflow_run`; no providers or external data execution.

- **Start first:** B's start returns `running` inside an uncommitted transaction.
  A's review still finishes and commits before that transaction releases its
  locks. Its running-Run query cannot see B's uncommitted update.
- **Review first:** a test barrier pauses A immediately after its real no-running
  query returns false. B starts and commits while A holds its locks; A then
  continues and commits using the earlier result.
- **Control:** a committed start in B is already rejected correctly by A's review.
- **Privilege control:** `gds_web_write` has Tenant Lock SELECT but no UPDATE on
  any column. An actual `SELECT ... FOR UPDATE` as that role raises
  `InsufficientPrivilege`. Adding a direct backend locking query would fail.

The first two tests assert the current incorrect overlap deliberately; promote
them with inverse ordering assertions when the implementation changes.

## Why this happens

`features/model_change_sets/service.py::review_records` currently takes Model A
FOR UPDATE, then calls `authorize_tenant(...TENANT_MODEL_WRITE)`, which takes
Tenant Lock SHARE (`database/03_security.sql`, around line406). It next checks
`has_running_tenant_workflow` with a plain SELECT. Run start takes Run/Model B
FOR UPDATE and the same Tenant Lock SHARE (`database/13_application_workflow_runs.sql`,
around lines2179–2193). Different Model locks and compatible SHARE locks provide
no Tenant-wide serialization. The unique-running-Run index prevents two Starts,
but a review does not insert into that index.

## Minimal governed SQL boundary

Add one narrow `application.authorize_model_record_review` function in SQL14:

```
(entra_tenant_id UUID, entra_object_id UUID, expected_principal_type VARCHAR,
 tenant_id BIGINT, model_id BIGINT)
-> denial_code, principal_id, model_id, tenant_id, model_name, model_revision
```

Use `LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog`,
fully qualified names, PUBLIC revoke and EXECUTE only for the existing web role.
Register it in SQL19/20 integrity/privilege checks and web readiness as appropriate.
It changes no rows and grants no direct lock-table mutation rights.

Its exact order:

1. Reject malformed IDs or a principal type other than `user`.
2. Select the requested active Model belonging to the requested Tenant FOR UPDATE.
   A missing/foreign Model returns the existing safe unavailable outcome.
3. Run existing `tenant_read` authorization before taking the exclusive Tenant
   fence. Preserve identity/access denial behavior; no caller-supplied actor ID.
4. Lock that exact `security.tenant_lock` row FOR UPDATE.
5. Run existing `tenant_model_write` authorization **after** the wait. This
   rechecks effective role, real lock owner and current clock-based expiry.
6. Return only the authorized principal ID and existing Model header, or a safe
   denial code with null result fields.

The function owns Model-first ordering, so callers cannot accidentally take only
the Tenant fence before their Model lock. It does not call write authorization
before Tenant FOR UPDATE: upgrading two concurrent SHARE holders would deadlock.
It does not lock any other Model or Run. Existing physical review already holds
Tenant FOR UPDATE and never then locks Models; preserve that order.

In `model_change_sets/repository.py`, add the fixed query/method for this helper.
In `review_records`, replace its initial Model-read/write-authorization pair with
this one result; map denial codes to existing safe errors. Preserve all remaining
selected-ID validation, full-graph validation, field-only update, revision and
audit behavior. Other Model operations and global `authorize_tenant_operation`
SHARE semantics remain unchanged.

Keep replay **after current authorization but before stale-revision/running-Run
checks**, as it is today. Therefore the helper itself must not reject running
Runs. After an unknown-response retry, an already applied receipt remains readable
even if another Run subsequently started. New reviews check running state while
the exclusive Tenant fence is held. Keep review transaction READ COMMITTED
(`WebPostgresDatabase.write_transaction` current default): the post-wait query
must see the committed Start. Do not silently switch this boundary to a snapshot
fixed before the wait.

Holding the exclusive row lock prevents owner changes, but time still passes.
For a long validation/read, recheck existing write authorization immediately
before mutations (already holding the stronger lock), as physical review does.
Do not add a second write-auth SHARE acquisition before the exclusive fence.

## Production gate to promote

- Start-first: A review waits while B's start transaction is held; after B commits,
  review returns `tenant_workflow_conflict`, with unchanged Analysis/Model/audit.
- Review-first: B start waits while A holds its review transaction; after review
  commits, B starts normally. No lock upgrade or cross-Model deadlock.
- Concurrent reviews in different Models serialize on the one Tenant fence;
  same-Model review/start retains existing revision fencing. Include physical
  review overlap using its real governed function, not a mocked lock.
- Replay after a subsequent Run start returns the original receipt; changed-key
  payload still conflicts. Wrong role, owner, expired/missing lock, foreign Model,
  inactive Model and service-principal calls remain denied. Test expiry during
  the fence wait/long review before mutation.
- Direct Tenant Lock privileges remain SELECT-only; helper has the exact grant,
  definer and fixed search-path contract. No MCP tool or new lock-table endpoint.
- Existing Analysis all-four-actions/idempotency/evidence-preservation round trip
  plus HTTP error redaction still pass. No Code/Validation schema or dependency
  plan UI belongs in this slice.

## Implemented checkpoint

Governed `authorize_model_record_review` now locks the owned active Model, checks
read authority, acquires the exclusive Tenant fence, and checks write authority
after waiting. SQL14/19/20 and backend readiness enforce its web-only contract.
The service uses it first and reauthorizes immediately before mutation.

Frozen gate: **85 passed**, covering actual two-Model Start/review ordering,
Model/Model and Model/physical review serialization, PostgreSQL-observed lock
waits, expiry during waiting and validation, authorized receipt replay during a
later Run, denial/header isolation, unchanged direct privileges, readiness, and
existing Analysis/physical review behavior. Ruff, formatting and Pyright clean.
Permanent regression: `tests/web_backend/test_database_model_review_governance.py`;
missing-grant regression: `tests/web_backend/test_database_readiness.py`.
