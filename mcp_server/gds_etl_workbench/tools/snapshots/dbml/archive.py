"""Deterministic DBML Snapshot ZIP generation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from uuid import UUID

from gds_etl_workbench.domain.snapshots.model import ModelSnapshot
from gds_etl_workbench.tools.snapshots.archive import (
    SnapshotArchive,
    SnapshotContractError,
    SnapshotMember,
    utc_timestamp,
    write_snapshot_archive,
)

from .renderer import DbmlDocument, DbmlModelType

MAX_DBML_ARCHIVE_BYTES = 20 * 1024 * 1024


def build_dbml_snapshot_archive(
    output: Path,
    *,
    snapshot_id: UUID,
    snapshot: ModelSnapshot,
    model_type: DbmlModelType,
    include_submodels: bool,
    documents: Sequence[DbmlDocument],
    created_time: datetime,
    available_until: datetime,
    max_archive_bytes: int,
) -> SnapshotArchive:
    """Create and verify one bounded DBML Snapshot ZIP."""
    if snapshot_id.version != 4:
        raise SnapshotContractError("snapshot_id must be a UUID version 4")
    generated_at = utc_timestamp("created_time", created_time)
    available_at = utc_timestamp("available_until", available_until)
    if available_until <= created_time:
        raise SnapshotContractError("available_until must be after created_time")
    if not documents:
        raise SnapshotContractError("DBML Snapshot must contain at least one DBML file")
    expected_layers = (
        {"conceptual", "logical", "dimensional"} if model_type == "full" else {model_type}
    )
    actual_layers = {document.layer for document in documents}
    if actual_layers != expected_layers:
        raise SnapshotContractError("DBML files do not match the selected model type")
    if not include_submodels and any(document.view != "complete" for document in documents):
        raise SnapshotContractError("DBML files contain an unrequested submodel view")

    ordered_documents = tuple(sorted(documents, key=lambda document: document.path))

    members = tuple(
        SnapshotMember(path=f"files/{document.path}", content=document.content)
        for document in ordered_documents
    )
    table_count = sum(document.table_count for document in ordered_documents)
    relationship_count = sum(document.relationship_count for document in ordered_documents)
    files = tuple(
        {
            "path": member.path,
            "layer": document.layer,
            "view": document.view,
            "submodel_name": document.submodel_name,
            "table_count": document.table_count,
            "relationship_count": document.relationship_count,
            "size_bytes": len(document.content),
            "sha256": hashlib.sha256(document.content).hexdigest(),
        }
        for member, document in zip(members, ordered_documents, strict=True)
    )

    def build_manifest(
        member_records: tuple[dict[str, object], ...],
        expanded_bytes: int,
    ) -> Mapping[str, object]:
        return {
            "schema_version": "2.0",
            "snapshot_kind": "dbml",
            "snapshot_id": str(snapshot_id),
            "database_ids_included": False,
            "model_id": snapshot.model_id,
            "model_name": snapshot.model_name,
            "model_revision": snapshot.model_revision,
            "model_type": model_type,
            "include_submodels": include_submodels,
            "generated_at": generated_at,
            "available_until": available_at,
            "counts": {
                "dbml_file_count": len(ordered_documents),
                "table_count": table_count,
                "relationship_count": relationship_count,
                "file_count": len(members) + 1,
                "expanded_bytes": expanded_bytes,
            },
            "files": files,
            "members": member_records,
        }

    return write_snapshot_archive(
        output,
        archive_root="model-dbml",
        members=members,
        row_count=table_count,
        max_archive_bytes=min(max_archive_bytes, MAX_DBML_ARCHIVE_BYTES),
        build_manifest=build_manifest,
    )
