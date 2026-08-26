from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WEB_APP_CI = ROOT / ".github" / "workflows" / "web-app.yml"


def test_databricks_app_runs_one_supervised_python_process() -> None:
    app_config = (ROOT / "app.yaml").read_text(encoding="utf-8")

    assert "command:\n  - uv\n  - run\n  - --frozen\n  - python\n  - -m\n" in app_config
    assert "gds_workbench_api.app_process" in app_config
    assert "GDS_WEB_STATIC_DIR" in app_config
    assert "value: web_app/frontend/dist" in app_config
    assert "GDS_WEB_AGENT_EXECUTION_MODE" in app_config
    assert "GDS_WEB_AGENT_PROVIDER" in app_config
    assert "value: databricks" in app_config
    assert "GDS_WEB_DATABRICKS_MODEL_ENDPOINT" in app_config
    assert "valueFrom: agent-model-endpoint" in app_config
    assert "GDS_WEB_FOUNDRY" not in app_config
    assert "AZURE_CONTAINER" not in app_config
    assert set(re.findall(r"^  - name: (\S+)$", app_config, re.MULTILINE)) == {
        "NODE_ENV",
        "GDS_WEB_ENVIRONMENT",
        "GDS_WEB_STATIC_DIR",
        "GDS_WEB_AGENT_EXECUTION_MODE",
        "GDS_WEB_AGENT_PROVIDER",
        "GDS_WEB_DATABRICKS_EXECUTION_MODE",
        "GDS_WEB_DATABASE_DSN",
        "GDS_WEB_CURSOR_SIGNING_KEY",
        "GDS_WEB_ENTRA_TENANT_ID",
        "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE",
        "GDS_WEB_DATABRICKS_MODEL_ENDPOINT",
    }
    assert set(re.findall(r"^    valueFrom: (\S+)$", app_config, re.MULTILINE)) == {
        "postgres-dsn",
        "cursor-signing-key",
        "entra-tenant-id",
        "databricks-environment-code",
        "agent-model-endpoint",
    }


def test_bundle_grants_only_required_app_resources() -> None:
    bundle = (ROOT / "databricks.yml").read_text(encoding="utf-8")

    assert (
        'bundle:\n  name: gds-workbench-app\n  databricks_cli_version: ">=0.294.0"'
        in bundle
    )
    assert "source_code_path: ." in bundle
    assert "iam.access-control:read" in bundle
    assert "iam.current-user:read" in bundle
    assert "level: CAN_USE" in bundle
    assert bundle.count("permission: READ") == 4
    assert "permission: CAN_QUERY" in bundle
    assert "scope: ${var.secret_scope}" in bundle
    assert "key: ${var.database_dsn_secret_key}" in bundle
    assert "DATABRICKS_CLIENT_SECRET" not in bundle
    assert "tests/**" in bundle
    assert '"**/.env*"' in bundle
    assert '"**/*.key"' in bundle
    assert '"**/*.p12"' in bundle
    assert '"**/*.pem"' in bundle
    assert '"**/*.pfx"' in bundle
    assert "database/**" in bundle
    assert "artifacts/**" in bundle
    assert "plugins/**" in bundle
    assert "IMPLEMENTATION_PLAN.md" in bundle
    assert "web_app/prototypes/**" in bundle


def test_root_manifests_are_locked_hybrid_app_inputs() -> None:
    python_project = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    node_project = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert (ROOT / "uv.lock").is_file()
    assert (ROOT / "package-lock.json").is_file()
    assert python_project["project"]["requires-python"] == ">=3.14,<3.15"
    assert set(python_project["tool"]["uv"]["sources"]) == {
        "gds-etl-workbench-mcp",
        "gds-workbench-api",
    }
    assert all(
        source["editable"] is False
        for source in python_project["tool"]["uv"]["sources"].values()
    )
    assert node_project["engines"]["node"] == ">=22.16 <23"
    assert node_project["workspaces"] == ["web_app/frontend"]
    assert (
        node_project["scripts"]["build"]
        == "npm run build --workspace=gds-workbench-web"
    )


def test_frontend_build_dependencies_are_available_in_production() -> None:
    frontend = json.loads(
        (ROOT / "web_app" / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    build_config = json.loads(
        (ROOT / "web_app" / "frontend" / "tsconfig.build.json").read_text(
            encoding="utf-8"
        )
    )

    for dependency in (
        "@types/react",
        "@types/react-dom",
        "@vitejs/plugin-react",
        "typescript",
        "vite",
    ):
        assert dependency in frontend["dependencies"]
    assert "tsconfig.build.json" in frontend["scripts"]["build"]
    assert build_config["exclude"]
    assert all(
        ".test." in pattern or pattern.startswith("src/test/")
        for pattern in build_config["exclude"]
    )


def test_ci_uses_the_deployment_engines_and_frozen_release_inputs() -> None:
    workflow = WEB_APP_CI.read_text(encoding="utf-8")

    assert 'python-version: "3.14"' in workflow
    assert 'node-version: "22.16.0"' in workflow
    assert "uv==0.10.2" in workflow
    assert "uv sync --frozen" in workflow
    assert "npm ci" in workflow
    assert "npm run check" in workflow
    assert "tests/web_backend" in workflow
    assert "tests/web_packaging" in workflow
    assert "contents: read" in workflow
    assert "databricks bundle deploy" not in workflow
