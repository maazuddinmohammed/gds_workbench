from __future__ import annotations

import base64
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = ROOT / ".dockerignore"
ROOT_PACKAGE_LOCK = ROOT / "package-lock.json"
COMPOSE = ROOT / "web_app" / "compose.local.yaml"
BACKEND_DOCKERFILE = ROOT / "web_app" / "backend" / "Dockerfile"
FRONTEND_PACKAGE = ROOT / "web_app" / "frontend" / "package.json"
FRONTEND_INDEX = ROOT / "web_app" / "frontend" / "index.html"
FRONTEND_BUILD_TSCONFIG = ROOT / "web_app" / "frontend" / "tsconfig.build.json"
INSTALL_DATABASE = ROOT / "web_app" / "local" / "install_database.sh"
DATABASE_ROOT = ROOT / "database"
AZURE_FRESH_DEPLOYMENT = ROOT / "docs" / "AZURE_FRESH_DEPLOYMENT.md"
WEB_APP_WORKFLOW = ROOT / ".github" / "workflows" / "web-app.yml"
PLUGIN_WINDOWS_WORKFLOW = ROOT / ".github" / "workflows" / "plugin-windows.yml"
DATABASE_ARCHITECTURE = ROOT / "docs" / "architecture" / "database.md"
MCP_ARCHITECTURE = ROOT / "docs" / "architecture" / "overview.md"
MCP_TOOL_CONTRACT = ROOT / "plugins" / "v2" / "gds" / "tool-contract.json"


def test_local_compose_is_loopback_only_and_uses_one_combined_app() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    app = compose[compose.index("  app:\n") : compose.index("\nvolumes:\n")]

    assert "postgres:18.6-bookworm@sha256:1c59e2c3c818eaa0" in compose
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
        "deployment",
        "docs",
        "artifacts",
        "plugins",
        "tests",
        "web_app/compose.local.yaml",
        "web_app/local",
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


def test_frontend_declares_a_self_contained_svg_favicon() -> None:
    index = FRONTEND_INDEX.read_text(encoding="utf-8")

    match = re.search(
        r'<link\s+rel="icon"\s+type="image/svg\+xml"\s+sizes="any"\s+'
        r'href="data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)"\s*/>',
        index,
    )
    assert match is not None
    root = ET.fromstring(base64.b64decode(match.group(1), validate=True))
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"] == "0 0 64 64"
    assert root.find("{http://www.w3.org/2000/svg}path") is not None


def test_database_initializer_uses_exact_canonical_order_and_no_destructive_sql() -> (
    None
):
    initializer = INSTALL_DATABASE.read_text(encoding="utf-8")
    expected = [
        path.name
        for path in sorted(DATABASE_ROOT.glob("[0-9][0-9]_*.sql"))
        if path.name not in {"00_preflight.sql", "20_verify_install.sql"}
    ]
    assert [int(name[:2]) for name in expected] == list(range(1, 20))
    release_block = re.search(
        r"release_files=\(\n(?P<files>.*?)\n\)", initializer, re.DOTALL
    )

    assert release_block is not None
    assert (
        re.findall(
            r"^\s+([0-9][0-9]_[a-z0-9_]+\.sql)$", release_block["files"], re.MULTILINE
        )
        == expected
    )
    assert "00_preflight.sql" in initializer
    assert "20_verify_install.sql" in initializer
    assert "--single-transaction" in initializer
    assert "01_metadata_snapshot_demo.sql" in initializer
    assert "03_local_super_admin.template.sql" in initializer
    assert "04_application_reference.sql" in initializer
    assert "05_global_prompt_defaults.template.sql" in initializer
    assert initializer.index("03_local_super_admin.template.sql") < initializer.index(
        "05_global_prompt_defaults.template.sql"
    )
    assert not re.search(r"\b(?:DROP|TRUNCATE|RESET)\b", initializer, re.IGNORECASE)


def test_documented_fresh_install_matches_the_exact_canonical_database_release() -> (
    None
):
    guide = AZURE_FRESH_DEPLOYMENT.read_text(encoding="utf-8")
    expected = [
        path.name
        for path in sorted(DATABASE_ROOT.glob("[0-9][0-9]_*.sql"))
        if path.name not in {"00_preflight.sql", "20_verify_install.sql"}
    ]
    install_block = re.search(r"for file in \\\n(?P<files>.*?)\ndo", guide, re.DOTALL)

    assert install_block is not None
    assert (
        re.findall(r"database/([0-9][0-9]_[a-z0-9_]+\.sql)", install_block["files"])
        == expected
    )
    assert "\\password gds_mcp_runtime" in guide
    assert "\\password gds_web_runtime" in guide
    assert "database/seed/04_application_reference.sql" in guide
    assert "database/seed/05_global_prompt_defaults.template.sql" in guide
    assert guide.index("database/20_verify_install.sql") < guide.index(
        "database/seed/04_application_reference.sql"
    )
    assert guide.index("database/seed/04_application_reference.sql") < guide.index(
        "database/seed/05_global_prompt_defaults.template.sql"
    )


def test_database_cleanup_reference_is_complete_and_remains_commented() -> None:
    sql = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(DATABASE_ROOT.glob("[0-9][0-9]_*.sql"))
    )
    preflight = (DATABASE_ROOT / "00_preflight.sql").read_text(encoding="utf-8")
    expected_cleanup = [
        "DROP SCHEMA mcp CASCADE;",
        "DROP SCHEMA application CASCADE;",
        "DROP SCHEMA workflow CASCADE;",
        "DROP SCHEMA model CASCADE;",
        "DROP SCHEMA security CASCADE;",
        "DROP SCHEMA core CASCADE;",
        "DROP SCHEMA reference CASCADE;",
        "DROP OWNED BY gds_mcp_runtime CASCADE;",
        "DROP OWNED BY gds_web_runtime CASCADE;",
        "DROP OWNED BY gds_notebook_runtime CASCADE;",
        "DROP OWNED BY gds_app_write CASCADE;",
        "DROP OWNED BY gds_web_write CASCADE;",
        "DROP OWNED BY gds_migration CASCADE;",
        "DROP ROLE gds_mcp_runtime;",
        "DROP ROLE gds_web_runtime;",
        "DROP ROLE gds_notebook_runtime;",
        "DROP ROLE gds_app_write;",
        "DROP ROLE gds_web_write;",
        "DROP ROLE gds_migration;",
    ]

    assert not re.search(
        r"^\s*(?:DROP|TRUNCATE|RESET)\b",
        sql,
        re.IGNORECASE | re.MULTILINE,
    )
    assert (
        re.findall(
            r"^--(DROP (?:SCHEMA|OWNED BY|ROLE) .+;)$",
            preflight,
            re.MULTILINE,
        )
        == expected_cleanup
    )


def test_database_and_mcp_changes_trigger_the_disposable_postgres_ci_suite() -> None:
    workflow = WEB_APP_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count('      - "database/**"') == 2
    assert workflow.count('      - "tests/mcp/**"') == 2
    assert "uv sync --frozen --project mcp_server" in workflow
    assert "uv run --frozen --project mcp_server python -m pytest" in workflow
    assert "-c mcp_server/pyproject.toml tests/mcp" in workflow


def test_loader_has_an_independent_frozen_python_312_ci_job() -> None:
    workflow = WEB_APP_WORKFLOW.read_text(encoding="utf-8")
    loader_job = workflow[
        workflow.index("  loader:\n") : workflow.index("\n  database-and-mcp:\n")
    ]

    assert 'python-version: "3.12"' in loader_job
    assert "uv sync --frozen --project load_and_merge_scripts" in loader_job
    assert (
        "uv run --frozen --project load_and_merge_scripts python -m pytest"
        in loader_job
    )
    assert "load_and_merge_scripts/tests" in loader_job


def test_windows_plugin_ci_tracks_and_uses_the_frozen_mcp_project() -> None:
    workflow = PLUGIN_WINDOWS_WORKFLOW.read_text(encoding="utf-8")

    assert '      - "mcp_server/**"' in workflow
    assert "uv sync --frozen --project mcp_server" in workflow
    assert "uv run --frozen --project mcp_server python -m pytest" in workflow
    assert "tests/plugin_v2 -q" in workflow
    assert "pip install pytest" not in workflow


def test_current_architecture_counts_match_checked_in_contracts() -> None:
    database_architecture = DATABASE_ARCHITECTURE.read_text(encoding="utf-8")
    mcp_architecture = MCP_ARCHITECTURE.read_text(encoding="utf-8")
    tool_contract = json.loads(MCP_TOOL_CONTRACT.read_text(encoding="utf-8"))

    assert "There are 99 tables" in database_architecture
    assert "defines three non-login, non-superuser group roles" in database_architecture
    assert "exact 32 secure `application` functions" in database_architecture
    assert "`ChangeSetsFeature` draft-expiry worker" not in database_architecture
    assert "post-lock PostgreSQL wall-clock" in database_architecture
    assert f"{tool_contract['tool_count']} governed MCP tools" in mcp_architecture
    assert "Ten read-only MCP tools" not in mcp_architecture
    assert "No write or Tenant Lock MCP tool is registered" not in mcp_architecture
