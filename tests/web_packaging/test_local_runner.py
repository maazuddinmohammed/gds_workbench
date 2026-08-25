from __future__ import annotations

import importlib.util
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY_ROOT / "web_app" / "local" / "run.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("gds_local_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_environment_is_random_and_contains_no_external_endpoint() -> None:
    runner = _load_runner()

    first = runner.build_local_environment(frontend_port=8080, api_port=8000)
    second = runner.build_local_environment(frontend_port=8080, api_port=8000)

    assert first != second
    assert first["GDS_LOCAL_PROJECT_NAME"].startswith("gdswb_")
    assert first["GDS_LOCAL_DATABASE_NAME"].startswith("gds_local_")
    assert len(first["GDS_LOCAL_WEB_PASSWORD"]) >= 64
    assert len(first["GDS_LOCAL_MCP_PASSWORD"]) >= 64
    assert first["GDS_LOCAL_WEB_PASSWORD"] != first["GDS_LOCAL_MCP_PASSWORD"]
    assert first["GDS_LOCAL_FRONTEND_PORT"] == "8080"
    assert first["GDS_LOCAL_API_PORT"] == "8000"
    assert not any("URL" in key or "DSN" in key or "ENDPOINT" in key for key in first)


@pytest.mark.parametrize(
    "environment",
    [
        {"DATABASE_URL": "postgresql://example.invalid/database"},
        {"GDS_WEB_DATABASE_DSN": "host=example.invalid"},
        {"GDS_LOCAL_DATABASE_NAME": "caller-controlled"},
        {"DATABRICKS_HOST": "https://example.invalid"},
        {"OPENAI_API_KEY": "not-a-real-key"},
        {"COMPOSE_FILE": "different.yaml"},
        {"DOCKER_HOST": "tcp://example.invalid:2375"},
        {"DOCKER_TLS_VERIFY": "1"},
        {"BUILDKIT_HOST": "tcp://example.invalid:1234"},
    ],
)
def test_ambient_connection_or_override_configuration_is_rejected(
    environment: dict[str, str],
) -> None:
    runner = _load_runner()

    with pytest.raises(runner.LocalSafetyError):
        runner.assert_safe_environment(environment)


@pytest.mark.parametrize(
    "endpoint", ["unix:///var/run/docker.sock", "npipe:////./pipe/docker_engine"]
)
def test_local_docker_endpoints_are_accepted(endpoint: str) -> None:
    runner = _load_runner()

    runner.assert_local_docker_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "tcp://127.0.0.1:2375",
        "tcp://example.invalid:2375",
        "ssh://host",
        "https://host",
    ],
)
def test_network_docker_endpoints_are_rejected(endpoint: str) -> None:
    runner = _load_runner()

    with pytest.raises(runner.LocalSafetyError):
        runner.assert_local_docker_endpoint(endpoint)


def test_secret_environment_file_is_private_and_removed_with_its_directory(
    tmp_path: Path,
) -> None:
    runner = _load_runner()
    run_directory = tmp_path / "outside-repository"
    run_directory.mkdir()
    values = runner.build_local_environment(frontend_port=8080, api_port=8000)

    environment_file = runner.write_environment_file(run_directory, values)

    assert environment_file.parent == run_directory
    assert stat.S_IMODE(environment_file.stat().st_mode) == 0o600
    contents = environment_file.read_text(encoding="utf-8")
    assert "postgresql://" not in contents
    assert "host=" not in contents


def test_compose_cleanup_always_disposes_volumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[-2:] == ["version", "--short"]:
            return subprocess.CompletedProcess(command, 0, stdout="2.39.0\n")
        if "context" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="unix:///var/run/docker.sock\n",
            )
        if "up" in command:
            raise KeyboardInterrupt
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    assert runner.run_local(frontend_port=8080, api_port=8000) == 130
    assert any("up" in command and "--build" in command for command in calls)
    assert any(
        "down" in command and "--volumes" in command and "--remove-orphans" in command
        for command in calls
    )
    image_removal = next(
        command for command in calls if command[:3] == ["docker", "image", "rm"]
    )
    assert len(image_removal) == 5
    backend_suffix = image_removal[3].removeprefix("gds-workbench-backend:local-")
    frontend_suffix = image_removal[4].removeprefix("gds-workbench-frontend:local-")
    assert backend_suffix == frontend_suffix
    assert re.fullmatch(r"[0-9a-f]{12}", backend_suffix)


def test_standalone_compose_is_used_when_cli_plugin_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = _load_runner()
    calls: list[list[str]] = []

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[:2] == ["docker", "compose"]:
            raise subprocess.CalledProcessError(125, command)
        return subprocess.CompletedProcess(command, 0, stdout="5.0.0\n")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    assert runner.detect_compose_command() == ("docker-compose",)
    assert calls == [
        ["docker", "compose", "version", "--short"],
        ["docker-compose", "version", "--short"],
    ]
