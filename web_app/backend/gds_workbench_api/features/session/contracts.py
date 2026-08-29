"""Server-derived Principal Session HTTP contracts."""

from gds_etl_workbench.domain.authorization import ActorKind
from pydantic import BaseModel, ConfigDict, Field


class SessionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str
    email: str | None = Field(default=None, min_length=4, max_length=320)
    actor_kind: ActorKind
    is_super_admin: bool
    last_tenant_id: int | None
