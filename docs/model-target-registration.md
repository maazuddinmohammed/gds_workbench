# Model target export and registration

Mapping and Code belong to Logical or Dimensional Entities. Authoring can continue
without registered target Objects. When ready for an operational handoff, use
**Export** on the applied Logical or Dimensional layer:

| Applied design | Registered metadata |
| --- | --- |
| Logical | Silver |
| Dimensional | Gold |

1. Click **Export**. The workbook includes selected Entities, or all active Entities
   when none are selected. Each Entity uses its saved schema; the backend chooses
   the registered Table type and the owning Tenant's GDS Connection.
2. Import the workbook into a Metadata draft, validate, review, and apply it.
   Registration records Object and Attribute metadata; it does not create tables.
3. Use the registered physical metadata when authoring Process configuration and
   external artifact paths. File placement and orchestration execution remain
   explicit operational handoffs.

There is no Target Binding screen or separate Model Binding step. Export does not
change the applied Model or associate its records with registered physical IDs.
A changed Model revision requires refreshing before export.

Exports preserve modeled names, definitions, declared storage types, nullability,
keys, and audit flags. Logical source metadata supplies applicable masking flags;
Dimensional export follows its Logical Attribute support. Dimensional business and
surrogate key roles become Metadata natural/surrogate key flags. Unique modeled
positions are preserved; ties receive stable sequential physical positions ordered
by modeled position and record ID. Each workbook supports at most 200 Entities
and 5,000 Attributes.

Metadata registration retains its own authorization, owned Tenant Lock, physical
review, validation, and Apply requirements. It does not replace Model revision,
record-lock, and complete Mapping/Code coverage rules. See
[ADR 012](adr/012-entity-owned-mapping-and-code.md) for the ownership contract.
