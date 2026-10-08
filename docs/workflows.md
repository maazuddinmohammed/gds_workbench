# Workflow sources and handoffs

The SQL seeds and Python code are the maintained web workflow sources. Atlas
plugin workflows live in its [task skills](../atlas/README.md#maintainer-boundaries)
and load references on demand. The two applications share governed contracts
and orchestrate their work independently. Do not copy prompt text, schemas, tool lists or review transcripts
into this navigation guide.

| Concern | Source |
| --- | --- |
| Published default system/instruction prompts and selected readers | [seed 05](../database/seed/05_global_prompt_defaults.template.sql) |
| Installed workflow/variable reference metadata | [seed 04](../database/seed/04_application_reference.sql) |
| Mapping Output Templates | [seed 07](../database/seed/07_global_mapping_output_templates.template.sql) |
| Variable registration and projection | [prompt_inputs.py](../web_app/backend/gds_workbench_api/features/workflows/authoring/prompt_inputs.py), [context_inputs.py](../web_app/backend/gds_workbench_api/features/workflows/authoring/context_inputs.py), [downstream_inputs.py](../web_app/backend/gds_workbench_api/features/workflows/authoring/downstream_inputs.py) |
| Reader contracts, selection and paging | [context_contracts.py](../web_app/backend/gds_workbench_api/features/workflows/authoring/context_contracts.py), [context_readers.py](../web_app/backend/gds_workbench_api/features/workflows/authoring/context_readers.py) |
| Downstream variable schemas | [downstream_contracts.py](../web_app/backend/gds_workbench_api/features/workflows/authoring/downstream_contracts.py) |
| Models, limits and worker policy | [backend config](../web_app/backend/gds_workbench_api/config/README.md) |
| Candidate validation | Each backend `features/<workflow>/` contract/validator/policy and shared `mcp_server/gds_etl_workbench/application/change_sets/` graph validation |

Seeds update database configuration only when explicitly run using their documented
procedure. The application reads published database prompts, then freezes their
versions, digests, variable choices and readers for each Run. Editing source does
not silently change installed or already-running prompts.

## Evidence flow

| Workflow | Main evidence and intended output |
| --- | --- |
| Profiling | Exact selected physical Attributes and row scope → deterministic current measurements with provenance. |
| Object/Attribute Enrichment | Source context, selected physical metadata, ingestion lineage and current Profiles → Model-owned descriptions, inferred types and natural/primary key, nullability and PII findings. Human edits and locks stay Model-specific. |
| Analysis | Physical Objects/Attributes with available Model-owned enrichment, Profiles, lineage and relevant context → supported relationship inference; measured validation remains separate. |
| Conceptual | Source context, physical evidence, Analysis and applicable Assertions → business concepts and relationships. |
| Logical | Physical metadata with available Model-owned enrichment, Profiles, Analysis, Assertions and model naming/key/audit policy → normalized Entity/Attribute/relationship design. Web runs exclude Conceptual records and use the Model coverage setting (default 70%) for distinct selected Objects. After retries, below-target candidates fail when Logical enforcement is on; otherwise valid partial coverage returns with a warning when off (default). Attribute selection follows the design. |
| Dimensional | Selected applied Logical Entities/Attributes, their authorized physical support, Profiles, Analysis, Assertions and Gold policy → dimensions, facts, bridges, grains and measures. Use the Model coverage setting (default 60%) for distinct selected Logical Entities. After retries, below-target candidates fail when Dimensional enforcement is on; otherwise valid partial coverage returns with a warning when off (default). |
| Mapping | Modeled target/Attributes, eligible physical or modeled sources, support evidence, Assertions, existing protected Mapping and selected templates → Object/Attribute transformation documents per Entity/System pair. |
| Code | Applied transformation documents, their exact saved template definitions, modeled target shape, eligible sources and frozen artifact requirements → SQL artifacts with exact source-System assignment. Partial Mapping requires explicit gaps and placeholders. |
| Validation | Complete Mapping, relevant current Code, metadata and applicable requirements → deterministic Validation Groups/Checks. |

Web Attribute Enrichment reads physical evidence only for missing inferred types.
It resolves source schema and bounded samples first, then reads Bronze only for
unresolved columns. PII/masking exclusions and per-query limits still apply.
Object and Attribute authoring remain separate agent calls.

Logical defaults require evidence-based business grain, identity, normalization and
consolidation decisions. One-shot embeds enrichment, Profiles with provenance and
Analysis validation in Object/Attribute/Relationship context; tool-assisted readers
expose the same evidence across complete pages. Recorded conflicts remain visible
for design decisions; synthetic transport tests do not prove provider reasoning.
Registered natural-key metadata and Model enrichment have separate fields, including
when enrichment is unknown or disagrees. Logical defaults plan business Submodels
and Entity grain before evaluating relationships. Referenced generated surrogate
keys must be explicit candidate Attributes so initial reference validation succeeds.
Common audit fields remain backend-projected.

Profiling precedes Model-owned Enrichment. The plugin prefers Profiling → Enrichment
→ Analysis → Conceptual → Logical, reusing valid evidence and pending local records.
Refresh the Snapshot after backend Profiling; related authored phases can remain in
one local draft until reviewed submission. Actual applied downstream prerequisites
still apply. [Plugin enrichment](../atlas/atlas-plugin/references/model/enrichment.md)
uses Model Change Sets; physical Metadata correction remains separate.

Only configured variables/readers enter an agent request; do not assume an earlier
workflow's whole output is implicitly appended. One-shot and tool-assisted modes
must expose equivalent eligible evidence. Readers paginate frozen context; follow
all cursors and retain complete records. Oversized/unavailable evidence is an error,
not an empty result or permission to fabricate details.

Coverage means assessing all selected inputs and required outputs. Unsupported
relationships, fields, joins, conversions or KPI calculations must remain explicit
gaps. Examples teach format, not facts for the current Model. Preserve evidence
provenance and distinguish unknown, absent, zero, failed and contradictory states.

## Mapping and Code

Default Object templates carry sources, filter criteria and a sample query;
Attribute templates carry source columns, transformation logic and default-record
instructions. Exact definitions live in seed 07. Saved inactive/custom template
definitions still travel with documents that reference them. No template field or
nested custom value may be dropped by an internal-ID cleanup rule.

Mapping supports partial output. See [current decisions](architecture/decisions.md)
for omission, lock and failure behavior. `mapping_support_records` provides typed
paged support; target selection and output scope must not expand when support
Objects are included for interpretation.

Code reads Object-level rowset/filter/stage logic and Attribute expressions together.
Its `artifact_requirements` is only frozen file layout, selected source-System codes
and protected artifact names. SQL conventions belong in the Code Prompt, not a
second policy document. Unspecified layout resolves to `combined`; per-System
layout assigns each System once to its own transformation file. Preserve protected
files and reject conflicts rather than inventing alternative assignments.

Code omits database/framework-generated columns, retains separately named source
identifiers, and emits explicit modeled column order. The orchestration runtime owns
persistent tables, loads and merges; transformation artifacts use permitted reads
and temporary stages. Missing expressions may use typed-null placeholders with
warnings; unknown rowsets use zero-row branches. Conflicting rules remain blocking.
SQL parsing proves syntax/shape only, not live business correctness.

## Target registration

Logical/Dimensional Export produces Silver/Gold metadata workbooks from applied
Entities using their saved schemas and configured GDS placement. Metadata draft
import, validation, review and Apply register physical Objects/Attributes; they do
not create tables or bind Models to physical IDs. Process configuration and external
file placement happen later. Mapping/Code do not require this export.

## Changing a workflow

1. Change the runtime contract/projection first when evidence shapes change.
2. Update seed 04's variable reference and seed 05's prompts/readers together;
   update seed 07 only when template semantics change.
3. Verify rendering with actual registered variables and readers, candidate
   validation, complete paging, protected records and missing/conflicting evidence.
4. Exercise meaningful synthetic cases and disposable-database round trips.
   Synthetic success does not guarantee every provider's production output.
5. Rebuild affected local artifacts. Database installation and deployment remain
   separate operator actions. Use [AGENTS.md](../AGENTS.md) for checks.
