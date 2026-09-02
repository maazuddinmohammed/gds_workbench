from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds"
BUILDER = REPOSITORY_ROOT / "plugins" / "build_gds_v2_plugin_zip.py"
PLUGIN_VERSION = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))[
    "version"
]
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


def write_builder_fixture(
    root: Path,
    *,
    plugin_manifest: object | None = None,
    mcp_manifest: object | None = None,
) -> Path:
    builder = root / "plugins" / BUILDER.name
    builder.parent.mkdir()
    shutil.copy2(BUILDER, builder)
    plugin_root = builder.parent / "v2" / "gds"
    plugin_root.mkdir(parents=True)
    (plugin_root / "plugin.json").write_text(
        json.dumps(
            plugin_manifest
            if plugin_manifest is not None
            else {
                "$schema": (
                    "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
                ),
                "name": "gds",
                "version": "0.2.0",
            }
        )
    )
    (plugin_root / "mcp.json").write_text(
        json.dumps(
            mcp_manifest
            if mcp_manifest is not None
            else {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {
                    "gds-workbench": {
                        "type": "streamable-http",
                        "url": "https://safe.example/mcp",
                    }
                },
            }
        )
    )
    return builder


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
        assert "gds/plugin.json" in names
        assert "gds/mcp.json" in names
        assert "gds/docs/USER_GUIDE.md" in names
        assert "gds/skills/gds/SKILL.md" in names
        assert "gds/skills/gds/scripts/gds-local.js" in names
        assert "gds/skills/gds/scripts/gds-local.ps1" in names
        assert "gds/tool-contract.json" not in names
        assert "gds/skills/gds/workbench/index.html" in names
        assert "gds/.codex-plugin/plugin.json" not in names
        assert "gds/.mcp.json" not in names
        assert "gds/skills/gds/agents/openai.yaml" not in names
        assert {Path(name).parts[0] for name in names} == {"gds"}
        assert all(".." not in Path(name).parts for name in names)
        assert names == expected_names
        for source, archive_name in zip(source_files, expected_names, strict=True):
            assert archive.read(archive_name) == source.read_bytes()
        assert all(not info.is_dir() for info in archive.infolist())
        assert all(
            (info.external_attr >> 16) & 0o170000 != 0o120000
            for info in archive.infolist()
        )


def test_checked_in_archive_is_the_current_deterministic_build(tmp_path: Path) -> None:
    expected = tmp_path / DIST_ARCHIVE.name
    result = run_builder("--output", str(expected))
    assert result.returncode == 0, result.stderr

    assert sorted(DIST_ARCHIVE.parent.glob("*.zip")) == [DIST_ARCHIVE]
    assert DIST_ARCHIVE.read_bytes() == expected.read_bytes()
    with zipfile.ZipFile(DIST_ARCHIVE) as archive:
        assert "gds/tool-contract.json" not in archive.namelist()
        assert "gds/docs/USER_GUIDE.md" in archive.namelist()


def test_mcp_override_changes_archive_only(tmp_path: Path) -> None:
    output = tmp_path / "override.zip"
    endpoint = "https://gds.company.example/mcp"
    source = (PLUGIN_ROOT / "mcp.json").read_bytes()

    result = run_builder("--output", str(output), "--mcp-url", endpoint)

    assert result.returncode == 0, result.stderr
    assert (PLUGIN_ROOT / "mcp.json").read_bytes() == source
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("gds/mcp.json"))
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
    ("manifest", "expected"),
    (
        (
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {
                    "gds-workbench": {
                        "type": "streamable-http",
                        "url": "http://unsafe.example/mcp",
                    }
                },
            },
            "must use https",
        ),
        (
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {
                    "gds-workbench": {
                        "type": "stdio",
                        "url": "https://safe.example/mcp",
                    }
                },
            },
            "must use streamable-http",
        ),
        (
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {
                    "gds-workbench": {
                        "type": "streamable-http",
                        "url": "https://safe.example/mcp",
                    },
                    "unexpected": {
                        "type": "streamable-http",
                        "url": "https://safe.example/mcp",
                    },
                },
            },
            "only the gds-workbench server",
        ),
    ),
)
def test_builder_validates_the_default_mcp_manifest(
    tmp_path: Path,
    manifest: object,
    expected: str,
) -> None:
    builder = write_builder_fixture(tmp_path, mcp_manifest=manifest)

    result = subprocess.run(
        [sys.executable, str(builder), "--output", str(tmp_path / "unsafe.zip")],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert expected in result.stderr


@pytest.mark.parametrize(
    ("manifest", "expected"),
    (
        (
            {
                "$schema": "https://example.invalid/plugin.schema.json",
                "name": "gds",
                "version": "0.2.0",
            },
            "must target Agent Plugins 1.0.0",
        ),
        (
            {
                "$schema": (
                    "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
                ),
                "name": "gds",
                "version": "0.2.0",
                "skills": "./skills",
            },
            "non-portable fields: skills",
        ),
        (
            {
                "$schema": (
                    "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
                ),
                "name": "gds",
                "version": "0.2.0",
                "author": "GDS Workbench",
            },
            "author must be an object",
        ),
        (["not", "an", "object"], "must contain a JSON object"),
    ),
)
def test_explicit_output_still_validates_plugin_manifest(
    tmp_path: Path,
    manifest: object,
    expected: str,
) -> None:
    builder = write_builder_fixture(tmp_path, plugin_manifest=manifest)

    result = subprocess.run(
        [sys.executable, str(builder), "--output", str(tmp_path / "unsafe.zip")],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert expected in result.stderr
