"""Build a deterministic, clean GDS Agent Plugin archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path


PLUGIN_ROOT = Path(__file__).parent / "gds"
DIST_ROOT = Path(__file__).parent / "dist"
IGNORED_NAMES = frozenset({".DS_Store", "__pycache__"})
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _plugin_version() -> str:
    manifest = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("plugin.json has no valid version")
    return version


def _source_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(PLUGIN_ROOT.rglob("*")):
        if any(part in IGNORED_NAMES for part in path.relative_to(PLUGIN_ROOT).parts):
            continue
        if path.is_symlink():
            raise ValueError(f"plugin contains a symbolic link: {path}")
        if path.is_file():
            files.append(path)
    if not files:
        raise ValueError("plugin contains no files")
    return files


def build(output: Path) -> tuple[int, str]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing archive: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = _source_files()
    with zipfile.ZipFile(
        output,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for source in files:
            relative = source.relative_to(PLUGIN_ROOT)
            archive_name = (Path(PLUGIN_ROOT.name) / relative).as_posix()
            info = zipfile.ZipInfo(archive_name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if source.suffix in {".sh", ".ps1"} else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, source.read_bytes(), compresslevel=9)
    content = output.read_bytes()
    return len(content), hashlib.sha256(content).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    version = _plugin_version()
    output = arguments.output or DIST_ROOT / f"gds-agent-plugin-{version}.zip"
    try:
        size, digest = build(output.resolve())
    except (FileExistsError, OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"archive={output.resolve()}")
    print(f"size_bytes={size}")
    print(f"sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
