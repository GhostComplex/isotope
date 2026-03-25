"""isotope-agents tools — reusable tool definitions for agent presets."""

from __future__ import annotations

from collections.abc import Callable

from isotope_core.tools import Tool

from isotope_agents.tools.bash import make_bash_tool
from isotope_agents.tools.edit import make_edit_tool
from isotope_agents.tools.glob import make_glob_tool
from isotope_agents.tools.grep import make_grep_tool
from isotope_agents.tools.read import make_read_tool
from isotope_agents.tools.write import make_write_tool

# Canonical name → factory mapping
TOOL_FACTORIES: dict[str, Callable[[], Tool]] = {
    "bash": make_bash_tool,
    "read": make_read_tool,
    "write": make_write_tool,
    "edit": make_edit_tool,
    "grep": make_grep_tool,
    "glob": make_glob_tool,
}


def get_tool(name: str) -> Tool:
    """Instantiate a tool by canonical name.

    Raises:
        KeyError: If the tool name is not registered.
    """
    factory = TOOL_FACTORIES.get(name)
    if factory is None:
        available = ", ".join(sorted(TOOL_FACTORIES))
        raise KeyError(f"Unknown tool: {name!r} (available: {available})")
    return factory()


def get_tools(names: list[str]) -> list[Tool]:
    """Instantiate multiple tools by name."""
    return [get_tool(n) for n in names]


__all__ = [
    "TOOL_FACTORIES",
    "get_tool",
    "get_tools",
    "make_bash_tool",
    "make_read_tool",
    "make_write_tool",
    "make_edit_tool",
    "make_grep_tool",
    "make_glob_tool",
]
