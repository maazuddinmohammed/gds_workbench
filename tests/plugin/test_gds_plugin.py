from __future__ import annotations

import json
import os
import re
import subprocess
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import pytest

from gds_etl_workbench.tools.snapshots.metadata.archive import (
    build_snapshot_archive,
    encode_dataset,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = REPOSITORY_ROOT / "plugins" / "gds"
METADATA_SKILL = PLUGIN_ROOT / "skills" / "manage-gds-metadata"
TOOLS_REFERENCE = METADATA_SKILL / "references" / "tools.md"
SHELL_INITIALIZER = METADATA_SKILL / "scripts" / "initialize-gds-workspace.sh"
POWERSHELL_INITIALIZER = (
    METADATA_SKILL / "scripts" / "initialize-gds-workspace.ps1"
)
SHELL_SNAPSHOT_VALIDATOR = (
    METADATA_SKILL / "scripts" / "validate-metadata-snapshot.sh"
)
POWERSHELL_SNAPSHOT_VALIDATOR = (
    METADATA_SKILL / "scripts" / "validate-metadata-snapshot.ps1"
)
SHELL_CATALOG_INSPECTOR = (
    METADATA_SKILL / "scripts" / "inspect-metadata-catalog.sh"
)
POWERSHELL_CATALOG_INSPECTOR = (
    METADATA_SKILL / "scripts" / "inspect-metadata-catalog.ps1"
)
SHELL_CHANGE_SET_INITIALIZER = (
    METADATA_SKILL / "scripts" / "initialize-metadata-change-set.sh"
)
POWERSHELL_CHANGE_SET_INITIALIZER = (
    METADATA_SKILL / "scripts" / "initialize-metadata-change-set.ps1"
)
SHELL_LOCAL_CHANGE_SET_VALIDATOR = (
    METADATA_SKILL / "scripts" / "validate-local-change-set.sh"
)
POWERSHELL_LOCAL_CHANGE_SET_VALIDATOR = (
    METADATA_SKILL / "scripts" / "validate-local-change-set.ps1"
)
SHELL_LOCAL_STATE_UPDATER = (
    METADATA_SKILL / "scripts" / "update-local-change-set-state.sh"
)
POWERSHELL_LOCAL_STATE_UPDATER = (
    METADATA_SKILL / "scripts" / "update-local-change-set-state.ps1"
)
SHELL_LOCAL_RECORD_UPSERTER = (
    METADATA_SKILL / "scripts" / "upsert-local-metadata-record.sh"
)
POWERSHELL_LOCAL_RECORD_UPSERTER = (
    METADATA_SKILL / "scripts" / "upsert-local-metadata-record.ps1"
)
POWERSHELL_SCHEMA_HELPER = (
    METADATA_SKILL / "scripts" / "metadata-schema.ps1"
)
SHELL_STAGE_REVIEWER = (
    METADATA_SKILL / "scripts" / "prepare-metadata-stage-review.sh"
)
POWERSHELL_STAGE_REVIEWER = (
    METADATA_SKILL / "scripts" / "prepare-metadata-stage-review.ps1"
)
SHELL_LOCAL_RECORD_REMOVER = (
    METADATA_SKILL / "scripts" / "remove-local-metadata-record.sh"
)
POWERSHELL_LOCAL_RECORD_REMOVER = (
    METADATA_SKILL / "scripts" / "remove-local-metadata-record.ps1"
)
SNAPSHOT_ID = UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233")
CHANGE_SET_ID = UUID("4a4d40a7-7fc9-48ab-b1dc-c14e23ee64ad")

EXPECTED_TOOLS = {
    "list_tenants",
    "get_tenant_details",
    "list_objects",
    "get_objects",
    "get_object_lineage",
    "list_copy_groups",
    "get_copy_group",
    "list_process_groups",
    "get_process_group",
    "get_metadata_snapshot",
    "check_tenant_lock",
    "acquire_tenant_lock",
    "renew_tenant_lock",
    "release_tenant_lock",
    "override_tenant_lock",
    "create_metadata_change_set",
    "stage_metadata_change_set",
    "get_metadata_change_set",
    "validate_metadata_change_set",
    "apply_metadata_change_set",
    "archive_metadata_change_set",
}

ELIGIBLE_DATASETS = {
    "source_object",
    "source_attribute",
    "bronze_object",
    "bronze_attribute",
    "silver_object",
    "silver_attribute",
    "gold_object",
    "gold_attribute",
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "copy_group",
    "member_group",
    "copy_group_control",
    "copy",
    "process_group",
    "process",
}


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _run_shell(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SHELL_INITIALIZER), str(root)],
        cwd=root.parent,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


def _line_output(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        key, separator, value = line.partition("=")
        assert separator, line
        values[key] = value
    return values


def _build_snapshot(
    workspace: Path,
    *,
    include_project: bool = False,
    dataset_rows: dict[str, list[dict[str, Any]]] | None = None,
) -> Path:
    archive_path = workspace / "snapshot.zip"
    encoded_datasets = []
    for dataset in DATASETS:
        rows: list[dict[str, Any]] = []
        if include_project and dataset.name == "project":
            rows.append(
                {
                    "project_code": "DEMO",
                    "project_name": "Demo",
                    "project_description": "SENSITIVE-ROW-CONTENT",
                    "is_active": True,
                }
            )
        if dataset_rows and dataset.name in dataset_rows:
            rows.extend(dataset_rows[dataset.name])
        encoded_datasets.append(encode_dataset(dataset, rows))
    build_snapshot_archive(
        archive_path,
        snapshot_id=SNAPSHOT_ID,
        tenant_code="TENANT",
        created_time=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        available_until=datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
        + timedelta(minutes=20),
        encoded_datasets=tuple(encoded_datasets),
        max_archive_bytes=268435456,
    )
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(workspace)
    return workspace / "metadata-snapshot"


def _run_snapshot_validator(
    snapshot: Path,
    *,
    tenant_code: str = "TENANT",
    snapshot_id: str | None = str(SNAPSHOT_ID),
) -> subprocess.CompletedProcess[str]:
    arguments = [str(SHELL_SNAPSHOT_VALIDATOR), str(snapshot), tenant_code]
    if snapshot_id is not None:
        arguments.append(snapshot_id)
    return subprocess.run(
        arguments,
        cwd=snapshot.parent,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_catalog_inspector(
    snapshot: Path,
    dataset: str | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [str(SHELL_CATALOG_INSPECTOR), str(snapshot)]
    if dataset is not None:
        arguments.append(dataset)
    return subprocess.run(
        arguments,
        cwd=snapshot.parent,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_change_set_initializer(
    workspace: Path,
    *,
    usage: str = "fresh",
    acknowledge_outdated: bool = False,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        str(SHELL_CHANGE_SET_INITIALIZER),
        "--workspace",
        str(workspace),
        "--tenant-id",
        "1",
        "--tenant-code",
        "TENANT",
        "--snapshot-id",
        str(SNAPSHOT_ID),
        "--snapshot-usage",
        usage,
        "--change-set-id",
        str(CHANGE_SET_ID),
        "--server-status",
        "active",
        "--draft-revision",
        "1",
    ]
    if acknowledge_outdated:
        arguments.append("--acknowledge-outdated-snapshot")
    return subprocess.run(
        arguments,
        cwd=workspace.parent,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_local_change_set_validator(
    change_set: Path,
    *,
    revision: int = 1,
    require_staged: bool = False,
    require_reviewed: bool = False,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        str(SHELL_LOCAL_CHANGE_SET_VALIDATOR),
        str(change_set),
        str(CHANGE_SET_ID),
        str(revision),
    ]
    if require_staged:
        arguments.append("--require-staged")
    if require_reviewed:
        arguments.append("--require-reviewed")
    return subprocess.run(
        arguments,
        cwd=change_set.parent,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_local_state_updater(
    change_set: Path,
    *,
    expected_revision: int,
    server_revision: int,
    status: str,
    dataset: str | None = None,
    sha256: str | None = None,
) -> subprocess.CompletedProcess[str]:
    arguments = [
        str(SHELL_LOCAL_STATE_UPDATER),
        "--change-set",
        str(change_set),
        "--change-set-id",
        str(CHANGE_SET_ID),
        "--expected-current-revision",
        str(expected_revision),
        "--server-revision",
        str(server_revision),
        "--server-status",
        status,
    ]
    if dataset is not None:
        arguments.extend(["--staged-dataset", dataset])
    if sha256 is not None:
        arguments.extend(["--staged-sha256", sha256])
    return subprocess.run(
        arguments,
        cwd=change_set.parent,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_local_record_upserter(
    change_set: Path,
    dataset: str,
    record_file: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(SHELL_LOCAL_RECORD_UPSERTER),
            "--change-set",
            str(change_set),
            "--dataset",
            dataset,
            "--record-file",
            str(record_file),
        ],
        cwd=change_set.parent,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _run_stage_reviewer(
    change_set: Path,
    *,
    revision: int = 1,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(SHELL_STAGE_REVIEWER),
            "--change-set",
            str(change_set),
            "--change-set-id",
            str(CHANGE_SET_ID),
            "--expected-draft-revision",
            str(revision),
        ],
        cwd=change_set.parent,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def _run_local_record_remover(
    change_set: Path,
    dataset: str,
    key_file: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(SHELL_LOCAL_RECORD_REMOVER),
            "--change-set",
            str(change_set),
            "--dataset",
            dataset,
            "--key-file",
            str(key_file),
        ],
        cwd=change_set.parent,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )


def _source_object_record(**updates: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "tenant_code": "TENANT",
        "system_code": "SYSTEM",
        "connection_code": "CONNECTION",
        "object_schema": "dbo",
        "object_name": "customer",
        "fc_object_schema": None,
        "fc_object_name": None,
        "object_transformation": None,
        "object_description": None,
        "batch_attribute_name": None,
        "object_type_code": "TABLE",
        "zone_code": "source",
        "is_locked": False,
        "is_active": True,
    }
    record.update(updates)
    return record


def _dataset_summary(stdout: str, dataset: str) -> list[str]:
    prefix = f"dataset={dataset}|"
    matches = [line for line in stdout.splitlines() if line.startswith(prefix)]
    assert len(matches) == 1
    return matches[0].removeprefix("dataset=").split("|")


def test_plugin_contract_is_named_gds_and_contains_no_credentials() -> None:
    manifest = _json(PLUGIN_ROOT / "plugin.json")
    mcp = _json(PLUGIN_ROOT / "mcp.json")

    assert manifest["name"] == PLUGIN_ROOT.name == "gds"
    assert manifest["version"] == "1.0.0"
    assert manifest["$schema"].endswith("/plugin.schema.json")
    assert (PLUGIN_ROOT / "skills" / "understand-gds" / "SKILL.md").is_file()
    assert (METADATA_SKILL / "SKILL.md").is_file()

    server = mcp["mcpServers"]["gds-workbench"]
    endpoint = urlsplit(server["url"])
    assert server["type"] == "streamable-http"
    assert endpoint.scheme == "https"
    assert endpoint.path == "/mcp"
    assert not endpoint.username and not endpoint.password and not endpoint.query

    serialized = json.dumps({"manifest": manifest, "mcp": mcp}).casefold()
    for forbidden in (
        "authorization",
        "bearer ",
        "client_secret",
        "access_token",
        "password",
    ):
        assert forbidden not in serialized


def test_metadata_skill_documents_exact_tools_datasets_and_safety() -> None:
    tools_text = TOOLS_REFERENCE.read_text(encoding="utf-8")
    documented_tools = set(re.findall(r"^### `([a-z_]+)`$", tools_text, re.MULTILINE))
    assert documented_tools == EXPECTED_TOOLS

    change_text = (
        METADATA_SKILL / "references" / "change-sets.md"
    ).read_text(encoding="utf-8")
    for dataset in ELIGIBLE_DATASETS:
        assert re.search(rf"\b{re.escape(dataset)}\b", change_text)

    bundle = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(METADATA_SKILL.rglob("*.md"))
    ).casefold()
    normalized_bundle = " ".join(bundle.split())
    assert "complete accumulated local" in normalized_bundle
    assert "explicit user confirmation immediately before apply" in normalized_bundle
    assert "ask before calling `acquire_tenant_lock`" in normalized_bundle
    assert "ask once before staging" in normalized_bundle
    assert "never delete applied metadata" in normalized_bundle
    assert "override only releases" in normalized_bundle
    assert "direct sql" in normalized_bundle


def test_plugin_has_no_python_runtime_dependency() -> None:
    assert not list(PLUGIN_ROOT.rglob("*.py"))
    text_files = [
        path
        for path in PLUGIN_ROOT.rglob("*")
        if path.is_file() and path.suffix in {".md", ".json", ".ps1", ".sh"}
    ]
    bundle = "\n".join(path.read_text(encoding="utf-8") for path in text_files)
    assert "python" not in bundle.casefold()
    assert "local_draft" not in bundle
    assert ".gds-metadata" not in bundle


def test_macos_initializer_creates_flat_ignored_workspace_and_is_idempotent(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project with spaces"
    project.mkdir()
    root = project / "gds-workspace"

    first = _run_shell(root)
    assert first.returncode == 0, first.stderr
    assert _line_output(first.stdout) == {
        "ok": "true",
        "workspace": str(root.resolve()),
        "created": "true",
        "metadata_snapshot_exists": "false",
        "change_set_exists": "false",
    }
    assert (root / ".gitignore").read_bytes() == b"*\n!.gitignore\n"
    assert sorted(path.name for path in root.iterdir()) == [".gitignore"]

    second = _run_shell(root)
    assert second.returncode == 0, second.stderr
    assert _line_output(second.stdout)["created"] == "false"


def test_initializer_reports_existing_managed_folders_without_modifying_them(
    tmp_path: Path,
) -> None:
    root = tmp_path / "gds-workspace"
    assert _run_shell(root).returncode == 0
    snapshot = root / "metadata-snapshot"
    change_set = root / "change-set"
    snapshot.mkdir()
    change_set.mkdir()
    snapshot_marker = snapshot / "catalog.json"
    change_marker = change_set / "change-set.json"
    snapshot_marker.write_text("snapshot-marker", encoding="utf-8")
    change_marker.write_text("change-marker", encoding="utf-8")

    result = _run_shell(root)
    assert result.returncode == 0, result.stderr
    output = _line_output(result.stdout)
    assert output["metadata_snapshot_exists"] == "true"
    assert output["change_set_exists"] == "true"
    assert snapshot_marker.read_text(encoding="utf-8") == "snapshot-marker"
    assert change_marker.read_text(encoding="utf-8") == "change-marker"


def test_initializer_rejects_unsafe_or_ambiguous_workspace(tmp_path: Path) -> None:
    wrong_name = _run_shell(tmp_path / "metadata-workspace")
    assert wrong_name.returncode == 2
    assert "must be named gds-workspace" in wrong_name.stderr

    root = tmp_path / "gds-workspace"
    root.mkdir()
    (root / ".gitignore").write_text("not-ignored\n", encoding="utf-8")
    unexpected_ignore = _run_shell(root)
    assert unexpected_ignore.returncode == 2
    assert "unexpected content" in unexpected_ignore.stderr


def test_initializer_rejects_symbolic_link_workspace(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir()
    linked = tmp_path / "gds-workspace"
    try:
        os.symlink(actual, linked, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symbolic links unavailable: {error}")

    result = _run_shell(linked)
    assert result.returncode == 2
    assert "symbolic link" in result.stderr


def test_powershell_initializer_uses_a_5_1_compatible_static_contract() -> None:
    script = POWERSHELL_INITIALIZER.read_text(encoding="utf-8")
    assert "$PSVersionTable.PSVersion.Major -lt 5" in script
    assert "-LiteralPath" in script
    assert "ReparsePoint" in script
    assert "ok=true" in script
    assert "metadata_snapshot_exists=" in script
    assert "change_set_exists=" in script
    for unsupported in (
        "ConvertFrom-Json -AsHashtable",
        "ForEach-Object -Parallel",
        "??",
        "?.",
    ):
        assert unsupported not in script


def test_macos_snapshot_validator_accepts_exact_current_snapshot_contract(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    snapshot = _build_snapshot(workspace)

    result = _run_snapshot_validator(snapshot)
    assert result.returncode == 0, result.stderr
    output = _line_output(result.stdout)
    assert output["ok"] == "true"
    assert output["snapshot"] == str(snapshot.resolve())
    assert output["snapshot_id"] == str(SNAPSHOT_ID)
    assert output["tenant_code"] == "TENANT"
    assert output["member_count"] == "69"
    assert output["logical_dataset_count"] == "29"
    assert output["row_count"] == "0"

    reused = _run_snapshot_validator(snapshot, snapshot_id=None)
    assert reused.returncode == 0, reused.stderr
    assert _line_output(reused.stdout)["snapshot_id"] == str(SNAPSHOT_ID)


def test_snapshot_validator_rejects_wrong_identity_and_tampered_rows(
    tmp_path: Path,
) -> None:
    snapshot = _build_snapshot(tmp_path)

    wrong_tenant = _run_snapshot_validator(snapshot, tenant_code="OTHER")
    assert wrong_tenant.returncode == 2
    assert "Tenant does not match" in wrong_tenant.stderr

    wrong_id = _run_snapshot_validator(
        snapshot,
        snapshot_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    )
    assert wrong_id.returncode == 2
    assert "Snapshot ID does not match" in wrong_id.stderr

    rows = snapshot / "data" / "foundational" / "project" / "rows.jsonl"
    sentinel = "SENSITIVE-ROW-CONTENT"
    rows.write_text(sentinel, encoding="utf-8")
    tampered = _run_snapshot_validator(snapshot)
    assert tampered.returncode == 2
    assert "member size mismatch" in tampered.stderr
    assert sentinel not in tampered.stdout
    assert sentinel not in tampered.stderr


def test_snapshot_validator_rejects_unexpected_file(tmp_path: Path) -> None:
    snapshot = _build_snapshot(tmp_path)
    (snapshot / "unexpected.json").write_text("{}", encoding="utf-8")

    result = _run_snapshot_validator(snapshot)
    assert result.returncode == 2
    assert "missing or unexpected files" in result.stderr


def test_powershell_snapshot_validator_has_5_1_static_contract() -> None:
    script = POWERSHELL_SNAPSHOT_VALIDATOR.read_text(encoding="utf-8")
    assert "$PSVersionTable.PSVersion.Major -lt 5" in script
    assert "ConvertFrom-Json" in script
    assert "Get-FileHash" in script
    assert "ReparsePoint" in script
    assert "ExpectedTenantCode" in script
    assert "ExpectedSnapshotId" in script
    assert "logical_dataset_count=" in script
    for unsupported in (
        "ConvertFrom-Json -AsHashtable",
        "ForEach-Object -Parallel",
        "??",
        "?.",
    ):
        assert unsupported not in script


def test_macos_catalog_inspector_lists_and_selects_without_printing_rows(
    tmp_path: Path,
) -> None:
    snapshot = _build_snapshot(tmp_path, include_project=True)

    listing = _run_catalog_inspector(snapshot)
    assert listing.returncode == 0, listing.stderr
    dataset_lines = [
        line for line in listing.stdout.splitlines() if line.startswith("dataset=")
    ]
    assert len(dataset_lines) == 29
    assert "dataset=foundational|project|1|true" in dataset_lines
    assert "dataset=operational|source_object|0|false" in dataset_lines
    assert "dataset_count=29" in listing.stdout
    assert "SENSITIVE-ROW-CONTENT" not in listing.stdout

    selected = _run_catalog_inspector(snapshot, "source_object")
    assert selected.returncode == 0, selected.stderr
    output = _line_output(selected.stdout)
    assert output["section"] == "operational"
    assert output["dataset"] == "source_object"
    assert output["search_result_complete"] == "false"
    assert output["canonical_key"] == (
        "tenant_code,system_code,connection_code,object_schema,object_name"
    )
    assert output["search_file"].endswith("/source_object/lookup.jsonl")
    assert output["rows_file"].endswith("/source_object/rows.jsonl")
    assert "SENSITIVE-ROW-CONTENT" not in selected.stdout


def test_catalog_inspector_rejects_unknown_dataset(tmp_path: Path) -> None:
    snapshot = _build_snapshot(tmp_path)
    result = _run_catalog_inspector(snapshot, "unknown_dataset")
    assert result.returncode == 2
    assert "not present" in result.stderr


def test_dataset_guide_names_every_snapshot_dataset_once() -> None:
    guide = (METADATA_SKILL / "references" / "datasets.md").read_text(
        encoding="utf-8"
    )
    table_datasets = re.findall(r"^\| `([a-z0-9_]+)` \|", guide, re.MULTILINE)
    assert len(table_datasets) == 29
    assert set(table_datasets) == {dataset.name for dataset in DATASETS}
    assert "Snapshot's `catalog.json`" in guide
    assert "authoritative" in guide
    assert "ask instead of" in guide
    assert "Foundational/reference parents must already exist" in guide


def test_powershell_catalog_inspector_has_5_1_static_contract() -> None:
    script = POWERSHELL_CATALOG_INSPECTOR.read_text(encoding="utf-8")
    assert "$PSVersionTable.PSVersion.Major -lt 5" in script
    assert "ConvertFrom-Json" in script
    assert "-LiteralPath" in script
    assert "dataset_count=" in script
    assert "canonical_key=" in script
    for unsupported in (
        "ConvertFrom-Json -AsHashtable",
        "ForEach-Object -Parallel",
        "??",
        "?.",
    ):
        assert unsupported not in script


def test_macos_change_set_initializer_creates_exact_control_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)

    result = _run_change_set_initializer(workspace)
    assert result.returncode == 0, result.stderr
    output = _line_output(result.stdout)
    change_set = workspace / "change-set"
    assert output["change_set"] == str(change_set.resolve())
    assert output["metadata_change_set_id"] == str(CHANGE_SET_ID)
    assert output["draft_revision"] == "1"
    assert (change_set / "datasets").is_dir()
    state = _json(change_set / "change-set.json")
    assert state == {
        "format_version": "1.0",
        "tenant": {"tenant_id": 1, "tenant_code": "TENANT"},
        "snapshot": {
            "snapshot_id": str(SNAPSHOT_ID),
            "path": "../metadata-snapshot",
            "usage": "fresh",
            "outdated_snapshot_warning_acknowledged": False,
        },
        "server_change_set": {
            "metadata_change_set_id": str(CHANGE_SET_ID),
            "draft_revision": 1,
            "status": "active",
        },
        "datasets": {},
    }

    repeated = _run_change_set_initializer(workspace)
    assert repeated.returncode == 2
    assert "already exists" in repeated.stderr
    assert state == _json(change_set / "change-set.json")


def test_macos_local_change_set_validator_summarizes_without_printing_rows(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    sentinel = "SENSITIVE-METADATA-VALUE"
    records = [_source_object_record(object_description=sentinel)]
    dataset = change_set / "datasets" / "source_object.json"
    dataset.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    result = _run_local_change_set_validator(change_set)
    assert result.returncode == 0, result.stderr
    assert "dataset=source_object|1|" in result.stdout
    assert "dataset_count=1" in result.stdout
    assert "metadata_change_set_id=" + str(CHANGE_SET_ID) in result.stdout
    assert sentinel not in result.stdout
    assert sentinel not in result.stderr

    stale_revision = _run_local_change_set_validator(change_set, revision=2)
    assert stale_revision.returncode == 2
    assert "Draft revision does not match" in stale_revision.stderr


def test_local_change_set_validator_rejects_database_ids_and_unknown_datasets(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    dataset = change_set / "datasets" / "source_object.json"
    dataset.write_text('[{"object_id": 7}]\n', encoding="utf-8")

    database_id = _run_local_change_set_validator(change_set)
    assert database_id.returncode == 2
    assert "schema or uniqueness" in database_id.stderr
    assert "object_id" not in database_id.stderr

    dataset.unlink()
    unknown = change_set / "datasets" / "project.json"
    unknown.write_text("[]\n", encoding="utf-8")
    wrong_dataset = _run_local_change_set_validator(change_set)
    assert wrong_dataset.returncode == 2
    assert "not Change Set eligible" in wrong_dataset.stderr


def test_reused_snapshot_requires_explicit_acknowledgement(tmp_path: Path) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)

    missing_ack = _run_change_set_initializer(workspace, usage="reused")
    assert missing_ack.returncode == 2
    assert "requires explicit" in missing_ack.stderr
    assert not (workspace / "change-set").exists()

    accepted = _run_change_set_initializer(
        workspace,
        usage="reused",
        acknowledge_outdated=True,
    )
    assert accepted.returncode == 0, accepted.stderr
    state = _json(workspace / "change-set" / "change-set.json")
    assert state["snapshot"]["usage"] == "reused"
    assert state["snapshot"]["outdated_snapshot_warning_acknowledged"] is True


def test_powershell_change_set_scripts_have_5_1_static_contract() -> None:
    initializer = POWERSHELL_CHANGE_SET_INITIALIZER.read_text(encoding="utf-8")
    validator = POWERSHELL_LOCAL_CHANGE_SET_VALIDATOR.read_text(encoding="utf-8")
    schema_helper = POWERSHELL_SCHEMA_HELPER.read_text(encoding="utf-8")
    for script in (initializer, validator):
        assert "$PSVersionTable.PSVersion.Major -lt 5" in script
        assert "ConvertFrom-Json" in script
        assert "-LiteralPath" in script
        for unsupported in (
            "ConvertFrom-Json -AsHashtable",
            "ForEach-Object -Parallel",
            "??",
            "?.",
        ):
            assert unsupported not in script
    assert "AcknowledgeOutdatedSnapshot" in initializer
    assert "ConvertTo-Json -Depth 5" in initializer
    assert "Database ID fields are forbidden" in validator + schema_helper
    assert "Assert-GdsDataset" in validator
    assert "dataset_count=" in validator


def test_stage_state_records_hash_and_detects_later_local_edits(tmp_path: Path) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    dataset = change_set / "datasets" / "source_object.json"
    records = [_source_object_record()]
    dataset.write_text(json.dumps(records) + "\n", encoding="utf-8")

    before = _run_local_change_set_validator(change_set)
    assert before.returncode == 0, before.stderr
    summary = _dataset_summary(before.stdout, "source_object")
    assert summary[1] == "1"
    reviewed_sha = summary[3]
    assert summary[4:] == ["false", ""]

    recorded = _run_local_state_updater(
        change_set,
        expected_revision=1,
        server_revision=2,
        status="active",
        dataset="source_object",
        sha256=reviewed_sha,
    )
    assert recorded.returncode == 0, recorded.stderr
    assert "stage_recorded=true" in recorded.stdout
    state = _json(change_set / "change-set.json")
    assert state["server_change_set"]["draft_revision"] == 2
    assert state["datasets"]["source_object"] == {
        "file": "datasets/source_object.json",
        "record_count": 1,
        "staged_sha256": reviewed_sha,
        "staged_revision": 2,
    }

    synchronized = _run_local_change_set_validator(
        change_set,
        revision=2,
        require_staged=True,
    )
    assert synchronized.returncode == 0, synchronized.stderr
    assert _dataset_summary(synchronized.stdout, "source_object")[4:] == [
        "true",
        "2",
    ]

    records.append(_source_object_record(object_name="order"))
    dataset.write_text(json.dumps(records) + "\n", encoding="utf-8")
    edited = _run_local_change_set_validator(change_set, revision=2)
    assert edited.returncode == 0, edited.stderr
    assert _dataset_summary(edited.stdout, "source_object")[4:] == ["false", "2"]
    require_staged = _run_local_change_set_validator(
        change_set,
        revision=2,
        require_staged=True,
    )
    assert require_staged.returncode == 2
    assert "not synchronized" in require_staged.stderr


def test_revision_reconciliation_clears_staged_markers_conservatively(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    dataset = change_set / "datasets" / "copy_group.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "tenant_code": "TENANT",
                    "system_code": "SYSTEM",
                    "copy_group_name": "daily",
                    "copy_group_description": None,
                    "is_member_group_required": False,
                    "is_active": True,
                }
            ]
        )
        + "\n"
    )
    checked = _run_local_change_set_validator(change_set)
    reviewed_sha = _dataset_summary(checked.stdout, "copy_group")[3]
    staged = _run_local_state_updater(
        change_set,
        expected_revision=1,
        server_revision=2,
        status="active",
        dataset="copy_group",
        sha256=reviewed_sha,
    )
    assert staged.returncode == 0, staged.stderr

    member_group = change_set / "datasets" / "member_group.json"
    member_group.write_text(
        json.dumps(
            [
                {
                    "tenant_code": "TENANT",
                    "system_code": "SYSTEM",
                    "member_group_name": "all",
                    "member_group_description": None,
                    "member_group_initial_load_date": None,
                    "is_active": True,
                }
            ]
        )
        + "\n"
    )
    checked = _run_local_change_set_validator(change_set, revision=2)
    member_hash = _dataset_summary(checked.stdout, "member_group")[3]
    second_stage = _run_local_state_updater(
        change_set,
        expected_revision=2,
        server_revision=3,
        status="active",
        dataset="member_group",
        sha256=member_hash,
    )
    assert second_stage.returncode == 0, second_stage.stderr
    both_staged = _run_local_change_set_validator(
        change_set,
        revision=3,
        require_staged=True,
    )
    assert both_staged.returncode == 0, both_staged.stderr
    assert _dataset_summary(both_staged.stdout, "copy_group")[4:] == ["true", "2"]
    assert _dataset_summary(both_staged.stdout, "member_group")[4:] == ["true", "3"]

    validated = _run_local_state_updater(
        change_set,
        expected_revision=3,
        server_revision=3,
        status="validated",
    )
    assert validated.returncode == 0, validated.stderr
    state = _json(change_set / "change-set.json")
    assert state["server_change_set"]["status"] == "validated"
    assert "copy_group" in state["datasets"]

    reconciled = _run_local_state_updater(
        change_set,
        expected_revision=3,
        server_revision=5,
        status="active",
    )
    assert reconciled.returncode == 0, reconciled.stderr
    state = _json(change_set / "change-set.json")
    assert state["server_change_set"]["draft_revision"] == 5
    assert state["datasets"] == {}
    unstaged = _run_local_change_set_validator(
        change_set,
        revision=5,
        require_staged=True,
    )
    assert unstaged.returncode == 2
    assert "not synchronized" in unstaged.stderr


def test_stage_state_rejects_wrong_hash_without_changing_control_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    (change_set / "datasets" / "process_group.json").write_text("[]\n")
    original_state = _json(change_set / "change-set.json")

    result = _run_local_state_updater(
        change_set,
        expected_revision=1,
        server_revision=2,
        status="active",
        dataset="process_group",
        sha256="0" * 64,
    )
    assert result.returncode == 2
    assert "changed after" in result.stderr
    assert _json(change_set / "change-set.json") == original_state


def test_powershell_state_updater_has_5_1_static_contract() -> None:
    script = POWERSHELL_LOCAL_STATE_UPDATER.read_text(encoding="utf-8")
    assert "$PSVersionTable.PSVersion.Major -lt 5" in script
    assert "ExpectedCurrentRevision" in script
    assert "StagedSha256" in script
    assert "Get-FileHash" in script
    assert "ConvertTo-Json -Depth 8" in script
    assert "stage_recorded=" in script
    for unsupported in (
        "ConvertFrom-Json -AsHashtable",
        "ForEach-Object -Parallel",
        "??",
        "?.",
    ):
        assert unsupported not in script


def test_macos_record_upserter_inserts_and_replaces_by_canonical_key(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    record_file = workspace / "record-input.json"

    first = _source_object_record(object_description="FIRST-SENSITIVE-VALUE")
    record_file.write_text(json.dumps(first), encoding="utf-8")
    inserted = _run_local_record_upserter(
        change_set,
        "source_object",
        record_file,
    )
    assert inserted.returncode == 0, inserted.stderr
    assert _line_output(inserted.stdout)["action"] == "inserted"
    assert "FIRST-SENSITIVE-VALUE" not in inserted.stdout + inserted.stderr

    replacement = _source_object_record(
        tenant_code=" tenant ",
        system_code="system",
        connection_code="Connection",
        object_schema="DBO",
        object_name="Customer",
        object_description="SECOND-SENSITIVE-VALUE",
    )
    record_file.write_text(json.dumps(replacement), encoding="utf-8")
    replaced = _run_local_record_upserter(
        change_set,
        "source_object",
        record_file,
    )
    assert replaced.returncode == 0, replaced.stderr
    output = _line_output(replaced.stdout)
    assert output["action"] == "replaced"
    assert output["record_count"] == "1"
    assert "SECOND-SENSITIVE-VALUE" not in replaced.stdout + replaced.stderr

    stored = json.loads(
        (change_set / "datasets" / "source_object.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored == [replacement]


def test_record_upserter_rejects_schema_errors_without_changing_dataset(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    record_file = workspace / "record-input.json"
    record_file.write_text(json.dumps(_source_object_record()), encoding="utf-8")
    assert (
        _run_local_record_upserter(change_set, "source_object", record_file).returncode
        == 0
    )
    dataset_file = change_set / "datasets" / "source_object.json"
    original = dataset_file.read_bytes()

    invalid = _source_object_record(zone_code="bronze", unexpected="SENTINEL")
    record_file.write_text(json.dumps(invalid), encoding="utf-8")
    rejected = _run_local_record_upserter(
        change_set,
        "source_object",
        record_file,
    )
    assert rejected.returncode == 2
    assert "schema" in rejected.stderr.casefold()
    assert "SENTINEL" not in rejected.stdout + rejected.stderr
    assert dataset_file.read_bytes() == original


def test_local_validator_enforces_snapshot_schema_and_unique_constraints(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"

    invalid_schema = change_set / "datasets" / "source_object.json"
    invalid_schema.write_text(
        json.dumps([_source_object_record(zone_code="bronze")]),
        encoding="utf-8",
    )
    schema_result = _run_local_change_set_validator(change_set)
    assert schema_result.returncode == 2
    assert "schema or uniqueness" in schema_result.stderr

    invalid_schema.unlink()
    base_attribute = {
        "tenant_code": "TENANT",
        "system_code": "SYSTEM",
        "connection_code": "CONNECTION",
        "object_schema": "dbo",
        "object_name": "customer",
        "attribute_name": "first_name",
        "fc_attribute_name": None,
        "attribute_ordinal_position": 1,
        "attribute_description": None,
        "attribute_data_type": "varchar",
        "attribute_nullability": True,
        "attribute_custom_code": None,
        "is_surrogate_key": False,
        "is_natural_key": False,
        "is_meta_data": False,
        "is_masking_required": False,
        "is_mapped": False,
        "is_purge": False,
        "is_active": True,
    }
    duplicate_ordinal = dict(base_attribute, attribute_name="last_name")
    attribute_file = change_set / "datasets" / "source_attribute.json"
    attribute_file.write_text(
        json.dumps([base_attribute, duplicate_ordinal]),
        encoding="utf-8",
    )
    unique_result = _run_local_change_set_validator(change_set)
    assert unique_result.returncode == 2
    assert "schema or uniqueness" in unique_result.stderr


def test_powershell_record_upserter_has_5_1_static_contract() -> None:
    script = POWERSHELL_LOCAL_RECORD_UPSERTER.read_text(encoding="utf-8")
    helper = POWERSHELL_SCHEMA_HELPER.read_text(encoding="utf-8")
    bundle = script + helper
    assert "$PSVersionTable.PSVersion.Major -lt 5" in script
    assert "x-gds-canonical-key" in bundle
    assert "x-gds-unique-constraints" in bundle
    assert "ConvertFrom-Json" in bundle
    assert "ConvertTo-Json -InputObject" in script
    assert "-Depth 20" in script
    assert "action=" in script
    for unsupported in (
        "ConvertFrom-Json -AsHashtable",
        "ForEach-Object -Parallel",
        "??",
        "?.",
    ):
        assert unsupported not in bundle


def test_macos_record_remover_removes_exact_canonical_key_and_stales_review(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    dataset_file = change_set / "datasets" / "source_object.json"
    records = [
        _source_object_record(
            object_name="customer",
            object_description="REMOVE-ME-SENSITIVE",
        ),
        _source_object_record(object_name="orders"),
    ]
    dataset_file.write_text(json.dumps(records), encoding="utf-8")
    assert _run_stage_reviewer(change_set).returncode == 0
    key_file = workspace / "record-key.json"
    key_file.write_text(
        json.dumps(
            {
                "tenant_code": " tenant ",
                "system_code": "system",
                "connection_code": "Connection",
                "object_schema": "DBO",
                "object_name": "Customer",
            }
        ),
        encoding="utf-8",
    )

    removed = _run_local_record_remover(
        change_set,
        "source_object",
        key_file,
    )
    assert removed.returncode == 0, removed.stderr
    output = _line_output(removed.stdout)
    assert output["action"] == "removed"
    assert output["record_count"] == "1"
    assert output["dataset_empty"] == "false"
    assert "REMOVE-ME-SENSITIVE" not in removed.stdout + removed.stderr
    assert json.loads(dataset_file.read_text(encoding="utf-8")) == [records[1]]

    stale = _run_local_change_set_validator(
        change_set,
        require_reviewed=True,
    )
    assert stale.returncode == 2
    assert "review is missing or stale" in stale.stderr.casefold()

    key_file.write_text(
        json.dumps(
            {
                "tenant_code": "TENANT",
                "system_code": "SYSTEM",
                "connection_code": "CONNECTION",
                "object_schema": "dbo",
                "object_name": "orders",
            }
        ),
        encoding="utf-8",
    )
    emptied = _run_local_record_remover(
        change_set,
        "source_object",
        key_file,
    )
    assert emptied.returncode == 0, emptied.stderr
    assert _line_output(emptied.stdout)["dataset_empty"] == "true"
    assert json.loads(dataset_file.read_text(encoding="utf-8")) == []
    assert _run_local_change_set_validator(change_set).returncode == 0


def test_record_remover_rejects_inexact_or_missing_key_without_changes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    dataset_file = change_set / "datasets" / "source_object.json"
    dataset_file.write_text(
        json.dumps([_source_object_record()]),
        encoding="utf-8",
    )
    original = dataset_file.read_bytes()
    key_file = workspace / "record-key.json"
    key_file.write_text(
        json.dumps(
            {
                "tenant_code": "TENANT",
                "system_code": "SYSTEM",
                "connection_code": "CONNECTION",
                "object_schema": "dbo",
                "object_name": "missing",
                "unexpected": "SENSITIVE-KEY-VALUE",
            }
        ),
        encoding="utf-8",
    )
    invalid = _run_local_record_remover(
        change_set,
        "source_object",
        key_file,
    )
    assert invalid.returncode == 2
    assert "canonical key" in invalid.stderr.casefold()
    assert "SENSITIVE-KEY-VALUE" not in invalid.stdout + invalid.stderr
    assert dataset_file.read_bytes() == original

    key_file.write_text(
        json.dumps(
            {
                "tenant_code": "TENANT",
                "system_code": "SYSTEM",
                "connection_code": "CONNECTION",
                "object_schema": "dbo",
                "object_name": "not-present",
            }
        ),
        encoding="utf-8",
    )
    missing = _run_local_record_remover(
        change_set,
        "source_object",
        key_file,
    )
    assert missing.returncode == 2
    assert "not present" in missing.stderr.casefold()
    assert dataset_file.read_bytes() == original


def test_powershell_record_remover_has_5_1_static_contract() -> None:
    script = POWERSHELL_LOCAL_RECORD_REMOVER.read_text(encoding="utf-8")
    helper = POWERSHELL_SCHEMA_HELPER.read_text(encoding="utf-8")
    bundle = script + helper
    assert "$PSVersionTable.PSVersion.Major -lt 5" in script
    assert "Remove-GdsRecord" in bundle
    assert "x-gds-canonical-key" in bundle
    assert "dataset_empty=" in script
    assert "ConvertTo-Json -InputObject" in script
    for unsupported in (
        "ConvertFrom-Json -AsHashtable",
        "ForEach-Object -Parallel",
        "??",
        "?.",
    ):
        assert unsupported not in bundle


def test_macos_stage_review_classifies_actions_without_exposing_full_rows(
    tmp_path: Path,
) -> None:
    baseline = [
        _source_object_record(
            object_name="customer",
            object_description="BASELINE-CUSTOMER-SENSITIVE",
        ),
        _source_object_record(object_name="old_table", is_active=True),
        _source_object_record(object_name="dormant", is_active=False),
        _source_object_record(object_name="unchanged"),
    ]
    local = [
        _source_object_record(
            object_name="customer",
            object_description="UPDATED-CUSTOMER-SENSITIVE",
        ),
        _source_object_record(object_name="old_table", is_active=False),
        _source_object_record(object_name="dormant", is_active=True),
        _source_object_record(object_name="new_table"),
        _source_object_record(object_name="unchanged"),
    ]
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(
        workspace,
        dataset_rows={
            "project": [
                {
                    "project_code": "PROJECT",
                    "project_name": "Project",
                    "project_description": None,
                    "is_active": True,
                }
            ],
            "tenant": [
                {
                    "tenant_code": "TENANT",
                    "project_code": "PROJECT",
                    "tenant_name": "Tenant",
                    "tenant_description": None,
                    "tenant_catalog": "tenant_catalog",
                    "gds_admin_catalog": "admin_catalog",
                    "gds_connection_tenant_code": None,
                    "gds_connection_system_code": None,
                    "gds_connection_code": None,
                    "tenant_visibility": "private",
                    "is_active": True,
                }
            ],
            "system_type": [
                {
                    "system_type_code": "TYPE",
                    "system_type_name": "Type",
                    "system_type_description": None,
                    "is_active": True,
                }
            ],
            "system": [
                {
                    "system_code": "SYSTEM",
                    "system_name": "System",
                    "system_description": None,
                    "system_type_code": "TYPE",
                    "is_active": True,
                }
            ],
            "connection_type": [
                {
                    "connection_type_code": "TYPE",
                    "connection_type_name": "Type",
                    "connection_type_description": None,
                    "is_active": True,
                }
            ],
            "connection": [
                {
                    "tenant_code": "TENANT",
                    "system_code": "SYSTEM",
                    "connection_code": "CONNECTION",
                    "connection_name": "Connection",
                    "connection_type_code": "TYPE",
                    "has_foreign_catalog": False,
                    "foreign_catalog": None,
                    "is_global_data_store": False,
                    "is_active": True,
                }
            ],
            "object_type": [
                {
                    "object_type_code": "TABLE",
                    "object_type_name": "Table",
                    "object_type_description": None,
                    "is_active": True,
                }
            ],
            "zone": [
                {
                    "zone_code": "source",
                    "zone_name": "Source",
                    "zone_description": None,
                    "is_active": True,
                }
            ],
            "source_object": baseline,
        },
    )
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    dataset_file = change_set / "datasets" / "source_object.json"
    dataset_file.write_text(json.dumps(local), encoding="utf-8")

    result = _run_stage_reviewer(change_set)
    assert result.returncode == 0, result.stderr
    output = _line_output(result.stdout)
    assert output["ok"] == "true"
    assert output["dataset_count"] == "1"
    assert output["record_count"] == "5"
    assert output["insert_count"] == "1"
    assert output["update_count"] == "1"
    assert output["deactivate_count"] == "1"
    assert output["reactivate_count"] == "1"
    assert output["no_change_count"] == "1"
    assert "SENSITIVE" not in result.stdout + result.stderr

    review = _json(change_set / "review.json")
    assert review["format_version"] == "1.0"
    assert review["tenant"] == {"tenant_id": 1, "tenant_code": "TENANT"}
    assert review["server_change_set"] == {
        "metadata_change_set_id": str(CHANGE_SET_ID),
        "draft_revision": 1,
    }
    source_review = review["datasets"]["source_object"]
    assert source_review["record_count"] == 5
    assert source_review["actions"] == {
        "insert": 1,
        "update": 1,
        "deactivate": 1,
        "reactivate": 1,
        "no_change": 1,
    }
    assert source_review["canonical_key"] == [
        "tenant_code",
        "system_code",
        "connection_code",
        "object_schema",
        "object_name",
    ]
    assert {item["action"] for item in source_review["records"]} == {
        "insert",
        "update",
        "deactivate",
        "reactivate",
        "no_change",
    }
    serialized_review = json.dumps(review)
    assert "BASELINE-CUSTOMER-SENSITIVE" not in serialized_review
    assert "UPDATED-CUSTOMER-SENSITIVE" not in serialized_review


def test_review_freshness_gate_rejects_changes_after_review(tmp_path: Path) -> None:
    workspace = tmp_path / "gds-workspace"
    workspace.mkdir()
    _build_snapshot(workspace)
    assert _run_change_set_initializer(workspace).returncode == 0
    change_set = workspace / "change-set"
    dataset_file = change_set / "datasets" / "source_object.json"
    dataset_file.write_text(
        json.dumps([_source_object_record(object_name="new_table")]),
        encoding="utf-8",
    )
    prepared = _run_stage_reviewer(change_set)
    assert prepared.returncode == 0, prepared.stderr

    reviewed = _run_local_change_set_validator(
        change_set,
        require_reviewed=True,
    )
    assert reviewed.returncode == 0, reviewed.stderr
    assert _line_output(reviewed.stdout)["reviewed"] == "true"

    dataset_file.write_text(
        json.dumps(
            [
                _source_object_record(
                    object_name="new_table",
                    object_description="changed after review",
                )
            ]
        ),
        encoding="utf-8",
    )
    stale = _run_local_change_set_validator(
        change_set,
        require_reviewed=True,
    )
    assert stale.returncode == 2
    assert "review is missing or stale" in stale.stderr.casefold()


def test_powershell_stage_reviewer_has_5_1_static_contract() -> None:
    script = POWERSHELL_STAGE_REVIEWER.read_text(encoding="utf-8")
    helper = POWERSHELL_SCHEMA_HELPER.read_text(encoding="utf-8")
    bundle = script + helper
    assert "$PSVersionTable.PSVersion.Major -lt 5" in script
    assert "Get-Content -LiteralPath" in script
    assert "Get-GdsNormalizedKey" in bundle
    assert "review.json" in script
    assert "no_change_count=" in script
    assert "Get-FileHash" in script
    for unsupported in (
        "ConvertFrom-Json -AsHashtable",
        "ForEach-Object -Parallel",
        "??",
        "?.",
    ):
        assert unsupported not in bundle


def test_markdown_links_resolve_within_plugin() -> None:
    for document in PLUGIN_ROOT.rglob("*.md"):
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            relative = target.split("#", 1)[0]
            assert (document.parent / relative).resolve().exists(), (
                document,
                target,
            )
