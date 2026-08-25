from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets import metadata as canonical_metadata
from gds_etl_workbench.tools.change_sets.validation import MetadataChangeSetValidation
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS_BY_NAME
from psycopg.types.json import Jsonb

from gds_workbench_api.features.metadata.workbook import (
    XLSX_MEDIA_TYPE,
    MetadataWorkbookSheet,
    build_metadata_workbook,
)
from gds_workbench_api.features.metadata_change_sets.contracts import (
    ApplyMetadataChangeSetResult,
    ArchiveMetadataChangeSetResult,
    CreateMetadataChangeSetRequest,
    CreateMetadataChangeSetResult,
    ExpectedDraftRevisionRequest,
    GetMetadataChangeSetResult,
    ImportMetadataWorkbookResult,
    MetadataChangeSetDatasetCount,
    StageMetadataChangeSetRequest,
    StageMetadataChangeSetResult,
    StageMetadataDatasetRequest,
    ValidateMetadataChangeSetResult,
)
from gds_workbench_api.features.metadata_change_sets.service import (
    DatabaseMetadataChangeSetService,
)
from gds_workbench_api.main import create_app

_CHANGE_SET_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_IDEMPOTENCY_KEY = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_NOW = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _counts() -> tuple[MetadataChangeSetDatasetCount, ...]:
    return tuple(
        MetadataChangeSetDatasetCount(dataset=dataset, record_count=0)
        for dataset in canonical_metadata.CHANGE_SET_DATASETS
    )


def _staged() -> StageMetadataChangeSetResult:
    return StageMetadataChangeSetResult(
        tenant_id=7,
        metadata_change_set_id=_CHANGE_SET_ID,
        datasets=(MetadataChangeSetDatasetCount(dataset="copy_group", record_count=1),),
        draft_revision=2,
        expires_at=_NOW,
    )


def _validated() -> ValidateMetadataChangeSetResult:
    return ValidateMetadataChangeSetResult(
        tenant_id=7,
        metadata_change_set_id=_CHANGE_SET_ID,
        valid=True,
        phase="complete",
        status="validated",
        draft_revision=2,
        candidate_digest="d" * 64,
        staged_record_count=1,
        error_count=0,
        errors=(),
        action_review=(),
        validated_at=_NOW,
        expires_at=_NOW,
    )


class RecordingMetadataChangeSetService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    @staticmethod
    def _assert_principal(principal: RequestPrincipal) -> None:
        assert principal.actor_kind is ActorKind.HUMAN

    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        command: CreateMetadataChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateMetadataChangeSetResult:
        self._assert_principal(principal)
        assert tenant_id == 7
        assert command.schema_version == "1.0"
        assert idempotency_key == _IDEMPOTENCY_KEY
        self.calls.append(("create", tenant_id))
        return CreateMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=_CHANGE_SET_ID,
            created=True,
            status="active",
            draft_revision=1,
            created_at=_NOW,
            expires_at=_NOW,
        )

    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: StageMetadataChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageMetadataChangeSetResult:
        self._assert_principal(principal)
        assert (tenant_id, change_set_id, command.expected_draft_revision) == (
            7,
            _CHANGE_SET_ID,
            1,
        )
        assert command.changes[0].dataset == "copy_group"
        assert idempotency_key == _IDEMPOTENCY_KEY
        self.calls.append(("stage", command.changes[0].records))
        return _staged()

    async def get(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        dataset: canonical_metadata.ChangeSetDataset | None,
    ) -> GetMetadataChangeSetResult:
        self._assert_principal(principal)
        assert (tenant_id, change_set_id, dataset) == (7, _CHANGE_SET_ID, "copy_group")
        self.calls.append(("get", dataset))
        return GetMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            status="active",
            draft_revision=2,
            candidate_digest=None,
            validation_outcome=None,
            dataset_counts=_counts(),
            dataset=dataset,
            records=(),
            created_at=_NOW,
            last_activity_at=_NOW,
            expires_at=_NOW,
            validated_at=None,
            applied_at=None,
            terminal_at=None,
        )

    async def validate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
    ) -> ValidateMetadataChangeSetResult:
        self._assert_principal(principal)
        assert (tenant_id, change_set_id, command.expected_draft_revision) == (
            7,
            _CHANGE_SET_ID,
            2,
        )
        self.calls.append(("validate", command.expected_draft_revision))
        return _validated()

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyMetadataChangeSetResult:
        self._assert_principal(principal)
        assert (tenant_id, change_set_id, command.expected_draft_revision) == (
            7,
            _CHANGE_SET_ID,
            2,
        )
        assert idempotency_key == _IDEMPOTENCY_KEY
        self.calls.append(("apply", command.expected_draft_revision))
        return ApplyMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            valid=True,
            applied=True,
            phase="complete",
            status="applied",
            draft_revision=2,
            candidate_digest="d" * 64,
            staged_record_count=1,
            action_count=1,
            error_count=0,
            errors=(),
            action_review=(),
            applied_at=_NOW,
        )

    async def archive(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ArchiveMetadataChangeSetResult:
        self._assert_principal(principal)
        assert (tenant_id, change_set_id, command.expected_draft_revision) == (
            7,
            _CHANGE_SET_ID,
            2,
        )
        assert idempotency_key == _IDEMPOTENCY_KEY
        self.calls.append(("archive", command.expected_draft_revision))
        return ArchiveMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            draft_revision=2,
            archived_at=_NOW,
        )

    async def import_workbook(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        expected_draft_revision: int,
        content: bytes,
        idempotency_key: UUID,
    ) -> ImportMetadataWorkbookResult:
        self._assert_principal(principal)
        assert (tenant_id, change_set_id, expected_draft_revision) == (
            7,
            _CHANGE_SET_ID,
            1,
        )
        assert idempotency_key == _IDEMPOTENCY_KEY
        self.calls.append(("import", content))
        return ImportMetadataWorkbookResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            imported_sheet_count=1,
            staged=_staged(),
            validation=_validated(),
        )


def test_metadata_change_set_routes_derive_identity_and_expose_every_command() -> None:
    service = RecordingMetadataChangeSetService()
    app = create_app(
        identity_provider=_identity_provider(),
        metadata_change_set_service=service,
    )
    headers = {"Idempotency-Key": str(_IDEMPOTENCY_KEY)}
    base = f"/api/v1/tenants/7/metadata-change-sets/{_CHANGE_SET_ID}"

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/tenants/7/metadata-change-sets",
            headers=headers,
            json={},
        )
        staged = client.put(
            f"{base}/stage",
            headers=headers,
            json={
                "expected_draft_revision": 1,
                "changes": [{"dataset": "copy_group", "records": [{"safe": "row"}]}],
            },
        )
        fetched = client.get(f"{base}?dataset=copy_group")
        validated = client.post(
            f"{base}/validate",
            json={"expected_draft_revision": 2},
        )
        applied = client.post(
            f"{base}/apply",
            headers=headers,
            json={"expected_draft_revision": 2},
        )
        archived = client.post(
            f"{base}/archive",
            headers=headers,
            json={"expected_draft_revision": 2},
        )
        imported = client.post(
            f"{base}/imports/xlsx",
            headers={
                **headers,
                "If-Match": "1",
                "Content-Type": XLSX_MEDIA_TYPE,
            },
            content=b"bounded workbook",
        )

    assert [
        response.status_code for response in (created, staged, fetched, validated)
    ] == [
        201,
        200,
        200,
        200,
    ]
    assert [response.status_code for response in (applied, archived, imported)] == [
        200,
        200,
        200,
    ]
    assert [name for name, _value in service.calls] == [
        "create",
        "stage",
        "get",
        "validate",
        "apply",
        "archive",
        "import",
    ]
    assert imported.json()["validation"]["status"] == "validated"


def test_xlsx_route_rejects_non_xlsx_content_before_calling_service() -> None:
    service = RecordingMetadataChangeSetService()
    app = create_app(
        identity_provider=_identity_provider(),
        metadata_change_set_service=service,
    )

    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/tenants/7/metadata-change-sets/{_CHANGE_SET_ID}/imports/xlsx",
            headers={
                "Idempotency-Key": str(_IDEMPOTENCY_KEY),
                "If-Match": "1",
                "Content-Type": "application/octet-stream",
            },
            content=b"not an xlsx",
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert service.calls == []


class StageTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[LiteralString, tuple[Any, ...]]] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "mcp.stage_metadata_change_set" in query:
            staged = parameters[6]
            assert isinstance(staged, Jsonb)
            staged_value: object = staged.obj
            assert isinstance(staged_value, dict)
            staged_document = cast(dict[object, object], staged_value)
            dataset_counts: dict[str, int] = {}
            for dataset, records in staged_document.items():
                if isinstance(dataset, str) and isinstance(records, list):
                    dataset_counts[dataset] = len(cast(list[object], records))
            return {
                "staged": True,
                "denial_code": None,
                "draft_revision": 2,
                "dataset_counts": dataset_counts,
                "expires_time": _NOW,
            }
        raise AssertionError(query)

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class StageDatabase:
    def __init__(self) -> None:
        self.transaction = StageTransaction()
        self.entered = 0

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[StageTransaction]:
        self.entered += 1
        yield self.transaction


def _principal() -> RequestPrincipal:
    return _identity_provider().authenticate({})


def _copy_group_record() -> dict[str, object]:
    return {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "copy_group_name": "CRM daily",
        "copy_group_description": "Daily customer load",
        "is_member_group_required": False,
        "is_active": True,
    }


@pytest.mark.asyncio
async def test_stage_service_uses_canonical_complete_dataset_function() -> None:
    database = StageDatabase()
    service = DatabaseMetadataChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )

    result = await service.stage(
        _principal(),
        tenant_id=7,
        change_set_id=_CHANGE_SET_ID,
        command=StageMetadataChangeSetRequest(
            expected_draft_revision=1,
            changes=[
                StageMetadataDatasetRequest(
                    dataset="copy_group",
                    records=[_copy_group_record()],
                )
            ],
        ),
        idempotency_key=_IDEMPOTENCY_KEY,
    )

    assert result.draft_revision == 2
    assert database.entered == 1
    query, parameters = database.transaction.calls[0]
    assert "mcp.stage_metadata_change_set" in query
    assert parameters[:6] == (
        UUID("11111111-1111-1111-1111-111111111111"),
        UUID("22222222-2222-2222-2222-222222222222"),
        "user",
        7,
        _CHANGE_SET_ID,
        1,
    )
    assert isinstance(parameters[6], Jsonb)
    assert parameters[6].obj == {"copy_group": [_copy_group_record()]}
    assert parameters[7] == _IDEMPOTENCY_KEY


@pytest.mark.asyncio
async def test_stage_service_accepts_iso_date_fields_from_a_json_request() -> None:
    database = StageDatabase()
    service = DatabaseMetadataChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )
    record: dict[str, object] = {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "copy_group_name": "CRM daily",
        "member_group_name": None,
        "copy_group_control_initial_load_date": "2026-08-24",
        "copy_group_control_last_run_time": "2026-08-24T10:42:00Z",
        "copy_group_control_last_run_value": "1048",
    }

    result = await service.stage(
        _principal(),
        tenant_id=7,
        change_set_id=_CHANGE_SET_ID,
        command=StageMetadataChangeSetRequest(
            expected_draft_revision=1,
            changes=[
                StageMetadataDatasetRequest(
                    dataset="copy_group_control",
                    records=[record],
                )
            ],
        ),
        idempotency_key=_IDEMPOTENCY_KEY,
    )

    assert result.datasets == (
        MetadataChangeSetDatasetCount(dataset="copy_group_control", record_count=1),
    )
    staged = database.transaction.calls[0][1][6]
    assert isinstance(staged, Jsonb)
    assert staged.obj == {"copy_group_control": [record]}


def _copy_group_workbook() -> bytes:
    definition = DATASETS_BY_NAME["copy_group"]
    return build_metadata_workbook(
        tenant_id=7,
        sheets=(
            MetadataWorkbookSheet(
                code="copy_group",
                name=definition.label,
                columns=tuple(definition.row_model.model_fields),
                canonical_key=definition.canonical_key,
                row_schema=definition.row_model.model_json_schema(),
                rows=(_copy_group_record(),),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_xlsx_import_parses_before_write_stages_then_validates_without_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = StageDatabase()
    service = DatabaseMetadataChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )

    async def validated(
        transaction: WriteTransaction,
        *,
        tenant_id: int,
        metadata_change_set_id: UUID,
        expected_draft_revision: int,
        principal: RequestPrincipal,
        authorizer: AuthorizationService,
    ) -> tuple[MetadataChangeSetValidation, Mapping[str, Any]]:
        assert transaction is database.transaction
        assert (tenant_id, metadata_change_set_id, expected_draft_revision) == (
            7,
            _CHANGE_SET_ID,
            2,
        )
        assert principal.actor_kind is ActorKind.HUMAN
        assert isinstance(authorizer, AuthorizationService)
        return (
            MetadataChangeSetValidation(
                valid=True,
                phase="complete",
                candidate_digest="d" * 64,
                staged_record_count=1,
                issues=(),
                action_review=(),
            ),
            {
                "metadata_change_set_status": "validated",
                "draft_revision": 2,
                "candidate_digest": "d" * 64,
                "validated_time": _NOW,
                "expires_time": _NOW,
            },
        )

    monkeypatch.setattr(canonical_metadata, "_validate_and_persist", validated)

    result = await service.import_workbook(
        _principal(),
        tenant_id=7,
        change_set_id=_CHANGE_SET_ID,
        expected_draft_revision=1,
        content=_copy_group_workbook(),
        idempotency_key=_IDEMPOTENCY_KEY,
    )

    assert result.imported_sheet_count == 1
    assert result.validation.valid is True
    assert database.entered == 1
    assert len(database.transaction.calls) == 1
    assert "mcp.stage_metadata_change_set" in database.transaction.calls[0][0]
    assert all(
        "mcp.apply_metadata_change_set" not in query
        for query, _parameters in database.transaction.calls
    )


@pytest.mark.asyncio
async def test_invalid_xlsx_fails_before_any_database_transaction() -> None:
    database = StageDatabase()
    service = DatabaseMetadataChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )

    with pytest.raises(InvalidRequestError, match="XLSX package"):
        await service.import_workbook(
            _principal(),
            tenant_id=7,
            change_set_id=_CHANGE_SET_ID,
            expected_draft_revision=1,
            content=b"not a workbook",
            idempotency_key=_IDEMPOTENCY_KEY,
        )

    assert database.entered == 0
