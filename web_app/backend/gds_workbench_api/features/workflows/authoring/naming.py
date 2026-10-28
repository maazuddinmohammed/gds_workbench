"""Shared default naming guidance for Project authoring agents."""

from __future__ import annotations

from typing import Literal

type NamingWorkflow = Literal["logical", "dimensional"]

_DEFAULT_NAMING_INSTRUCTIONS: dict[NamingWorkflow, str] = {
    "logical": (
        "Use PascalCase for Logical entity, attribute, and relationship names. "
        "Identifier Attribute names end with ID, with both I and D uppercase."
    ),
    "dimensional": (
        "Use PascalCase for Dimensional entity and attribute names. "
        "Start each Entity name with its type: Dim for a Dimension, Fact for a Fact, "
        "Bridge for a Bridge (DimCustomer, FactSalesOrder, BridgeCustomerGroup). "
        "Surrogate and foreign key names end with Key."
    ),
}


def effective_naming_instructions(
    workflow: NamingWorkflow,
    override: str | None,
) -> str:
    """Use Project/user policy when supplied; otherwise use the shared default."""

    if override is not None and override.strip():
        return override
    return _DEFAULT_NAMING_INSTRUCTIONS[workflow]


__all__ = ["NamingWorkflow", "effective_naming_instructions"]
