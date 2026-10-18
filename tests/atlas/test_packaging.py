from __future__ import annotations

import base64
import json
import re
import shutil
import struct
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from jsonschema import Draft202012Validator

from atlas import build_plugin

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "atlas" / "atlas-plugin"


def test_brand_assets_match_across_independent_packages() -> None:
    """Keep separately shipped favicons, header marks and extension identity aligned."""
    favicon = (ROOT / "web_app/frontend/public/assets/atlas.svg").read_bytes()
    assert (PLUGIN_ROOT / "workbench/atlas.svg").read_bytes() == favicon
    artwork = ET.fromstring(favicon)
    assert artwork.attrib["viewBox"] == "0 0 32 32"
    paths = artwork.findall("{http://www.w3.org/2000/svg}path")
    assert len(paths) == 1
    assert paths[0].attrib["fill-rule"] == "evenodd"
    assert paths[0].attrib["fill"] == "#00338D"
    for header, asset in (
        (ROOT / "web_app/frontend/src/shared/ui.tsx", "/assets/atlas.svg"),
        (PLUGIN_ROOT / "workbench/app.js", "atlas.svg"),
    ):
        source = header.read_text(encoding="utf-8")
        assert f'src="{asset}" width="32" height="32"' in source
        assert ">ATLAS<" in source
    font_names = {
        "OpenSans-Regular.woff2",
        "OpenSans-SemiBold.woff2",
        "OpenSans_Condensed-Bold.woff2",
        "OFL.txt",
    }
    web_fonts = ROOT / "web_app/frontend/public/assets/fonts"
    workbench_fonts = PLUGIN_ROOT / "workbench/fonts"
    assert {path.name for path in web_fonts.iterdir()} == font_names
    assert {path.name for path in workbench_fonts.iterdir()} == font_names | {"fonts.css"}
    for name in font_names:
        assert (workbench_fonts / name).read_bytes() == (web_fonts / name).read_bytes()
    embedded_fonts = re.findall(
        r"data:font/woff2;base64,([A-Za-z0-9+/=]+)",
        (workbench_fonts / "fonts.css").read_text(encoding="utf-8"),
    )
    assert len(embedded_fonts) == 3
    assert {base64.b64decode(font, validate=True) for font in embedded_fonts} == {
        (web_fonts / name).read_bytes() for name in font_names if name.endswith(".woff2")
    }
    extension = ROOT / "atlas/atlas-vs-code"
    manifest = json.loads((extension / "package.json").read_text(encoding="utf-8"))
    png = (extension / manifest["icon"]).read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (512, 512)


def test_archive_round_trip_and_reproducibility(tmp_path: Path) -> None:
    first = build_plugin.build(tmp_path / "one.zip")
    second = build_plugin.build(tmp_path / "two.zip")
    assert first.read_bytes() == second.read_bytes()
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads((ROOT / ".github/plugin/marketplace.json").read_text(encoding="utf-8"))
    assert marketplace["plugins"] == [
        {
            "name": "atlas",
            "description": "Atlas metadata and modeling workflows.",
            "version": manifest["version"],
            "source": "./atlas/atlas-plugin",
            "strict": True,
        }
    ]
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
        assert {name for name in expected if name.startswith("atlas/docs/")} == {
            "atlas/docs/copilot-vs-code-installation-and-setup.md",
            "atlas/docs/usage-guide.md",
            "atlas/docs/install-and-update.md",
        }
        assert "atlas/references/local-runtime.md" in expected
        assert "atlas/docs/assets/workbench-table-preview.png" not in expected
        assert "atlas/docs/workbench-design.md" not in expected
        assert "atlas/docs/extension-design.md" not in expected
        assert "atlas/docs/validation-index.md" not in expected
        assert "atlas/workbench/README.md" not in expected
        assert "atlas/mcp.json" in expected
        assert "atlas/scripts/atlas-local.js" in expected
        assert "atlas/workbench/validation/run.js" in expected
        assert all((info.external_attr >> 16) & 0o170000 == 0o100000 for info in archive.infolist())
        archive.extractall(tmp_path / "extracted")

    extracted = tmp_path / "extracted" / "atlas"
    schema = json.loads((ROOT / "tests/atlas/plugin.schema.json").read_text(encoding="utf-8"))
    # jsonschema's public validate method has incomplete type annotations.
    Draft202012Validator(schema).validate(  # pyright: ignore[reportUnknownMemberType]
        json.loads((extracted / "plugin.json").read_text(encoding="utf-8"))
    )
    skills = sorted((extracted / "skills").glob("*/SKILL.md"))
    assert {skill.parent.name for skill in skills} == {
        "atlas",
        "atlas-investigate",
        "atlas-source-analysis",
        "atlas-conceptual-model",
        "atlas-logical-model",
        "atlas-dimensional-model",
        "atlas-mapping",
        "atlas-code-generation",
        "atlas-verify",
        "atlas-project-change",
        "atlas-metadata",
        "atlas-registration",
    }
    assert (extracted / "templates" / "validation-summary.md").is_file()
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


def test_stage_runner_vsix_matches_source() -> None:
    extension = ROOT / "atlas/atlas-vs-code"
    manifest = json.loads((extension / "package.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(
        ROOT / "atlas/dist" / f"atlas-stage-runner-{manifest['version']}.vsix"
    ) as archive:
        for packaged, source in (
            ("package.json", "package.json"),
            ("dist/extension.cjs", "dist/extension.cjs"),
            ("readme.md", "README.md"),
        ):
            assert archive.read(f"extension/{packaged}") == (extension / source).read_bytes()
        packaged_manifest = json.loads(archive.read("extension/package.json"))
        assert packaged_manifest["contributes"]["commands"] == [
            {"command": "atlasStageRunner.check", "title": "ATLAS: Check Stage Runner"}
        ]
        assert {
            tool["name"] for tool in packaged_manifest["contributes"]["languageModelTools"]
        } == {"atlas_checkStageRunner", "atlas_stageApprovedManifest"}


def test_existing_output_and_source_directory_are_preserved(tmp_path: Path) -> None:
    output = tmp_path / "existing.zip"
    output.write_bytes(b"preserve this file")
    with pytest.raises(FileExistsError):
        build_plugin.build(output)
    assert output.read_bytes() == b"preserve this file"
    with pytest.raises(ValueError, match="outside the plugin source"):
        build_plugin.build(PLUGIN_ROOT / "unexpected.zip")
    assert not (PLUGIN_ROOT / "unexpected.zip").exists()


@pytest.mark.parametrize(
    "addition",
    [
        "symlink",
        "private-file",
        "invalid-manifest",
        "unreviewed-font",
        "font-script",
        "font-stylesheet",
        "text-file",
    ],
)
def test_invalid_package_inputs_fail_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, addition: str
) -> None:
    fixture = tmp_path / "plugin"
    shutil.copytree(PLUGIN_ROOT, fixture)
    if addition == "symlink":
        (fixture / "docs" / "outside.md").symlink_to(tmp_path / "outside.md")
    elif addition == "private-file":
        (fixture / "docs" / ".env").write_text("synthetic fixture; not package content")
    elif addition == "unreviewed-font":
        (fixture / "workbench/fonts/Other.woff2").write_bytes(b"synthetic fixture")
    elif addition == "font-script":
        (fixture / "workbench/fonts/Other.js").write_text("synthetic fixture")
    elif addition == "font-stylesheet":
        (fixture / "workbench/fonts/Other.css").write_text("synthetic fixture")
    elif addition == "text-file":
        (fixture / "workbench/unreviewed.txt").write_text("synthetic fixture")
    else:
        (fixture / "plugin.json").write_text("{}")
    monkeypatch.setattr(build_plugin, "PLUGIN_ROOT", fixture)
    output = tmp_path / "rejected.zip"
    with pytest.raises(ValueError):
        build_plugin.build(output)
    assert not output.exists()
