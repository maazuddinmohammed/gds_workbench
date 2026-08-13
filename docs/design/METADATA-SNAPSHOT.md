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
  "download_url": "https://storage.example/metadata/123/7d7cc8ad-62b5-44ef-aeb0-c09c770ff233.zip?<read-only-sas>",
  "download_url_expires_at": "2026-08-11T16:15:00Z",
  "size_bytes": 1234567,
  "sha256": "64 lowercase hexadecimal characters",
  "content_type": "application/zip"
}
```

The result never contains Blob bytes, data rows, or archive members. It contains
one temporary SAS URL only after Tenant Read authorization succeeds.

## Temporary download URL

After upload, the tool:

1. validates the exact Blob path, immutable metadata, and logical availability;
2. creates a read-only user-delegation SAS for that Blob only;
3. limits the URL to 15 minutes and HTTPS; and
4. returns it in the authorized MCP response without logging it.

Opening the URL downloads directly from private Blob Storage. Anyone holding
the URL can read that one ZIP until it expires, so the URL must not enter logs,
audit rows, or documentation.

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

Logical Blob availability defaults to 24 hours. SAS expiry is the earlier of 15
minutes or logical Blob expiry. The storage account must configure lifecycle
deletion for the code-owned `metadata/` prefix at or after the configured
availability window. The App Service does not implement a broad Blob cleanup
command.

## Metadata Discovery Scope

Add this admin-controlled Core table:

```sql
CREATE TABLE core.tenant_metadata_discovery_scope (
    tenant_metadata_discovery_scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    gds_connection_id BIGINT NOT NULL,
    zone_id BIGINT NOT NULL,
    object_schema VARCHAR(400) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_metadata_discovery_scope_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_metadata_discovery_scope_connection FOREIGN KEY (gds_connection_id)
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
        gds_connection_id,
        zone_id,
        lower(btrim(object_schema))
    );

CREATE INDEX ix_metadata_discovery_scope_tenant_active
    ON core.tenant_metadata_discovery_scope (
        tenant_id,
        is_active,
        gds_connection_id,
        zone_id
    );
```

The table is populated only through approved administration/bootstrap, not an
MCP CRUD tool or Metadata Change Set. An active row is a discovery seed only
when its Connection is an active global data store and its Zone is Bronze,
Silver, or Gold. Invalid active scope configuration fails snapshot generation
safely rather than widening discovery.

All scope rows for the requested Tenant, including inactive rows, are exported
under `foundational` for explanation. Only active valid rows expand discovery.
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
├── catalog.json
├── schemas/
│   └── <dataset>.schema.json
└── data/
    ├── foundational/
    │   └── <dataset>/rows.jsonl
    ├── reference/
    │   └── <dataset>/rows.jsonl
    └── operational/
        └── <dataset>/{rows.jsonl,lookup.jsonl}
```

There are 23 physical source tables and 29 logical snapshot datasets. The
physical `core.object` and `core.attribute` tables become eight Zone-specific
datasets. Objects and Attributes remain separate; Object rows never contain a
nested or duplicate Attribute array.

`is_locked` exists only on Object rows. Attribute rows do not duplicate it.
A locked Object blocks changes to both that Object and its Attributes. Validate
reports the staged records; Apply locks and rechecks the physical Object rows
before its first write. Apply remains one PostgreSQL transaction, so any later
failure rolls back all earlier dataset writes.

The five Foundational datasets are Project, Tenant, System, Connection, and
Tenant Metadata Discovery Scope. The eight allowlisted `reference.*` datasets
are Reference. The remaining 16 change-set-eligible datasets are Operational.

Every dataset has one `rows.jsonl` and one JSON Schema. Only these ten wide
datasets have `lookup.jsonl`: the four Object datasets, the four Attribute
datasets, `copy`, and `copy_group_control`. Compact datasets use `rows.jsonl`
as their search file. This avoids duplicating every row while keeping large
scripts, transformations, descriptions, and control values out of normal agent
search output.

Archive member names are constants. Database values never become directory or
file names. ZIP entries are regular files only, use deterministic ordering and
fixed safe metadata, and contain no absolute path, `..`, drive prefix, or
symbolic link.

## JSONL encoding

`rows.jsonl` contains one flat, ID-free Pydantic-validated metadata record per
UTF-8 line. Database IDs and audit columns are never exported. Foreign keys are
expanded to the target record's natural-key columns. Rows are sorted by their
canonical natural key. Newlines inside text values are JSON escaped.

For example, an Object is identified by:

```json
{
  "tenant_code": "ACME",
  "system_code": "ERP",
  "connection_code": "SOURCE",
  "object_schema": "sales",
  "object_name": "orders"
}
```

`lookup.jsonl` contains the canonical key, selected small filter fields, and a
one-based `line`. It contains no file path and no large text fields. The line
points to the matching line in that dataset's `rows.jsonl`. Archive validation
proves lookup count, line number, key, and filter values match the full rows.

Wire encodings preserve PostgreSQL values exactly:

- non-ID `BIGINT` values use canonical decimal strings so JavaScript cannot
  lose 64-bit precision;
- integer types that fit JSON's safe range use JSON numbers;
- Boolean values use JSON Booleans;
- `DATE` uses `YYYY-MM-DD`;
- timestamps use UTC RFC 3339 strings;
- SQL null uses JSON null; and
- binary, non-finite, cyclic, and unsupported values fail serialization.

`business_glossary_id`, test batch IDs, and other opaque IDs without an
ID-free target contract are excluded.

## Root contracts

### `manifest.json`

The manifest is the immutable archive instance and integrity contract. It contains:

- schema version, snapshot kind, snapshot ID, Tenant code, generation time, and
  availability time;
- physical table, logical dataset, lookup file, row, file, and expanded-byte counts;
- the `foundational`, `reference`, and `operational` sections;
- one entry for every non-manifest member with path, SHA-256, byte count, and
  row count when applicable; and
- a direct path and digest for `catalog.json` plus the schema directory count.

It contains no full data row. The ZIP SHA-256 and compressed byte count are
returned by MCP and stored as Blob metadata because a ZIP cannot include its
own final digest.

### `schemas/<dataset>.schema.json`

Each file is standard JSON Schema Draft 2020-12 generated from the same shared
Pydantic model used to validate snapshot rows. The future Metadata Change Set
can import these Pydantic models instead of copying field definitions.

GDS extensions describe relational meaning that JSON Schema cannot express:

```json
{
  "x-gds-dataset": "source_object",
  "x-gds-record-type": "object",
  "x-gds-canonical-key": [
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name"
  ],
  "x-gds-unique-constraints": [
    [
      "tenant_code",
      "system_code",
      "connection_code",
      "object_schema",
      "object_name"
    ]
  ],
  "x-gds-references": [
    {
      "columns": ["tenant_code", "system_code", "connection_code"],
      "target_record_type": "connection",
      "target_columns": ["tenant_code", "system_code", "connection_code"],
      "nullable": false
    }
  ]
}
```

Foundational and Reference datasets declare `change_set_eligible: false`. The
16 Operational datasets declare `true`.

### `catalog.json`

The catalog is the small agent navigation guide. It:

- instructs the agent never to recursively load the snapshot;
- lists all three sections and all 29 datasets;
- groups the four Object and four Attribute datasets for cross-Zone search;
- gives each dataset's row count, canonical key, search fields, schema file,
  search file, rows file, and `search_result_complete`; and
- tells the agent to read a full row only when a lookup result is incomplete.

The intended workflow is: read `catalog.json`, select a dataset, search its
`search_file`, read the exact full row only if needed, then read its schema only
when field/key/reference meaning is needed. The manifest is for integrity, not
routine navigation.

## Metadata Change Set alignment

`mcp.metadata_change_set` has 16 list-shaped documents so every metadata
dataset marked eligible has a governed write path:

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

The database JSONB columns, size checks, event Section allowlist, shared
Pydantic record models, and apply logic use this exact registry. The Stage tool
publishes a discriminated input schema for all 16 datasets through MCP
`tools/list`, so the agent knows every required field before calling it.

Stage replaces one complete pending dataset list and advances one global draft
revision. Get returns either 16 counts or only one requested list. Validate and
Apply load the current Snapshot closure internally; rows never enter tool
output. Validation stops after the first failed phase and returns at most 100
small errors. Apply reruns validation in one transaction and resolves natural
keys to PostgreSQL IDs server-side.

Reference rows are never appendable or mutable through a Metadata Change Set.
Metadata records refer to these rows by their canonical code or name, never by
database ID:

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
  -> resolve internal IDs to natural keys
  -> validate rows with shared Pydantic models
  -> build deterministic rows, selective lookups, schemas, and catalog
  -> validate every row count, unique key, lookup, and archive member
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
- `tenant_not_found` for a safely hidden Tenant absence;
- `payload_too_large` for row, expanded, or archive bounds;
- `dependency_unavailable` for PostgreSQL, identity, or Azure unavailability;
  and
- `internal_error` for invalid relational closure, serialization, manifest,
  ZIP, or unexpected failures.

The MCP Tool Call Log receives only its existing bounded, server-derived
summary. Logs and telemetry exclude SQL results, rows, JSONL, indexes,
manifests, Blob URLs, SAS values, archive members, ZIP bytes,
checksums from untrusted input, and raw exceptions.

Temporary directories are removed after success and every failure. Snapshot
generation never drops, truncates, resets, migrates, backfills, or cleans a
database.

## Implementation locality

Feature-specific code remains cohesive under one package, split only by its
stable responsibilities:

```text
mcp_server/gds_etl_workbench/domain/
└── metadata_records.py

mcp_server/gds_etl_workbench/tools/snapshots/metadata/
├── contracts.py
├── sql.py
├── projection.py
├── archive.py
├── storage.py
└── get_metadata_snapshot.py
```

`domain/metadata_records.py` owns the ID-free record shapes so Snapshot and
future Metadata Change Set code use one field/type contract. Snapshot-specific
dataset paths, keys, references, and lookup choices remain in `contracts.py`.

Small integration edits are still required in existing boundaries:

- `configuration.py` for validated environment settings;
- `adapters/mcp/server.py` for registration;
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
- complete ID-free columns, natural-key references, unique groups, and
  deterministic row order;
- all eight allowlisted reference tables and no other reference/Core tables;
- 29 row files, 29 schemas, exactly ten selective lookup files, and no unsafe
  ZIP members;
- exact non-ID BIGINT string encoding and browser-safe round trips;
- lookup, schema, catalog, manifest, member digest, ZIP digest, count, and size
  validation;
- temporary-file cleanup on every failure;
- create-only Blob upload, private-container assumptions, and lifecycle
  metadata;
- the MCP response remains small and contains no row, archive member, bytes, or
  base64, and contains only the intended temporary SAS credential;
- Tenant authorization happens before a blob-specific, read-only, 15-minute SAS
  enters the MCP result;
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
7. Direct SAS result with identity/Azure fakes.
8. MCP registration, audit, response-isolation, and package tests.

No later step begins while the preceding step's focused tests fail.
