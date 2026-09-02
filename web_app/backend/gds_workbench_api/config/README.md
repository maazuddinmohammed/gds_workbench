# Backend constant registries

`workflow_execution.json` defines the bounded lease, heartbeat, idle-poll, and
error-poll defaults for the separate durable Workflow worker process. Deployment
environment variables may override those timings only within backend-validated
bounds.

Mapping has no backend registry. It stores flexible transformation documents.
An optional output template supplies soft agent guidance; the backend derives
binding identity, provenance, lifecycle status, and integrity constraints.
