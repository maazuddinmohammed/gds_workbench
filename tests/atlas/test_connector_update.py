from __future__ import annotations

import ast
import os
import runpy
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from atlas import build_connector, build_plugin

ROOT = Path(__file__).resolve().parents[2]
replace_packages = cast(
    Callable[[Path, Path, Path], None],
    runpy.run_path(str(ROOT / "atlas/atlas-connector/update.py"))["replace_packages"],
)


def test_updater_supports_the_documented_python_312_runtime() -> None:
    ast.parse((ROOT / "atlas/atlas-connector/update.py").read_text(), feature_version=(3, 12))


def installed_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    parent = tmp_path / "Atlas with spaces"
    parent.mkdir()
    plugin = build_plugin.build(tmp_path / "plugin.zip")
    connector = build_connector.build(tmp_path / "connector.zip")
    for source in (plugin, connector):
        with zipfile.ZipFile(source) as archive:
            archive.extractall(parent)
    (parent / "codex-atlas").mkdir()
    (parent / "codex-atlas/plugin.json").write_text("generated plugin fixture")
    (parent / "atlas/docs/old-file.md").write_text("previous release fixture")
    (parent / "atlas-connector/old-file.txt").write_text("previous release fixture")
    return parent, plugin, connector


def test_both_packages_replace_cleanly_and_keep_configuration_and_backups(tmp_path: Path) -> None:
    parent, plugin, connector = installed_fixture(tmp_path)
    replace_packages(parent, plugin, connector)
    assert not (parent / "atlas/docs/old-file.md").exists()
    assert not (parent / "atlas-connector/old-file.txt").exists()
    assert (parent / "codex-atlas/plugin.json").read_text() == "generated plugin fixture"
    backups = list(parent.glob("atlas-backup-*"))
    assert len(backups) == 1
    assert (backups[0] / "atlas/docs/old-file.md").is_file()
    assert (backups[0] / "atlas-connector/old-file.txt").is_file()
    assert not (parent / ".atlas-setup.lock").exists()


@pytest.mark.parametrize(
    "name", ["../escaped", "atlas/../escaped", "atlas/docs/unsafe.js", "atlas/docs/.env"]
)
def test_invalid_zip_leaves_both_packages_intact(tmp_path: Path, name: str) -> None:
    parent, plugin, connector = installed_fixture(tmp_path)
    with zipfile.ZipFile(plugin, "a") as archive:
        archive.writestr(name, "fixture")
    with pytest.raises(ValueError):
        replace_packages(parent, plugin, connector)
    assert (parent / "atlas/docs/old-file.md").is_file()
    assert (parent / "atlas-connector/old-file.txt").is_file()
    assert not list(parent.glob("atlas-backup-*"))
    assert not (tmp_path / "escaped").exists()


def test_failed_second_replacement_restores_both_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent, plugin, connector = installed_fixture(tmp_path)
    original = os.replace

    def fail_connector(source: Path, destination: Path) -> None:
        if source.parent.name.startswith(".atlas-download-") and source.name == "atlas-connector":
            raise OSError("simulated file lock")
        original(source, destination)

    monkeypatch.setattr(os, "replace", fail_connector)
    with pytest.raises(OSError):
        replace_packages(parent, plugin, connector)
    assert (parent / "atlas/docs/old-file.md").is_file()
    assert (parent / "atlas-connector/old-file.txt").is_file()
    assert (parent / "codex-atlas/plugin.json").read_text() == "generated plugin fixture"


def test_setup_lock_prevents_package_replacement(tmp_path: Path) -> None:
    parent, plugin, connector = installed_fixture(tmp_path)
    (parent / ".atlas-setup.lock").write_text("existing setup")
    with pytest.raises(ValueError, match="setup may be running"):
        replace_packages(parent, plugin, connector)
    assert (parent / ".atlas-setup.lock").read_text() == "existing setup"
    assert (parent / "atlas/docs/old-file.md").is_file()
