# Metadata authoring intake

Resolve information already supplied before asking. Read only the affected table pages from the [shared index](../../../references/metadata/index.md).

| Missing information | Exact question | Choices / response |
|---|---|---|
| Outcome | What metadata would you like to add or change? | User describes the result; do not force Source/Bronze choices for unrelated edits. |
| Records | Which Objects, Copy Groups, Copies, or Processes are in scope? | Names/complete keys, a supplied definition set, or an explicit bounded selection. |
| Source placement | Which registered System and Connection contain these Objects? | User supplies names/codes; list applicable choices when requested. |
| New definitions | Where should atlas obtain the definitions? | Supplied DDL, schema export, documentation, existing metadata, or permitted SQL inspection. |
| Ingestion deliverable | Do you want Source registration only, or Source and Bronze ingestion setup? | Ask only when registering a new ingestion path and intent is unclear. |
| Ambiguous value | For this field, should atlas use the documented value or preserve the existing value? | Show the actual discrepancy and its effect. |
| Custom or unclear framework usage | Please provide the relevant orchestration code or a working example showing how these fields are used. | Ask only when confirmed conventions do not resolve the requested behavior. |

SQL choices are Never, Essential, Proactive. Environment choices are `dev`, `qa`, `stg`, `prod`; `dev` is the default when needed and no selection exists. Resolve actual registered access before executing queries.

## Example: focused Copy correction

User: "For the orders Copy in the daily group, use the same landing-file naming convention as the working invoices Copy."

- Resolve the complete Copy Group and endpoint keys; ask only if ambiguous.
- Read [Copy](../../../references/metadata/tables/copy.md) and the relevant Snapshot records. Confirm the example uses the same naming consumer; open File Type documentation only for a format question.
- Propose the corresponding orders naming values. Check agreement between landing writer and Bronze reader; request relevant code if adapting the convention is unclear.
- Preserve other fields. A landing filename change does not rename the registered Source/Bronze Objects.
- A new Model, Bronze bundle, and Process definition are not implied.
- Validate the proposed record; fix failures and rerun affected checks before reporting it ready. Report unavailable checks explicitly.

## Example: source registration

User: "Register the tables described in my schema export under the ERP source Connection."

- Resolve owner, registered placement, selected Objects, and supplied file location.
- Read [Object](../../../references/metadata/tables/object.md) and [Attribute](../../../references/metadata/tables/attribute.md).
- Reuse actual Object Type/Zone records; preserve physical names/types.
- Resolve missing required fields; do not invent business meaning from names.

## Example: shared Bronze target

User: "Load the north and south Sources into the same Bronze orders table. Keep five incoming columns and add a fixed business_domain of retail."

- Read [Object Mapping](../../../references/metadata/tables/ingestion-object-mapping.md) and [Bronze projection rules](../../../references/metadata/tables/attribute.md#custom-select-expressions); verify each input supplies the fields actually referenced.
- Reuse the intended Bronze target. For new ingestion paths, author the required Object Mapping and Copy records; preserve existing paths.
- Define the five selected Bronze Attributes and the constant expression `'retail' AS business_domain`. Extra incoming fields may remain unused.
- Leave Attribute Mapping empty unless reference records are explicitly needed. Explain skipped Copies when the Copy Group, Copy or Object Mapping is inactive.

## Example: Process order change

User: "Move the customer Process before the order Process."

- Read [Process](../../../references/metadata/tables/process.md) and its current group/dependencies.
- Execution order is part of Process identity; an upsert at a different order creates a different key.
- Give the user [manual database-change instructions](../../../references/metadata/editing.md#manual-natural-key-changes). Do not stage the reorder or create/deactivate records to simulate it. Refresh the Snapshot after the user completes the correction.

## Example: operational control correction

User: "Correct the stored watermark for this Copy Group and Member Group."

- Read [Copy Group Control](../../../references/metadata/tables/copy-group-control.md).
- Establish the exact intended value and affected control key from supplied evidence.
- Explain the confirmed consumer effect; do not guess whether the change causes replay or skipping.
- New controls instead start with null run time/value; do not copy existing progress or today's date into them. Populate an initial-load date only for an established framework filter requirement.
