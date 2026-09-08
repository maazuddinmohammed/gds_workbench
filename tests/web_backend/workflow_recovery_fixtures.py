"""Shared recording handoff for executor recovery tests; no database or provider I/O."""

from dataclasses import dataclass, field
from typing import Any

from gds_etl_workbench.domain.authorization import RequestPrincipal


@dataclass
class RetainingHandoff:
    retained: list[dict[str, Any]] = field(
        default_factory=lambda: list[dict[str, Any]](), repr=False
    )
    retention_error: Exception | None = field(default=None, repr=False)

    async def retain_failed_candidate(
        self, principal: RequestPrincipal, **parameters: Any
    ) -> object:
        del principal
        if self.retention_error is not None:
            raise self.retention_error
        self.retained.append(parameters)
        return None
