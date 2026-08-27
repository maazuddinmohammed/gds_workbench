from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "deployment" / "databricks_ui" / "build_uploads.py"
ROOT_GITIGNORE = ROOT / ".gitignore"

APP_ROOT_FILES = {
    "app.yaml",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "uv.lock",
}
APP_ROOT_DIRECTORIES = {"mcp_server", "web_app"}
NOTEBOOK_PACKAGE_FILES = {"__init__.py", "app_client.py", "notebook.py"}
NOTEBOOK_SOURCE_FILES = {
    "analysis_inference.py",
    "analysis_validation.py",
    "code_generation.py",
    "conceptual.py",
    "dimensional.py",
    "logical.py",
    "mapping.py",
    "profiling.py",
}
FORBIDDEN_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "database",
    "docs",
    "load_and_merge_scripts",
    "node_modules",
    "plugins",
    "prototypes",
    "tests",
}


def _load_builder():
    spec = importlib.util.spec_from_file_location("databricks_ui_builder", BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _relative_files(directory: Path) -> set[str]:
    return {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_builder_creates_exact_ui_upload_roots(tmp_path: Path) -> None:
    builder = _load_builder()

    result = builder.build_uploads(tmp_path / "release")

    app_root = result.app_source_directory
    notebook_root = result.notebook_source_directory
    assert {path.name for path in app_root.iterdir()} == (
        APP_ROOT_FILES | APP_ROOT_DIRECTORIES
    )
    assert {path.name for path in notebook_root.iterdir()} == {
        "gds_workbench_notebooks",
        "notebooks",
        "requirements.txt",
    }
    assert {
        path.name for path in (notebook_root / "gds_workbench_notebooks").iterdir()
    } == (NOTEBOOK_PACKAGE_FILES)
    assert {path.name for path in (notebook_root / "notebooks").iterdir()} == (
        NOTEBOOK_SOURCE_FILES
    )
    assert "/artifacts/databricks-ui/" in ROOT_GITIGNORE.read_text(encoding="utf-8")


def test_generated_app_contains_runtime_source_only(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    app_files = _relative_files(result.app_source_directory)

    assert "mcp_server/pyproject.toml" in app_files
    assert "mcp_server/gds_etl_workbench/runtime.py" in app_files
    assert "web_app/backend/pyproject.toml" in app_files
    assert "web_app/backend/uv.lock" in app_files
    assert "web_app/backend/gds_workbench_api/app_process.py" in app_files
    assert (
        "web_app/backend/gds_workbench_api/config/agent_capabilities.json" in app_files
    )
    assert "web_app/frontend/index.html" in app_files
    assert "web_app/frontend/src/main.tsx" in app_files
    assert "web_app/frontend/src/styles.css" in app_files

    for relative in app_files:
        path = Path(relative)
        assert not (set(path.parts) & FORBIDDEN_PARTS)
        assert ".test." not in path.name
        assert not path.name.startswith(".env")
        assert path.suffix not in {".key", ".p12", ".pem", ".pfx", ".pyc"}

    assert not any(
        path.name == "dist" for path in result.app_source_directory.rglob("*")
    )
    assert not any(
        path.name == "Dockerfile" for path in result.app_source_directory.rglob("*")
    )


def test_generated_notebook_object_markers_are_unambiguous(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    package_root = result.notebook_source_directory / "gds_workbench_notebooks"
    notebook_root = result.notebook_source_directory / "notebooks"

    for name in NOTEBOOK_PACKAGE_FILES:
        assert (
            not (package_root / name)
            .read_text(encoding="utf-8")
            .startswith("# Databricks notebook source\n")
        )
    for name in NOTEBOOK_SOURCE_FILES:
        assert (
            (notebook_root / name)
            .read_text(encoding="utf-8")
            .startswith("# Databricks notebook source\n")
        )


def test_archives_have_no_extra_outer_directory_and_match_expanded_trees(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")

    for source_directory, archive in (
        (result.app_source_directory, result.app_archive),
        (result.notebook_source_directory, result.notebook_archive),
    ):
        expected = _relative_files(source_directory)
        with ZipFile(archive) as package:
            actual = {name for name in package.namelist() if not name.endswith("/")}
            assert package.testzip() is None
        assert actual == expected


def test_archive_members_are_safe_regular_reproducible_files(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")

    for archive in (result.app_archive, result.notebook_archive):
        with ZipFile(archive) as package:
            names = package.namelist()
            assert names == sorted(names)
            assert len(names) == len(set(names))
            for info in package.infolist():
                path = Path(info.filename)
                mode = info.external_attr >> 16
                assert not path.is_absolute()
                assert ".." not in path.parts
                assert not info.is_dir()
                assert info.date_time == (1980, 1, 1, 0, 0, 0)
                assert stat.S_ISREG(mode)
                assert stat.S_IMODE(mode) == 0o644


def test_manifest_matches_every_generated_source_file(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))

    for key, directory in (
        ("app_source", result.app_source_directory),
        ("notebook_source", result.notebook_source_directory),
    ):
        records = {record["path"]: record for record in manifest[key]}
        assert set(records) == _relative_files(directory)
        for relative, record in records.items():
            content = (directory / relative).read_bytes()
            assert record["size"] == len(content)
            assert record["sha256"] == hashlib.sha256(content).hexdigest()


def test_checksum_file_matches_both_archives(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    records = {
        name: digest
        for digest, name in (
            line.split("  ", maxsplit=1)
            for line in result.checksums.read_text(encoding="utf-8").splitlines()
        )
    }

    assert records == {
        result.app_archive.name: _sha256(result.app_archive),
        result.notebook_archive.name: _sha256(result.notebook_archive),
    }


def test_extracted_notebook_package_imports_without_repository_paths(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    extracted = tmp_path / "extracted-notebooks"
    with ZipFile(result.notebook_archive) as package:
        package.extractall(extracted)

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(extracted)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "from gds_workbench_notebooks import run_notebook; assert callable(run_notebook)",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr


def test_archives_are_reproducible_and_source_files_are_unchanged(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    first = builder.build_uploads(tmp_path / "first")
    second = builder.build_uploads(tmp_path / "second")

    assert _sha256(first.app_archive) == _sha256(second.app_archive)
    assert _sha256(first.notebook_archive) == _sha256(second.notebook_archive)
    assert (first.app_source_directory / "app.yaml").read_bytes() == (
        ROOT / "app.yaml"
    ).read_bytes()
    assert (
        first.notebook_source_directory / "gds_workbench_notebooks" / "app_client.py"
    ).read_bytes() == (
        ROOT / "databricks_notebooks" / "gds_workbench_notebooks" / "app_client.py"
    ).read_bytes()


def test_existing_output_is_never_replaced_without_its_generated_marker(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    output = tmp_path / "release"
    output.mkdir()
    (output / "user-file.txt").write_text("preserve me", encoding="utf-8")

    with pytest.raises(builder.ArtifactBuildError, match="refusing to replace"):
        builder.build_uploads(output, replace=True)

    assert (output / "user-file.txt").read_text(encoding="utf-8") == "preserve me"


def test_failed_rebuild_preserves_previous_generated_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = _load_builder()
    output = tmp_path / "release"
    builder.build_uploads(output)
    original_checksum = _sha256(output / "gds-workbench-app-source.zip")

    def fail_build(_destination: Path) -> None:
        raise builder.ArtifactBuildError("simulated build failure")

    monkeypatch.setattr(builder, "_build_app_source", fail_build)
    with pytest.raises(builder.ArtifactBuildError, match="simulated build failure"):
        builder.build_uploads(output, replace=True)

    assert _sha256(output / "gds-workbench-app-source.zip") == original_checksum
