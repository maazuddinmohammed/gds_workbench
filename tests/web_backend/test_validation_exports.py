"""Validation ZIPs preserve complete SQL and machine-readable comparison rules."""

import json
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile

import pytest
from fastapi.testclient import TestClient
from gds_workbench_api.features.validation import downloads
from gds_workbench_api.features.validation.contracts import (
    ExportValidationRequest,
    ValidationBundleLimitExceededError,
    ValidationExportEmptyError,
    ValidationLedger,
)
from gds_workbench_api.main import create_app

from tests.web_backend.test_code_generation import (
    _identity_provider,  # pyright: ignore[reportPrivateUsage]
)
from tests.web_backend.test_validation_read import (
    StaticValidationService,
    _principal,  # pyright: ignore[reportPrivateUsage]
)


@pytest.fixture
async def ledger() -> ValidationLedger:
    saved = await StaticValidationService().read_ledger(_principal(), tenant_id=7, project_id=18)
    group = saved.groups[0]
    check = group.checks[0].model_copy(
        update={
            "validation_check_name": "../../CON\r\n",
            "validation_query_sql": "SELECT 'é';\n" + "-- full stored SQL\n" * 2000,
            "validation_comparison_query_sql": "SELECT 0;\n",
            "validation_result_data_type": "integer",
            "validation_comparison_operator": "equal",
            "validation_comparison_value_type": "query",
            "is_locked": True,
        }
    )
    literal = check.model_copy(
        update={
            "validation_check_id": 502,
            "validation_comparison_query_sql": None,
            "validation_comparison_value_type": "literal_list",
            "validation_comparison_operator": "in",
            "validation_comparison_value": [0, 1],
        }
    )
    shared = group.model_copy(
        update={
            "code_context_is_current": False,
            "validation_group_is_current": False,
            "checks": (check, literal, check.model_copy(update={"is_active": False})),
        }
    )
    return saved.model_copy(
        update={
            "groups": (
                shared,
                group.model_copy(update={"is_active": False}),
                group.model_copy(update={"modeled_entity_type": "dimensional_entity"}),
            )
        }
    )


def test_validation_zip_keeps_full_sql_comparison_criteria_and_stale_flags(
    ledger: ValidationLedger,
) -> None:
    command = ExportValidationRequest(entity_type="logical_entity", expected_project_revision=4)
    content, count = downloads.build_validation_zip(ledger, command)
    assert count == 2
    assert (content, count) == downloads.build_validation_zip(ledger, command)
    with ZipFile(BytesIO(content)) as archive:
        assert set(archive.namelist()) == {
            "check_501.sql",
            "check_501__comparison.sql",
            "check_502.sql",
            "manifest.json",
        }
        assert all(member.compress_type == ZIP_STORED for member in archive.infolist())
        assert (
            archive.read("check_501.sql")
            == ledger.groups[0].checks[0].validation_query_sql.encode()
        )
        assert archive.read("check_501__comparison.sql") == b"SELECT 0;\n"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["scope"] == "active_validation_checks"
        assert manifest["project_revision"] == 4
        assert len(manifest["groups"]) == 1
        group = manifest["groups"][0]
        assert group["validation_group_is_current"] is False
        query, literal = group["checks"]
        assert query["is_locked"] is True
        assert query["validation_severity"] == "blocking"
        assert query["validation_comparison_operator"] == "equal"
        assert query["comparison_query_file"] == "check_501__comparison.sql"
        assert literal["validation_comparison_value"] == [0, 1]
        assert literal["comparison_query_file"] is None


@pytest.mark.parametrize("limit", ["MAX_EXPORT_CHECKS", "MAX_EXPORT_BYTES", "MAX_ZIP_BYTES"])
def test_validation_zip_rejects_bound_overflow_without_partial_download(
    ledger: ValidationLedger, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    monkeypatch.setattr(downloads, limit, 1)
    with pytest.raises(ValidationBundleLimitExceededError):
        downloads.build_validation_zip(
            ledger,
            ExportValidationRequest(entity_type="logical_entity", expected_project_revision=4),
        )


def test_empty_validation_export_is_explicit(ledger: ValidationLedger) -> None:
    with pytest.raises(ValidationExportEmptyError):
        downloads.build_validation_zip(
            ledger.model_copy(update={"groups": ()}),
            ExportValidationRequest(entity_type="logical_entity", expected_project_revision=4),
        )


def test_validation_export_http_contract_revision_and_strict_input() -> None:
    app = create_app(
        identity_provider=_identity_provider(), validation_read_service=StaticValidationService()
    )
    path = "/api/v1/tenants/7/projects/18/validation/downloads/all.zip"
    with TestClient(app) as client:
        command = {"entity_type": "logical_entity", "expected_project_revision": 4}
        response = client.post(path, json=command)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-gds-check-count"] == "1"
        assert response.headers["x-gds-export-scope"] == "active_validation_checks"
        assert response.headers["content-disposition"] == (
            'attachment; filename="gds_validation_logical__project_18__r4.zip"'
        )
        stale = client.post(path, json={**command, "expected_project_revision": 3})
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "project_revision_conflict"
        for invalid in ({}, {**command, "entity_type": "conceptual"}, {**command, "all": True}):
            assert client.post(path, json=invalid).status_code == 422
