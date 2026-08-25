# Model authoring workflow

Use this shared workflow for Conceptual, Logical, Dimensional, Mapping, Profiling,
Analysis, and Assertion authoring. The selected skill supplies the domain method;
this reference supplies the common evidence and governance boundary.

## Choose the stopping point

Infer the smallest boundary from the user's verbs. Do not ask when it is clear and
never advance beyond it.

- **Inspect:** read focused current records, answer, and stop.
- **Proposal:** return checked complete records or a compact design/diff; write
  nothing.
- **Local draft:** update only `GDS/model-change-set`; keep the Snapshot immutable.
  Do not acquire a lock or call server Change Set mutations.
- **Server draft:** use `$manage-gds-model` for create/resume, local handoff, Stage,
  Validate, or archive. Stage only the approved complete affected dataset lists.
- **Apply:** show the server's authoritative `action_review` and obtain fresh explicit
  approval immediately before `apply_model_change_set`.

If an essential local workspace, identity, evidence source, or business decision is
missing, stop at the highest safe lower boundary. Ask one smallest material question;
otherwise continue with explicit, non-blocking assumptions. Use `$grill-data-model`
only when the user requests or accepts an interview.

## Establish the baseline

1. Resolve the existing Tenant and Model. Use `get_model` only when identity, revision,
   description, or naming policy is needed. There is no public Model-create tool.
2. Read only requested records and direct dependencies. Reading a dependency does not
   make its dataset affected.
3. Preserve current naming templates and established names unless the user requests a
   change or a real collision blocks the work.
4. Use governed evidence in this order when relevant: physical Metadata and Model
   Scope, Profiling, Analysis, Modeling Assertions, accepted decisions, then clearly
   labeled assumptions. Never turn an assumption into observed evidence.
5. Call `describe_model_dataset` only for datasets that will be authored. Its live
   schema is authoritative.

## Author and check

- Draft complete, ID-free records, never patches or database IDs. Preserve every
  required nullable field and exact nested discriminator.
- Compare canonical keys with current and pending state. A key change inserts a new
  record; retire the old key only when requested.
- Keep uncertainty honest with supported confidence/status values and a named owner or
  next validation step. Never fabricate counts, relationship results, document
  provenance, mappings, or execution claims.
- Review the affected datasets only: record counts, intended effect, canonical-key
  changes, references, material assumptions/conflicts, and deferred checks.
- Do not echo full schemas, unchanged records, raw physical rows, prompts, credentials,
  temporary URLs, connection values, SQL, or unredacted tool output unless a safe
  subset is explicitly requested.

For a local draft, use `$open-gds-metadata-workbench` or the documented Model workspace
helpers and stop after local validation/review. Local validation is not server
validation.

For a server boundary, read the
[governed Model workflow](governed-model-workflow.md), route through
`$manage-gds-model`, reconcile every nonempty resumed pending dataset, and keep lock,
Stage, Validate, and Apply decisions distinct. Release a lock acquired by the workflow
at the requested stopping point when no immediate governed write follows.

## Report

Normally report no more than three bullets and 120 words:

1. result and confidence/validation state;
2. affected datasets and counts; and
3. blocker, open decision, or next governed boundary.

Approval reviews, material conflicts, and requested artifacts may be longer.
