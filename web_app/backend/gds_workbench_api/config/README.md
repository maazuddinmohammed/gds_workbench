# Backend constant registries

`workflow_execution.json` defines the bounded lease, heartbeat, idle-poll, and
error-poll defaults for the separate durable Workflow worker process. Deployment
environment variables may override those timings only within backend-validated
bounds.

`mapping_profiles.json` pins the globally reusable Release-1 Mapping profile.
It is metadata, not authority. On load, the backend regenerates the three root
JSON Schemas from `features/mapping/contracts.py` using Pydantic 2.13.4 in
validation mode, then compares the configured runtime version and SHA-256.
The generated digest must also equal the profile resolved by the shared
`gds_etl_workbench.domain.mapping_profiles` boundary used by MCP materialization.
The exact `MappingPackageDocumentV1` model is likewise shared from
`gds_etl_workbench.domain.mapping_contracts`; MCP and web do not maintain copies.

The canonical bundle is an object with `schema_bundle_version="1.0"`,
`json_schema_mode="validation"`, and a `schemas` array. Each array item is
`{"class_name": ..., "json_schema": ...}`. Items are ordered lexicographically
by class name: `AttributeMapperBatchOutputV1`, `GeneratorDocumentV1`, then
`HeaderMapperOutputV1`. Bundle bytes are UTF-8 JSON with lexicographically
sorted object keys, compact separators, preserved array order, and no floats or
non-finite values. The resulting `mapping.standard@1.0.0` digest is
`b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa`.

Changing Pydantic, a contract model, validation mode, wrapper, or root order is
a profile-version compatibility change and must intentionally update the
golden test, registry, and canonical greenfield SQL together.
