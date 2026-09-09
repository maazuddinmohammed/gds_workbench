"""Applied Generated Code context for one Code Generation target."""

from typing import Literal

from gds_etl_workbench.domain.modeling_records import (
    GeneratedCodeRecord,
    GeneratedCodeSourceSystemRecord,
)
from pydantic import BaseModel, ConfigDict, Field

type ModeledEntityType = Literal["logical_entity", "dimensional_entity"]


class CodeGenerationArtifactContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    object_id: int = Field(gt=0, repr=False)
    code_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    sql_generation_guide_version_id: int = Field(gt=0)
    modeled_entity_type: ModeledEntityType
    modeled_entity_name: str = Field(min_length=1, max_length=255)
    source_system_codes: tuple[str, ...] = Field(min_length=1, max_length=200)
    applied_generated_code: tuple[GeneratedCodeRecord, ...] = Field(
        default=(),
        max_length=5_000,
    )
    applied_generated_code_source_systems: tuple[GeneratedCodeSourceSystemRecord, ...] = Field(
        default=(), max_length=50_000
    )
    current_artifact_names: tuple[str, ...] = Field(default=(), max_length=5_000)
