# GDS Workbench containers

## Run the complete local stack

Requirements: Docker Desktop/Engine with Compose, using a local Unix socket or
Windows named pipe.

From the repository root:

```bash
python3 web_app/local/run.py
```

Open `http://127.0.0.1:8080`. Stop with `Ctrl-C`.

The runner creates random database credentials, runtime passwords, local
identity UUIDs, and a cursor key in a private temporary directory. It starts a
fresh PostgreSQL 18 volume, runs the canonical preflight/install/verification,
adds only the repository demo/reference/local-identity seed, and disposes the
containers and volume on exit. The database is never published to the host.

The API and durable worker use local fake Agent and Databricks adapters. They do
not call provider, Azure, Databricks, or other external runtime endpoints.

Optional loopback ports:

```bash
python3 web_app/local/run.py --frontend-port 9080 --api-port 9000
```

The runner refuses ambient database, provider, Compose, GDS, or network Docker
configuration. Remove the named setting shown by the error instead of
overriding that guard.

## Build the two application images

The API and worker intentionally share the backend image.

```bash
docker build --file web_app/backend/Dockerfile --tag gds-workbench-backend:local .
docker build --file web_app/frontend/Dockerfile --tag gds-workbench-frontend:local web_app/frontend
```

The Python and Node build stages use immutable base-image digests; the NGINX
runtime uses an exact version tag. Dependency installation uses frozen lock
files. No Azure deployment is performed by these commands.

For local verification and the complete step-by-step Azure procedure, use
[`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md). The shorter immutable Azure
topology contract remains in
[`AZURE_CONTAINER_APPS.md`](AZURE_CONTAINER_APPS.md).
