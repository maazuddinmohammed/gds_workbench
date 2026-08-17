from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

BUILD_SCRIPT = Path(__file__).parents[2] / "mcp_server" / "build_zip.py"
PROJECT_FILE = BUILD_SCRIPT.with_name("pyproject.toml")


def build_zip(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--output", str(output)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_appservice_zip_uses_runtime_only_allowlist(tmp_path: Path) -> None:
    artifact = tmp_path / "app.zip"
    completed = build_zip(artifact)
    assert completed.returncode == 0

    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        assert {
            "app.py",
            "startup.sh",
            "requirements.txt",
            "BUILD_MANIFEST.json",
            "gds_etl_workbench/tools/snapshots/dataset_description.py",
            "gds_etl_workbench/tools/snapshots/service.py",
            "gds_etl_workbench/tools/snapshots/storage.py",
            "gds_etl_workbench/tools/snapshots/metadata/archive.py",
            "gds_etl_workbench/tools/snapshots/metadata/contracts.py",
            "gds_etl_workbench/tools/snapshots/metadata/get_metadata_snapshot.py",
            "gds_etl_workbench/tools/snapshots/metadata/guidance.py",
            "gds_etl_workbench/tools/snapshots/metadata/sql.py",
            "gds_etl_workbench/tools/snapshots/model/selection.py",
            "gds_etl_workbench/tools/catalog/get_object_lineage.py",
            "gds_etl_workbench/tools/catalog/get_objects.py",
            "gds_etl_workbench/tools/catalog/list_objects.py",
            "gds_etl_workbench/tools/catalog/visibility.py",
            "gds_etl_workbench/tools/ingestion/copy_groups.py",
            "gds_etl_workbench/tools/processing/process_groups.py",
            "gds_etl_workbench/tools/tenants/get_tenant_details.py",
            "gds_etl_workbench/tools/tenants/tenant_locks.py",
        } <= set(names)
        assert "gds_etl_workbench/tools/snapshots/metadata/storage.py" not in names
        assert all(
            name in {"app.py", "startup.sh", "requirements.txt", "BUILD_MANIFEST.json"}
            or name.startswith("gds_etl_workbench/")
            for name in names
        )
        assert all("tests/" not in name and ".env" not in name for name in names)
        assert all(
            info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist()
        )

        manifest = json.loads(archive.read("BUILD_MANIFEST.json"))
        for item in manifest["files"]:
            content = archive.read(item["path"])
            assert len(content) == item["size"]
            assert hashlib.sha256(content).hexdigest() == item["sha256"]

        requirements = archive.read("requirements.txt").decode()
        assert "aiohttp==3.14.3" in requirements
        assert "azure-identity==1.25.3" in requirements
        assert "azure-storage-blob==12.30.0" in requirements

        startup = archive.read("startup.sh").decode()
        assert 'gds_server_port="${SERVER_PORT:-8000}"' in startup
        assert "gds_web_concurrency=2" in startup
        assert "gds_request_timeout_seconds=120" in startup
        assert "GDS_REQUEST_TIMEOUT_SECONDS" not in startup
        assert "WEB_CONCURRENCY" not in startup
        assert "${PORT" not in startup


def test_appservice_zip_builder_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "app.zip"
    first = build_zip(output)
    second = build_zip(output)

    assert first.returncode == 0
    assert second.returncode != 0


def test_packaged_server_import_does_not_require_project_metadata(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "app.zip"
    completed = build_zip(artifact)
    assert completed.returncode == 0

    app_root = tmp_path / "app"
    with zipfile.ZipFile(artifact) as archive:
        assert all(".dist-info/" not in name for name in archive.namelist())
        archive.extractall(app_root)

    project_version = tomllib.loads(PROJECT_FILE.read_text())["project"]["version"]
    import_check = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.metadata
import sys

installed_version = importlib.metadata.version


def version_without_project_metadata(name: str) -> str:
    if name == "gds-etl-workbench-mcp":
        raise importlib.metadata.PackageNotFoundError(name)
    return installed_version(name)


importlib.metadata.version = version_without_project_metadata
from gds_etl_workbench.adapters.mcp.server import MCP_SERVER_VERSION

assert MCP_SERVER_VERSION == sys.argv[1]
""",
            project_version,
        ],
        cwd=app_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert import_check.returncode == 0, import_check.stderr
