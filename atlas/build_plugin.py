"""Build the portable Atlas plugin; no install, publication or network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path
from typing import cast

PLUGIN_ROOT = Path(__file__).resolve().parent / "atlas-plugin"
DIST_ROOT = Path(__file__).resolve().parent / "dist"


def build(output: Path | None = None) -> Path:
    """Package only reviewed source families; exclude local work and build state."""
    if PLUGIN_ROOT.is_symlink():
        raise ValueError("plugin root must not be a symbolic link")
    files: list[Path] = []
    for source in sorted(PLUGIN_ROOT.rglob("*")):
        relative = source.relative_to(PLUGIN_ROOT)
        if source.is_symlink():
            raise ValueError(f"symbolic links are not packaged: {relative}")
        if any(part in {".DS_Store", "__pycache__"} for part in relative.parts):
            continue
        if source.is_dir():
            continue
        if not source.is_file():
            raise ValueError(f"not a regular package file: {relative}")
        allowed = {
            "skills": {".md"},
            "references": {".md"},
            "docs": {".md", ".png"},
            "scripts": {".js", ".ps1", ".sh", ".py"},
            "contracts": {".json"},
            "workbench": {".js", ".html", ".css", ".md", ".json"},
            "assets": {".json"},
        }
        if relative not in {Path("plugin.json"), Path("mcp.json")} and (
            source.suffix not in allowed.get(relative.parts[0], set())
            or any(part.startswith(".") for part in relative.parts)
        ):
            raise ValueError(f"outside the reviewed plugin source families: {relative}")
        files.append(source)

    decoded: object = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("expected a JSON object in plugin.json")
    manifest = cast(dict[str, object], decoded)
    if set(manifest) != {
        "$schema",
        "name",
        "version",
        "description",
    }:
        raise ValueError("expected the four-field Atlas manifest")
    if manifest["$schema"] != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        raise ValueError("expected Agent Plugins 1.0.0")
    if manifest["name"] != "atlas":
        raise ValueError("expected plugin name atlas")
    version = manifest["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:-dev\.\d+)?", version):
        raise ValueError("expected a semantic version, such as 0.1.0")
    if not isinstance(manifest["description"], str) or not manifest["description"].strip():
        raise ValueError("expected a nonempty description")

    output = (output or DIST_ROOT / f"atlas-agent-plugin-{version}.zip").absolute()
    if output.resolve().is_relative_to(PLUGIN_ROOT.resolve()):
        raise ValueError("archive must be outside the plugin source")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing to overwrite archive: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in files:
            relative = source.relative_to(PLUGIN_ROOT)
            # Package identity is atlas; the requested source folder is atlas-plugin.
            info = zipfile.ZipInfo(f"atlas/{relative.as_posix()}", (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | (0o755 if source.suffix == ".sh" else 0o644)) << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new ZIP path; existing files are preserved")
    arguments = parser.parse_args()
    try:
        output = build(arguments.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"archive={output}")
    print(f"sha256={hashlib.sha256(output.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
