# Model conventions

At a new build, show the Model's actual naming and audit templates and confirm only missing choices. Reuse approved policies for incremental work. User changes override defaults; do not rename or rekey existing records globally without that intent.

Default Entity/Attribute names use PascalCase. Every Logical Entity has a generated BIGINT surrogate first: `CustomerID`; ID is uppercase. Foreign keys refer to the referenced surrogate, e.g. `Order.CustomerID`, with compatible type. Natural/business identifiers remain separate and evidence-based.

Dimensional names use the approved dim/fact prefixes; keys end in `Key` (capital K, lowercase ey), e.g. `CustomerKey`. Retain relevant Logical identifiers when the design needs them. An Entity's own declared surrogate is database-generated; a foreign key is not.

Ask whether to include these optional Source audit fields; they are not defaults:

- `SourceCreatedDate`, `SourceUpdatedDate`: TIMESTAMP.
- `SourceCreatedBy`, `SourceUpdatedBy`: STRING.

If selected, place them before the shared audit block and specify each System's source expression or confirmed missing-value behavior. Never silently invent an audit timestamp or user identity.

Shared columns, in order:

| Column | Population |
| --- | --- |
| SourceSystemID | BIGINT originating System identifier from registered provenance, typically Bronze source_system_id |
| IsDataValid | Framework |
| HashKey | Framework |
| IsActive | Framework |
| GDSBatchID | Framework |
| PipelineRunID | Framework |
| CreatedDate | Framework |
| UpdatedDate | Framework |
| CreatedBy | Framework |
| UpdatedBy | Framework |

Show actual types from approved Model templates. Resolve missing authoritative types before finalizing affected definitions; screenshots establish names/order, not every type. The user may add/remove/change audit columns through the policy confirmation.

All intended columns belong in Model, DDL, and Binding. For code projection and population ownership, follow `orchestration-rules.md`: SQL ends at SourceSystemID and excludes the target's generated surrogate. Mapping must account for those omitted generated fields explicitly.
