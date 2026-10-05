"""Build the local Codex bridge relay; excludes runtime and workspace state."""

from __future__ import annotations

import argparse
import json
import stat
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "atlas-connector"
FILES = (
    "README.md",
    "atlas-connector.cjs",
    "install.cjs",
    "update.py",
    "package-lock.json",
    "package.json",
)


def build(output: Path | None = None) -> Path:
    version = json.loads((SOURCE / "package.json").read_text(encoding="utf-8"))["version"]
    output = (output or SOURCE.parent / "dist" / f"atlas-connector-{version}.zip").absolute()
    if output.resolve().is_relative_to(SOURCE.resolve()):
        raise ValueError("archive must be outside connector source")
    if output.exists() or output.is_symlink():
        raise FileExistsError("refusing to overwrite archive")
    entries: dict[str, bytes] = {}
    for name in FILES:
        source = SOURCE / name
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"missing or unsafe connector input: {name}")
        entries[f"atlas-connector/{name}"] = source.read_bytes()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, content, compresslevel=9)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    print(build(args.output))
