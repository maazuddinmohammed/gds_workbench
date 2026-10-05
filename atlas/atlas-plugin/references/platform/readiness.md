# Decide the next SDLC step

Readiness belongs to the selected artifact/scope, not one global Model stage. Derive a compact brief from current records and checks; task progress helps locate work but cannot prove freshness, approval or completion.

## Retrieve and classify

Use `status` for the selected task, `inspect` for installed catalogs, bounded `select` for relevant effective/applied records, and `review` for pending changes. Use authoritative server reads for current Model revision, scope and operation state. Follow [focused reads](../tools/reads.md) and actual command contracts; these helpers do not return a computed business-readiness verdict.

For each requested artifact, distinguish missing, applicable applied work, pending draft, known stale input, blocked/protected work and unresolved evidence. These are report categories, not new persisted record statuses. Bind conclusions to actual Snapshot IDs/revisions, selected canonical keys and draft digests. Missing/truncated evidence remains unknown. A changed Model revision alone does not invalidate every artifact.

## Prerequisites and completion evidence

| Outcome | Required inputs | Evidence of requested completion |
|---|---|---|
| Source analysis | Authorized exact sources; Model Input Scope for Model work; known population/protection for execution | Selected-input coverage, supported key/grain/relationship findings, measured versus inferred claims and explicit gaps. |
| Conceptual model | Scoped physical evidence and/or attributable requirements | Clear concept meanings, real supports, relationships and conceptual quality review. |
| Logical model | Eligible scoped evidence, actual naming/schema/key/audit policy | Supported grain/identity, normalized design, relationships/lineage/Submodels, whole-graph and coverage checks. |
| Dimensional model | Active applied Logical Entities/Attributes; no compulsory physical Silver registration or Logical Mapping | Defensible analytical grain, conformance, measures/history and cross-process review. |
| Mapping | Active applied target Entities/Attributes and eligible inputs | Complete target/System coverage and independently usable transformation instructions; missing branches remain explicit. |
| Code generation | Applied nonempty Mapping and applied target model; all five consumer-context components | Exact SQL/file/record content, valid System assignments and translation checks. Partial Mapping permits labeled incomplete drafts, not a claim of business correctness. |
| SQL Validation definitions | Applied complete Mapping; actual relevant Code if implementation is tested | Purposeful checked definitions with independent expectations/populations. Definitions alone are not executed evidence. |
| Target registration | Applied selected logical/dimensional targets and confirmed owner/placement | Compatible Metadata records checked per owner; requested DDL separately labeled generated, not executed. |
| Process registration | Applied Code/Mapping, assignments, registered targets and confirmed runtime details | Compatible complete Process identities, intended dependencies and checked Metadata; no implied upload or execution. |

Reuse applicable outputs and ask only about uncertainty that changes the result. For an upstream change, inspect actual affected dependencies using [change impact](../methods/change-impact.md); mark uncertain effects rather than claiming an exhaustive graph. Use [Model enrichment](../model/enrichment.md) for source findings; check [capabilities](capabilities.md) for unavailable interfaces.

The working brief needs only: requested outcome/scope, verified owner/Model, input bindings, relevant drafts, SQL policy, unresolved decisions, readiness evidence and next necessary action. Store supporting evidence in existing task fields. Do not create another stage ledger, permission model or automatic Apply rule.
