# DBML workflow

## Purpose

DBML publishes a deterministic visualization of effective Conceptual and/or
Logical Sections. The export is immutable and bound to one Model revision. It
does not change the Model and uses no agent or Spark runtime.

There are two delivery paths. A human calls shared read-only `get_model_dbml`,
reads the returned immutable resource, and chooses a client-local save path.
The delegated workflow authorizes a safe relative directory, downloads the
same resource, publishes beneath its configured Volume root, and records a
completion receipt. The App Service writes neither destination.

## Request and preconditions

The Workflow Grant freezes:

- one Model;
- `conceptual`, `logical`, or `both` layer;
- Logical `complete` or `bundle` mode;
- color on or off; and
- one safe relative output directory.

`complete` produces the complete Logical view. `bundle` also includes
per-Submodel views and an optional default view for Entities without a
Submodel. The production adapter additionally requires
`GDS_JOBS_DBML_OUTPUT_ROOT` to be exactly
`/Volumes/<catalog>/<schema>/<volume>`.

The server renders only `active` and `needs_review` applied artifacts. Invalid references,
unsupported graph content, or size-limit violations fail closed before an
archive is returned.

## Data flow

1. Request the DBML envelope for the exact frozen render options.
2. Verify that Model, layer, Logical mode, and color agree with the request.
3. Download the content-addressed ZIP resource.
4. Verify MIME type, archive SHA-256, export digest, manifest, exact member
   inventory, member names, sizes, and per-file hashes.
5. Reject duplicate, traversing, linked, non-regular, or over-limit content.
6. Derive a final directory name from Model ID, revision, and export digest.
7. Traverse the deployment-owned Volume root with descriptor-relative
   no-follow operations.
8. Write regular files into a uniquely owned sibling pending directory, fsync
   them, and atomically rename without replacement.
9. Treat an existing final directory as replay only when its complete file set
   and bytes are identical.
10. Record server completion with the exact revision, export and archive
    digests, relative directory, file count, and total bytes.
11. Verify the completion receipt before returning success.

## Persistence and revision

The files are published only beneath the configured Unity Catalog Volume root.
The server stores the idempotent completion outcome and completes the Workflow
Grant and Workflow Run. There is no DBML-specific Model artifact and no Model
revision change.

The final directory is immutable by content identity. The server never receives
or writes an arbitrary absolute client path.

## Failure, retry, and concurrency

An archive identity mismatch, unsafe path, different existing bytes, failed
write, or invalid publication/completion receipt fails the run. No partial
directory is promoted as final. If publication succeeds but completion is
interrupted, retry verifies the identical final bytes and then replays or
records completion.

The completion key includes Workflow Run and export digest. Atomic no-replace
rename makes concurrent publication converge on one identical directory;
different bytes are never overwritten.

## Boundaries

DBML renders metadata, not database DDL or physical data. It does not expose
arbitrary filesystem writes, change Model state, create physical objects, or
run generated code. MCP clients may download the same archive and choose their
own local save path; only the Databricks workflow uses the governed Volume
publisher.

Sources:
[`workflow.py`](../../../jobs/src/gds_etl_jobs/dbml/workflow.py),
[`archive.py`](../../../jobs/src/gds_etl_jobs/dbml/archive.py),
[`writer.py`](../../../jobs/src/gds_etl_jobs/dbml/writer.py),
[`application/dbml.py`](../../../mcp_server/src/gds_etl_workbench/application/dbml.py),
[`ADR 0004`](../../adr/0004-governed-dbml-export.md), and
[`test_dbml_workflow.py`](../../../tests/workflows/unit/test_dbml_workflow.py).
