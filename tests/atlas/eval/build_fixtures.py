"""Record a realistic Atlas evaluation world from the real MCP server.

Installs the fresh-install schema and demo seeds into a disposable PostgreSQL container
(the same fixture the database tests use), then calls the real read and Snapshot tools as
a local Super Admin. Responses and Snapshot ZIPs are written to `fixtures/` for the fake
MCP server to replay. Requires Docker; never connects to any other database.

    PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python \
        -m tests.atlas.eval.build_fixtures
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, LiteralString, cast
from uuid import UUID, uuid4

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.configuration import AuthMode, RuntimeSettings
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.snapshot_archive import SnapshotArchive
from gds_etl_workbench.tools.snapshots.storage import SnapshotKind
from mcp import Client
from psycopg import sql

from tests.mcp.conftest import DisposablePostgres, disposable_postgres

ROOT = Path(__file__).resolve().parents[3]
SEED_ROOT = ROOT / "database/seed"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TENANT_CODE = "DEMO_TENANT"
PROJECT_NAME = "Customer Orders 360"
SECTION_DATASETS = (
    "profiling_profile",
    "object_enrichment",
    "attribute_enrichment",
    "analysis_result",
    "context_group",
    "context_record",
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "mapping_object",
    "mapping_attribute",
)


class StaticIdentityProvider(IdentityProvider):
    def __init__(self, entra_tenant_id: UUID, entra_object_id: UUID) -> None:
        super().__init__(AuthMode.DEV)
        self._principal = RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
        )

    def request_principal(self, request: object | None) -> RequestPrincipal:
        del request
        return self._principal


class CapturingSnapshotStore:
    """Keeps uploaded archives in memory instead of Azure Blob storage."""

    def __init__(self) -> None:
        self.archives: dict[SnapshotKind, bytes] = {}

    async def close(self) -> None:
        return None

    async def upload_archive(
        self,
        archive: SnapshotArchive,
        *,
        snapshot_kind: SnapshotKind,
        tenant_id: int,
        scope_id: int,
        schema_version: str,
        snapshot_id: UUID,
        created_at: datetime,
        available_until: datetime,
    ) -> None:
        del tenant_id, scope_id, schema_version, snapshot_id, created_at, available_until
        self.archives[snapshot_kind] = archive.path.read_bytes()

    async def create_read_url(self, **_identity: object) -> str | None:
        return "file:///atlas-eval-snapshot.zip"


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://unused@invalid.example.invalid/unused",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_LOCAL_PRINCIPAL_OBJECT_ID": "33333333-3333-3333-3333-333333333333",
            "GDS_MCP_PUBLIC_URL": "https://testserver/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": "https://snapshot.blob.core.windows.net",
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


def _install_seeds(database: DisposablePostgres, entra_tenant_id: UUID, object_id: UUID) -> None:
    """Same order as tests/mcp/test_database_local_workbench_seed.py."""
    with database.connect_owner() as connection:
        for name in ("01_metadata_snapshot_demo.sql", "04_application_reference.sql"):
            connection.execute(cast(LiteralString, (SEED_ROOT / name).read_text()))
        identity_seed = (
            (SEED_ROOT / "03_local_super_admin.template.sql")
            .read_text()
            .replace("__REPLACE_WITH_EXPECTED_DATABASE_NAME__", database.database)
            .replace("__REPLACE_WITH_ENTRA_TENANT_ID__", str(entra_tenant_id))
            .replace("__REPLACE_WITH_LOCAL_PRINCIPAL_OBJECT_ID__", str(object_id))
        )
        connection.execute(cast(LiteralString, identity_seed))
        for name in (
            "05_global_prompt_defaults.template.sql",
            "07_global_mapping_output_templates.template.sql",
        ):
            rendered = (
                (SEED_ROOT / name)
                .read_text()
                .replace("__REPLACE_WITH_ENTRA_TENANT_ID__", str(entra_tenant_id))
                .replace("__REPLACE_WITH_ENTRA_OBJECT_ID__", str(object_id))
                .replace("__REPLACE_WITH_PRINCIPAL_TYPE__", "user")
            )
            connection.execute(cast(LiteralString, rendered))
        review_seed = (SEED_ROOT / "08_local_workbench_review.sql").read_text()
        guard = "current_database() !~ '^gds_local_[0-9a-f]{12}$'"
        fixture_guard = (
            sql.SQL("current_database() <> {}")
            .format(sql.Literal(database.database))
            .as_string(connection)
        )
        assert review_seed.count(guard) == 1
        connection.execute(cast(LiteralString, review_seed.replace(guard, fixture_guard, 1)))


async def _record(
    database: DisposablePostgres, identity: IdentityProvider, output: Path
) -> dict[str, Any]:
    store = CapturingSnapshotStore()
    server = create_mcp_server(
        _settings(),
        database.create_runtime_adapter(),
        identity,
        snapshot_store=store,
    )
    responses: list[dict[str, Any]] = []

    async with Client(server) as client:

        async def call(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
            result = await client.call_tool(tool, arguments)
            assert result.is_error is False, (tool, arguments, result.content)
            content = cast(dict[str, Any], result.structured_content)
            responses.append({"tool": tool, "arguments": arguments, "result": content})
            return content

        tenants = await call("list_tenants", {})
        tenant = next(item for item in tenants["tenants"] if item["tenant_code"] == TENANT_CODE)
        tenant_id = tenant["tenant_id"]
        await call("get_tenant_details", {"tenant_id": tenant_id})
        projects = await call("list_projects", {"tenant_id": tenant_id})
        project = next(
            item for item in projects["projects"] if item["project_name"] == PROJECT_NAME
        )
        project_id = project["project_id"]
        await call("get_project_input_scope", {"project_id": project_id})
        await call("check_tenant_lock", {"tenant_id": tenant_id})
        for zone in ("source", "bronze", "silver", "gold"):
            await call(
                "inspect_metadata", {"tenant_id": tenant_id, "view": "objects", "zone": zone}
            )
        mapping_targets: set[tuple[str, str, str]] = set()
        for dataset in SECTION_DATASETS:
            section = await call(
                "read_project_section", {"project_id": project_id, "dataset": dataset}
            )
            if dataset == "mapping_object":
                mapping_targets |= {
                    (
                        record["modeled_entity_type"],
                        record["modeled_entity_schema_name"],
                        record["modeled_entity_name"],
                    )
                    for record in section["records"]
                }
        # Agents read all five components with the first response's context digest.
        for entity_type, schema_name, entity_name in sorted(mapping_targets):
            target = {
                "project_id": project_id,
                "modeled_entity_type": entity_type,
                "modeled_entity_schema_name": schema_name,
                "modeled_entity_name": entity_name,
                "expected_project_revision": project["project_revision"],
                "page_size": 100,
            }
            first = await call("read_mapping_context", {**target, "component": "target_metadata"})
            for component in (
                "source_metadata",
                "source_systems",
                "object_transformations",
                "attribute_transformations",
            ):
                page = await call(
                    "read_mapping_context",
                    {
                        **target,
                        "component": component,
                        "expected_context_digest": first["context_digest"],
                    },
                )
                assert page["next_cursor"] is None, "eval fixture expects single-page components"
        snapshots: dict[str, dict[str, Any]] = {}
        for kind, tool, arguments in (
            ("metadata", "create_metadata_snapshot", {"tenant_id": tenant_id}),
            ("project", "create_project_snapshot", {"project_id": project_id}),
        ):
            descriptor = await call(tool, arguments)
            content = store.archives[cast(SnapshotKind, kind)]
            file_name = f"{kind}-snapshot.zip"
            (output / file_name).write_bytes(content)
            assert hashlib.sha256(content).hexdigest() == descriptor["sha256"]
            snapshots[kind] = {
                "file": file_name,
                "snapshot_id": descriptor["snapshot_id"],
                "size_bytes": descriptor["size_bytes"],
                "sha256": descriptor["sha256"],
            }
    return {
        "schema_version": "1.0",
        "generated_by": "tests/atlas/eval/build_fixtures.py",
        "tenant": {"tenant_id": tenant_id, "tenant_code": TENANT_CODE},
        "project": {
            "project_id": project_id,
            "project_name": PROJECT_NAME,
            "project_revision": project["project_revision"],
        },
        "snapshots": snapshots,
        "responses": responses,
    }


def build(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    entra_tenant_id, object_id = uuid4(), uuid4()
    with contextmanager(disposable_postgres)() as database:
        _install_seeds(database, entra_tenant_id, object_id)
        identity = StaticIdentityProvider(entra_tenant_id, object_id)
        world = asyncio.run(_record(database, identity, output))
    (output / "world.json").write_text(
        json.dumps(world, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    build(FIXTURES)
    print(f"wrote {FIXTURES.relative_to(ROOT)}")
