# Manual model editing, lifecycle, and permanent deletion

Status: accepted

Historical contract: Binding dependencies and historical physical selections superseded by ADR 012; governance decisions retained.
See [Entity-owned Mapping and Code](012-entity-owned-mapping-and-code.md).

## Decision

The web UI reuses governed Model Change Sets for human edits and lifecycle changes.
A current owned Tenant Lock, model authorization, revision fence, no running Tenant
workflow, and idempotency receipt protect every write. These operations are not MCP tools.

Conceptual, Logical, and Dimensional detail pages offer **Edit definition**, **Lock**,
**Unlock**, **Deactivate**, and **Activate**. Edit forms expose supported scalar definition
fields using the backend record schema. Canonical identity, relationship endpoints,
evidence, memberships, and lifecycle cannot be changed through the editor. Renaming
an identity or changing relationship endpoints is a separate operation, not an upsert
under a new natural key.

**Deactivate** preserves database rows and can be reversed using **Activate**.
Modeling tables default to Active records; the status filter also exposes Inactive
records. Lifecycle actions remain separate from permanent deletion.

Only **Super Admins and Tenant Admins** can use **Delete selected**, detail-page
**Delete**, and **Clear layer**. These permanently delete rows after an impact preview
and explicit confirmation. Clear includes every record in the layer, including
inactive rows, submodels, supporting records, and memberships. Filters and visible
pages do not limit Clear. Applying requires the exact preview digest. Locked selected
or dependent rows block the entire operation. Deletion is atomic and cannot be undone
through Activate. The UI shows actions directly; there is no duplicate Record history
dialog.

Physical tables, registered metadata, assertions, and historical workflow runs remain.
Historical mapping-run target selections reference physical Object identity rather
than a live binding, so deleting the binding does not erase or block run history.
The existing fresh-install SQL sequence defines this constraint; no populated-database
migration or cleanup script is provided.

## Dependency behavior

- Conceptual Object deletion includes incident Conceptual relationships and owned
  support records. No persisted
  Conceptual-to-Logical ownership link exists; similar names never imply ownership.
- Logical/Dimensional Entity deletion includes Attributes, incident relationships,
  source support, memberships, target bindings, mappings across all contributing
  Systems, and generated artifacts. Existing complete-coverage rules also remove
  the affected binding/mapping/code bundle when a bound Attribute is deleted.
- Deleting an individual Submodel removes its memberships while retaining its
  Entities. Clear layer additionally deletes every Submodel in that layer.
- Persisted Dimensional Entity/Attribute source links to Logical Silver targets are
  followed across layers. This is based on full physical identity, not name matching.
- Dependency Order remains independent orchestration configuration.
- Validation groups/checks have System-level identity, not explicit target Object
  dependencies. A group is deleted when its System loses its last remaining mapping.
  Otherwise checks remain and the preview explicitly requires review; arbitrary SQL
  is not parsed to guess ownership or delete unrelated checks.

Activating an inactive record activates required parents, not every previously
deactivated child. Editing retains downstream records; review and regenerate them
where appropriate. Deletion retains an audited, idempotent Model Change Set receipt
and advances the Model revision. A restricted web-only SQL function checks the
administrator, owned Tenant Lock, revision, confirmed identities, record locks, and
Model ownership. Neither runtime role receives direct DELETE privileges; MCP cannot
call this function. Complete Data Model deletion, identity renaming, and
target-specific Validation ownership are outside this change.
