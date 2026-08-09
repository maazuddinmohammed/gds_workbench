"""Build the deterministic Azure App Service ZIP from an explicit allowlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

_ROOT_FILES = ("app.py", "requirements.txt", "startup.sh")
_PACKAGE = "gds_etl_workbench"
_FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def build_zip(output: Path) -> Path:
    source_root = Path(__file__).resolve().parent
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {output.name}")
    output.parent.mkdir(parents=True, exist_ok=True)

    selected = [source_root / name for name in _ROOT_FILES]
    selected.extend(
        path
        for path in sorted((source_root / _PACKAGE).rglob("*.py"))
        if "__pycache__" not in path.parts
    )
    entries: list[tuple[str, bytes, int]] = []
    manifest_files: list[dict[str, Any]] = []
    for path in selected:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"invalid package source: {path.name}")
        relative = path.relative_to(source_root)
        archive_name = PurePosixPath(*relative.parts).as_posix()
        content = path.read_bytes()
        mode = 0o755 if archive_name == "startup.sh" else 0o644
        entries.append((archive_name, content, mode))
        manifest_files.append(
            {
                "path": archive_name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )

    manifest = (
        json.dumps(
            {
                "schema_version": "1.0",
                "artifact": "gds-etl-workbench-mcp-appservice",
                "python_version": "3.12",
                "files": manifest_files,
            },
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    entries.append(("BUILD_MANIFEST.json", manifest, 0o644))

    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for archive_name, content, mode in sorted(entries):
            info = zipfile.ZipInfo(archive_name, date_time=_FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, content, compresslevel=9)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "dist" / "gds-mcp-appservice.zip",
    )
    args = parser.parse_args()
    artifact = build_zip(args.output)
    print(artifact)


if __name__ == "__main__":
    main()
