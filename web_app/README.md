# Atlas web application

React and FastAPI run on one Databricks App origin with an embedded durable workflow
worker. The App connects directly to PostgreSQL, Foundry and governed Databricks SQL;
it does not start or call MCP. PostgreSQL authorization, locks, revision fencing and
idempotency remain authoritative. Startup never installs schema.

## Local run

With Docker and Compose available, run from the repository root:

```bash
python3 web_app/local/run.py
```

Open <http://127.0.0.1:8080>; stop with Ctrl-C. The runner creates random credentials,
a fresh PostgreSQL 18 container and local fixtures, uses local identity plus fake
Agent/Databricks adapters, then disposes the database on exit. It makes no Azure,
Foundry, Databricks, MCP or persistent-database call.

Optional loopback ports:

```bash
python3 web_app/local/run.py --frontend-port 9080 --api-port 9000
```

Use [AGENTS.md](../AGENTS.md) for source-aware tests, types and builds.
[Architecture](../docs/architecture/overview.md) identifies ownership/modules;
[workflow sources](../docs/workflows.md) identifies prompts, variables and validators.

## Deployment

[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) owns the operator procedure. Root
`databricks.yml`/`app.yaml` define resources and startup; root Python/Node manifests
and lock files define dependencies/builds. Deploy only a verified compatible release.
Databricks protects App access; backend resolves the forwarded identity; PostgreSQL
resolves application permissions. Secrets remain in App resources, never browser state.
