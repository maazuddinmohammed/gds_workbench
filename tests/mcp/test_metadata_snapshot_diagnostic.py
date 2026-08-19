from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from gds_etl_workbench.diagnostics.metadata_snapshot import (
    inspect_deployment,
    load_settings_for_diagnostic,
)


BUILD_SCRIPT = Path(__file__).parents[2] / "mcp_server" / "build_zip.py"


def test_configuration_diagnostic_recovers_without_mutating_production_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = {
        "GDS_ENVIRONMENT": "production",
        "GDS_DATABASE_DSN": (
            "postgresql://app@db.example.invalid/workbench?sslmode=verify-full"
        ),
        "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
        "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
        "GDS_LOCAL_PRINCIPAL_OBJECT_ID": "33333333-3333-3333-3333-333333333333",
        "GDS_MCP_PUBLIC_URL": "https://workbench.example.test/mcp",
        "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
            "https://snapshot.blob.core.windows.net"
        ),
        "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
    }

    settings, clean = load_settings_for_diagnostic(values)

    assert settings is not None
    assert clean is False
    assert "GDS_LOCAL_PRINCIPAL_OBJECT_ID" in values
    output = capsys.readouterr().out
    assert "configuration=FAILED" in output
    assert "configuration_recovery=OK" in output


def test_deployment_inspection_checks_every_manifest_file(tmp_path: Path) -> None:
    artifact = tmp_path / "app.zip"
    completed = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), "--output", str(artifact)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0

    deployed_root = tmp_path / "deployed"
    with zipfile.ZipFile(artifact) as archive:
        archive.extractall(deployed_root)

    inspection = inspect_deployment(deployed_root)
    assert inspection.status == "OK"
    assert inspection.file_count > 0
    assert inspection.missing_count == 0
    assert inspection.mismatch_count == 0
    assert inspection.configuration_matches is True
    assert inspection.metadata_snapshot_matches is True

    help_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gds_etl_workbench.diagnostics.metadata_snapshot",
            "--help",
        ],
        cwd=deployed_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0
    assert "--tenant-id" in help_result.stdout

    diagnostic_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "gds_etl_workbench.diagnostics.metadata_snapshot",
            "--tenant-id",
            "5",
        ],
        cwd=deployed_root,
        env={},
        check=False,
        capture_output=True,
        text=True,
    )
    assert diagnostic_result.returncode == 1
    assert "deployment=OK" in diagnostic_result.stdout
    assert "configuration_source=OK" in diagnostic_result.stdout
    assert "metadata_snapshot_source=OK" in diagnostic_result.stdout
    assert "configuration=FAILED" in diagnostic_result.stdout
    assert "diagnostic=FAILED" in diagnostic_result.stdout
    assert diagnostic_result.stderr == ""

    configuration = deployed_root / "gds_etl_workbench" / "configuration.py"
    configuration.write_bytes(configuration.read_bytes() + b"\n# stale deployment\n")
    (deployed_root / "gds_etl_workbench" / "stale_file.py").write_text("pass\n")

    stale = inspect_deployment(deployed_root)
    assert stale.status == "FAILED"
    assert stale.missing_count == 0
    assert stale.mismatch_count == 1
    assert stale.unlisted_python_count == 1
    assert stale.configuration_matches is False
    assert stale.metadata_snapshot_matches is True
