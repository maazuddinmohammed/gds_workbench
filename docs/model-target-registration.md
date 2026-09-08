# Model target registration and Binding

Use **Export** on Logical or Dimensional, then **Target Binding** in the Model
journey. Both layers use the same handoff:

| Applied design | Registered target |
| --- | --- |
| Logical | Silver |
| Dimensional | Gold |

1. Click **Export** on Logical or Dimensional and enter a schema. Export includes
   selected Entities, or all active Entities when none are selected. The backend
   chooses the registered Table type and the owning Tenant’s GDS Connection.
2. Open Metadata registration. Import the workbook into a Metadata draft,
   validate, review, and apply it. Registration records metadata; it does not
   create physical tables.
3. Open **Target Binding** and choose **Logical** or **Dimensional**. Refresh after
   registration. Each Entity shows its registered target schema and Object, or a
   dash when unbound. **Search** finds an Object within a registered schema;
   **Show details** opens the Attribute assignments.
4. Use **Generate** and select a registered schema to preview name matches for all
   Entities. The backend trims names and compares them case-insensitively. Only
   unique, compatible matches become changes; unmatched, ambiguous, existing,
   and locked bindings are reported separately. Apply the reviewed matches.
5. Within one Entity, use **Search** to choose an Attribute or **Generate Attribute
   bindings** to suggest name matches. Review changed assignments before Apply,
   then continue to Mapping.

Existing registered targets can go directly to step 3. The screen also exposes
existing Object and Attribute Bindings through selection and bulk Lock/Unlock
controls above their tables. Locked bindings remain visible but cannot be changed.

Exports preserve names, definitions, declared storage types, nullability, keys,
audit flags, and masking requirements from active physical sources. Dimensional
business/surrogate key roles become Metadata natural/surrogate key flags. Unique
modeled positions are preserved; ties receive stable sequential physical
positions, ordered by modeled position and record ID. The applied design stays
unchanged. Each workbook supports up to 200 Entities and 5,000 Attributes.

Binding requires an owned Tenant Lock and the current Model revision. Every
active modeled and target Attribute must be assigned exactly once, including
technical/audit columns. The backend verifies registered storage types,
nullability, keys, audit flags, masking, and the complete Model graph. Existing
active Bindings are not silently replaced; locked records remain protected.
Metadata changes after preview invalidate the approval digest. A retry of an
unconfirmed Apply uses the same idempotency key and returns its original receipt.
