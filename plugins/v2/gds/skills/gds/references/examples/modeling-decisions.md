# Worked modeling decisions

Fictional evidence for reasoning only; inspect the user's own scope and schemas before authoring records.

## Evidence

- Sales Order rows repeat order date and billed customer for each LineNumber. The documented grain is one order line; `(OrderID, LineNumber)` is unique. Header descriptors depend on OrderID.
- CRM Customer and Service Client both describe customers. Their local IDs overlap, but no crosswalk establishes shared identity. Account names and postal addresses are not unique identifiers.
- Orders preserve the billing/shipping address at purchase. CRM stores a mutable current mailing address. No evidence establishes addresses as independently managed business objects.
- Confirmed Sales rules: Quantity and UnitPrice belong to a line; OrderTotal belongs to the whole order. Revenue definition, currency conversion and customer survivorship are not supplied.

## Reconciled outputs

**Analysis:** measure candidate joins within their identifier domains. Reject equality of cross-System IDs as identity proof. Record header/detail dependencies in notes, not fabricated `analysis_result` pairs.

**Conceptual:** Customer and Order explain the purchase process; OrderLine need not be a separate concept. CRM/Service may support shared Customer meaning without asserting common row identity. Address roles remain distinct.

**Logical:** separate Order headers from OrderLine’s composite grain. Customer can share a structure with source-qualified identity until a crosswalk exists. Reuse through submodel memberships.

Keep the order's historical address values with their documented order/role grain; current mailing address belongs with current customer state. Introduce CustomerAddress/Address entities only if evidence establishes multiple addresses, independent identity or lifecycle. Never deduplicate people by address. A proposed LineAmount requires a confirmed calculation, rounding/currency semantics and source rationale; do not label it Revenue by guesswork.

**Dimensional:** Quantity is valid at line grain; repeated OrderTotal is not summable there. Use order-grain facts or confirmed allocation. Revenue, conformance and historical lookups remain blocked pending their rules.

Inspect the effective graph: omission does not retire superseded concepts; explicit retirement needs repaired references. Preserve locks/scope and review input/output coverage.
