"""Shared default naming guidance for Model authoring agents."""

from __future__ import annotations

from typing import Literal

type NamingWorkflow = Literal["conceptual", "logical", "dimensional"]

_DEFAULT_NAMING_INSTRUCTIONS: dict[NamingWorkflow, str] = {
    "conceptual": (
        "Use PascalCase for Conceptual concept and relationship names. "
        "Keep names business-facing and independent of physical table names."
    ),
    "logical": (
        "Use PascalCase for Logical entity, attribute, and relationship names. "
        "Identifier Attribute names end with ID, with both I and D uppercase."
    ),
    "dimensional": (
        "Use PascalCase for Dimensional submodel, entity, attribute, and relationship names. "
        "Dimensional key Attribute names end with Key."
    ),
}


def effective_naming_instructions(
    workflow: NamingWorkflow,
    override: str | None,
) -> str:
    """Use Model/user policy when supplied; otherwise use the shared default."""

    if override is not None and override.strip():
        return override
    return _DEFAULT_NAMING_INSTRUCTIONS[workflow]


__all__ = ["NamingWorkflow", "effective_naming_instructions"]
