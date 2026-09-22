#!/usr/bin/env python3
"""Build deterministic, source-only ZIP for manual Databricks UI upload."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import NamedTuple
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "databricks-ui"
APP_DIRECTORY_NAME = "gds-workbench-app-source"
GENERATED_MARKER = ".gds-databricks-ui-artifact"
GENERATED_MARKER_VALUE = "gds-databricks-ui-artifacts-v1\n"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ZIP_FILE_MODE = (stat.S_IFREG | 0o644) << 16
_ZIP_DIRECTORY_MODE = ((stat.S_IFDIR | 0o755) << 16) | 0x10

_APP_ROOT_FILES = (
    "app.yaml",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "uv.lock",
)
_FRONTEND_ROOT_FILES = (
    "index.html",
    "package.json",
    "tsconfig.build.json",
    "tsconfig.json",
    "vite.config.mjs",
)
_IGNORED_SOURCE_PARTS = frozenset(
    {
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "test",
        "tests",
    }
)
_IGNORED_SOURCE_NAMES = frozenset({".DS_Store", "README.md"})


class ArtifactBuildError(RuntimeError):
    """A manual-upload artifact could not be built safely."""


class UploadArtifacts(NamedTuple):
    output_directory: Path
    app_source_directory: Path
    app_archive: Path
    manifest: Path
    checksums: Path


def _copy_file(source: Path, destination: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ArtifactBuildError(f"required source is not a regular file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _is_ignored_source(path: Path, source_root: Path) -> bool:
    relative = path.relative_to(source_root)
    return (
        path.name in _IGNORED_SOURCE_NAMES
        or bool(set(relative.parts) & _IGNORED_SOURCE_PARTS)
        or ".test." in path.name
        or path.suffix == ".pyc"
    )


def _copy_tree(
    source_root: Path,
    destination_root: Path,
    *,
    allowed_suffixes: frozenset[str],
) -> None:
    if not source_root.is_dir() or source_root.is_symlink():
        raise ArtifactBuildError(
            f"required source directory is unavailable: {source_root}"
        )
    for source in sorted(source_root.rglob("*")):
        if source.is_symlink():
            raise ArtifactBuildError(f"source symlinks are not allowed: {source}")
        if source.is_dir() or _is_ignored_source(source, source_root):
            continue
        relative = source.relative_to(source_root).as_posix()
        if not source.is_file():
            raise ArtifactBuildError(f"source is not a regular file: {source}")
        if source.suffix not in allowed_suffixes:
            raise ArtifactBuildError(f"unexpected runtime source file: {source}")
        _copy_file(source, destination_root / relative)


def _build_app_source(destination: Path) -> None:
    for relative in _APP_ROOT_FILES:
        _copy_file(REPOSITORY_ROOT / relative, destination / relative)
    _copy_file(
        REPOSITORY_ROOT / "web_app" / "DEPLOYMENT_GUIDE.md",
        destination / "DEPLOYMENT_GUIDE.md",
    )

    _copy_file(
        REPOSITORY_ROOT / "mcp_server" / "pyproject.toml",
        destination / "mcp_server" / "pyproject.toml",
    )
    _copy_tree(
        REPOSITORY_ROOT / "mcp_server" / "gds_etl_workbench",
        destination / "mcp_server" / "gds_etl_workbench",
        allowed_suffixes=frozenset({".py"}),
    )

    _copy_file(
        REPOSITORY_ROOT / "web_app" / "backend" / "pyproject.toml",
        destination / "web_app" / "backend" / "pyproject.toml",
    )
    _copy_tree(
        REPOSITORY_ROOT / "web_app" / "backend" / "gds_workbench_api",
        destination / "web_app" / "backend" / "gds_workbench_api",
        allowed_suffixes=frozenset({".json", ".py"}),
    )
    for relative in _FRONTEND_ROOT_FILES:
        _copy_file(
            REPOSITORY_ROOT / "web_app" / "frontend" / relative,
            destination / "web_app" / "frontend" / relative,
        )
    _copy_tree(
        REPOSITORY_ROOT / "web_app" / "frontend" / "src",
        destination / "web_app" / "frontend" / "src",
        allowed_suffixes=frozenset({".css", ".ts", ".tsx"}),
    )


def _tree_manifest(directory: Path) -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    paths = sorted(
        directory.rglob("*"),
        key=lambda path: path.relative_to(directory).as_posix(),
    )
    for path in paths:
        if path.is_symlink():
            raise ArtifactBuildError(f"generated symlinks are not allowed: {path}")
        if not path.is_file():
            continue
        content = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        )
    return files


def _write_zip(source_directory: Path, archive: Path) -> None:
    entries: list[tuple[str, Path, bool]] = []
    for path in source_directory.rglob("*"):
        if path.is_symlink():
            raise ArtifactBuildError(f"generated symlinks are not allowed: {path}")
        relative = path.relative_to(source_directory).as_posix()
        parts = relative.split("/")
        if (
            not relative
            or "\\" in relative
            or PurePosixPath(relative).is_absolute()
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ArtifactBuildError(f"unsafe generated ZIP member: {relative}")
        if path.is_dir():
            entries.append((f"{relative}/", path, True))
        elif path.is_file():
            entries.append((relative, path, False))
        else:
            raise ArtifactBuildError(f"generated entry is not regular: {path}")

    entries.sort(key=lambda entry: entry[0])
    names = [name for name, _path, _is_directory in entries]
    if len(names) != len(set(names)):
        raise ArtifactBuildError("generated ZIP member names are not unique")

    with ZipFile(
        archive, mode="w", compression=ZIP_DEFLATED, compresslevel=9
    ) as package:
        for name, path, is_directory in entries:
            compression = ZIP_STORED if is_directory else ZIP_DEFLATED
            info = ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = compression
            info.create_system = 3
            info.external_attr = _ZIP_DIRECTORY_MODE if is_directory else _ZIP_FILE_MODE
            package.writestr(
                info,
                b"" if is_directory else path.read_bytes(),
                compress_type=compression,
                compresslevel=9,
            )
    with ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ArtifactBuildError(
                f"generated ZIP failed integrity validation: {archive}"
            )


def _write_operator_files(staging: Path, app: Path) -> tuple[Path, Path]:
    manifest = staging / "artifact-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "agent_provider": "microsoft_foundry",
                "app_source": _tree_manifest(app),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _copy_file(
        Path(__file__).with_name("README.md"), staging / "UPLOAD_INSTRUCTIONS.md"
    )

    checksums = staging / "SHA256SUMS.txt"
    archives = (staging / f"{APP_DIRECTORY_NAME}.zip",)
    checksums.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in archives
        ),
        encoding="utf-8",
    )
    return manifest, checksums


def _result(output: Path) -> UploadArtifacts:
    return UploadArtifacts(
        output_directory=output,
        app_source_directory=output / APP_DIRECTORY_NAME,
        app_archive=output / f"{APP_DIRECTORY_NAME}.zip",
        manifest=output / "artifact-manifest.json",
        checksums=output / "SHA256SUMS.txt",
    )


def build_uploads(
    output_directory: Path,
    *,
    replace: bool = False,
    agent_provider: str = "microsoft_foundry",
) -> UploadArtifacts:
    """Create App source and a content-root ZIP for manual UI upload."""
    if agent_provider != "microsoft_foundry":
        raise ArtifactBuildError(f"unsupported agent provider: {agent_provider}")
    output = output_directory.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    existing_output = output.exists()
    if existing_output:
        if not replace:
            raise ArtifactBuildError(f"output already exists: {output}")
        marker = output / GENERATED_MARKER
        if (
            marker.is_symlink()
            or not marker.is_file()
            or marker.read_text(encoding="utf-8") != GENERATED_MARKER_VALUE
        ):
            raise ArtifactBuildError(
                f"refusing to replace unrecognized output: {output}"
            )

    workspace = Path(
        tempfile.mkdtemp(prefix=f".{output.name}-build-", dir=output.parent)
    )
    staging = workspace / "new"
    staging.mkdir()
    backup = workspace / "previous"
    try:
        app = staging / APP_DIRECTORY_NAME
        _build_app_source(app)
        _write_zip(app, staging / f"{APP_DIRECTORY_NAME}.zip")
        _write_operator_files(staging, app)
        (staging / GENERATED_MARKER).write_text(
            GENERATED_MARKER_VALUE,
            encoding="utf-8",
        )
        if existing_output:
            output.replace(backup)
        staging.replace(output)
    except BaseException:
        if backup.exists() and not output.exists():
            backup.replace(output)
        shutil.rmtree(workspace, ignore_errors=True)
        raise
    shutil.rmtree(workspace, ignore_errors=True)
    return _result(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--agent-provider",
        choices=("microsoft_foundry",),
        default="microsoft_foundry",
        help="Compatibility option; all builds use Microsoft Foundry and canonical app.yaml.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace only a prior output carrying this builder's safety marker.",
    )
    arguments = parser.parse_args()
    output = arguments.output
    if output is None:
        output = DEFAULT_OUTPUT
    try:
        result = build_uploads(
            output,
            replace=arguments.replace,
            agent_provider=arguments.agent_provider,
        )
    except ArtifactBuildError as error:
        parser.exit(2, f"artifact build refused: {error}\n")
    print(result.app_archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
