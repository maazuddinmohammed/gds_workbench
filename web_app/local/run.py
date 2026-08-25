#!/usr/bin/env python3
"""Start one isolated, disposable local GDS Workbench stack."""

from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from uuid import uuid4


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPOSITORY_ROOT / "web_app" / "compose.local.yaml"
_FORBIDDEN_EXACT = frozenset(
    {
        "DATABASE_URL",
        "DB_URL",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
    }
)
_FORBIDDEN_PREFIXES = (
    "AZURE_",
    "BUILDKIT_",
    "BUILDX_",
    "COMPOSE_",
    "DATABRICKS_",
    "DOCKER_",
    "GDS_",
    "OPENAI_",
    "PG",
    "POSTGRES_",
)
_ENVIRONMENT_VALUE = re.compile(r"[A-Za-z0-9_.-]+")


class LocalSafetyError(RuntimeError):
    """Local orchestration refused an unsafe caller-controlled input."""


def assert_safe_environment(environment: Mapping[str, str]) -> None:
    """Reject ambient connection, provider, Compose, and local-run overrides."""
    unsafe = sorted(
        key
        for key, value in environment.items()
        if value.strip()
        and (
            key in _FORBIDDEN_EXACT
            or any(key.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)
        )
    )
    if unsafe:
        raise LocalSafetyError(
            f"remove unsafe ambient setting before local startup: {unsafe[0]}"
        )


def assert_local_docker_endpoint(endpoint: str) -> None:
    """Allow only a local Docker socket; TCP is rejected even on loopback."""
    normalized = endpoint.strip().lower()
    if not normalized.startswith(("unix://", "npipe://")):
        raise LocalSafetyError("local startup requires a local Docker socket")


def _validated_port(value: int, *, name: str) -> int:
    if not 1024 <= value <= 65535:
        raise LocalSafetyError(f"{name} must be between 1024 and 65535")
    return value


def build_local_environment(*, frontend_port: int, api_port: int) -> dict[str, str]:
    """Generate all per-run identifiers and credentials in memory."""
    frontend_port = _validated_port(frontend_port, name="frontend port")
    api_port = _validated_port(api_port, name="API port")
    if frontend_port == api_port:
        raise LocalSafetyError("frontend and API ports must be different")

    run_suffix = secrets.token_hex(6)
    return {
        "GDS_LOCAL_API_PORT": str(api_port),
        "GDS_LOCAL_CURSOR_SIGNING_KEY": secrets.token_hex(48),
        "GDS_LOCAL_DATABASE_ADMIN": f"gds_admin_{run_suffix}",
        "GDS_LOCAL_DATABASE_NAME": f"gds_local_{run_suffix}",
        "GDS_LOCAL_ENTRA_TENANT_ID": str(uuid4()),
        "GDS_LOCAL_FRONTEND_PORT": str(frontend_port),
        "GDS_LOCAL_IMAGE_SUFFIX": run_suffix,
        "GDS_LOCAL_MCP_PASSWORD": secrets.token_hex(48),
        "GDS_LOCAL_POSTGRES_ADMIN_PASSWORD": secrets.token_hex(48),
        "GDS_LOCAL_PRINCIPAL_OBJECT_ID": str(uuid4()),
        "GDS_LOCAL_PROJECT_NAME": f"gdswb_{run_suffix}",
        "GDS_LOCAL_RUN_SENTINEL": run_suffix,
        "GDS_LOCAL_WEB_PASSWORD": secrets.token_hex(48),
    }


def write_environment_file(directory: Path, values: Mapping[str, str]) -> Path:
    """Write secrets to one private file outside the repository."""
    environment_file = directory / "local.env"
    lines: list[str] = []
    for key, value in sorted(values.items()):
        if not _ENVIRONMENT_VALUE.fullmatch(value):
            raise LocalSafetyError(f"generated local value is not env-file safe: {key}")
        lines.append(f"{key}={value}\n")
    descriptor = os.open(
        environment_file,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.writelines(lines)
    return environment_file


def detect_compose_command() -> tuple[str, ...]:
    """Prefer the Docker CLI plugin, with the standalone binary as fallback."""
    for candidate in (("docker", "compose"), ("docker-compose",)):
        try:
            subprocess.run(
                [*candidate, "version", "--short"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        return candidate
    raise LocalSafetyError("Docker Compose is required")


def _compose_base(
    *,
    compose_command: tuple[str, ...],
    project_name: str,
    environment_file: Path,
) -> list[str]:
    return [
        *compose_command,
        "--project-name",
        project_name,
        "--env-file",
        str(environment_file),
        "--file",
        str(COMPOSE_FILE),
    ]


def _check_local_docker() -> None:
    result = subprocess.run(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert_local_docker_endpoint(result.stdout)


def run_local(*, frontend_port: int, api_port: int) -> int:
    """Run the stack and always dispose its containers, network, and volume."""
    assert_safe_environment(os.environ)
    compose_command = detect_compose_command()
    _check_local_docker()
    values = build_local_environment(frontend_port=frontend_port, api_port=api_port)
    project_name = values["GDS_LOCAL_PROJECT_NAME"]

    with tempfile.TemporaryDirectory(prefix="gds-workbench-local-") as temporary:
        environment_file = write_environment_file(Path(temporary), values)
        compose = _compose_base(
            compose_command=compose_command,
            project_name=project_name,
            environment_file=environment_file,
        )
        result = 0
        try:
            print(f"Workbench: http://127.0.0.1:{frontend_port}")
            subprocess.run(
                [*compose, "up", "--build", "--abort-on-container-exit"],
                check=True,
            )
        except KeyboardInterrupt:
            result = 130
        except subprocess.CalledProcessError as exc:
            result = exc.returncode or 1
        finally:
            subprocess.run(
                [*compose, "down", "--volumes", "--remove-orphans"],
                check=False,
            )
            image_suffix = values["GDS_LOCAL_IMAGE_SUFFIX"]
            subprocess.run(
                [
                    "docker",
                    "image",
                    "rm",
                    f"gds-workbench-backend:local-{image_suffix}",
                    f"gds-workbench-frontend:local-{image_suffix}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-port", type=int, default=8080)
    parser.add_argument("--api-port", type=int, default=8000)
    arguments = parser.parse_args(argv)
    try:
        return run_local(
            frontend_port=arguments.frontend_port,
            api_port=arguments.api_port,
        )
    except (LocalSafetyError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"local startup refused: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
