"""Packaged Subject Area sizing, shared by run inputs and answer validation."""

from __future__ import annotations

from functools import cache
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SubjectAreaPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    max_subject_area_columns: int = Field(ge=1, le=100_000)


@cache
def load_subject_area_policy() -> SubjectAreaPolicy:
    raw = files("gds_workbench_api").joinpath("config/subject_areas.json").read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("subject area configuration is too large")
    return SubjectAreaPolicy.model_validate_json(raw, strict=True)


__all__ = ["SubjectAreaPolicy", "load_subject_area_policy"]
