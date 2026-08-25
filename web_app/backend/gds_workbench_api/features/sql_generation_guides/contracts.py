"""Public SQL Generation Guide HTTP contracts."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

type SqlGenerationGuideVersionStatus = Literal["draft", "published", "retired"]


class SqlGenerationGuideContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SqlGenerationGuideSummary(SqlGenerationGuideContract):
    sql_generation_guide_id: int = Field(gt=0)
    sql_generation_guide_code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]{0,99}$",
    )
    sql_generation_guide_name: str = Field(min_length=1, max_length=200)
    sql_generation_guide_description: str | None = Field(
        default=None,
        max_length=2000,
    )
    is_default: bool
    is_active: bool
    latest_version_id: int | None = Field(default=None, gt=0)
    latest_version_number: int | None = Field(default=None, gt=0)
    latest_version_status: SqlGenerationGuideVersionStatus | None = None
    latest_version_digest: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    latest_version_updated_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_latest_version(self) -> Self:
        latest = (
            self.latest_version_id,
            self.latest_version_number,
            self.latest_version_status,
            self.latest_version_digest,
            self.latest_version_updated_at,
        )
        if any(value is None for value in latest) and not all(value is None for value in latest):
            raise ValueError("latest SQL Generation Guide version is incomplete")
        return self


class SqlGenerationGuidePage(SqlGenerationGuideContract):
    tenant_id: int = Field(gt=0)
    items: tuple[SqlGenerationGuideSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class SqlGenerationGuideVersionDetail(SqlGenerationGuideContract):
    sql_generation_guide_version_id: int = Field(gt=0)
    sql_generation_guide_id: int = Field(gt=0)
    sql_generation_guide_version_number: int = Field(gt=0)
    sql_generation_guide_content: str = Field(
        min_length=1,
        max_length=262144,
        repr=False,
    )
    sql_generation_guide_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    sql_generation_guide_version_status: SqlGenerationGuideVersionStatus
    published_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SqlGenerationGuideDetail(SqlGenerationGuideContract):
    tenant_id: int = Field(gt=0)
    guide: SqlGenerationGuideSummary
    versions: tuple[SqlGenerationGuideVersionDetail, ...] = Field(max_length=200)
    history_next_cursor: str | None = Field(default=None, max_length=2048)


class SqlGenerationGuideRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SaveSqlGenerationGuideDraftRequest(SqlGenerationGuideRequest):
    expected_sql_generation_guide_version_id: int | None = Field(default=None, gt=0)
    expected_updated_at: datetime | None = None
    sql_generation_guide_content: str = Field(
        min_length=1,
        max_length=262144,
        repr=False,
    )

    @field_validator("sql_generation_guide_content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SQL Generation Guide content must be nonblank")
        if len(value.encode("utf-8")) > 262144:
            raise ValueError("SQL Generation Guide content exceeds 262144 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def validate_fence_pair(self) -> Self:
        if (self.expected_sql_generation_guide_version_id is None) != (
            self.expected_updated_at is None
        ):
            raise ValueError("Draft version and timestamp fences must be supplied together")
        return self


class SqlGenerationGuideVersionState(SqlGenerationGuideContract):
    sql_generation_guide_version_id: int = Field(gt=0)
    sql_generation_guide_id: int = Field(gt=0)
    sql_generation_guide_version_number: int = Field(gt=0)
    sql_generation_guide_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    sql_generation_guide_version_status: SqlGenerationGuideVersionStatus
    published_at: datetime | None = None
    retired_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
