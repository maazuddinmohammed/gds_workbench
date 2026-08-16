---
name: author-model-metadata
description: "Explain, draft, or locally validate GDS physical metadata JSON using live schemas and Metadata Snapshots. Use for exact record shapes, synthetic examples, source/zone metadata, ingestion lineage JSON, local Workbench files, or snapshot-to-change-set guidance; route server mutation to manage-gds-metadata."
---

# Author Model Metadata

Help a team understand and author the physical metadata that supports models. This
skill is for Metadata Snapshot/Change Set datasets; use the Model-building skills for
Conceptual, Logical, Dimensional, or Model Mapping records.

Use the existing metadata references as needed:

- [tool contract](../manage-gds-metadata/references/tools.md);
- [snapshot contract](../manage-gds-metadata/references/snapshot.md);
- [dataset meanings](../manage-gds-metadata/references/datasets.md);
- [local workspace](../manage-gds-metadata/references/local-workspace.md); and
- [Metadata Change Sets](../manage-gds-metadata/references/change-sets.md).

## Explain an exact JSON shape

1. Identify the Tenant and exact dataset; never guess from an approximate name.
2. Call `describe_metadata_dataset(dataset, schema_version="1.0")`.
3. Explain the returned Section, eligibility, canonical key, unique constraints,
   references/dependencies, population rules, fields, required nullable values,
   accepted values, and limits in plain language.
4. If the user wants an example, use obviously synthetic codes and values. Include
   every required field and no database IDs, secrets, connection values, raw physical
   rows, or undocumented properties.
5. Label the example unvalidated until checked against the live schema.

Validate the finished example against the exact returned schema before calling it
schema-valid. If no validator can run, keep the unvalidated label. Schema success is
still local only: cross-record references, Tenant scope, locks, and server policy
remain authoritative during Metadata Change Set validation.

For Model dataset JSON, route to `describe_model_dataset` and the matching modeling
skill instead; Metadata and Model schemas have different keys and normalization.

## Author from a Snapshot

Use `get_metadata_snapshot(tenant_id, schema_version="2.0")` for a broad baseline.
Do not repeat or store the temporary download URL. The user places the extracted
`metadata-snapshot` folder under their local `GDS` workspace. Validate its manifest,
hashes, Tenant identity, catalog, and 29-dataset count with the bundled validator
before reading records.

Use the catalog and exact search files to locate current natural keys. Build complete
records—not patches—for eligible datasets only. Preserve required parents and order;
use the live schema's metadata-specific key normalization and unique constraints.
The bundled Workbench may add/edit local JSON arrays, but its draft is not Staged,
server-validated, or applied.

## Govern a Metadata Change Set

When the user requests a server change, hand off to or follow
`$manage-gds-metadata` exactly:

1. finish local drafting and validation without a lock;
2. show dataset/action counts, affected natural keys, and hashes;
3. check the Tenant Lock and ask before acquiring it;
4. create or resume the owner's Metadata Change Set and inspect all pending data;
5. reconcile, obtain Stage approval, and Stage complete dataset lists with the latest
   revision;
6. run server Validate and repair until valid;
7. display the authoritative action review and ask separately before Apply; and
8. verify fresh metadata and release the lock.

An empty staged list clears pending records only. Deactivate applied metadata through
the record's lifecycle field. Never replay an ambiguous non-idempotent call; inspect
current state first.

## Completion check

Report dataset, exact schema version, Snapshot identity without its URL, canonical
key, record count, local/server validation status, Change Set revision, action review
status, and unresolved references. Do not call JSON valid solely because it parses.
