"""Plan permanent project deletion, including owned source-mapping rows."""

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import LiteralString, cast

from gds_etl_workbench.application.project_snapshot import ProjectReviewSnapshot
from gds_etl_workbench.domain.snapshots.project import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

from .review import ProjectLayer, ProjectReviewDataset, plan_project_record_review, review_lifecycle


@dataclass(frozen=True, slots=True)
class DeletionItem:
    dataset: str
    record_id: int
    label: str
    selected: bool
    is_locked: bool
    status: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProjectDeletionPlan:
    items: tuple[DeletionItem, ...]
    records: dict[str, list[int]]
    digest: str


# Fixed SQL identifiers only. Source mappings are not standalone authored datasets,
# but their numeric identities and locks must participate in deletion confirmation.
_SUPPORT_PARENTS = tuple(
    (f"{layer}_{kind}", tuple(f"{layer}_{parent}" for parent in parents))
    for layer in ("logical", "dimensional")
    for kind, parents in (
        ("entity_source_mapping", ("entity",)),
        ("attribute_source_mapping", ("entity", "attribute")),
    )
)


async def plan_project_deletion(
    transaction: ReadTransaction,
    review: ProjectReviewSnapshot,
    *,
    dataset: ProjectReviewDataset,
    record_ids: list[int],
    layer: ProjectLayer | None,
) -> ProjectDeletionPlan:
    decisions = plan_project_record_review(
        review, dataset=dataset, record_ids=list(record_ids), action="delete", layer=layer
    )
    records: dict[str, list[int]] = defaultdict(list)
    items: list[DeletionItem] = []
    for decision in decisions:
        if not isinstance(decision.record_id, int):
            raise ValueError("Context records do not support permanent deletion")
        records[decision.dataset].append(decision.record_id)
        locked, status = review_lifecycle(decision.original, decision.dataset)
        items.append(
            DeletionItem(
                dataset=decision.dataset,
                record_id=decision.record_id,
                label=" · ".join(
                    str(getattr(decision.original, field))
                    for field in DATASETS_BY_NAME[decision.dataset].canonical_key
                ),
                selected=decision.selected,
                is_locked=locked,
                status=status,
                reason="Selected for deletion." if decision.selected else "Dependent record.",
            )
        )
    support_revisions: list[str] = []
    # Query in a stable order so the preview digest does not depend on row storage order.
    for table, parents in _SUPPORT_PARENTS:
        if not any(records.get(parent) for parent in parents):
            continue
        where = " OR ".join(f"target.{parent}_id = ANY(%s)" for parent in parents)
        query = cast(
            LiteralString,
            f"""
            SELECT '{table}' AS dataset, target.{table}_id AS record_id,
                   target.{table}_is_locked AS is_locked,
                   CASE WHEN target.{table}_is_active THEN 'active' ELSE 'inactive' END
                       AS status,
                   target.updated_time::TEXT AS revision
              FROM workflow.{table} AS target
             WHERE target.project_id = %s AND ({where})
        """,
        )
        rows = await transaction.fetch_all(
            query, (review.snapshot.project_id, *(records.get(parent, []) for parent in parents))
        )
        for row in sorted(rows, key=lambda row: row["record_id"]):
            records[row["dataset"]].append(row["record_id"])
            items.append(
                DeletionItem(
                    dataset=row["dataset"],
                    record_id=row["record_id"],
                    label=f"{row['dataset'].replace('_', ' ')} · {row['record_id']}",
                    selected=False,
                    is_locked=row["is_locked"],
                    status=row["status"],
                    reason="Owned source mapping.",
                )
            )
            support_revisions.append(row["revision"])
    digest = hashlib.sha256(
        json.dumps(
            {
                "project_id": review.snapshot.project_id,
                "project_revision": review.snapshot.project_revision,
                "dataset": dataset,
                "record_ids": sorted(record_ids),
                "layer": layer,
                "items": [asdict(item) for item in items],
                "support_revisions": support_revisions,
                "originals": [decision.original.model_dump(mode="json") for decision in decisions],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return ProjectDeletionPlan(items=tuple(items), records=dict(records), digest=digest)
