"""Dynamic tool loading from Python module paths.

Allows registering additional tools via config by specifying dotted
Python module paths.  Each module is imported and any ``Tool`` instances
found at module level are collected.
"""

from __future__ import annotations

import importlib

from isotopes_core.tools import Tool


def load_tools_from_config(tool_paths: list[str]) -> list[Tool]:
    """Import modules and collect Tool objects.

    Each entry is a dotted Python module path (e.g. "mypackage.tools.custom").
    The module is imported and any Tool instances found at module level are
    collected.

    Args:
        tool_paths: List of dotted module paths to import.

    Returns:
        List of Tool instances discovered in the given modules.

    Raises:
        ImportError: If a module path cannot be imported.
    """
    tools: list[Tool] = []
    for path in tool_paths:
        module = importlib.import_module(path)
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if isinstance(obj, Tool):
                tools.append(obj)
    return tools
