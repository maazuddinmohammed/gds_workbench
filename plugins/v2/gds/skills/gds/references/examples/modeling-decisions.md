# Worked modeling decisions

Fictional evidence for reasoning only; inspect the user's own scope and schemas before authoring records.

## Evidence

- Sales Order rows repeat order date and billed customer for each LineNumber. The documented grain is one order line; `(OrderID, LineNumber)` is unique. Header descriptors depend on OrderID.
- CRM Customer and Service Client both describe customers. Their local IDs overlap, but no crosswalk establishes shared identity. Account names and postal addresses are not unique identifiers.
- Orders preserve the billing/shipping address at purchase. CRM stores a mutable current mailing address. No evidence establishes addresses as independently managed business objects.
- Confirmed Sales rules: Quantity and UnitPrice belong to a line; OrderTotal belongs to the whole order. Revenue definition, currency conversion and customer survivorship are not supplied.

## Reconciled outputs

**Analysis:** support OrderLine→Customer only within the documented System/key boundary, with the appropriate cardinality evidence. Reject equality of cross-System IDs as identity proof. Keep header/detail dependencies in model rationale, not fabricated `analysis_result` pairs. A name match remains a hypothesis.

**Conceptual:** retain Customer, Order and Product with business definitions and verb-based relationships. OrderLine describes an implementation of ordering detail; it need not be a separate business concept in this scope. CRMCustomer and ServiceClient become aliases/supports for Customer. Mailing and purchase addresses describe different roles; merging their values would destroy meaning. Every physical input is considered even though fewer concepts survive.

**Logical:** Sales submodel contains Order and OrderLine. Move order-level descriptors to Order; line attributes remain with the composite line key. CustomerManagement contains a shared Customer structure with source-qualified identity until an approved crosswalk exists. Sharing a table does not assert that two source records identify the same person. Other submodels reuse Customer through memberships.

Keep the order's historical address values with their documented order/role grain; current mailing address belongs with current customer state. Introduce CustomerAddress/Address entities only if evidence establishes multiple addresses, independent identity or lifecycle. Never deduplicate people by address. A proposed LineAmount requires a confirmed calculation, rounding/currency semantics and source rationale; do not label it Revenue by guesswork.

**Dimensional:** an OrderLine fact is one line in one order. Quantity is valid at that grain; repeated OrderTotal is not a summable line measure. A separate order-grain fact or confirmed allocation can represent it. Customer Dimension conformance and historical lookup require identity and history rules. Missing Revenue/conformance rules remain explicit blockers for those outputs, not made-up measures or default Type 2 behavior.

After drafting, inspect the effective graph: superseded mutable CRMCustomer concepts need explicit retirement and repaired references. Merely omitting them leaves them active. Preserve locked/out-of-scope records. Confirm both input coverage and justification of every remaining output before technical validation.
