from fastapi.testclient import TestClient

from gds_workbench_api.main import ReadinessResult, create_app


class ReadyDependency:
    async def readiness(self) -> ReadinessResult:
        return ReadinessResult(ready=True, code="ready")


class UnavailableDependency:
    async def readiness(self) -> ReadinessResult:
        return ReadinessResult(ready=False, code="database_unavailable")


def test_health_reports_that_the_process_is_running() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_generated_api_documentation_is_not_exposed() -> None:
    with TestClient(create_app()) as client:
        docs = client.get("/docs")
        schema = client.get("/openapi.json")

    assert docs.status_code == 404
    assert schema.status_code == 404


def test_readiness_reports_that_dependencies_are_ready() -> None:
    with TestClient(create_app(readiness=ReadyDependency())) as client:
        response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "code": "ready"}


def test_readiness_is_unavailable_when_a_dependency_is_not_ready() -> None:
    with TestClient(create_app(readiness=UnavailableDependency())) as client:
        response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "code": "database_unavailable",
    }
