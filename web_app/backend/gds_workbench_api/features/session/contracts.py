"""Server-derived Principal Session HTTP contracts."""

from gds_etl_workbench.domain.authorization import ActorKind
from pydantic import BaseModel, ConfigDict


class SessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str
    actor_kind: ActorKind
    is_super_admin: bool
    last_tenant_id: int | None
