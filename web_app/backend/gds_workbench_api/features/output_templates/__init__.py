"""Read-only Output Template catalog feature."""

from gds_workbench_api.features.output_templates.contracts import (
    OutputTemplateDetail,
    OutputTemplateField,
    OutputTemplatePage,
    OutputTemplateSummary,
    OutputTemplateTargetType,
)
from gds_workbench_api.features.output_templates.router import (
    create_output_templates_router,
)
from gds_workbench_api.features.output_templates.service import (
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
