from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "deployment" / "databricks_ui" / "build_uploads.py"
INSTRUCTIONS_PATH = ROOT / "deployment" / "databricks_ui" / "README.md"
ROOT_GITIGNORE = ROOT / ".gitignore"

APP_ROOT_FILES = {
    "DEPLOYMENT_GUIDE.md",
    "app.foundry.yaml.example",
    "app.yaml",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "uv.lock",
}
APP_ROOT_DIRECTORIES = {"mcp_server", "web_app"}
NOTEBOOK_PACKAGE_SOURCES = {
    "gds_workbench_notebooks": (
        ROOT / "databricks_notebooks" / "src" / "gds_workbench_notebooks",
        {".py"},
    ),
    "gds_workbench_runtime": (
        ROOT / "web_app" / "backend" / "gds_workbench_runtime",
        {".json", ".py"},
    ),
    "gds_workbench_api": (
        ROOT / "web_app" / "backend" / "gds_workbench_api",
        {".json", ".py"},
    ),
    "gds_etl_workbench": (
        ROOT / "mcp_server" / "gds_etl_workbench",
        {".py"},
    ),
}
NOTEBOOK_SOURCE_ROOT = ROOT / "databricks_notebooks" / "notebooks"
NOTEBOOK_PACKAGE_EXCLUSIONS = {
    "gds_workbench_api": (
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
        },
        {
            "features/metadata",
            "features/metadata_change_sets",
            "features/model_input_scope",
            "features/output_templates",
            "features/prompts",
            "features/session",
            "features/sql_generation_guides",
            "features/tenant_locks",
            "features/tenants",
            "features/workflows/commands",
            "features/workflows/overview",
        },
    ),
    "gds_etl_workbench": (
        {
            "adapters/auth/middleware.py",
            "runtime.py",
            "tools/catalog/get_object_lineage.py",
            "tools/catalog/get_objects.py",
            "tools/catalog/inspect_metadata.py",
            "tools/catalog/list_objects.py",
            "tools/change_sets/metadata.py",
            "tools/change_sets/validation.py",
            "tools/databricks/execute_sql.py",
            "tools/modeling/model_details.py",
            "tools/modeling/model_input_scope.py",
            "tools/modeling/read_model_section.py",
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
        },
        {
            "adapters/mcp",
            "diagnostics",
            "tools/ingestion",
            "tools/processing",
            "tools/snapshots/dbml",
            "tools/tenants",
        },
    ),
}
IGNORED_RUNTIME_PARTS = {
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "test",
    "tests",
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


def _relative_directories(directory: Path) -> set[str]:
    return {
        f"{path.relative_to(directory).as_posix()}/"
        for path in directory.rglob("*")
        if path.is_dir()
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_runtime_files(source_root: Path, suffixes: set[str]) -> set[str]:
    return {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if path.is_file()
        and path.name not in {".DS_Store", "README.md"}
        and not (set(path.relative_to(source_root).parts) & IGNORED_RUNTIME_PARTS)
        and ".test." not in path.name
        and path.suffix in suffixes
    }


def _is_notebook_excluded(package_name: str, relative: str) -> bool:
    excluded_files, excluded_prefixes = NOTEBOOK_PACKAGE_EXCLUSIONS.get(
        package_name, (set(), set())
    )
    return relative in excluded_files or any(
        relative == prefix or relative.startswith(f"{prefix}/")
        for prefix in excluded_prefixes
    )


def test_builder_creates_exact_ui_upload_roots(tmp_path: Path) -> None:
    builder = _load_builder()

    result = builder.build_uploads(tmp_path / "release")

    app_root = result.app_source_directory
    notebook_root = result.notebook_source_directory
    assert {path.name for path in app_root.iterdir()} == (
        APP_ROOT_FILES | APP_ROOT_DIRECTORIES
    )
    assert {path.name for path in notebook_root.iterdir()} == {
        ".env.example",
        "notebooks",
        "requirements.txt",
        "src",
    }
    assert {path.name for path in (notebook_root / "src").iterdir()} == set(
        NOTEBOOK_PACKAGE_SOURCES
    )
    assert _relative_files(notebook_root / "notebooks") == {
        path.name for path in NOTEBOOK_SOURCE_ROOT.glob("*.py")
    }
    for package_name, (source_root, suffixes) in NOTEBOOK_PACKAGE_SOURCES.items():
        generated_root = notebook_root / "src" / package_name
        expected_files = {
            relative
            for relative in _expected_runtime_files(source_root, suffixes)
            if not _is_notebook_excluded(package_name, relative)
        }
        assert _relative_files(generated_root) == expected_files
        for relative in expected_files:
            assert (generated_root / relative).read_bytes() == (
                source_root / relative
            ).read_bytes()
    assert "/artifacts/databricks-ui/" in ROOT_GITIGNORE.read_text(encoding="utf-8")
    assert "/artifacts/databricks-ui-foundry/" in ROOT_GITIGNORE.read_text(
        encoding="utf-8"
    )


def test_notebook_pruning_does_not_remove_sources_from_the_app_artifact(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    app_roots = {
        "gds_workbench_api": (
            result.app_source_directory / "web_app/backend/gds_workbench_api"
        ),
        "gds_etl_workbench": result.app_source_directory
        / "mcp_server/gds_etl_workbench",
    }

    for package_name, (source_root, suffixes) in NOTEBOOK_PACKAGE_SOURCES.items():
        if package_name not in NOTEBOOK_PACKAGE_EXCLUSIONS:
            continue
        generated_root = result.notebook_source_directory / "src" / package_name
        excluded = {
            relative
            for relative in _expected_runtime_files(source_root, suffixes)
            if _is_notebook_excluded(package_name, relative)
        }
        assert excluded
        for relative in excluded:
            assert not (generated_root / relative).exists()
            assert (app_roots[package_name] / relative).read_bytes() == (
                source_root / relative
            ).read_bytes()


def test_generated_app_contains_runtime_source_only(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    app_files = _relative_files(result.app_source_directory)

    assert "mcp_server/pyproject.toml" in app_files
    assert "mcp_server/gds_etl_workbench/runtime.py" in app_files
    assert "web_app/backend/pyproject.toml" in app_files
    assert "web_app/backend/uv.lock" not in app_files
    assert "web_app/backend/gds_workbench_api/app_process.py" in app_files
    assert (
        "web_app/backend/gds_workbench_api/config/agent_capabilities.json" in app_files
    )
    assert "web_app/backend/gds_workbench_runtime/profiling/execution.py" in app_files
    assert "web_app/backend/gds_workbench_runtime/config/profiling.json" in app_files
    assert "web_app/frontend/index.html" in app_files
    assert "web_app/frontend/src/main.tsx" in app_files
    assert "web_app/frontend/src/styles.css" in app_files
    assert (result.app_source_directory / "DEPLOYMENT_GUIDE.md").read_bytes() == (
        ROOT / "web_app/DEPLOYMENT_GUIDE.md"
    ).read_bytes()
    assert (
        result.app_source_directory / "web_app/frontend/index.html"
    ).read_bytes() == (ROOT / "web_app/frontend/index.html").read_bytes()

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


def test_generated_notebook_is_source_only_and_has_unambiguous_markers(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    source_root = result.notebook_source_directory / "src"
    package_root = source_root / "gds_workbench_notebooks"
    notebook_root = result.notebook_source_directory / "notebooks"
    notebook_files = _relative_files(result.notebook_source_directory)

    assert ".env.example" in notebook_files
    assert ".env" not in notebook_files
    assert "requirements.txt" in notebook_files
    assert "notebooks/00_tenant_lock.py" in notebook_files
    assert not any(Path(relative).name == ".env" for relative in notebook_files)
    assert not any(Path(relative).suffix == ".whl" for relative in notebook_files)

    for path in package_root.rglob("*.py"):
        assert not path.read_text(encoding="utf-8").startswith(
            "# Databricks notebook source\n"
        )
    for path in notebook_root.glob("*.py"):
        assert path.read_text(encoding="utf-8").startswith(
            "# Databricks notebook source\n"
        )

    for relative in notebook_files:
        path = Path(relative)
        assert not (set(path.parts) & FORBIDDEN_PARTS)
        assert ".test." not in path.name
        assert path.suffix not in {".key", ".p12", ".pem", ".pfx", ".pyc"}


def test_generated_notebook_python_is_valid_for_databricks_runtime_16_4(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")

    for path in result.notebook_source_directory.rglob("*.py"):
        ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            feature_version=(3, 12),
        )


def test_notebook_entrypoints_do_not_start_app_or_mcp_servers(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    forbidden_imports = {
        "gds_etl_workbench.adapters.mcp.server",
        "gds_etl_workbench.runtime",
        "gds_workbench_api.app_process",
        "gds_workbench_api.workflow_worker",
        "gunicorn",
        "mcp",
        "subprocess",
        "uvicorn",
    }

    for path in (result.notebook_source_directory / "notebooks").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        assert not any(
            imported == forbidden or imported.startswith(f"{forbidden}.")
            for imported in imports
            for forbidden in forbidden_imports
        )


def test_operator_instructions_use_folder_upload_as_the_primary_ui_path() -> None:
    instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    normalized = " ".join(instructions.split())

    assert "Do not import the ZIP in the Workspace UI" in normalized
    assert "The ZIPs are transport containers only" in normalized
    assert "Upload the expanded same-named folder" in normalized
    assert "Drag the expanded local `gds-workbench-notebooks` folder" in normalized
    assert "drag the expanded `gds-workbench-app-source` folder" in normalized
    assert "flatten its nested source folders" in normalized
    assert "CLI upload alternative" in instructions
    assert "--agent-provider microsoft_foundry" in instructions
    assert "Do not edit or replace its generated `app.yaml`" in normalized


def test_archives_have_explicit_hierarchy_and_match_expanded_trees(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")

    for source_directory, archive in (
        (result.app_source_directory, result.app_archive),
        (result.notebook_source_directory, result.notebook_archive),
    ):
        expected_files = _relative_files(source_directory)
        expected_directories = _relative_directories(source_directory)
        with ZipFile(archive) as package:
            infos = package.infolist()
            actual_files = {info.filename for info in infos if not info.is_dir()}
            actual_directories = {info.filename for info in infos if info.is_dir()}
            assert package.testzip() is None
        assert actual_files == expected_files
        assert actual_directories == expected_directories
        assert not any(
            name.startswith(f"{source_directory.name}/")
            for name in actual_files | actual_directories
        )

        names = [info.filename for info in infos]
        positions = {name: index for index, name in enumerate(names)}
        for filename in actual_files:
            parent = PurePosixPath(filename).parent
            while parent != PurePosixPath("."):
                directory_name = f"{parent.as_posix()}/"
                assert directory_name in positions
                assert positions[directory_name] < positions[filename]
                parent = parent.parent

        extracted = tmp_path / f"extracted-{archive.stem}"
        with ZipFile(archive) as package:
            package.extractall(extracted)
        assert _relative_files(extracted) == expected_files
        assert _relative_directories(extracted) == expected_directories
        assert not (extracted / source_directory.name).exists()


def test_archive_members_are_safe_reproducible_files_and_directories(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")

    for archive in (result.app_archive, result.notebook_archive):
        with ZipFile(archive) as package:
            names = package.namelist()
            assert names == sorted(names)
            assert len(names) == len(set(names))
            for info in package.infolist():
                raw_name = info.filename.removesuffix("/")
                path = PurePosixPath(raw_name)
                mode = info.external_attr >> 16
                assert not path.is_absolute()
                assert ".." not in path.parts
                assert "." not in path.parts
                assert "\\" not in info.filename
                assert info.date_time == (1980, 1, 1, 0, 0, 0)
                assert info.create_system == 3
                if info.is_dir():
                    assert info.file_size == 0
                    assert info.compress_size == 0
                    assert info.compress_type == ZIP_STORED
                    assert stat.S_ISDIR(mode)
                    assert stat.S_IMODE(mode) == 0o755
                else:
                    assert info.compress_type == ZIP_DEFLATED
                    assert stat.S_ISREG(mode)
                    assert stat.S_IMODE(mode) == 0o644


def test_manifest_matches_every_generated_source_file(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert manifest["agent_provider"] == "databricks"

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
    artifact_source = extracted / "src"
    environment["PYTHONPATH"] = str(artifact_source)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "import gds_etl_workbench, gds_workbench_api, gds_workbench_notebooks, "
                "gds_workbench_runtime; "
                "from gds_workbench_notebooks.notebook import run_notebook; "
                "source = Path('src').resolve(); "
                "modules = (gds_etl_workbench, gds_workbench_api, "
                "gds_workbench_notebooks, gds_workbench_runtime); "
                "assert callable(run_notebook); "
                "assert all(Path(module.__file__).resolve().is_relative_to(source) "
                "for module in modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=extracted,
    )
    assert completed.returncode == 0, completed.stderr


def test_every_packaged_notebook_module_imports_from_the_extracted_artifact(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    extracted = tmp_path / "extracted-all-modules"
    with ZipFile(result.notebook_archive) as package:
        package.extractall(extracted)

    source_root = extracted / "src"
    modules = set()
    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root)
        parts = relative.with_suffix("").parts
        modules.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib, json, sys; "
                "[importlib.import_module(name) for name in json.loads(sys.argv[1])]"
            ),
            json.dumps(sorted(modules)),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=extracted,
    )
    assert completed.returncode == 0, completed.stderr


def test_extracted_notebook_shared_workflow_runtime_assembles_from_source(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    extracted = tmp_path / "extracted-runtime"
    with ZipFile(result.notebook_archive) as package:
        package.extractall(extracted)

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(extracted / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import asyncio; "
                "from gds_etl_workbench.application.authorization import AuthorizationService; "
                "from gds_workbench_api.capabilities import load_default_agent_capabilities; "
                "from gds_workbench_api.features.workflows.execution.assembly import "
                "create_workflow_runtime_services; "
                "from gds_workbench_api.integrations.agents.configuration import "
                "AgentRuntimeConfiguration; "
                "from gds_workbench_api.integrations.databricks import "
                "create_databricks_execution_adapters; "
                "services = create_workflow_runtime_services("
                "database=object(), authorizer=AuthorizationService(), "
                "agent_runtime=AgentRuntimeConfiguration("
                "mode='fake', timeout_seconds=120, connections=()), "
                "agent_capability_registry=load_default_agent_capabilities(), "
                "databricks_environment_code='PROD', "
                "databricks_execution=create_databricks_execution_adapters('fake')); "
                "execution = services.execution_services(); "
                "assert all(getattr(execution, name) is getattr(services, name) for name in ("
                "'profiling', 'analysis_inference', 'analysis_validation', 'conceptual', "
                "'logical', 'dimensional', 'mapping', 'code_generation')); "
                "asyncio.run(services.close())"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=extracted,
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
        first.notebook_source_directory
        / "src"
        / "gds_workbench_notebooks"
        / "runtime.py"
    ).read_bytes() == (
        ROOT / "databricks_notebooks" / "src" / "gds_workbench_notebooks" / "runtime.py"
    ).read_bytes()


def test_foundry_build_selects_manifest_before_hashing_and_is_self_contained(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(
        tmp_path / "foundry-release",
        agent_provider="microsoft_foundry",
    )

    app_yaml = result.app_source_directory / "app.yaml"
    guide = result.app_source_directory / "DEPLOYMENT_GUIDE.md"
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    app_records = {record["path"]: record for record in manifest["app_source"]}

    assert app_yaml.read_bytes() == (ROOT / "app.foundry.yaml.example").read_bytes()
    assert guide.read_bytes() == (ROOT / "web_app/DEPLOYMENT_GUIDE.md").read_bytes()
    assert manifest["agent_provider"] == "microsoft_foundry"
    assert app_records["app.yaml"]["sha256"] == _sha256(app_yaml)
    with ZipFile(result.app_archive) as package:
        assert package.read("app.yaml") == app_yaml.read_bytes()
        assert package.read("DEPLOYMENT_GUIDE.md") == guide.read_bytes()


def test_builder_rejects_unknown_agent_provider_before_writing(tmp_path: Path) -> None:
    builder = _load_builder()
    output = tmp_path / "invalid-release"

    with pytest.raises(builder.ArtifactBuildError, match="unsupported agent provider"):
        builder.build_uploads(output, agent_provider="unknown")

    assert not output.exists()


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

    def fail_build(_destination: Path, *, agent_provider: str) -> None:
        assert agent_provider == "databricks"
        raise builder.ArtifactBuildError("simulated build failure")

    monkeypatch.setattr(builder, "_build_app_source", fail_build)
    with pytest.raises(builder.ArtifactBuildError, match="simulated build failure"):
        builder.build_uploads(output, replace=True)

    assert _sha256(output / "gds-workbench-app-source.zip") == original_checksum
