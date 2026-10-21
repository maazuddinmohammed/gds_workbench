"""Bounded process observations and installed-source fingerprints; no run data.

This module preserves Python 3.10 standard-library syntax so the standalone
artifact builder can reuse it. Fingerprints describe disk bytes, not loaded bytecode.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from time import monotonic
from typing import Literal

SOURCE_FINGERPRINT_VERSION = 1

WorkerBoundary = Literal[
    "database_open", "database_readiness", "claim", "usage_initialization", "executor", "heartbeat"
]
WorkflowFailureCategory = Literal[
    "unexpected",
    "invalid_contract",
    "database_schema",
    "database_access",
    "database_contention",
    "database_connectivity",
    "dependency_unavailable",
    "workflow_guard",
]
WorkerState = Literal[
    "not_attached", "starting", "ready", "polling", "executing", "waiting", "stopped"
]
ReadinessCode = Literal[
    "ready",
    "database_version_invalid",
    "database_schema_unavailable",
    "database_role_invalid",
    "database_unavailable",
]
PollResult = Literal["idle", "completed", "execution_failed", "claim_lost", "poll_failed"]


def source_tree_sha256(root: Path) -> str:
    """Hash sorted relative names, NUL separators and raw SHA-256 file digests."""
    if not root.is_dir() or root.is_symlink():
        raise ValueError("runtime source root is unavailable")
    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.suffix in {".py", ".json"} and "__pycache__" not in path.relative_to(root).parts
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    if not paths:
        raise ValueError("runtime source files are unavailable")
    digest = hashlib.sha256()
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("runtime source file is unavailable")
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class InstalledSourceSnapshot:
    fingerprint_version: Literal[1] = SOURCE_FINGERPRINT_VERSION
    api_sha256: str | None = None
    shared_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerFaultSnapshot:
    category: WorkflowFailureCategory
    boundary: WorkerBoundary
    age_seconds: int


@dataclass(frozen=True, slots=True)
class WorkerSnapshot:
    state: WorkerState
    started: bool
    readiness_code: ReadinessCode | None
    boundary: WorkerBoundary | None
    last_poll_result: PollResult | None
    last_poll_age_seconds: int | None
    last_fault: WorkerFaultSnapshot | None


@dataclass(frozen=True, slots=True)
class RuntimeDiagnosticsSnapshot:
    installed_source: InstalledSourceSnapshot
    worker: WorkerSnapshot


class RuntimeDiagnostics:
    """One event-loop-owned observation shared by the embedded API and worker."""

    def __init__(
        self,
        installed_source: InstalledSourceSnapshot | None = None,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._installed_source = installed_source or InstalledSourceSnapshot()
        self._clock = clock
        self.state: WorkerState = "not_attached"
        self.started = False
        self.readiness_code: ReadinessCode | None = None
        self.boundary: WorkerBoundary | None = None
        self._last_poll: tuple[PollResult, float] | None = None
        self._last_fault: tuple[WorkflowFailureCategory, WorkerBoundary, float] | None = None

    @classmethod
    def capture_installed_sources(cls) -> RuntimeDiagnostics:
        digests: list[str | None] = []
        for package in ("gds_workbench_api", "gds_etl_workbench"):
            try:
                spec = find_spec(package)
                roots = None if spec is None else spec.submodule_search_locations
                if roots is None or len(roots) != 1:
                    raise ValueError("runtime package source is unavailable")
                digests.append(source_tree_sha256(Path(roots[0])))
            except (ImportError, OSError, ValueError):  # fmt: skip
                digests.append(None)
        return cls(InstalledSourceSnapshot(api_sha256=digests[0], shared_sha256=digests[1]))

    def enter(self, boundary: WorkerBoundary) -> None:
        self.boundary = boundary
        self.state = (
            "starting"
            if boundary in {"database_open", "database_readiness"}
            else "polling"
            if boundary == "claim"
            else "executing"
        )

    def record_poll(self, result: PollResult) -> None:
        self._last_poll = (result, self._clock())
        self.boundary = None
        self.state = "ready" if result == "completed" else "waiting"

    def record_fault(self, category: WorkflowFailureCategory, boundary: WorkerBoundary) -> None:
        # Accept only categories, never an exception object, message or Run identity.
        self._last_fault = (category, boundary, self._clock())

    def snapshot(self) -> RuntimeDiagnosticsSnapshot:
        now = self._clock()
        poll = self._last_poll
        fault = self._last_fault
        return RuntimeDiagnosticsSnapshot(
            installed_source=self._installed_source,
            worker=WorkerSnapshot(
                state=self.state,
                started=self.started,
                readiness_code=self.readiness_code,
                boundary=self.boundary,
                last_poll_result=None if poll is None else poll[0],
                last_poll_age_seconds=(
                    None if poll is None else min(2_147_483_647, max(0, int(now - poll[1])))
                ),
                last_fault=(
                    None
                    if fault is None
                    else WorkerFaultSnapshot(
                        category=fault[0],
                        boundary=fault[1],
                        age_seconds=min(2_147_483_647, max(0, int(now - fault[2]))),
                    )
                ),
            ),
        )
