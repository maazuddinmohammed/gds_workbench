# Plugin output-quality review

Date: 2026-09-10. Scope: packaged GDS plugin, shared validation and inference,
local helpers, workflow instructions, and user guide.

## Finding

The RCA describes an applied, structurally valid model whose business design
was not established. The failure is systemic: the workflow makes transport,
scope counts and schema checks executable, while grain, identity, dependencies
and relationship decisions depend on prose that an agent can skip.

Adding more instructions alone will not establish quality. The repair needs
executable evidence checks, a persistent decision handoff, useful aggregate
investigation tools, and evaluation of actual modeling decisions.

The supplied RCA is the evidence for the original session. Its transcripts,
Snapshots and applied model were not supplied here. Local reproductions use
fictional fixtures and actual repository functions; they establish specific
product defects, not an independent reconstruction of the original session.
The RCA's numerical allocation of responsibility is an opinion, not a measured
causal attribution. No live Model, Databricks data or external system is changed
by this review.

The RCA reports seven scoped Objects, seven Concepts and seven Logical Entities;
87/87 business Attributes with single-source lineage; 70 audit Attributes plus
seven surrogates; five unresolved Analysis results without deterministic counts;
and two active Logical relationships, only one crossing Entities, leaving six
connected components. These are reported session figures, not independently
remeasured here. Their shape warrants investigation, not an automatic verdict
that every one-to-one representation or isolated Entity is wrong.

## Confirmed failure mechanisms

The table records the implementation inspected before these repairs.

| Area | Repository evidence | Consequence |
| --- | --- | --- |
| Readiness | `plugins/v2/gds/skills/gds/SKILL.md` lifecycle says a valid result is ready | Schema success becomes the completion signal despite missing modeling evidence |
| Analysis | `references/workflows/analysis.md` delegates determinants, grain and composite keys to notes | No executable completeness or cross-phase check |
| Evidence retention | `references/session.md` uses task-local freeform object notes | Metadata investigations can disappear at task boundaries |
| Delegation | `references/guided-journey.md` specifies model choice but no semantic acceptance contract | Separate agents can complete incompatible phases |
| Numeric inference | `features/metadata_enrichment/inference.py` and plugin SQL derive precision from observed width | Tiny samples produce decimals unable to hold ordinary future magnitudes |
| Analysis integrity | `domain/modeling_records.py` checks all-or-none validation fields | A claimed supported result can contradict its own orphan counts |
| Model relationships | Logical relationships have no structured Analysis reference | Confidence and narrative basis cannot prove relationship support |
| Phase routing | `references/workflow-targets.md` nests Profiling inside Logical Build | A small profiling request lacks an explicit stop boundary |
| Review | `references/server-handoff.md` emphasizes authoritative action counts | User can approve a large graph without seeing weak keys or isolated entities |
| Snapshot recovery | `scripts/gds-local.js` and `.ps1` compare whole records literally | Optional null defaults and Decimal JSON representations prevent retirement |

Paths above are relative to the plugin skill, backend or MCP area as indicated.

### Reproductions

1. Before repair, the actual sample inference function returned `DECIMAL(5,5)` for two values
   near zero. The same function is used by backend enrichment; the plugin SQL
   duplicates this behavior. Existing tests explicitly expected narrow types.
2. The real `validate_future_graph` accepted a complete synthetic graph after
   Analysis is made unresolved while Conceptual and Logical relationships stay
   active. It also accepted removal of Logical relationships while keeping the
   Conceptual edge, and removal of every Logical natural-key flag.
3. A deterministic Analysis result labeled supported passed shared record
   validation even when its own missing-target count is nonzero.
4. The actual Snapshot helper rejected backend-normalized nested `source_order:
   null` additions and equivalent profiling Decimal strings. Exact records pass;
   genuinely changed definitions and numbers correctly fail.
5. Snapshot cleanup ran inside the rollback region after local retirement.
   A cleanup failure can restore the old Snapshot after pending work was retired.
   This is an additional recovery defect discovered during inspection.

## What good output requires

### Metadata definitions

Definitions should explain the represented occurrence, role and known domain
meaning. An Attribute definition should clarify distinctions that matter:
identifier domain, unit, date/time semantics, code meaning or null behavior where
supported. Rewording a physical name does not establish those facts. Generated
descriptions remain hypotheses; later phases must not cite them as independent
confirmation of their own interpretation.

Missing business context should lead to a focused question or a bounded
investigation. Filling every description with plausible text is worse than
leaving an explicit uncertainty. Preserve useful source comments and existing
approved definitions. Do not invent acronym expansions, code meanings or units.

### Profiling and Analysis

Column statistics answer how populated or varied individual fields are. They
cannot establish tuple uniqueness, dependencies or joins. Standard Profiling
should remain deterministic and easy to execute. Analysis needs comparably
accessible aggregate probes for keys, dependencies, relationship coverage and
conversion failures.

An investigation must retain its selected Objects, row/batch scope, Snapshot
identity, observation time, aggregate findings and resulting decision. Empty
tables and partial samples are inconclusive for universal business rules.
Source and target scopes can differ: recent transactions may refer to historical
master data. Equal values prove neither shared identity nor the meaning of a role.

Composite keys and dependencies must be tested as tuples. Separate uniqueness
checks of each column cannot prove or disprove a composite key. A generated
surrogate does not resolve missing business identity, deduplication or lifecycle.

### Conceptual and Logical design

Conceptual should explain activities and business occurrences in shared
vocabulary. Logical should separate independently identified occurrences and
lifecycles, and place descriptors with the determinant that owns them.

One source table may contain several entities; several sources may describe the
same concept. Shared structure does not authorize merging equal local IDs across
Systems. Retain source-qualified identities until a crosswalk or confirmed rule
establishes sameness. Repeating groups require an atomicity and lifecycle
decision; their string storage does not make them atomic business attributes.

Do not split every repeating description into a lookup. A normalized source can
legitimately map directly into a Logical entity. Isolated reference data can be
legitimate. Shape metrics should trigger an evidence-based challenge, never a
quota for entities, joins or splits.

An active relationship needs supported existence and endpoint roles. Unknown
Conceptual cardinality can represent supported existence with unresolved
multiplicity; it cannot turn an unproven relationship into a fact. Logical foreign
keys additionally require supported cardinality and a defined source-key to
target-key lookup. Low confidence is not a substitute for that evidence.

Every Conceptual relationship needs an explicit Logical implementation or an
explained defer/reject decision. Type changes need conversion evidence and
invalid-value behavior. Audit columns belong to the approved framework policy;
they are not evidence of business completeness.

### Numeric capacity

Use authoritative declared precision when available. A small sample can suggest
syntax but cannot establish target bounds. Sample-based decimal inference should
reserve available precision and remain provisional. Full-scope conversion and
range checks, business capacity and required scale determine the final target.
Even `DECIMAL(38,s)` is finite; scale 38 leaves no integer digits. Widening alone
does not prove that all data or future values fit.

## Implemented repairs

Changes were made and checked in cohesive slices:

1. Corrected shared/plugin sample decimal inference to reserve precision 38 while preserving authoritative types and marking sample capacity provisional.
2. Shared deterministic Analysis count/verdict checks across Python, JavaScript and native PowerShell, including matched-distinct conservation. All-null unresolved evidence remains valid.
3. Added a separate local modeling evidence report, generated decision scaffold and computed graph diagnostics. Acceptance and Stage Runner bind report, decisions, cited notes and supporting Snapshot manifests. Changed evidence invalidates handoff before writes. Large-graph name examples are bounded; totals and decision coverage remain complete.
4. Added `analysis-plan` for composite keys, functional dependencies and directional joins, using registered coordinates, explicit all-row scope and one aggregate result per query. Profiling now reports direct/inherited masking exclusions and produces no SQL for fully masked Objects. It generates SQL without execution. Custom expressions, inferred casts and batch predicates are excluded from this planner; targeted conversion evidence still requires a separate governed investigation.
5. Repaired retirement-only comparison for declared defaults, exact decimal equivalence and server-reordered modeled sources/supports/submodels. Approval byte digests stay exact. Recoverable retirement backups and the installation commit boundary preserve pending work when local cleanup fails.
6. Rewrote workflow guidance and the user guide around useful definitions, dependency evidence, complete identities, relationship decisions and recovery. A modeling owner retains current reasoning across phases. Phase-only requests stop at that phase. Missing full audit templates require policy confirmation. Capability discovery precedes lock-unavailable claims.
7. Evaluated realistic design exercises independently and rebuilt matching local packages; verification details below.

No new foundational MCP tools, populated-database migration, policy bypass,
automatic Apply, new Model dataset or external deployment is needed for these
plugin improvements. Local quality checks supplement authoritative server
validation; they cannot verify the truth of user statements or an agent's prose.

## Quality review shown to the user

Before existing acknowledgement and Apply boundaries, show:

- Entity grain and natural/composite identity; unresolved lifecycle decisions.
- Relationship existence/cardinality evidence, missing targets and duplicate
  target keys, plus unresolved candidates.
- Cross-entity edges, self-references, connected components and isolated entities.
- Source-to-concept/entity support and single-source Attribute lineage share.
- Business Attribute count separately from audit columns and generated keys.
- Normalization choices, justified exceptions and Conceptual-to-Logical gaps.
- Type conversions, bounded evidence limitations and excluded sensitive inputs.

The schema describes Attribute lineage, not typed transformations. Therefore a
single physical source does **not** prove a direct copy; it may be cast or derived.
Report the measurable lineage ratio accurately. Do not label it a copy percentage
unless actual transformations were inspected.

## Evaluation and release confidence

Executable regressions must exercise failing behavior, not only assert that a
guide contains phrases. Use independent modeling exercises with fictional inputs:

| Case | Necessary behavior |
| --- | --- |
| Denormalized order lines | Separate header/line grains; avoid duplicated order measures |
| Already-normalized sources | Preserve a justified one-to-one structure |
| Overlapping IDs in unrelated CRMs | No unproven cross-System identity merge |
| Unresolved join | Investigate or defer; do not activate by relabeling confidence |
| Same names, different roles or lifecycles | Preserve distinctions |
| Empty/sample-only numeric data | No claim of proven key, capacity or full conversion |
| Updated run-state observations | Resolve run versus observation identity |
| Legitimate isolated reference object | Explain isolation; never invent an edge |

Compare plain-prompt and plugin-assisted results on the same evidence and desired
outcome. Score correctness of grain, dependencies, identity, relationships,
definitions and uncertainty handling separately from command count and elapsed
time. Measure full workflow effort including failed commands, repeated questions,
and user corrections. The plugin earns its cost only if it adds reliability or
quality beyond an ordinary prompt.

Unit and contract tests establish mechanical behavior; an independent exercise
establishes behavior on that exercise only. Neither justifies a universal output
quality score. A production re-evaluation requires a new governed modeling pass
against the actual authorized data and business rules.

## Independent design exercises

A plain-prompt agent and a fresh agent using the revised skill received the same
fictional order/customer/product evidence and an offline design request. Neither
was shown the RCA, implementation findings, or intended answer. This compared
design reasoning; it did not exercise live tools, Stage, Apply or elapsed workflow
cost. Both produced the key header/detail split and preserved historical address
meaning. The plain prompt was already strong; this exercise does **not** show a
quality or speed advantage for the plugin.

The revised-skill agent produced actual Order, OrderLine, SalesCustomer and Product
designs, with full source-qualified business identities and surrogate lookups. It
kept ambiguous line-price semantics unresolved, deferred unsupported Service
identity, and did not invent a fiscal-period join or numeric capacity from tiny
samples. These are observed decisions, not a score inferred from instruction text.

One weakness remained: it treated complete join coverage as required participation
without explicit source-null evidence. The Analysis guide now distinguishes those
facts. A second fresh exercise used 100 Invoices, 80 populated supplier references,
75 matched suppliers and 90 unique suppliers. The agent correctly proposed optional
many-to-one participation, including 20 unassigned invoices and 15 unused suppliers.
This demonstrates the corrected case only, not universal reliability.

The executable suite separately covers an already-normalized source, unresolved
relationships, wrong lineage/cardinality, composite surrogate identity, append-only
identity with documented support, stale evidence, and large disconnected graphs.
The tests do not award points for adding Entities, relationships or prose. Final independent code review also found and prompted a regression for known Conceptual cardinality: supported row counts alone must not pass a contradictory one-to-one claim; unknown cardinality and documented business-grain evidence remain distinct.

A local diagnostic microbenchmark used 10,000 synthetic Entities and 10,000
Attributes. The evaluator retained all 10,000 component/isolated counts while
limiting name examples to 200; its result was 6,080 bytes and evaluation took
59 ms in that run. This measures the in-memory evaluator only: no Snapshot I/O,
schema validation, authored-decision review or SQL execution was included.

## Verification and local delivery

- Broad MCP/backend regression run: 2,543 passed; its one failing fixture claimed
  supported Analysis despite orphan/impossible overlap counts. Corrected that
  fixture and reran the failing database regression successfully. The new probe
  SQL and Analysis database suite separately passed 19 checks.
- Notebook suite on Python 3.12: 161 passed. Web packaging: 61 passed.
- JavaScript Workbench/helper suite: 95 passed. Stage Runner: 92 passed;
  TypeScript check, bundle and VSIX build succeeded.
- Final plugin Python suite with native PowerShell 7: 352 passed, including
  packaging. Evaluator outputs, byte-identical reports and evidence bindings
  match JavaScript; native Snapshot/profiling/Analysis regressions pass.
- Both Python project Pyright checks reported zero errors/warnings. Changed
  Python/tests passed Ruff; skill frontmatter and whitespace checks passed.
- Instructions remain within existing limits: 12,995 words across skill Markdown;
  the Logical path including the new quality guide is 6,056/6,100 words.
- Plugin ZIP, Stage Runner VSIX and generated extension bundle were rebuilt.
  All 12 packaging checks passed, including artifact/source equality.

Local packages: `plugins/v2/dist/gds-agent-plugin-0.5.0.zip` and
`plugins/v2/dist/gds-stage-runner-0.1.1.vsix`. Install matching packages together.
The human guide is `plugins/v2/gds/docs/USER_GUIDE.md`; the plugin's conditional
agent references are under `plugins/v2/gds/skills/gds/references/`.

These are local artifacts, not an installed or deployed release. Shared MCP/backend
Python changes take effect when those services are separately built/deployed through
the approved process. No external publishing, service deployment, live SQL or Model
Apply was performed.

## Remaining limits

- The actual CBCM model and data were not replayed or repaired in this task.
  Re-evaluation needs its authorized Snapshots, business evidence and a governed
  modeling run. This is the necessary next evidence for a production-quality claim.
- Citations, tuple declarations and count arithmetic are checkable. Whether a
  definition, normalization decision or business Assertion is true remains a
  modeling/reviewer responsibility. A filled note is not proof.
- Existing `analysis_result` records describe individual Attribute pairs.
  Composite measurements stay in sanitized notes; a composite surrogate lookup
  needs applicable documented business support. No new Model dataset was added.
- SQL probes were exercised on disposable PostgreSQL with quoted-identifier
  translation and checked against the governed SQL parser. No Databricks execution
  occurred; runtime planning/execution cost on production volumes is unmeasured.
- Native PowerShell 7 ran locally. Windows-specific file handles and PowerShell 5.1
  remain covered by the repository's Windows CI requirement.
- Local acceptance created by older helpers has no evidence binding. Revalidate
  and acknowledge the current modeling result before resuming handoff with the
  new helper/runner. Invalid historical deterministic counts need fresh evidence;
  the repair adds no populated-database cleanup or migration.

## RCA qualifications

- The Conceptual guide prohibited persisting the process matrix **as Model
  records**, not as sanitized task evidence. Clarify retention rather than adding
  another Model schema solely for that matrix.
- The lock-acquisition instructions already authorized an ordinary free lock
  after acknowledgement. This was primarily a capability-discovery/agent
  compliance failure; preserve ownership and override protections.
- The reported Windows handle failure cannot be reproduced on macOS. Do not
  replace atomic directory installation with unsafe partial copying. Give a
  bounded close-and-retry recovery and retain Windows-specific tests.

## Cursor article: applicable lessons

[Towards self-driving codebases](https://cursor.com/blog/self-driving-codebases)
describes experiments with role ownership, useful handoffs, fresh context and
empirical iteration. Its throughput tradeoffs do not justify weaker Apply gates.

Our adaptation: keep a modeling owner, delegate bounded evidence investigations,
retain current decisions, simplify repeated instructions, and evaluate actual
models. Avoid making the repair another large checklist or coordination system.
Use deterministic tools where facts can be checked and independent judgment where
business meaning must be assessed.
