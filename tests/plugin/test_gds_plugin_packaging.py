from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "gds"
BUILDER = REPOSITORY_ROOT / "plugins" / "build_gds_plugin_zip.py"


def _run_builder(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILDER), *arguments],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def test_mcp_url_override_changes_only_archived_manifest(tmp_path: Path) -> None:
    output = tmp_path / "company.zip"
    endpoint = "https://gds-workbench.company.example:8443/mcp"
    source_manifest = (PLUGIN_ROOT / "mcp.json").read_bytes()

    result = _run_builder(
        "--output",
        str(output),
        "--mcp-url",
        endpoint,
    )

    assert result.returncode == 0, result.stderr
    assert (PLUGIN_ROOT / "mcp.json").read_bytes() == source_manifest
    with zipfile.ZipFile(output) as archive:
        archived_manifest = json.loads(archive.read("gds/mcp.json"))
        assert archived_manifest["mcpServers"]["gds-workbench"]["url"] == endpoint
        for member in archive.namelist():
            if member == "gds/mcp.json":
                continue
            source = PLUGIN_ROOT / Path(member).relative_to("gds")
            assert archive.read(member) == source.read_bytes()


def test_mcp_url_override_is_reproducible(tmp_path: Path) -> None:
    endpoint = "https://gds-workbench.company.example/mcp"
    outputs = [tmp_path / "first.zip", tmp_path / "second.zip"]

    for output in outputs:
        result = _run_builder(
            "--output",
            str(output),
            "--mcp-url",
            endpoint,
        )
        assert result.returncode == 0, result.stderr

    assert outputs[0].read_bytes() == outputs[1].read_bytes()


def test_mcp_url_override_requires_explicit_output() -> None:
    result = _run_builder(
        "--mcp-url",
        "https://gds-workbench.company.example/mcp",
    )

    assert result.returncode != 0
    assert "--mcp-url requires --output" in result.stderr


@pytest.mark.parametrize(
    "endpoint, message",
    [
        ("", "must not be empty"),
        ("http://gds.example/mcp", "must use https"),
        ("https:///mcp", "must include a hostname"),
        ("https://gds_example/mcp", "must include a valid hostname"),
        ("https://gds.example\\evil/mcp", "must include a valid hostname"),
        ("https://user@gds.example/mcp", "must not contain credentials"),
        ("https://gds.example/root/mcp", "path must be exactly /mcp"),
        ("https://gds.example/mcp/", "path must be exactly /mcp"),
        ("https://gds.example/mcp?", "must not contain a query"),
        ("https://gds.example/mcp?slot=prod", "must not contain a query"),
        ("https://gds.example/mcp#", "must not contain a fragment"),
        ("https://gds.example/mcp#prod", "must not contain a fragment"),
        (" https://gds.example/mcp", "must not be empty or contain whitespace"),
        ("https://gds.example:bad/mcp", "invalid MCP URL"),
    ],
)
def test_mcp_url_override_rejects_unsafe_or_ambiguous_endpoints(
    tmp_path: Path,
    endpoint: str,
    message: str,
) -> None:
    output = tmp_path / "invalid.zip"

    result = _run_builder(
        "--output",
        str(output),
        "--mcp-url",
        endpoint,
    )

    assert result.returncode != 0
    assert message in result.stderr
    assert not output.exists()
