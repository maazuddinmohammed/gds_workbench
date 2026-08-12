# Metadata Snapshot design

**Status:** accepted for implementation  
**Date:** 2026-08-11  
**Contract version:** 2.0

## Purpose

`get_metadata_snapshot` gives an authorized agent a complete, bounded view of
one Tenant's relevant Core metadata without returning the metadata through the
MCP result. The App Service builds an immutable ZIP, uploads it to a private
Azure Blob container, and returns only a small descriptor.

The snapshot is independent of Model Snapshot and workflow execution. Its
structured files support selective agent reads and a separate HTML viewer.

## Non-goals

- No snapshot bytes, rows, indexes, manifests, or SAS tokens traverse MCP.
- No raw physical data is read or exported.
- No foundational CRUD, direct table mutation, arbitrary SQL, or reference-data
  mutation is exposed.
- Metadata Discovery Scope does not establish or restrict lineage.
- The snapshot tool does not create, validate, or apply a Metadata Change Set.
- The App Service never writes to a user's local filesystem.

## Public tool contract

The MCP tool is registered as `get_metadata_snapshot` under the existing
Tenant Read Tool Policy.

```python
get_metadata_snapshot(
    tenant_id: int,
    schema_version: Literal["2.0"] = "2.0",
)
```

It authorizes `tenant_id` server-side through the existing Principal and Tenant
authorization path. It synchronously returns only after the archive is fully
generated, validated, uploaded, and available.

Example result:

```json
{
  "schema_version": "2.0",
  "snapshot_id": "7d7cc8ad-62b5-44ef-aeb0-c09c770ff233",
  "snapshot_kind": "metadata",
  "status": "ready",
  "tenant_id": 123,
  "download_url": "https://app.example.com/metadata-snapshots/123/7d7cc8ad-62b5-44ef-aeb0-c09c770ff233/download",
  "available_until": "2026-08-12T16:00:00Z",
  "size_bytes": 1234567,
  "sha256": "64 lowercase hexadecimal characters",
  "content_type": "application/zip"
}
```

The result never contains Blob bytes, data rows, archive members, a SAS token,
or a SAS-bearing URL.

## Authenticated download

The non-secret result URL identifies this protected route:

```text
GET /metadata-snapshots/{tenant_id}/{snapshot_id}/download
```

The existing authentication middleware will protect both `/mcp` and
`/metadata-snapshots/`. The route:

1. parses bounded server-owned path values;
2. authenticates the current Principal;
3. reauthorizes Tenant Read for `tenant_id`;
4. verifies the exact Blob path, immutable Blob metadata, and availability;
5. creates a fresh, read-only user-delegation SAS;
6. returns an HTTP 302 redirect with `Cache-Control: no-store`; and
7. never logs the SAS or `Location` header.

The browser follows the redirect and downloads directly from Blob Storage. An
interactive user may open the URL manually; App Service Easy Auth prompts for
Microsoft Entra login when needed. A local helper may perform the same request
with an Entra token, but is not required.

Unauthenticated requests follow the existing Easy Auth/401 behavior. For an
authenticated Principal, unauthorized-Tenant, expired, missing, and malformed
snapshot requests all return 404. This prevents identifier probing from
revealing snapshot existence.

At upload, the Blob receives:

```text
Content-Type: application/zip
Content-Disposition: attachment; filename="metadata-snapshot-<tenant_id>-<snapshot_id>.zip"
```

## Blob identity and lifecycle

The container is deployment-created and private. The application does not
create containers or make them public. Blob names are code-owned:

```text
metadata/<tenant_id>/<snapshot_id>.zip
```

No caller-supplied value becomes a path segment without strict integer or UUID
parsing. Upload uses create-only behavior and cannot overwrite an existing
Blob.

Blob metadata contains only bounded control values: snapshot kind and version,
Tenant ID, snapshot ID, availability time, byte count, and archive SHA-256. It
contains no row, connection value, secret reference, credential, or Principal
identity.

Logical availability defaults to 24 hours. The download route rejects an
expired Blob even if physical lifecycle deletion has not run. The storage
account must configure lifecycle deletion for the code-owned `metadata/`
prefix at or after the configured availability window. The App Service does
not implement a broad Blob cleanup command.

## Metadata Discovery Scope

Add this admin-controlled Core table:

```sql
CREATE TABLE core.tenant_metadata_discovery_scope (
    tenant_metadata_discovery_scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    connection_id BIGINT NOT NULL,
    zone_id BIGINT NOT NULL,
    object_schema VARCHAR(400) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_metadata_discovery_scope_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_discovery_scope_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_discovery_scope_zone FOREIGN KEY (zone_id)
        REFERENCES reference.zone (zone_id) ON DELETE NO ACTION,
    CONSTRAINT ck_metadata_discovery_scope_schema CHECK (
        reference.is_nonblank(object_schema)
    )
);

CREATE UNIQUE INDEX ux_metadata_discovery_scope
    ON core.tenant_metadata_discovery_scope (
        tenant_id,
        connection_id,
        zone_id,
        lower(btrim(object_schema))
    );

CREATE INDEX ix_metadata_discovery_scope_tenant_active
    ON core.tenant_metadata_discovery_scope (
        tenant_id,
        is_active,
        connection_id,
        zone_id
    );
```

The table is populated only through approved administration/bootstrap, not an
MCP CRUD tool or Metadata Change Set. An active row is a discovery seed only
when its Connection is an active global data store and its Zone is Bronze,
Silver, or Gold. Invalid active scope configuration fails snapshot generation
safely rather than widening discovery.

All scope rows for the requested Tenant, including inactive rows, are exported
under `foundation` for explanation. Only active valid rows expand discovery.
An ingestion mapping, Process, or Model Scope may select an Object outside this
table; that is allowed because this table is not lineage or authorization.
The table's four database audit columns remain operational in PostgreSQL but
are not selected into the snapshot.

## Consistent SQL selection

All SQL runs in one PostgreSQL `REPEATABLE READ`, `READ ONLY` transaction. Rows
are selected through fixed, parameterized SQL declared in the tool module. The
tool never accepts SQL, table names, schemas, paths, filters, or policies from
the caller.

The included Object set is the union of:

1. every Object owned by a Connection of the requested Tenant;
2. Objects matched by an active valid Metadata Discovery Scope row on exact
   Connection, Zone, and case-insensitive trimmed schema;
3. endpoints of active ingestion mappings connected to the selected graph,
   including mappings referenced by a Copy in a requested-Tenant Copy Group;
4. Objects referenced by Processes whose Process Group belongs to the requested
   Tenant; and
5. Objects in Model Scope for every active Model owned by the requested Tenant.

Active ingestion mappings expand the connected lineage. Inactive mappings do
not grant cross-Tenant expansion, but are exported when both endpoints are
already included. Ingestion Attribute Mappings are exported when their parent
mapping and both Attributes are included.

Every Attribute of an included Object is exported, including inactive
Attributes. Objects and Attributes are partitioned by the exact active
`reference.zone.zone_code` values:

```text
source
bronze
silver
gold
```

An included Object with a missing, inactive, or different Zone fails snapshot
generation. The query does not infer Zone from a Connection, Tenant, schema, or
name.

Tenant-owned configuration selection includes all active and inactive rows:

- Copy Groups;
- Member Groups;
- Copy Group Controls;
- Copies;
- Process Groups; and
- Processes.

The selection includes every Ingestion Object Mapping referenced by an
included Copy and its qualifying Ingestion Attribute Mappings.

Foundation closure includes:

- the requested Tenant and its Project;
- every Connection required by the requested Tenant or an included Object;
- every owning Tenant and Project required by an included cross-Tenant
  Connection;
- every System referenced by an included Connection, Copy Group, Member Group,
  or Process Group; and
- all rows from the eight allowlisted reference tables below.

No `connection_location`, `connection_value`, `connection_parameter`, secret
reference, or unrelated Core/reference table is selected.

The SQL validates ownership and relational closure. It fails safely if a
selected configuration row has an unresolved parent, mismatched Tenant/System
witness, unsupported Zone, invalid discovery scope, or other incomplete
foreign-key context. It never silently drops such a row and never widens access
merely to make the snapshot complete.

## Archive layout

```text
metadata-snapshot/
├── manifest.json
├── schema.json
├── index.json
├── foundation/
│   ├── core/
│   │   ├── project/{index.jsonl,rows.jsonl}
│   │   ├── tenant/{index.jsonl,rows.jsonl}
│   │   ├── system/{index.jsonl,rows.jsonl}
│   │   ├── connection/{index.jsonl,rows.jsonl}
│   │   └── tenant_metadata_discovery_scope/{index.jsonl,rows.jsonl}
│   └── reference/
│       ├── system_type/{index.jsonl,rows.jsonl}
│       ├── connection_type/{index.jsonl,rows.jsonl}
│       ├── object_type/{index.jsonl,rows.jsonl}
│       ├── zone/{index.jsonl,rows.jsonl}
│       ├── chunk_type/{index.jsonl,rows.jsonl}
│       ├── file_type/{index.jsonl,rows.jsonl}
│       ├── data_operation/{index.jsonl,rows.jsonl}
│       └── process_type/{index.jsonl,rows.jsonl}
└── metadata/
    └── core/
        ├── source_object/{index.jsonl,rows.jsonl}
        ├── source_attribute/{index.jsonl,rows.jsonl}
        ├── bronze_object/{index.jsonl,rows.jsonl}
        ├── bronze_attribute/{index.jsonl,rows.jsonl}
        ├── silver_object/{index.jsonl,rows.jsonl}
        ├── silver_attribute/{index.jsonl,rows.jsonl}
        ├── gold_object/{index.jsonl,rows.jsonl}
        ├── gold_attribute/{index.jsonl,rows.jsonl}
        ├── ingestion_object_mapping/{index.jsonl,rows.jsonl}
        ├── ingestion_attribute_mapping/{index.jsonl,rows.jsonl}
        ├── copy_group/{index.jsonl,rows.jsonl}
        ├── member_group/{index.jsonl,rows.jsonl}
        ├── copy_group_control/{index.jsonl,rows.jsonl}
        ├── copy/{index.jsonl,rows.jsonl}
        ├── process_group/{index.jsonl,rows.jsonl}
        └── process/{index.jsonl,rows.jsonl}
```

There are 23 physical source tables and 29 logical snapshot datasets. The
physical `core.object` and `core.attribute` tables become eight Zone-specific
datasets. Each dataset has exactly one `rows.jsonl` in version 2; no part files
are generated.

Archive member names are constants. Database values never become directory or
file names. ZIP entries are regular files only, use deterministic ordering and
fixed safe metadata, and contain no absolute path, `..`, drive prefix, or
symbolic link.

## JSONL encoding

`rows.jsonl` contains one fixed-projection metadata row per UTF-8 line. Every
selected business column is present in contract order, including primary keys,
foreign keys, active state, and lock state. Database audit columns
(`created_time`, `created_by`, `updated_time`, and `updated_by`) are never
selected or exported. Rows are sorted by primary key. Newlines inside text
values are JSON escaped.

`index.jsonl` contains one bounded locator per row: the complete primary key, a
human-readable label, `file: "rows.jsonl"`, and a one-based line number. It
does not duplicate full rows or add selection-reason metadata.

Wire encodings preserve PostgreSQL values exactly:

- `BIGINT` and `BIGINT[]` elements use canonical decimal strings so a browser's
  JavaScript JSON parser cannot lose 64-bit precision;
- integer types that fit JSON's safe range use JSON numbers;
- Boolean values use JSON Booleans;
- `DATE` uses `YYYY-MM-DD`;
- timestamps use UTC RFC 3339 strings;
- arrays use JSON arrays;
- JSON/JSONB values retain their JSON structure;
- SQL null uses JSON null; and
- binary, non-finite, cyclic, and unsupported values fail serialization.

A decimal-string database ID remains a persisted ID, not a Local Reference.
Future Change Sets represent new identities with a separate typed
`local_ref`, never by placing a prefixed string into an ID column.

## Root contracts

### `manifest.json`

The manifest is the immutable instance and integrity contract. It contains:

- schema version, snapshot kind, snapshot ID, Tenant ID, generation time, and
  availability time;
- physical table, logical dataset, row, file, and expanded-byte counts;
- the `foundation` and `metadata` sections;
- one entry for every non-manifest member with path, SHA-256, byte count, and
  row count when applicable; and
- direct pointers and digests for `schema.json` and `index.json`.

It contains no full data row. The ZIP SHA-256 and compressed byte count are
returned by MCP and stored as Blob metadata because a ZIP cannot include its
own final digest.

### `schema.json`

The schema is the small, viewer-oriented contract. It does not duplicate
checksums or rows. Each logical dataset declares:

```json
{
  "name": "source_object",
  "label": "Source Objects",
  "database_table": "core.object",
  "section": "metadata",
  "change_set_eligible": true,
  "data_files": ["metadata/core/source_object/rows.jsonl"],
  "primary_key": ["object_id"],
  "display_columns": ["object_schema", "object_name"],
  "unique_column_groups": [
    ["connection_id", "object_schema", "object_name"]
  ],
  "columns": [
    {
      "name": "object_id",
      "type": "bigint",
      "nullable": false,
      "generated": true
    },
    {
      "name": "connection_id",
      "type": "bigint",
      "nullable": false,
      "generated": false
    }
  ],
  "foreign_keys": [
    {
      "columns": ["connection_id"],
      "references_table": "core.connection",
      "references_columns": ["connection_id"]
    }
  ]
}
```

Column arrays preserve display order. All columns are shown, including raw
foreign-key IDs. The viewer is not required to resolve IDs to labels.
`unique_column_groups` identifies the columns participating in each unique
constraint or unique index; PostgreSQL remains authoritative for expression
normalization and validation. A unique group belongs to `database_table`, so a
viewer evaluates it across every Zone dataset backed by the same physical
table rather than within one JSONL file only.

Foundation and reference datasets declare `change_set_eligible: false`. The 16
metadata datasets declare `true`.

### `index.json`

The root index is the small agent navigation guide. It:

- instructs the agent to read the manifest and root index first;
- instructs the agent never to recursively load the snapshot;
- lists both sections and all 29 datasets;
- gives each dataset's label, row count, data path, table-index path, primary
  key, and display columns; and
- tells the agent to search `index.jsonl` and then read only the located line
  from `rows.jsonl`.

It contains no complete row and no per-row selection explanation.

## Metadata Change Set alignment

The current 12-document `mcp.metadata_change_set` design expands to 16
documents so every metadata dataset marked eligible has a governed future
write path:

1. Source Object
2. Source Attribute
3. Bronze Object
4. Bronze Attribute
5. Silver Object
6. Silver Attribute
7. Gold Object
8. Gold Attribute
9. Ingestion Object Mapping
10. Ingestion Attribute Mapping
11. Copy Group
12. Member Group
13. Copy Group Control
14. Copy
15. Process Group
16. Process

The database JSONB columns, size checks, and event Section allowlist will be
updated together. This design change does not expose a mutation tool as part of
the snapshot slice.

Reference rows are never appendable or mutable through a Metadata Change Set.
Metadata rows may point their foreign-key columns to existing IDs from these
read-only allowlisted tables:

- `reference.system_type`;
- `reference.connection_type`;
- `reference.object_type`;
- `reference.zone`;
- `reference.chunk_type`;
- `reference.file_type`;
- `reference.data_operation`; and
- `reference.process_type`.

## Azure configuration

The runtime accepts only these deployment-specific snapshot settings:

```text
GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL
GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER
GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID=<optional UUID>
```

Download TTL `900` seconds, retention `24` hours, and maximum archive size
`268435456` bytes are checked-in snapshot policy.

There is no configurable Blob prefix, filesystem path, account key, SAS token,
or storage connection string. The full account URL supports the correct Azure
cloud endpoint without constructing it from an account name.

The App Service uses async Azure SDK clients with `DefaultAzureCredential`.
Production uses its system-assigned identity unless the optional user-assigned
identity client ID is configured. Local development uses a developer identity
supported by `DefaultAzureCredential`; tests inject Azure fakes and perform no
network call.

Required deployment posture:

- private Blob container;
- Blob create/read access scoped as narrowly as deployment permits;
- Storage Blob Delegator permission at storage-account scope for user-delegation
  keys;
- lifecycle deletion for the `metadata/` prefix; and
- no payload or response-header tracing.

## Generation flow

```text
MCP call
  -> authenticate Principal
  -> authorize Tenant Read
  -> open one repeatable-read, read-only transaction
  -> query and validate the bounded relational closure
  -> write deterministic JSONL, indexes, and schema in a temporary directory
  -> validate every row count, key, relationship, and archive member
  -> write manifest
  -> create deterministic safe ZIP
  -> enforce expanded and compressed limits
  -> calculate ZIP SHA-256
  -> upload create-only to private Blob Storage
  -> remove all server temporary files
  -> return the small descriptor
```

No partially built or partially uploaded archive is returned as ready. A Blob
success followed by an unexpected response failure leaves only an inaccessible
generated Blob that expires through normal lifecycle policy.

## Errors and audit

Existing bounded public error vocabulary is reused:

- `invalid_request` for malformed version or Tenant ID;
- `authentication_required` or `authorization_denied` at the protected MCP
  boundary;
- `not_found` for a safely hidden Tenant/snapshot absence;
- `payload_too_large` for row, expanded, or archive bounds;
- `dependency_unavailable` for PostgreSQL, identity, or Azure unavailability;
  and
- `internal_error` for invalid relational closure, serialization, manifest,
  ZIP, or unexpected failures.

The MCP Tool Call Log receives only its existing bounded, server-derived
summary. Logs and telemetry exclude SQL results, rows, JSONL, indexes,
manifests, Blob URLs, redirect headers, SAS values, archive members, ZIP bytes,
checksums from untrusted input, and raw exceptions.

Temporary directories are removed after success and every failure. Snapshot
generation never drops, truncates, resets, migrates, backfills, or cleans a
database.

## Implementation locality

Feature-specific code remains cohesive under one package, split only by its
stable responsibilities:

```text
mcp_server/gds_etl_workbench/tools/snapshots/metadata/
├── contracts.py
├── sql.py
├── archive.py
├── storage.py
└── get_metadata_snapshot.py
```

Small integration edits are still required in existing boundaries:

- `configuration.py` for validated environment settings;
- `adapters/mcp/server.py` for registration;
- `adapters/auth/middleware.py` for the protected download prefix;
- numbered SQL for Discovery Scope, Change Set alignment, indexes, and runtime
  privileges;
- the MCP dependency lock/export for Azure Identity and Blob Storage;
- App Service packaging checks; and
- focused tests.

No repository, manager, factory, service hierarchy, or generic export framework
is introduced for one feature.

## Required tests

Database tests use only the fixture-created disposable PostgreSQL container.
Azure tests use fakes/mocks and never contact a real account.

The slice must prove:

- Tenant Read authorization and non-disclosing denials;
- exact owned, discovery, ingestion, Process, and active-Model-Scope selection;
- discovery neither proves nor restricts lineage;
- active and inactive row inclusion;
- exact four-Zone partitioning and rejection of unsupported Zones;
- complete columns, IDs, foreign keys, unique groups, and deterministic row
  order;
- all eight allowlisted reference tables and no other reference/Core tables;
- 29 dataset paths, one index and one rows file per dataset, and no unsafe ZIP
  members;
- exact BIGINT string encoding and browser-safe round trips;
- schema, index, manifest, member digest, ZIP digest, count, and size validation;
- temporary-file cleanup on every failure;
- create-only Blob upload, private-container assumptions, and lifecycle
  metadata;
- the MCP response remains small and contains no row, archive member, bytes,
  base64, SAS, or secret;
- authenticated browser/helper redirects reauthorize Tenant access and mint
  read-only short-lived SAS values outside MCP;
- unauthenticated downloads follow Easy Auth/401, while authenticated
  unauthorized, expired, malformed, and missing downloads return 404;
- SAS values and snapshot contents never reach logs; and
- package/configuration checks include the new source and dependencies without
  including tests, local snapshots, or secrets.

## Implementation order

Implement and verify one change at a time:

1. Discovery Scope DDL and database tests.
2. Metadata Change Set 16-document alignment and database tests.
3. Azure configuration/dependency validation.
4. Pure snapshot contracts, JSONL, schema, index, manifest, and ZIP tests.
5. Fixed SQL selection and disposable-PostgreSQL tests.
6. Blob upload with Azure fakes.
7. Authenticated download redirect with identity/Azure fakes.
8. MCP registration, audit, response-isolation, and package tests.
9. Optional local helper and targeted-use documentation.

No later step begins while the preceding step's focused tests fail.
