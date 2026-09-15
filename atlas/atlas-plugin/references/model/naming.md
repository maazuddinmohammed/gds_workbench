# Model naming

Confirmed Atlas defaults for newly authored names. Reuse the selected Model's explicit user-approved overrides; show only unresolved naming choices at build entry. Preserve existing names and locked records during unrelated work. A convention change is not permission for a bulk rename.

| Name | Default / example |
|---|---|
| Conceptual Object | PascalCase business noun: `Customer`, `OrderLine`, `ProductCategory`. |
| Conceptual Relationship | PascalCase business phrase: `Places`, `Contains`, `BilledTo`. |
| Logical Entity / Submodel | PascalCase meaningful subject: `CustomerAccount`, `Sales`. |
| Logical Attribute | PascalCase: `CustomerName`, `OrderDate`, `TotalAmount`. Only identifiers take the `ID` suffix. |
| Logical identifier / foreign key | Uppercase `ID`: `CustomerID`, `BillingCustomerID`; never default to `CustomerId` or `customer_id`. |
| Logical Relationship | PascalCase phrase preserving the role: `BilledTo`, `Contains`. |
| Dimensional Entity / Submodel / Attribute / Relationship | PascalCase; apply confirmed Model prefixes where present, such as `DimCustomer` or `FactSales`. Do not invent mandatory prefixes. |
| Dimensional surrogate / foreign key | End in `Key`: `CustomerKey`, `BillingCustomerKey`. Retained source/business identifiers may still end in `ID`. |
| Audit fields | Preserve the exact confirmed spellings in [keys and audit columns](keys-and-audit.md), including `SourceSystemID`, `GDSBatchID` and `HashKey`. |

## Apply names without losing meaning

1. Check existing effective names, definitions, aliases and user terminology before naming a new record. Preserve one name for the same meaning; qualify genuinely different meanings or roles.
2. Use PascalCase without separators by default. Preserve meaningful identifier distinctions: `CustomerCode` remains a code, and `CustomerName` does not acquire an `ID` suffix.
3. Reserve the Entity's own surrogate name. If a source business identifier would collide with `CustomerID`, use a meaningful distinct name such as `SourceCustomerID` or `CustomerNumber`, based on its actual meaning. Preserve its exact physical source key in lineage.
4. Check normalized-name collisions in the correct scope: Entities/Submodels within their Model, Attributes within their Entity, Relationships by their published key. Do not create spelling variants to bypass an occupied or locked key.
5. Keep payload field names and enum values exactly as the schema defines them. PascalCase applies to modeled names, not JSON property names, physical source keys or status/type values. Existing physical Object/Attribute names remain unchanged.

Aliases are business synonyms, not alternate casing copies. Definitions use ordinary readable prose. Do not silently apply new naming defaults to existing records; structural renaming requires an explicit request and the supported lifecycle. [Model authoring](change-sets.md) and [record state](../record-state.md) still apply.

Atlas's local policy validator checks new names against the default convention, preserving existing names. Explicit user-approved overrides remain valid; when the convention exists only in prose, the validator requests review instead of claiming an automated pass. Generic record schemas alone do not enforce naming conventions.
