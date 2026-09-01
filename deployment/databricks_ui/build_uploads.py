#!/usr/bin/env python3
"""Build deterministic, source-only ZIPs for manual Databricks UI upload."""

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
DEFAULT_FOUNDRY_OUTPUT = REPOSITORY_ROOT / "artifacts" / "databricks-ui-foundry"
APP_DIRECTORY_NAME = "gds-workbench-app-source"
NOTEBOOK_DIRECTORY_NAME = "gds-workbench-notebooks"
GENERATED_MARKER = ".gds-databricks-ui-artifact"
GENERATED_MARKER_VALUE = "gds-databricks-ui-artifacts-v1\n"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ZIP_FILE_MODE = (stat.S_IFREG | 0o644) << 16
_ZIP_DIRECTORY_MODE = ((stat.S_IFDIR | 0o755) << 16) | 0x10

_APP_ROOT_FILES = (
    "app.foundry.yaml.example",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "uv.lock",
)
_AGENT_PROVIDER_MANIFESTS = {
    "databricks": "app.yaml",
    "microsoft_foundry": "app.foundry.yaml.example",
}
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
_NOTEBOOK_API_EXCLUDED_PREFIXES = frozenset(
    {
        "features/metadata",
        "features/metadata_change_sets",
        "features/model_scope",
        "features/output_templates",
        "features/prompts",
        "features/session",
        "features/sql_generation_guides",
        "features/tenant_locks",
        "features/tenants",
        "features/workflows/commands",
        "features/workflows/overview",
    }
)
_NOTEBOOK_API_EXCLUDED_FILES = frozenset(
    {
        "app_process.py",
        "authentication.py",
        "config/workflow_execution.json",
        "configuration.py",
        "errors.py",
        "features/model_change_sets/router.py",
        "features/workflows/authoring/change_set_apply_router.py",
        "features/workflows/execution/configuration.py",
        "frontend.py",
        "main.py",
        "runtime.py",
        "workflow_worker.py",
    }
)
_NOTEBOOK_ETL_EXCLUDED_PREFIXES = frozenset(
    {
        "adapters/mcp",
        "diagnostics",
        "tools/ingestion",
        "tools/processing",
        "tools/snapshots/dbml",
        "tools/tenants",
    }
)
_NOTEBOOK_ETL_EXCLUDED_FILES = frozenset(
    {
        "adapters/auth/middleware.py",
        "runtime.py",
        "tools/catalog/get_object_lineage.py",
        "tools/catalog/get_objects.py",
        "tools/catalog/list_objects.py",
        "tools/change_sets/metadata.py",
        "tools/change_sets/validation.py",
        "tools/databricks/execute_sql.py",
        "tools/modeling/code_generation_authoring.py",
        "tools/modeling/dimensional.py",
        "tools/modeling/logical.py",
        "tools/modeling/mapping_authoring.py",
        "tools/modeling/model_details.py",
        "tools/modeling/model_scope.py",
        "tools/server_contract.py",
        "tools/snapshots/archive.py",
        "tools/snapshots/metadata/archive.py",
        "tools/snapshots/metadata/describe_metadata_dataset.py",
        "tools/snapshots/metadata/get_metadata_snapshot.py",
        "tools/snapshots/metadata/guidance.py",
        "tools/snapshots/metadata/projection.py",
        "tools/snapshots/metadata/sql.py",
        "tools/snapshots/model/archive.py",
        "tools/snapshots/model/describe_model_dataset.py",
        "tools/snapshots/model/get_model_snapshot.py",
        "tools/snapshots/service.py",
        "tools/snapshots/storage.py",
    }
)


class ArtifactBuildError(RuntimeError):
    """A manual-upload artifact could not be built safely."""


class UploadArtifacts(NamedTuple):
    output_directory: Path
    app_source_directory: Path
    notebook_source_directory: Path
    app_archive: Path
    notebook_archive: Path
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
    excluded_relative_files: frozenset[str] = frozenset(),
    excluded_relative_prefixes: frozenset[str] = frozenset(),
) -> None:
    if not source_root.is_dir() or source_root.is_symlink():
        raise ArtifactBuildError(
            f"required source directory is unavailable: {source_root}"
        )
    for exclusion in excluded_relative_files | excluded_relative_prefixes:
        path = PurePosixPath(exclusion)
        if (
            not exclusion
            or "\\" in exclusion
            or path.is_absolute()
            or path.as_posix() != exclusion
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ArtifactBuildError(f"invalid source exclusion: {exclusion}")
    for relative in excluded_relative_files:
        excluded_source = source_root / relative
        if excluded_source.is_symlink() or not excluded_source.is_file():
            raise ArtifactBuildError(
                f"excluded source file is unavailable: {excluded_source}"
            )
    for relative in excluded_relative_prefixes:
        excluded_source = source_root / relative
        if excluded_source.is_symlink() or not excluded_source.is_dir():
            raise ArtifactBuildError(
                f"excluded source directory is unavailable: {excluded_source}"
            )

    for source in sorted(source_root.rglob("*")):
        if source.is_symlink():
            raise ArtifactBuildError(f"source symlinks are not allowed: {source}")
        if source.is_dir() or _is_ignored_source(source, source_root):
            continue
        relative = source.relative_to(source_root).as_posix()
        if relative in excluded_relative_files or any(
            relative == prefix or relative.startswith(f"{prefix}/")
            for prefix in excluded_relative_prefixes
        ):
            continue
        if not source.is_file():
            raise ArtifactBuildError(f"source is not a regular file: {source}")
        if source.suffix not in allowed_suffixes:
            raise ArtifactBuildError(f"unexpected runtime source file: {source}")
        _copy_file(source, destination_root / relative)


def _build_app_source(destination: Path, *, agent_provider: str) -> None:
    for relative in _APP_ROOT_FILES:
        _copy_file(REPOSITORY_ROOT / relative, destination / relative)
    try:
        manifest_source = _AGENT_PROVIDER_MANIFESTS[agent_provider]
    except KeyError as error:
        raise ArtifactBuildError(
            f"unsupported agent provider: {agent_provider}"
        ) from error
    _copy_file(REPOSITORY_ROOT / manifest_source, destination / "app.yaml")
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
    _copy_tree(
        REPOSITORY_ROOT / "web_app" / "backend" / "gds_workbench_runtime",
        destination / "web_app" / "backend" / "gds_workbench_runtime",
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


def _build_notebook_source(destination: Path) -> None:
    source_root = REPOSITORY_ROOT / "databricks_notebooks"
    _copy_file(source_root / ".env.example", destination / ".env.example")
    _copy_file(source_root / "requirements.txt", destination / "requirements.txt")
    for (
        package_name,
        package_root,
        allowed_suffixes,
        excluded_files,
        excluded_prefixes,
    ) in (
        (
            "gds_workbench_notebooks",
            source_root / "src" / "gds_workbench_notebooks",
            frozenset({".py"}),
            frozenset(),
            frozenset(),
        ),
        (
            "gds_workbench_runtime",
            REPOSITORY_ROOT / "web_app" / "backend" / "gds_workbench_runtime",
            frozenset({".json", ".py"}),
            frozenset(),
            frozenset(),
        ),
        (
            "gds_workbench_api",
            REPOSITORY_ROOT / "web_app" / "backend" / "gds_workbench_api",
            frozenset({".json", ".py"}),
            _NOTEBOOK_API_EXCLUDED_FILES,
            _NOTEBOOK_API_EXCLUDED_PREFIXES,
        ),
        (
            "gds_etl_workbench",
            REPOSITORY_ROOT / "mcp_server" / "gds_etl_workbench",
            frozenset({".py"}),
            _NOTEBOOK_ETL_EXCLUDED_FILES,
            _NOTEBOOK_ETL_EXCLUDED_PREFIXES,
        ),
    ):
        _copy_tree(
            package_root,
            destination / "src" / package_name,
            allowed_suffixes=allowed_suffixes,
            excluded_relative_files=excluded_files,
            excluded_relative_prefixes=excluded_prefixes,
        )
    _copy_tree(
        source_root / "notebooks",
        destination / "notebooks",
        allowed_suffixes=frozenset({".py"}),
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


def _write_operator_files(
    staging: Path, app: Path, notebooks: Path, *, agent_provider: str
) -> tuple[Path, Path]:
    manifest = staging / "artifact-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "agent_provider": agent_provider,
                "app_source": _tree_manifest(app),
                "notebook_source": _tree_manifest(notebooks),
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
    archives = (
        staging / f"{APP_DIRECTORY_NAME}.zip",
        staging / f"{NOTEBOOK_DIRECTORY_NAME}.zip",
    )
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
        notebook_source_directory=output / NOTEBOOK_DIRECTORY_NAME,
        app_archive=output / f"{APP_DIRECTORY_NAME}.zip",
        notebook_archive=output / f"{NOTEBOOK_DIRECTORY_NAME}.zip",
        manifest=output / "artifact-manifest.json",
        checksums=output / "SHA256SUMS.txt",
    )


def build_uploads(
    output_directory: Path,
    *,
    replace: bool = False,
    agent_provider: str = "databricks",
) -> UploadArtifacts:
    """Create expanded sources and content-root ZIPs for two UI target folders."""
    if agent_provider not in _AGENT_PROVIDER_MANIFESTS:
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
        notebooks = staging / NOTEBOOK_DIRECTORY_NAME
        _build_app_source(app, agent_provider=agent_provider)
        _build_notebook_source(notebooks)
        _write_zip(app, staging / f"{APP_DIRECTORY_NAME}.zip")
        _write_zip(notebooks, staging / f"{NOTEBOOK_DIRECTORY_NAME}.zip")
        _write_operator_files(
            staging,
            app,
            notebooks,
            agent_provider=agent_provider,
        )
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
        choices=tuple(_AGENT_PROVIDER_MANIFESTS),
        default="databricks",
        help="Select the Databricks-only or Foundry-enabled app.yaml before hashing.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace only a prior output carrying this builder's safety marker.",
    )
    arguments = parser.parse_args()
    output = arguments.output
    if output is None:
        output = (
            DEFAULT_FOUNDRY_OUTPUT
            if arguments.agent_provider == "microsoft_foundry"
            else DEFAULT_OUTPUT
        )
    try:
        result = build_uploads(
            output,
            replace=arguments.replace,
            agent_provider=arguments.agent_provider,
        )
    except ArtifactBuildError as error:
        parser.exit(2, f"artifact build refused: {error}\n")
    print(result.app_archive)
    print(result.notebook_archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
