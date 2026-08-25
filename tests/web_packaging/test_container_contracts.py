from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = ROOT / ".dockerignore"
ROOT_PACKAGE_LOCK = ROOT / "package-lock.json"
COMPOSE = ROOT / "web_app" / "compose.local.yaml"
BACKEND_DOCKERFILE = ROOT / "web_app" / "backend" / "Dockerfile"
FRONTEND_PACKAGE = ROOT / "web_app" / "frontend" / "package.json"
FRONTEND_BUILD_TSCONFIG = ROOT / "web_app" / "frontend" / "tsconfig.build.json"
INSTALL_DATABASE = ROOT / "web_app" / "local" / "install_database.sh"


def test_local_compose_is_loopback_only_and_uses_one_combined_app() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    app = compose[compose.index("  app:\n") : compose.index("\nvolumes:\n")]

    assert "postgres:18.4-bookworm@sha256:882236b897e39051" in compose
    assert '"127.0.0.1:${GDS_LOCAL_API_PORT}:8000"' in compose
    assert '"127.0.0.1:${GDS_LOCAL_FRONTEND_PORT}:8000"' in compose
    assert not re.search(r"ports:\s*\n(?:\s+-.*\n)*\s+-\s*[\"']?5432:", compose)
    assert (
        compose.count(
            "gds-workbench-app:local-${GDS_LOCAL_IMAGE_SUFFIX:?generated image suffix required}"
        )
        == 1
    )
    assert "  api:\n" not in compose
    assert "  worker:\n" not in compose
    assert "  frontend:\n" not in compose
    assert "GDS_WEB_STATIC_DIR: /app/web_app/frontend/dist" in compose
    assert 'DATABRICKS_APP_PORT: "8000"' in compose
    assert "GDS_WEB_AGENT_EXECUTION_MODE: fake" in compose
    assert "GDS_WEB_DATABRICKS_EXECUTION_MODE: fake" in compose
    assert "local_backend:\n    internal: true" in compose
    assert "local_edge:\n" in compose
    assert "- local_backend" in app and "- local_edge" in app
    assert "<<: *app-security" in app
    assert "cap_drop:" in compose and "- ALL" in compose


def test_combined_local_image_builds_react_and_python_then_runs_one_app_process() -> (
    None
):
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert (
        "node:22.16.0-bookworm-slim@sha256:048ed02c5fd52e86fda6fbd2f6a76cf0d4492f"
        in dockerfile
    )
    assert dockerfile.count("python:3.14.7-slim-trixie@sha256:ce40764625a4ff50") == 2
    assert "uv==0.11.14" in dockerfile
    assert "COPY package.json package-lock.json ./" in dockerfile
    assert "npm ci --omit=dev" in dockerfile
    assert "npm run build" in dockerfile
    assert "COPY pyproject.toml uv.lock /workspace/" in dockerfile
    assert "uv sync --frozen --no-dev --no-editable" in dockerfile
    assert "/workspace/web_app/frontend/dist /app/web_app/frontend/dist" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert 'CMD ["python", "-m", "gds_workbench_api.app_process"]' in dockerfile


def test_combined_image_context_excludes_local_and_generated_content() -> None:
    ignored = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()

    assert {
        ".git",
        ".github",
        ".scratch",
        ".bundle",
        ".databricks",
        "**/.env*",
        "**/*.key",
        "**/*.p12",
        "**/*.pem",
        "**/*.pfx",
        "**/.pytest_cache",
        "**/.ruff_cache",
        "**/.venv",
        "**/dist",
        "**/node_modules",
        "database",
        "docs",
        "artifacts",
        "plugins",
        "tests",
        "web_app/compose.local.yaml",
        "web_app/local",
        "web_app/prototypes",
    } <= set(ignored)


def test_frontend_lock_contains_cross_platform_native_build_packages() -> None:
    packages = json.loads(ROOT_PACKAGE_LOCK.read_text(encoding="utf-8"))["packages"]

    for build_package in ("node_modules/rolldown", "node_modules/lightningcss"):
        optional_dependencies = packages[build_package]["optionalDependencies"]
        assert {
            f"node_modules/{dependency}" for dependency in optional_dependencies
        } <= packages.keys()


def test_frontend_production_build_does_not_require_test_dependencies() -> None:
    package = FRONTEND_PACKAGE.read_text(encoding="utf-8")
    build_config = FRONTEND_BUILD_TSCONFIG.read_text(encoding="utf-8")

    assert '"node": ">=22.16 <23"' in package
    assert (
        '"build": "tsc --project tsconfig.build.json --noEmit && vite build"' in package
    )
    assert '"extends": "./tsconfig.json"' in build_config
    assert '"src/**/*.test.ts"' in build_config
    assert '"src/**/*.test.tsx"' in build_config
    assert '"src/test/**"' in build_config
    assert not (ROOT / "web_app" / "frontend" / "Dockerfile").exists()
    assert not (ROOT / "web_app" / "frontend" / "nginx.conf.template").exists()
    assert not (ROOT / "web_app" / "frontend" / "package-lock.json").exists()


def test_database_initializer_uses_exact_canonical_order_and_no_destructive_sql() -> (
    None
):
    initializer = INSTALL_DATABASE.read_text(encoding="utf-8")
    expected = [
        "01_reference.sql",
        "02_core.sql",
        "03_security.sql",
        "04_model.sql",
        "05_workflow_analysis.sql",
        "06_workflow_conceptual.sql",
        "07_workflow_logical.sql",
        "08_workflow_dimensional.sql",
        "09_workflow_mapping.sql",
        "10_application.sql",
        "10_mcp.sql",
        "10_workflow_eligibility.sql",
        "11_mcp_metadata_apply.sql",
        "11_runtime_account.sql",
        "12_runtime_integrity.sql",
    ]

    positions = [initializer.index(name) for name in expected]
    assert positions == sorted(positions)
    assert "00_preflight.sql" in initializer
    assert "13_verify_install.sql" in initializer
    assert "--single-transaction" in initializer
    assert "01_metadata_snapshot_demo.sql" in initializer
    assert "03_local_super_admin.template.sql" in initializer
    assert "04_application_reference.sql" in initializer
    assert not re.search(r"\b(?:DROP|TRUNCATE|RESET)\b", initializer, re.IGNORECASE)
