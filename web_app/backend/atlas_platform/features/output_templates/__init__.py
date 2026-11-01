"""Read-only Output Template catalog feature."""

from atlas_platform.features.output_templates.contracts import (
    OutputTemplateDetail,
    OutputTemplateField,
    OutputTemplatePage,
    OutputTemplateSummary,
    OutputTemplateTargetType,
)
from atlas_platform.features.output_templates.router import (
    create_output_templates_router,
)
from atlas_platform.features.output_templates.service import (
    DatabaseOutputTemplateService,
    OutputTemplateDatabase,
    OutputTemplateNotFoundError,
    OutputTemplateService,
)

__all__ = [
    "DatabaseOutputTemplateService",
    "OutputTemplateDatabase",
    "OutputTemplateDetail",
    "OutputTemplateField",
    "OutputTemplateNotFoundError",
    "OutputTemplatePage",
    "OutputTemplateService",
    "OutputTemplateSummary",
    "OutputTemplateTargetType",
    "create_output_templates_router",
]
