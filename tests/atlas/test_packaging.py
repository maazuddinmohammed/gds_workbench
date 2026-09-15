from __future__ import annotations

import json
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from jsonschema import Draft202012Validator

from atlas import build_plugin

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "atlas" / "atlas-plugin"


def test_archive_round_trip_and_reproducibility(tmp_path: Path) -> None:
    first = build_plugin.build(tmp_path / "one.zip")
    second = build_plugin.build(tmp_path / "two.zip")
    assert first.read_bytes() == second.read_bytes()
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
    delivered = ROOT / "atlas" / "dist" / f"atlas-agent-plugin-{manifest['version']}.zip"
    assert delivered.read_bytes() == first.read_bytes()

    with zipfile.ZipFile(first) as archive:
        files = sorted(
            path
            for path in PLUGIN_ROOT.rglob("*")
            if path.is_file()
            and not any(
                part in {".DS_Store", "__pycache__"} for part in path.relative_to(PLUGIN_ROOT).parts
            )
        )
        expected = {
            f"atlas/{path.relative_to(PLUGIN_ROOT).as_posix()}": path.read_bytes() for path in files
        }
        assert archive.namelist() == list(expected)
        for name, content in expected.items():
            assert archive.read(name) == content
        assert "atlas/docs/user-guide.md" in expected
        assert "atlas/docs/assets/workbench-table-preview.png" in expected
        assert "atlas/mcp.json" in expected
        assert "atlas/scripts/atlas-local.js" in expected
        assert "atlas/workbench/validation/run.js" in expected
        assert "atlas/.codex-plugin/plugin.json" not in expected
        assert all((info.external_attr >> 16) & 0o170000 == 0o100000 for info in archive.infolist())
        archive.extractall(tmp_path / "extracted")

    extracted = tmp_path / "extracted" / "atlas"
    schema = json.loads(
        (ROOT / "tests/plugin_v2/agent_plugins_1_0_0/plugin.schema.json").read_text(
            encoding="utf-8"
        )
    )
    # jsonschema's public validate method has incomplete type annotations.
    Draft202012Validator(schema).validate(  # pyright: ignore[reportUnknownMemberType]
        json.loads((extracted / "plugin.json").read_text(encoding="utf-8"))
    )
    skills = sorted((extracted / "skills").glob("*/SKILL.md"))
    assert len(skills) == 14
    for skill in skills:
        text = skill.read_text(encoding="utf-8")
        frontmatter = text.split("---", 2)[1]
        fields = dict(line.split(": ", 1) for line in frontmatter.strip().splitlines())
        assert fields["name"] == skill.parent.name
        assert re.fullmatch(r"(?!.*--)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", fields["name"])
        assert 1 <= len(fields["name"]) <= 64
        assert 1 <= len(fields["description"]) <= 1024
        if skill.parent.name != "atlas":
            assert "change-set-lifecycle.md" in text

    # Check the extracted package, so source-only references cannot hide missing files.
    for document in extracted.rglob("*.md"):
        text = re.sub(r"```.*?```", "", document.read_text(encoding="utf-8"), flags=re.DOTALL)
        destinations: list[str] = re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", text)
        for destination in destinations:
            link = urlsplit(destination)
            if link.scheme or link.netloc:
                continue
            target = (document.parent / unquote(link.path)).resolve() if link.path else document
            assert target.is_relative_to(extracted), (document, destination)
            assert target.exists(), (document, destination)
            if link.fragment and target.suffix == ".md":
                headings = re.findall(
                    r"^#{1,6}\s+(.+)$", target.read_text(encoding="utf-8"), re.MULTILINE
                )
                anchors = {
                    re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
                    for heading in headings
                }
                assert unquote(link.fragment) in anchors, (document, destination)


def test_existing_output_and_source_directory_are_preserved(tmp_path: Path) -> None:
    output = tmp_path / "existing.zip"
    output.write_bytes(b"preserve this file")
    with pytest.raises(FileExistsError):
        build_plugin.build(output)
    assert output.read_bytes() == b"preserve this file"
    with pytest.raises(ValueError, match="outside the plugin source"):
        build_plugin.build(PLUGIN_ROOT / "unexpected.zip")
    assert not (PLUGIN_ROOT / "unexpected.zip").exists()


@pytest.mark.parametrize("addition", ["symlink", "private-file", "invalid-manifest"])
def test_invalid_package_inputs_fail_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, addition: str
) -> None:
    fixture = tmp_path / "plugin"
    shutil.copytree(PLUGIN_ROOT, fixture)
    if addition == "symlink":
        (fixture / "docs" / "outside.md").symlink_to(tmp_path / "outside.md")
    elif addition == "private-file":
        (fixture / "docs" / ".env").write_text("synthetic fixture; not package content")
    else:
        (fixture / "plugin.json").write_text("{}")
    monkeypatch.setattr(build_plugin, "PLUGIN_ROOT", fixture)
    output = tmp_path / "rejected.zip"
    with pytest.raises(ValueError):
        build_plugin.build(output)
    assert not output.exists()
