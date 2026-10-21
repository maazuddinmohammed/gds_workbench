"""Exercise production-style noneditable installs without network or provider I/O."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


def test_backend_source_and_registry_changes_refresh_installed_wheel(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required for the offline deployment cache regression")

    root = Path(__file__).resolve().parents[2]
    backend_settings = tomllib.loads(
        (root / "web_app/backend/pyproject.toml").read_text(encoding="utf-8")
    )
    cache_keys = backend_settings.get("tool", {}).get("uv", {}).get("cache-keys", [])
    package = tmp_path / "backend"
    module = package / "gds_workbench_api/__init__.py"
    registry = package / "gds_workbench_api/config/agent_capabilities.json"
    registry.parent.mkdir(parents=True)
    module.write_text('release_marker = "initial"\n', encoding="utf-8")
    registry.write_text('{"models": ["initial"]}', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "offline-app-fixture"\nversion = "0.1.0"\n'
        'dependencies = ["gds-workbench-api==0.1.0"]\n'
        "[tool.uv]\npackage = false\n"
        "[tool.uv.sources]\n"
        'gds-workbench-api = {path = "backend", editable = false}\n',
        encoding="utf-8",
    )
    (package / "pyproject.toml").write_text(
        '[project]\nname = "gds-workbench-api"\nversion = "0.1.0"\n'
        '[build-system]\nrequires = []\nbuild-backend = "build_backend"\n'
        'backend-path = ["."]\n'
        "[tool.uv]\ncache-keys = ["
        + ", ".join("{file = " + json.dumps(key["file"]) + "}" for key in cache_keys)
        + "]\n",
        encoding="utf-8",
    )
    # The tiny stdlib builder keeps this a cache test, without installing application deps.
    (package / "build_backend.py").write_text(
        """from pathlib import Path
from zipfile import ZipFile

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name = "gds_workbench_api-0.1.0-py3-none-any.whl"
    files = {
        path.as_posix(): path.read_bytes()
        for path in Path("gds_workbench_api").rglob("*") if path.is_file()
    }
    info = "gds_workbench_api-0.1.0.dist-info/"
    files[info + "METADATA"] = (
        b"Metadata-Version: 2.1\\nName: gds-workbench-api\\nVersion: 0.1.0\\n"
    )
    files[info + "WHEEL"] = b"Wheel-Version: 1.0\\nRoot-Is-Purelib: true\\nTag: py3-none-any\\n"
    files[info + "RECORD"] = "".join(
        f"{path},,\\n" for path in [*files, info + "RECORD"]
    ).encode()
    with ZipFile(Path(wheel_directory) / name, "w") as wheel:
        for path, content in files.items():
            wheel.writestr(path, content)
    return name
""",
        encoding="utf-8",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("UV_") and key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    environment["UV_PYTHON_DOWNLOADS"] = "never"
    python = tmp_path / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # Each edit must independently invalidate the same installed version and cached wheel.
    for changed_file, content, expected in (
        (None, "", ["initial", ["initial"]]),
        (module, 'release_marker = "updated-runtime"\n', ["updated-runtime", ["initial"]]),
        (registry, '{"models": ["updated-registry"]}', ["updated-runtime", ["updated-registry"]]),
    ):
        if changed_file is not None:
            changed_file.write_text(content, encoding="utf-8")
        installed = subprocess.run(
            [
                uv,
                "sync",
                "--offline",
                "--no-dev",
                "--project",
                str(tmp_path),
                "--cache-dir",
                str(tmp_path / "cache"),
                "--python",
                sys.executable,
            ],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert installed.returncode == 0, "Offline fixture wheel installation failed"
        imported = subprocess.run(
            [
                str(python),
                "-c",
                "import json, gds_workbench_api; from importlib.resources import files; "
                "print(json.dumps([gds_workbench_api.release_marker, "
                "json.loads(files(gds_workbench_api).joinpath("
                "'config/agent_capabilities.json').read_text())['models']]))",
            ],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            timeout=10,
            check=False,
        )
        assert imported.returncode == 0, "Installed fixture module could not be imported"
        assert json.loads(imported.stdout) == expected
