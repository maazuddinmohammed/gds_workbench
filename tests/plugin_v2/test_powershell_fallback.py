from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPOSITORY_ROOT / "plugins" / "v2" / "gds" / "skills" / "gds"
HELPER = SKILL_ROOT / "scripts" / "gds-local.ps1"
JAVASCRIPT_HELPER = SKILL_ROOT / "scripts" / "gds-local.js"
CONTRACT = SKILL_ROOT / "contracts" / "local-helper.json"


def source() -> str:
    return HELPER.read_text(encoding="utf-8")


def test_powershell_fallback_is_native_and_local_only() -> None:
    text = source()

    assert "Invoke-WebRequest" not in text
    assert "Invoke-RestMethod" not in text
    assert "HttpClient" not in text
    assert "Start-Process" not in text
    assert "node" not in text.lower()
    assert "python" not in text.lower()
    assert "manifest.json" in text
    assert "catalog.json" in text


def test_powershell_dispatch_matches_the_public_command_contract() -> None:
    text = source()
    commands = json.loads(CONTRACT.read_text(encoding="utf-8"))["commands"]

    for command in commands:
        assert f"'{command}'" in text
    for removed in (
        "contract-check",
        "mapping-proof",
        "generator-proof",
        "approve-reviewed",
    ):
        assert removed not in commands
        assert f"'{removed}'" not in text


def test_powershell_and_javascript_expose_the_same_readiness_targets() -> None:
    powershell = source()
    javascript = JAVASCRIPT_HELPER.read_text(encoding="utf-8")
    targets = (
        "metadata-authoring",
        "logical-build",
        "silver-registration",
        "logical-binding",
        "logical-mapping",
        "logical-code",
        "dimensional-build",
        "gold-registration",
        "dimensional-binding",
        "dimensional-mapping",
        "dimensional-code",
        "validation",
        "process-registration",
    )

    for target in targets:
        assert re.search(rf"['\"]{re.escape(target)}['\"]", powershell)
        assert re.search(rf"['\"]{re.escape(target)}['\"]", javascript)
    assert "'qa'" not in powershell


def test_powershell_readiness_is_snapshot_driven() -> None:
    text = source()

    assert "function Get-WorkflowReadiness" in text
    assert "snapshot_missing" in text
    assert "snapshot_stale" in text
    assert "Download and unzip one fresh required Snapshot" in text
    assert "mapping-proof" not in text
    assert "generator-proof" not in text


def test_powershell_model_validation_uses_snapshot_schema_references() -> None:
    text = source()

    assert "function Get-ValidationRecordType" in text
    assert "function Add-DeclaredReferenceIssues" in text
    assert "x-gds-record-type" in text
    assert "x-gds-references" in text
    assert "Locked records cannot be changed locally." in text
    assert "model_scope" not in text
    assert "qa_authoring_context" not in text


def test_powershell_acceptance_remains_digest_bound_but_is_not_a_ui_ceremony() -> None:
    text = source()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))["commands"]

    assert "function Accept-Changes" in text
    assert "Require-Option $Options 'digest'" in text
    assert "accept" in contract
    assert "approve-reviewed" not in contract


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="PowerShell is not installed")
def test_powershell_source_parses() -> None:
    result = subprocess.run(
        [
            "pwsh",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            (
                "$errors=$null; "
                f"[void][System.Management.Automation.Language.Parser]::ParseFile('{HELPER}',"
                "[ref]$null,[ref]$errors); if($errors.Count){$errors | Out-String; exit 1}"
            ),
        ],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
