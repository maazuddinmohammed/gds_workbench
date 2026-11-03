"""Agent SDK integration contracts, adapters, and runtime construction."""

from .adapters import ManagedModelAuthentication
from .composition import LocalFakeAgentAdapter, create_agent_execution_router

__all__ = [
    "LocalFakeAgentAdapter",
    "ManagedModelAuthentication",
    "create_agent_execution_router",
]
