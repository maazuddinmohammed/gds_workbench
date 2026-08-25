from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "web_app" / "compose.local.yaml"
BACKEND_DOCKERFILE = ROOT / "web_app" / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = ROOT / "web_app" / "frontend" / "Dockerfile"
NGINX_TEMPLATE = ROOT / "web_app" / "frontend" / "nginx.conf.template"
INSTALL_DATABASE = ROOT / "web_app" / "local" / "install_database.sh"


def test_local_compose_is_loopback_only_and_uses_one_backend_image() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "postgres:18.4-bookworm@sha256:882236b897e39051" in compose
    assert '"127.0.0.1:${GDS_LOCAL_API_PORT}:8000"' in compose
    assert '"127.0.0.1:${GDS_LOCAL_FRONTEND_PORT}:8080"' in compose
    assert not re.search(r"ports:\s*\n(?:\s+-.*\n)*\s+-\s*[\"']?5432:", compose)
    assert (
        compose.count(
            "gds-workbench-backend:local-${GDS_LOCAL_IMAGE_SUFFIX:?generated image suffix required}"
        )
        == 2
    )
    assert 'command: ["gds-workbench-worker"]' in compose
    assert "GDS_WEB_AGENT_EXECUTION_MODE: fake" in compose
    assert "GDS_WEB_DATABRICKS_EXECUTION_MODE: fake" in compose
    assert "internal: true" in compose
    assert "cap_drop:" in compose and "- ALL" in compose


def test_backend_image_is_python_314_frozen_and_non_root() -> None:
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    assert dockerfile.count("python:3.14.7-slim-trixie@sha256:ce40764625a4ff50") == 2
    assert "uv==0.11.14" in dockerfile
    assert "uv sync --frozen --no-dev --no-editable" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "gds_workbench_api.runtime:create_runtime_app" in dockerfile


def test_frontend_image_is_node_24_locked_and_unprivileged() -> None:
    dockerfile = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")

    assert "node:24.19.0-bookworm-slim@sha256:3638d9a6fe4030bd" in dockerfile
    assert "npm@11.6.0" in dockerfile
    assert "npm ci" in dockerfile
    assert "npm run build" in dockerfile
    assert "nginxinc/nginx-unprivileged:1.31.4-trixie" in dockerfile
    assert "USER nginx" in dockerfile


def test_frontend_proxy_has_api_proxy_spa_fallback_and_health_endpoint() -> None:
    nginx = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert "location /api/" in nginx
    assert "proxy_pass ${API_UPSTREAM}" in nginx
    assert "try_files $uri $uri/ /index.html" in nginx
    assert "location = /healthz" in nginx
    assert "listen 8080" in nginx


def test_database_initializer_uses_exact_canonical_order_and_no_destructive_sql() -> None:
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
