from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from gds_workbench_api.frontend import (
    RequestBodyLimitMiddleware,
    SecurityHeadersMiddleware,
    mount_frontend,
)


def _built_frontend(directory: Path) -> Path:
    assets = directory / "assets"
    assets.mkdir()
    (directory / "index.html").write_text("<main>workbench</main>", encoding="utf-8")
    (assets / "index-abc123.js").write_text("export {};", encoding="utf-8")
    return directory


def test_react_is_same_origin_with_spa_and_immutable_asset_caching(
    tmp_path: Path,
) -> None:
    app = FastAPI()

    async def api_route() -> dict[str, str]:
        return {"source": "api"}

    app.add_api_route("/api/example", api_route, methods=["GET"])
    mount_frontend(app, _built_frontend(tmp_path))
    app.add_middleware(SecurityHeadersMiddleware)

    with TestClient(app) as client:
        api = client.get("/api/example")
        page = client.get("/tenants/7/models/18")
        asset = client.get("/assets/index-abc123.js")
        missing_api = client.get("/api/not-present")

    assert api.json() == {"source": "api"}
    assert page.text == "<main>workbench</main>"
    assert page.headers["cache-control"] == "no-cache"
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert missing_api.status_code == 404
    assert missing_api.headers["content-type"].startswith("application/json")
    for response in (api, page, asset, missing_api):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "same-origin"
        assert "default-src 'self'" in response.headers["content-security-policy"]


def test_request_body_limit_rejects_declared_and_streamed_oversize_bodies() -> None:
    app = FastAPI()

    async def echo(request: Request) -> dict[str, int]:
        return {"bytes": len(await request.body())}

    app.add_api_route("/api/echo", echo, methods=["POST"])
    app.add_middleware(RequestBodyLimitMiddleware, maximum_bytes=4)

    with TestClient(app) as client:
        accepted = client.post("/api/echo", content=b"1234")
        rejected = client.post("/api/echo", content=b"12345")

    assert accepted.json() == {"bytes": 4}
    assert rejected.status_code == 413
    assert rejected.json() == {"detail": "Request body is too large."}


def test_frontend_mount_fails_closed_when_build_is_missing(tmp_path: Path) -> None:
    app = FastAPI()

    try:
        mount_frontend(app, tmp_path)
    except RuntimeError as exc:
        assert str(exc) == "the built React frontend is unavailable"
    else:
        raise AssertionError("missing frontend build must fail startup")
