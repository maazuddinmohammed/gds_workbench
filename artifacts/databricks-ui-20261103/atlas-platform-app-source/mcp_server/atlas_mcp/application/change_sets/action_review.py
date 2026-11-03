"""Shared Change Set action-review vocabulary and classification."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

type ChangeAction = Literal["insert", "update", "deactivate", "reactivate", "no_change"]
type ActiveState = Callable[[Mapping[str, object]], bool | None]


@dataclass(frozen=True, slots=True)
class ActionReviewKey:
    action: ChangeAction
    natural_key: dict[str, object]

    def as_document(self) -> dict[str, object]:
        return {"action": self.action, "natural_key": self.natural_key}


@dataclass(frozen=True, slots=True)
class DatasetActionReview:
    dataset: str
    insert_count: int
    update_count: int
    deactivate_count: int
    reactivate_count: int
    no_change_count: int
    keys: tuple[ActionReviewKey, ...]
    keys_truncated: bool

    def as_document(self) -> dict[str, object]:
        return {
            "dataset": self.dataset,
            "insert_count": self.insert_count,
            "update_count": self.update_count,
            "deactivate_count": self.deactivate_count,
            "reactivate_count": self.reactivate_count,
            "no_change_count": self.no_change_count,
            "keys": [key.as_document() for key in self.keys],
            "keys_truncated": self.keys_truncated,
        }


def classify_record_action(
    existing: Mapping[str, object] | None,
    staged: Mapping[str, object],
    *,
    active_state: ActiveState,
) -> ChangeAction:
    if existing is None:
        return "insert"
    if existing == staged:
        return "no_change"
    current_active = active_state(existing)
    staged_active = active_state(staged)
    if current_active is True and staged_active is False:
        return "deactivate"
    if current_active is False and staged_active is True:
        return "reactivate"
    return "update"
