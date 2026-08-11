# Testing and release

## Test architecture

Every invariant has one direct test owner and only the necessary
cross-boundary acceptance coverage. Fixed shapes stay in contract tests,
relational and locking behavior stays in PostgreSQL tests, and pure workflow
rules use small typed fakes. Tests do not reproduce Pydantic library behavior
or duplicate the same rule at every layer.

| Directory | Responsibility |
|---|---|
| `tests/mcp/` | App Service domain, adapters, identity, authorization, configuration, repository, telemetry, and lifecycle |
| `tests/workflows/` | Portable jobs core, adapters, seven workflows, agent runtimes, Spark, and DBML publication |
| `tests/contracts/` | Public schemas, canonical assets, actor registry, cross-runtime parity, and forbidden dependencies |
| `tests/database/` | Static SQL checks plus catalog, privilege, behavior, and concurrency assertions |
| `tests/acceptance/appservice/` | App ZIP allowlist, reproducibility, extracted boot/restart, protocol, and end-to-end state |
| `tests/acceptance/release/` | Databricks source-release allowlist, identity, imports, and reproducibility |
| `tests/acceptance/workflows/` | Cross-module workflow behavior such as post-commit Mapping retry |
| `tests/support/` | Test-only fakes, Easy Auth envelopes, disposable containers, and fixtures |

No test or test-support file is copied into either production deployment.

## Database and external safety

Local and CI database tests create their own disposable PostgreSQL 18 container
with random credentials, a random database, and a per-run sentinel. They reject
user, environment, default, local-service, Azure, staging, and production DSNs
before connecting. Only a validated local Unix Docker socket is accepted.
Container disposal is the only cleanup mechanism.

Azure-marked tests are excluded from T24. The separately approved T25 fixture
is the only path allowed to use its own sentinel-guarded disposable Azure
database. Tests never mutate the reference workspace or make production code
depend on `reference_snapshot/`.

## Verification layers

| Layer | Required rejection evidence |
|---|---|
| Formatting, lint, and typing | Invalid source, dependency direction, or type use fails before runtime tests |
| Contract conformance | Generated schemas, examples, capabilities, registry, deployment definitions, and canonical bytes match code |
| MCP and workflow suites | Authorization, actor separation, state machines, idempotency, limits, redaction, and workflow rules hold |
| PostgreSQL harness | All catalog, privilege, trigger, revision, lock, append-only, and concurrency groups pass against the disposable fixture |
| Spark suite | Pinned Python, Java, PySpark, and Spark environment executes all Spark-marked non-Azure tests |
| Artifact builds | Two independent Databricks source builds and two App ZIP builds have identical bytes and valid allowlists |
| Packaged acceptance | The selected extracted ZIP boots against disposable PostgreSQL and survives a restart without an alternate code path |
| Supply-chain gates | Secret/boundary scan, licenses, SBOMs, frozen dependency audits, manifests, and source/revision bindings pass |

The packaged App Service acceptance path uses the exact built ZIP and a
fixture-only promotion record. It verifies human/workload inventories and
resources, pagination, readiness, snapshots, DBML, durable receipts, safe logs,
stale revisions, expiry, locks, and restart behavior. Its recorded workflow
sequence covers Profiling, Analysis, Conceptual, Logical, externally fixture-
registered Silver, Mapping, Dimensional, externally fixture-registered Gold,
and final Mapping. The fixture promotion proof is never valid T24 evidence.

Coverage reports are required and their file/statement totals must reconcile,
but coverage percentage is report-only. Traceability and rejecting invariant
tests, not a percentage threshold, determine completeness.

## Canonical verification entry point

[`scripts/verify_local.sh`](../../scripts/verify_local.sh) is the shared local
and CI entry point. It validates execution provenance and workspace isolation
before creating a bounded randomized artifact directory. Its ordered gate is:

1. workspace, reference, manifest, and traceability checks;
2. frozen MCP sync, script/MCP quality checks, tests, and coverage;
3. the complete disposable PostgreSQL harness;
4. frozen jobs quality checks, non-Spark tests, and coverage;
5. the pinned Spark container suite;
6. two reproducible Databricks source builds plus import and seven-definition
   smoke checks;
7. two reproducible App Service ZIP builds plus extracted boot;
8. boot/restart/read end-to-end tests against the selected ZIP;
9. secret/boundary, license, SBOM, and approved dependency-audit gates; and
10. validation and writing of the exact evidence set.

Any failure, error, skip, xfail, xpass, warning, missing partition, flaky retry,
unavailable Docker prerequisite, or unexplained artifact blocks release
evidence.

## CI modes

Gate mode and evidence-provenance profile are separate values.

| Trigger | `GDS_RELEASE_GATE_MODE` | `GDS_CI_GATE_PROFILE` | Meaning |
|---|---|---|---|
| Local default | `deterministic` | Not CI | Runs the deterministic matrix without external OSV queries; it cannot claim complete T24 |
| GitHub push or pull request | `deterministic` | `ci-deterministic` | Runs the same deterministic posture on pinned Ubuntu, Python, uv, and actions |
| Explicit local release invocation | `release` | Not CI | Requires exact operator consent for dependency disclosure and the complete T24 run |
| Protected `workflow_dispatch` | `release` | `ci` | Runs the complete gate only through the `t24-release-approval` environment |

CI has read-only repository permissions, checks out the exact revision without
persisted credentials, cancels superseded runs, retains deterministic outputs
for 14 days, and retains protected release outputs for 30 days.

## Release evidence and promotion

Only a complete approved release-mode run writes the promotable
`evidence/release/verification.json` and its human-readable Markdown companion.
The record binds:

- validated local or GitHub Actions provenance and one clean Git revision;
- exact ordered gate outcomes with no adverse test result;
- tool, Python, container, PostgreSQL, Spark, and dependency versions;
- MCP/jobs coverage and complete PostgreSQL result schemas;
- contract, lock, workflow-deployment, and source-release identities;
- reproducible Databricks source and App Service artifacts;
- ZIP and source manifests/digests;
- scans, licenses, SBOMs, and both approved OSV audits; and
- the exact App Service ZIP eligible for selection.

[`select_release_artifact.py`](../../scripts/select_release_artifact.py) accepts
only that evidence directory. It has no direct artifact override. It rechecks
clean source identity, symlink and write safety, sidecar and artifact hashes,
the ZIP allowlist, every embedded digest, locks, contracts, dependency closure,
workflow deployment identity, and source revision before returning the ZIP path
and SHA-256 together.

Deployment must reopen that path without following symlinks, verify the digest,
and upload from the same open file descriptor. A selector result is not a safe
license to reopen and upload an unchecked path later.

At runtime, mutation registration requires all four values atomically:

1. `GDS_MUTATION_ENABLED=true`;
2. `GDS_T24_RELEASE_EVIDENCE_PATH`, an absolute path to the read-only external
   evidence file;
3. `GDS_T24_RELEASE_EVIDENCE_SHA256`, the SHA-256 of those exact evidence
   bytes; and
4. `GDS_RELEASE_ARTIFACT_SHA256`, the SHA-256 of the running App Service
   artifact.

When `GDS_MUTATION_ENABLED=true`, missing, writable, deterministic-only, stale,
failed, or mismatched proof leaves the application unready. Missing proof is
valid in the default read-only posture. Successful promotion registers only the
mutating tools already allowed for the authenticated actor and enables
authorize/revoke. It does not replace per-request authorization, grants, locks,
revisions, database roles, or transaction checks.

Release evidence is a binary-conformance proof, not authorization to deploy or
change an external environment. The evidence is unsigned, so platform
operations must protect the selected ZIP, settings, and evidence mount and must
deploy the exact selector-returned digest. A future provider-signed attestation
would be a new trust design, not an implicit property of T24.

## T24 and T25

| Gate | Scope | Result |
|---|---|---|
| T24 | Complete clean-checkout local/protected-CI conformance, reproducible artifacts, disposable local PostgreSQL, supply-chain checks, and consented OSV audits | A content-addressed release record that may satisfy runtime mutation-promotion proof |
| T25 | Separately authorized environment installation and validation of Azure PostgreSQL, App Service, Easy Auth, identities, policy, Databricks, Foundry, Unity Catalog, release smoke, and external operational evidence | Environment-specific deployment/release evidence; never inferred from T24 |

Local completion stops at T24. T25 remains `EXTERNAL` until a user explicitly
authorizes it and the guarded environment evidence genuinely exists. See
[Current gaps and external boundaries](14-current-gaps.md) for observed status;
do not encode a temporary blocker as intended architecture.

When a work package changes behavior, add or identify its rejecting test, run
focused and affected suites, review architecture and security/data integrity,
then update [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md) and
[`docs/traceability.md`](../traceability.md). Never edit generated evidence to
make a failed gate appear successful.

Authoritative sources:
[`local verification runbook`](../runbooks/local-verification.md),
[`CI workflow`](../../.github/workflows/ci.yml),
[`tests/README.md`](../../tests/README.md),
[`promotion.py`](../../mcp_server/src/gds_etl_workbench/promotion.py),
[`App Service selector`](../../scripts/select_release_artifact.py),
[`release status`](../../IMPLEMENTATION_STATUS.md), and
[`invariant traceability`](../traceability.md).
