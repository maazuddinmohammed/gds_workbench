from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import cast

import pytest
from mcp import Client

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import (
    MCP_SERVER_VERSION,
    create_mcp_server,
    tool_contract_sha256,
)
from gds_etl_workbench.configuration import RuntimeSettings
from gds_etl_workbench.infrastructure.postgres import Database


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"
BUILDER = REPOSITORY_ROOT / "plugins" / "build_gds_v2_plugin_zip.py"
PLUGIN_VERSION = json.loads(
    (PLUGIN_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
)["version"]
DIST_ARCHIVE = (
    REPOSITORY_ROOT
    / "plugins"
    / "v2"
    / "dist"
    / f"gds-agent-plugin-{PLUGIN_VERSION}.zip"
)


def run_builder(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


class SchemaDatabase:
    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def expire_tenant_locks(self) -> int:
        return 0


def runtime_settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://unused@invalid.example.invalid/unused",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_LOCAL_PRINCIPAL_OBJECT_ID": "33333333-3333-3333-3333-333333333333",
            "GDS_MCP_PUBLIC_URL": "https://testserver/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
                "https://snapshot.blob.core.windows.net"
            ),
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


@pytest.mark.asyncio
async def test_packaged_tool_contract_matches_the_runtime(tmp_path: Path) -> None:
    output = tmp_path / "contract.zip"
    result = run_builder("--output", str(output))
    assert result.returncode == 0, result.stderr

    settings = runtime_settings()
    server = create_mcp_server(
        settings,
        cast(Database, SchemaDatabase()),
        IdentityProvider(settings.auth_mode),
    )
    async with Client(server) as client:
        tools = (await client.list_tools()).tools

    with zipfile.ZipFile(output) as archive:
        contract = json.loads(archive.read("gds/tool-contract.json"))
    assert contract == {
        "schema_version": "1.0",
        "mcp_server_version": MCP_SERVER_VERSION,
        "tool_count": len(tools),
        "tool_contract_sha256": tool_contract_sha256(tools),
    }


def test_builder_creates_deterministic_complete_archive(tmp_path: Path) -> None:
    outputs = [tmp_path / "one.zip", tmp_path / "two.zip"]
    for output in outputs:
        result = run_builder("--output", str(output))
        assert result.returncode == 0, result.stderr

    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    with zipfile.ZipFile(outputs[0]) as archive:
        names = archive.namelist()
        source_files = sorted(path for path in PLUGIN_ROOT.rglob("*") if path.is_file())
        expected_names = [
            (Path(PLUGIN_ROOT.name) / path.relative_to(PLUGIN_ROOT)).as_posix()
            for path in source_files
        ]
        assert "gds/.codex-plugin/plugin.json" in names
        assert "gds/.mcp.json" in names
        assert "gds/docs/USER_GUIDE.md" in names
        assert "gds/skills/gds/SKILL.md" in names
        assert "gds/scripts/gds-local.js" in names
        assert "gds/scripts/gds-local.ps1" in names
        assert "gds/tool-contract.json" in names
        assert "gds/workbench/index.html" in names
        assert names == expected_names
        for source, archive_name in zip(source_files, expected_names, strict=True):
            assert archive.read(archive_name) == source.read_bytes()


def test_checked_in_archive_is_the_current_deterministic_build(tmp_path: Path) -> None:
    expected = tmp_path / DIST_ARCHIVE.name
    result = run_builder("--output", str(expected))
    assert result.returncode == 0, result.stderr

    assert DIST_ARCHIVE.read_bytes() == expected.read_bytes()
    with zipfile.ZipFile(DIST_ARCHIVE) as archive:
        assert "gds/tool-contract.json" in archive.namelist()
        assert "gds/docs/USER_GUIDE.md" in archive.namelist()


def test_mcp_override_changes_archive_only(tmp_path: Path) -> None:
    output = tmp_path / "override.zip"
    endpoint = "https://gds.company.example/mcp"
    source = (PLUGIN_ROOT / ".mcp.json").read_bytes()

    result = run_builder("--output", str(output), "--mcp-url", endpoint)

    assert result.returncode == 0, result.stderr
    assert (PLUGIN_ROOT / ".mcp.json").read_bytes() == source
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("gds/.mcp.json"))
        assert manifest["mcpServers"]["gds-workbench"]["url"] == endpoint


def test_mcp_override_rejects_an_ambiguous_numeric_hostname(tmp_path: Path) -> None:
    result = run_builder(
        "--output",
        str(tmp_path / "unsafe.zip"),
        "--mcp-url",
        "https://2130706433/mcp",
    )

    assert result.returncode != 0
    assert "valid hostname" in result.stderr


@pytest.mark.parametrize(
    ("server", "expected"),
    (
        (
            {"type": "streamable-http", "url": "http://unsafe.example/mcp"},
            "must use https",
        ),
        (
            {"type": "stdio", "url": "https://safe.example/mcp"},
            "must use streamable-http",
        ),
    ),
)
def test_builder_validates_the_default_mcp_manifest(
    tmp_path: Path,
    server: dict[str, str],
    expected: str,
) -> None:
    builder = tmp_path / "plugins" / BUILDER.name
    builder.parent.mkdir()
    shutil.copy2(BUILDER, builder)
    plugin_root = builder.parent / "v2" / "gds"
    plugin_root.mkdir(parents=True)
    (plugin_root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"gds-workbench": server}})
    )

    result = subprocess.run(
        [sys.executable, str(builder), "--output", str(tmp_path / "unsafe.zip")],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert expected in result.stderr
