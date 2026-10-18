"""Replay MCP server for Atlas agent evaluations.

The server is the real `create_mcp_server` composition, so agents see the exact tool
names, descriptions, input schemas and server instructions. Like Copilot's own
connection, the evaluated agent is not the Stage Runner: the real gate hides and
refuses Stage upload tools. A middleware placed before the audit boundary answers
`tools/call` from a recorded world (`fixtures/world.json`) plus small in-memory state
for locks and drafts, and logs every call. Contract-only `describe_*` tools run their
real handlers. No database, Databricks or Azure access.

    python -m tests.atlas.eval.fake_mcp --world fixtures/world.json \
        --snapshot-dir <dir> --log <calls.jsonl>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.adapters.mcp.stage_runner_gate import STAGE_UPLOAD_TOOLS, StageRunnerGate
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.change_sets.contracts import (
    canonical_records_sha256,
    stage_fingerprint_sha256,
)
from gds_etl_workbench.application.change_sets.metadata import (
    CHANGE_SET_DATASETS as METADATA_DATASETS,
)
from gds_etl_workbench.application.change_sets.metadata import (
    CreateMetadataChangeSetResult,
    GetMetadataChangeSetFingerprintResult,
    MetadataChangeSetDatasetFingerprint,
)
from gds_etl_workbench.application.change_sets.project import (
    CreateProjectChangeSetResult,
    GetProjectChangeSetFingerprintResult,
    ProjectChangeSetDatasetFingerprint,
)
from gds_etl_workbench.application.profiling.service import ProfilingStatus
from gds_etl_workbench.configuration import AuthMode, RuntimeSettings
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.domain.snapshots.project import CHANGE_SET_DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import Database
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    CreateMetadataSnapshotResult,
)
from gds_etl_workbench.tools.snapshots.project.get_project_snapshot import (
    CreateProjectSnapshotResult,
)
from gds_etl_workbench.tools.tenants.tenant_locks import (
    AcquireTenantLockResult,
    CheckTenantLockResult,
    ReleaseTenantLockResult,
    RenewTenantLockResult,
    TenantLockDetails,
)
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.lowlevel.server import lifespan as default_lifespan
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent

DELEGATED_TOOLS = frozenset({"describe_metadata_dataset", "describe_project_dataset"})
# Argument names that only page or version a read; replay ignores them when matching.
IGNORED_ARGUMENTS = frozenset({"schema_version", "page_size", "detail"})


class ToolFailureError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class ReplayDatabase:
    """Enough of `Database` for server composition; every query reports unavailable."""

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def expire_tenant_locks(self) -> int:
        return 0

    async def append_tool_call_log(self, _record: object) -> None:
        return None

    def read_transaction(self) -> Any:
        raise DependencyUnavailableError()

    def write_transaction(self) -> Any:
        raise DependencyUnavailableError()


class EvalIdentityProvider(IdentityProvider):
    def __init__(self) -> None:
        super().__init__(AuthMode.DEV)

    def request_principal(self, request: object | None) -> RequestPrincipal:
        del request
        return RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
            entra_object_id=UUID("33333333-3333-4333-8333-333333333333"),
        )


@dataclass
class Draft:
    area: str
    scope_id: int
    change_set_id: UUID = field(default_factory=uuid4)
    status: str = "active"
    draft_revision: int = 1


@dataclass
class EvalWorld:
    """Recorded responses plus the small amount of state a session mutates."""

    world: dict[str, Any]
    snapshot_dir: Path
    log_path: Path
    lock_owned: bool = False
    drafts: dict[tuple[str, int], Draft] = field(default_factory=lambda: {})
    profiling_runs: dict[int, dict[str, Any]] = field(default_factory=lambda: {})
    sequence: int = 0

    def log(self, tool: str, arguments: Mapping[str, Any], outcome: str, code: str | None) -> None:
        self.sequence += 1
        entry = {
            "seq": self.sequence,
            "tool": tool,
            "arguments": dict(arguments),
            "outcome": outcome,
            "error_code": code,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    def respond(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_tool_{tool}", None)
        if handler is not None:
            return cast(dict[str, Any], handler(arguments))
        return self._replay(tool, arguments)

    def _replay(self, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        requested = {key: value for key, value in arguments.items() if key not in IGNORED_ARGUMENTS}
        for response in self.world["responses"]:
            if response["tool"] != tool:
                continue
            recorded = {
                key: value
                for key, value in response["arguments"].items()
                if key not in IGNORED_ARGUMENTS
            }
            if recorded == requested:
                return cast(dict[str, Any], response["result"])
        raise ToolFailureError(
            "evaluation_world_missing",
            f"No recorded {tool} response matches these arguments in this evaluation world.",
        )

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _snapshot(self, kind: str) -> dict[str, Any]:
        snapshot = self.world["snapshots"][kind]
        source = Path(__file__).resolve().parent / "fixtures" / snapshot["file"]
        target = self.snapshot_dir / snapshot["file"]
        if not target.exists():
            shutil.copyfile(source, target)
        common: dict[str, Any] = {
            "snapshot_id": UUID(snapshot["snapshot_id"]),
            "download_url": target.resolve().as_uri(),
            "download_url_expires_at": self._now() + timedelta(minutes=15),
            "size_bytes": snapshot["size_bytes"],
            "sha256": snapshot["sha256"],
        }
        if kind == "metadata":
            return CreateMetadataSnapshotResult(
                tenant_id=self.world["tenant"]["tenant_id"], **common
            ).model_dump(mode="json")
        return CreateProjectSnapshotResult(
            project_id=self.world["project"]["project_id"],
            project_revision=self.world["project"]["project_revision"],
            **common,
        ).model_dump(mode="json")

    def _tool_create_metadata_snapshot(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._snapshot("metadata")

    def _tool_create_project_snapshot(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._snapshot("project")

    def _lock(self) -> TenantLockDetails:
        return TenantLockDetails(
            owner_display_name="Evaluation User",
            owned_by_current_principal=True,
            purpose="Atlas evaluation",
            acquired_at=self._now(),
            expires_at=self._now() + timedelta(hours=1),
        )

    def _tool_check_tenant_lock(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return CheckTenantLockResult(
            tenant_id=int(arguments["tenant_id"]),
            is_locked=self.lock_owned,
            lock=self._lock() if self.lock_owned else None,
        ).model_dump(mode="json")

    def _tool_acquire_tenant_lock(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if self.lock_owned:
            raise ToolFailureError("tenant_locked", "Tenant is locked by Evaluation User.")
        self.lock_owned = True
        return AcquireTenantLockResult(
            tenant_id=int(arguments["tenant_id"]), lock=self._lock()
        ).model_dump(mode="json")

    def _tool_renew_tenant_lock(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not self.lock_owned:
            raise ToolFailureError("tenant_lock_required", "An owned Tenant Lock is required.")
        return RenewTenantLockResult(
            tenant_id=int(arguments["tenant_id"]), lock=self._lock()
        ).model_dump(mode="json")

    def _tool_release_tenant_lock(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self.lock_owned = False
        return ReleaseTenantLockResult(tenant_id=int(arguments["tenant_id"])).model_dump(
            mode="json"
        )

    def _tool_override_tenant_lock(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        raise ToolFailureError("authorization_denied", "Lock override is not permitted here.")

    def _draft(self, area: str, arguments: Mapping[str, Any]) -> tuple[Draft, bool]:
        scope_id = int(arguments.get("tenant_id" if area == "metadata" else "project_id", 0))
        if not self.lock_owned:
            raise ToolFailureError("tenant_lock_required", "An owned Tenant Lock is required.")
        created = (area, scope_id) not in self.drafts
        draft = self.drafts.setdefault((area, scope_id), Draft(area=area, scope_id=scope_id))
        return draft, created

    def _tool_create_metadata_change_set(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        draft, created = self._draft("metadata", arguments)
        return CreateMetadataChangeSetResult(
            tenant_id=draft.scope_id,
            metadata_change_set_id=draft.change_set_id,
            created=created,
            status="active",
            draft_revision=draft.draft_revision,
            created_at=self._now(),
            expires_at=self._now() + timedelta(hours=4),
        ).model_dump(mode="json")

    def _tool_create_project_change_set(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        draft, created = self._draft("project", arguments)
        return CreateProjectChangeSetResult(
            project_id=draft.scope_id,
            project_change_set_id=draft.change_set_id,
            created=created,
            status="active",
            draft_revision=draft.draft_revision,
            created_at=self._now(),
            expires_at=self._now() + timedelta(hours=4),
        ).model_dump(mode="json")

    def _tool_get_metadata_change_set_fingerprint(
        self, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        draft, _ = self._draft("metadata", arguments)
        datasets = [
            MetadataChangeSetDatasetFingerprint(
                dataset=name, record_count=0, sha256=canonical_records_sha256([])
            )
            for name in METADATA_DATASETS
        ]
        return GetMetadataChangeSetFingerprintResult(
            tenant_id=draft.scope_id,
            metadata_change_set_id=draft.change_set_id,
            status="active",
            draft_revision=draft.draft_revision,
            dataset_count=len(datasets),
            record_count=0,
            datasets=datasets,
            fingerprint=stage_fingerprint_sha256(
                "metadata", [item.model_dump(mode="json") for item in datasets]
            ),
            expires_at=self._now() + timedelta(hours=4),
        ).model_dump(mode="json")

    def _tool_get_project_change_set_fingerprint(
        self, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        draft, _ = self._draft("project", arguments)
        datasets = tuple(
            ProjectChangeSetDatasetFingerprint(
                dataset=name,  # pyright: ignore[reportArgumentType]
                record_count=0,
                sha256=canonical_records_sha256([]),
            )
            for name in sorted(CHANGE_SET_DATASETS_BY_NAME)
        )
        return GetProjectChangeSetFingerprintResult(
            project_id=draft.scope_id,
            project_change_set_id=draft.change_set_id,
            status="active",
            draft_revision=draft.draft_revision,
            dataset_count=len(datasets),
            record_count=0,
            datasets=datasets,
            fingerprint=stage_fingerprint_sha256(
                "project", [item.model_dump(mode="json") for item in datasets]
            ),
            expires_at=self._now() + timedelta(hours=4),
        ).model_dump(mode="json")

    def _unstaged(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        raise ToolFailureError(
            "evaluation_requires_stage_runner",
            "This evaluation has no Stage Runner, so no draft content was staged.",
        )

    _tool_get_metadata_change_set = _unstaged
    _tool_get_project_change_set = _unstaged
    _tool_validate_metadata_change_set = _unstaged
    _tool_validate_project_change_set = _unstaged
    _tool_apply_metadata_change_set = _unstaged
    _tool_apply_project_change_set = _unstaged
    _tool_archive_metadata_change_set = _unstaged
    _tool_archive_project_change_set = _unstaged

    def _tool_start_profiling_run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        selected = list(cast(list[int], arguments.get("selected_object_ids", [])))
        if not selected:
            raise ToolFailureError("invalid_request", "Select at least one Object.")
        run_id = 9000 + len(self.profiling_runs) + 1
        status = ProfilingStatus(
            run_id=run_id,
            project_id=int(arguments.get("project_id", self.world["project"]["project_id"])),
            project_revision=self.world["project"]["project_revision"],
            state="completed",
            selected_object_count=len(selected),
            completed_object_count=len(selected),
            saved_profile_count=len(selected),
            failure_code=None,
            failure_message=None,
            started_at=self._now().isoformat(),
            completed_at=self._now().isoformat(),
        ).model_dump(mode="json")
        self.profiling_runs[run_id] = status
        return status

    def _tool_get_profiling_run_status(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        run = self.profiling_runs.get(int(arguments.get("run_id", 0)))
        if run is None:
            raise ToolFailureError("profiling_run_not_found", "Profiling run was not found.")
        return run

    def _tool_cancel_profiling_run(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return self._tool_get_profiling_run_status(arguments)

    def _tool_execute_databricks_sql(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        raise ToolFailureError(
            "databricks_connection_failed",
            "Databricks is unavailable in this evaluation; continue without measurements.",
        )


class ReplayMiddleware:
    def __init__(self, world: EvalWorld) -> None:
        self._world = world

    async def __call__(
        self, ctx: ServerRequestContext[Any, Any], call_next: CallNext
    ) -> HandlerResult:
        if ctx.method != "tools/call" or ctx.params is None:
            return await call_next(ctx)
        tool = str(ctx.params.get("name"))
        raw_arguments = ctx.params.get("arguments")
        arguments = (
            cast(Mapping[str, Any], raw_arguments) if isinstance(raw_arguments, Mapping) else {}
        )
        if tool in DELEGATED_TOOLS:
            self._world.log(tool, arguments, "delegated", None)
            return await call_next(ctx)
        if tool in STAGE_UPLOAD_TOOLS:
            # The production gate answers; the log still records the attempt.
            self._world.log(tool, arguments, "error", "stage_runner_required")
            return await call_next(ctx)
        try:
            result = self._world.respond(tool, arguments)
        except ToolFailureError as failure:
            self._world.log(tool, arguments, "error", failure.code)
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error executing tool {tool}: {failure}")],
                is_error=True,
            )
        self._world.log(tool, arguments, "replayed", None)
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
            structured_content=result,
            is_error=False,
        )


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://unused@invalid.example.invalid/unused",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_LOCAL_PRINCIPAL_OBJECT_ID": "33333333-3333-3333-3333-333333333333",
            "GDS_MCP_PUBLIC_URL": "https://testserver/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": "https://snapshot.blob.core.windows.net",
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


def create_replay_server(world: EvalWorld) -> MCPServer[None]:
    server = create_mcp_server(
        _settings(), cast(Database, ReplayDatabase()), EvalIdentityProvider()
    )
    middleware = server.middleware
    # Local settings treat in-memory sessions as the Stage Runner; evaluated agents are not.
    gate_index = next(
        index for index, item in enumerate(middleware) if isinstance(item, StageRunnerGate)
    )
    middleware[gate_index] = StageRunnerGate(allow_in_memory=False)
    audit_index = next(
        index for index, item in enumerate(middleware) if isinstance(item, ToolCallAuditMiddleware)
    )
    middleware.insert(audit_index, ReplayMiddleware(world))
    # The production lifespan starts lock-expiry and Profiling workers against PostgreSQL.
    server._lowlevel_server.lifespan = default_lifespan  # pyright: ignore[reportPrivateUsage]
    return server


def load_world(world_path: Path, snapshot_dir: Path, log_path: Path) -> EvalWorld:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.touch()
    return EvalWorld(
        world=json.loads(world_path.read_text(encoding="utf-8")),
        snapshot_dir=snapshot_dir,
        log_path=log_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_world = Path(__file__).resolve().parent / "fixtures/world.json"
    parser.add_argument("--world", type=Path, default=default_world)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    arguments = parser.parse_args()
    world = load_world(arguments.world, arguments.snapshot_dir, arguments.log)
    asyncio.run(create_replay_server(world).run_stdio_async())


if __name__ == "__main__":
    main()
