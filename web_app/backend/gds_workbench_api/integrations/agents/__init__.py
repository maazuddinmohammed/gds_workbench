"""Agent SDK integration contracts, adapters, and runtime construction."""

from .composition import LocalFakeAgentAdapter, create_agent_execution_router

__all__ = ["LocalFakeAgentAdapter", "create_agent_execution_router"]
