# Model redesign proposal (draft)

Temporary working files for discussion. Edit anything. Nothing here is installed,
and the real `database/*.sql` files are unchanged.

| File | Replaces |
|---|---|
| `00_reference_lists.sql` | additions to `database/01_reference.sql`: type lists you can extend with an INSERT |
| `01_subject_areas.sql` | `database/06_workflow_conceptual.sql` |
| `02_logical.sql` | `database/07_workflow_logical.sql` |
| `03_dimensional.sql` | `database/08_workflow_dimensional.sql` |
| `04_runs_and_checks.sql` | new: runs by subject area, Validate results |
| `05_ai_output.md` | what the AI sends back, and what the backend fills in |

## The rule for every column

A modeling column stays only if a later step reads it. Each column's comment says who
fills it and who reads it.

| Code | Reader |
|---|---|
| BUILD | the next Build or Optimize call (reads the saved model back) |
| DIM | Dimensional workflow |
| MAP | Mapping workflow |
| CODE | Code generation |
| VAL | Validate (data checks on Databricks) |
| DDL | Databricks DDL download |
| REG | Silver/Gold registration export |

| Filled by | Meaning |
|---|---|
| AI | the model writes it; only judgment calls |
| backend | computed; the AI never sends it |
| you | set by a person in review |

Control columns (`is_active`, `is_locked`, `workflow_run_id`, times) stay for
governance: locks, lifecycle and audit.

## What changes overall

1. **Subject areas replace** Conceptual concepts and both Submodel families
   (Logical and Dimensional).
2. **An entity's subject areas are worked out**, not stored: the areas of the tables
   it is built from.
3. **The AI stops sending what the backend can work out:** ids, column order,
   dependency order, surrogate keys, audit columns, lock flags, the parent key of a
   relationship, relationship optionality and kind.
4. **Text only where a later step needs it:**
   - An attribute definition defaults to the source column's description.
   - A source rationale is needed only when it isn't a straight copy.
5. **One `is_active` flag** replaces active / inactive / deprecated. Every reader only
   asks "is it active?".
6. **Dropped from every model table:**
   - `agent_run_id`: legacy; `workflow_run_id` already records the run.
   - `created_by`, `updated_by`: they always hold the database login
     (`CURRENT_USER`), never a person.
7. **Relationships always point child → parent:** from the foreign-key column to the
   parent entity. Many-to-many becomes an association entity, which is proper
   normalization anyway.
8. **No separate grain column:**
   - The definition's first sentence says what one row is ("One row per order line").
   - The natural-key columns are the same grain in a form Validate can check.
9. **Label lists live in reference tables:** Logical entity types and fact types. Adding a
   value is one INSERT, and the prompt, validation and dropdowns pick it up. Lists the
   backend acts on (fact / dimension / bridge, cardinality, check codes) stay fixed.

## Why it matters for scale

Today one Logical attribute in the AI's answer is about 790 bytes. In the shape in
`05_ai_output.md` it is roughly 120–200 bytes. One answer can then hold about 4–6
times more attributes, so subject areas can be bigger and calls fewer (estimate).

## Dimensional: same subject areas, its own three runs

- **No separate subject-area step.** Dimensional reuses the same subject areas.
- **Dimensional Build** for Sales works on the Logical entities built from Sales tables
  and produces Sales facts and dimensions. Each call sees:
  - the area's Logical entities in full;
  - Dimensional entities already built from them, to reuse or update;
  - a one-line list of all Dimensional entities, so it reuses `Date` instead of
    making a second one.
- **Dimensional Optimize** makes each shared dimension (Date, User) one table across
  areas.
- **Dimensional Validate** checks on the real data that each fact's grain is unique
  and that every fact row finds its dimension rows.

## Open points

1. Attribute definition default: copy the source column's description when the AI
   leaves it out. Agree?
2. Drop relationship names: the foreign-key column's name already carries the role
   (`BillingCustomerID`). Diagrams would show column names instead of verbs.
3. Keep `logical_entity_type` as a cheap hint for Dimensional, or drop it?
4. Size cap per subject area (for example 300 columns) so every Build call fits.
5. Mapping, Code and Validation tables are not trimmed in this pass.
