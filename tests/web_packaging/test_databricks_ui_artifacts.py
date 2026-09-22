from __future__ import annotations

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
    "app.yaml",
    "package-lock.json",
    "package.json",
    "pyproject.toml",
    "uv.lock",
}
APP_ROOT_DIRECTORIES = {"mcp_server", "web_app"}
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


def test_builder_creates_exact_ui_upload_roots(tmp_path: Path) -> None:
    builder = _load_builder()

    result = builder.build_uploads(tmp_path / "release")

    app_root = result.app_source_directory
    assert {path.name for path in app_root.iterdir()} == (
        APP_ROOT_FILES | APP_ROOT_DIRECTORIES
    )
    assert {path.name for path in result.output_directory.iterdir()} == {
        "gds-workbench-app-source",
        "gds-workbench-app-source.zip",
        "artifact-manifest.json",
        "SHA256SUMS.txt",
        "UPLOAD_INSTRUCTIONS.md",
        builder.GENERATED_MARKER,
    }
    assert "/artifacts/databricks-ui/" in ROOT_GITIGNORE.read_text(encoding="utf-8")
    assert "/artifacts/databricks-ui-foundry/" in ROOT_GITIGNORE.read_text(
        encoding="utf-8"
    )


def test_generated_app_contains_runtime_source_only(tmp_path: Path) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    app_files = _relative_files(result.app_source_directory)
    assert {
        path.name
        for path in (result.app_source_directory / "web_app/backend").iterdir()
    } == {"pyproject.toml", "gds_workbench_api"}

    assert "mcp_server/pyproject.toml" in app_files
    assert "mcp_server/gds_etl_workbench/runtime.py" in app_files
    assert "web_app/backend/pyproject.toml" in app_files
    assert "web_app/backend/uv.lock" not in app_files
    assert "web_app/backend/gds_workbench_api/app_process.py" in app_files
    assert "web_app/backend/gds_workbench_api/dependencies.py" in app_files
    assert (
        "web_app/backend/gds_workbench_api/config/agent_capabilities.json" in app_files
    )
    assert (
        "web_app/backend/gds_workbench_api/features/profiling/execution.py" in app_files
    )
    assert "web_app/backend/gds_workbench_api/config/profiling.json" in app_files
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


def test_operator_instructions_use_folder_upload_as_the_primary_ui_path() -> None:
    instructions = INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    normalized = " ".join(instructions.split())

    assert "Do not import the ZIP in the Workspace UI" in normalized
    assert "The ZIP is a transport container only" in normalized
    assert "Upload the expanded same-named folder" in normalized
    assert "drag the expanded `gds-workbench-app-source` folder" in normalized
    assert "flatten its nested source folders" in normalized
    assert "CLI upload alternative" in instructions
    assert "python3 deployment/databricks_ui/build_uploads.py\n" in instructions
    assert "Databricks-only" not in instructions
    assert "databricks-ui-foundry" not in instructions
    assert "Do not edit or replace its generated `app.yaml`" in normalized


def test_archives_have_explicit_hierarchy_and_match_expanded_trees(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")

    for source_directory, archive in (
        (result.app_source_directory, result.app_archive),
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

    for archive in (result.app_archive,):
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
    assert manifest["agent_provider"] == "microsoft_foundry"
    assert set(manifest) == {"agent_provider", "app_source"}

    for key, directory in (("app_source", result.app_source_directory),):
        records = {record["path"]: record for record in manifest[key]}
        assert set(records) == _relative_files(directory)
        for relative, record in records.items():
            content = (directory / relative).read_bytes()
            assert record["size"] == len(content)
            assert record["sha256"] == hashlib.sha256(content).hexdigest()


def test_checksum_file_matches_app_archive(tmp_path: Path) -> None:
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
    }


def test_extracted_app_workflow_runtime_assembles_from_source(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    result = builder.build_uploads(tmp_path / "release")
    extracted = tmp_path / "extracted-runtime"
    with ZipFile(result.app_archive) as package:
        package.extractall(extracted)

    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        str(extracted / relative) for relative in ("mcp_server", "web_app/backend")
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import asyncio, json; "
                "from importlib.resources import files; "
                "from pathlib import Path; "
                "import gds_etl_workbench, gds_workbench_api; "
                "source = Path.cwd().resolve(); "
                "assert all(Path(module.__file__).resolve().is_relative_to(source) "
                "for module in (gds_etl_workbench, gds_workbench_api)); "
                "from gds_etl_workbench.application.authorization import AuthorizationService; "
                "from gds_workbench_api.capabilities import load_default_agent_capabilities; "
                "from gds_workbench_api.features.profiling.execution import "
                "load_default_profiling_policy; "
                "assert load_default_profiling_policy().model_dump() == "
                "json.loads(files('gds_workbench_api').joinpath('config', "
                "'profiling.json').read_text(encoding='utf-8')); "
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
    assert (first.app_source_directory / "app.yaml").read_bytes() == (
        ROOT / "app.yaml"
    ).read_bytes()


def test_explicit_foundry_build_uses_canonical_manifest_and_is_self_contained(
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

    assert app_yaml.read_bytes() == (ROOT / "app.yaml").read_bytes()
    assert guide.read_bytes() == (ROOT / "web_app/DEPLOYMENT_GUIDE.md").read_bytes()
    assert manifest["agent_provider"] == "microsoft_foundry"
    assert set(manifest) == {"agent_provider", "app_source"}
    assert app_records["app.yaml"]["sha256"] == _sha256(app_yaml)
    with ZipFile(result.app_archive) as package:
        assert package.read("app.yaml") == app_yaml.read_bytes()
        assert package.read("DEPLOYMENT_GUIDE.md") == guide.read_bytes()


@pytest.mark.parametrize("provider", ["databricks", "unknown"])
def test_builder_rejects_removed_or_unknown_agent_provider_before_writing(
    tmp_path: Path, provider: str
) -> None:
    builder = _load_builder()
    output = tmp_path / "invalid-release"

    with pytest.raises(builder.ArtifactBuildError, match="unsupported agent provider"):
        builder.build_uploads(output, agent_provider=provider)

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

    def fail_build(_destination: Path) -> None:
        raise builder.ArtifactBuildError("simulated build failure")

    monkeypatch.setattr(builder, "_build_app_source", fail_build)
    with pytest.raises(builder.ArtifactBuildError, match="simulated build failure"):
        builder.build_uploads(output, replace=True)

    assert _sha256(output / "gds-workbench-app-source.zip") == original_checksum
