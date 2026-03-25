"""Tool framework for agent loop.

This module provides the Tool class and ToolResult type for defining
and executing tools within the agent loop.

Two decorator styles are supported:

1. Manual schema (existing):
   @tool(name="my_tool", description="...", parameters={...})
   async def my_tool(tool_call_id, params, signal, on_update): ...

2. Auto-schema from type hints (new):
   @auto_tool
   async def my_tool(pattern: str, path: str = ".", count: int = 10) -> str:
       \"\"\"Search for a pattern.

       Args:
           pattern: Regex pattern to search for.
           path: Directory to search in.
           count: Max results to return.
       \"\"\"
       ...
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar, Union, get_args, get_origin

from isotope_core.types import ImageContent, TextContent

# =============================================================================
# Tool Result
# =============================================================================


@dataclass
class ToolResult:
    """Result of a tool execution.

    Attributes:
        content: List of content blocks (text or images) to return to the model.
        is_error: Whether the tool execution resulted in an error.
    """

    content: list[TextContent | ImageContent] = field(default_factory=list)
    is_error: bool = False

    @classmethod
    def text(cls, text: str, is_error: bool = False) -> ToolResult:
        """Create a ToolResult with text content."""
        return cls(content=[TextContent(text=text)], is_error=is_error)

    @classmethod
    def error(cls, message: str) -> ToolResult:
        """Create an error ToolResult."""
        return cls(content=[TextContent(text=message)], is_error=True)


# =============================================================================
# Tool Update Callback
# =============================================================================

T = TypeVar("T")

ToolUpdateCallback = Callable[[ToolResult], None]


# =============================================================================
# Tool Execution Function Type
# =============================================================================

# Type for the execute function: async (tool_call_id, params, signal?, on_update?) -> ToolResult
ExecuteFn = Callable[
    [str, dict[str, Any], asyncio.Event | None, ToolUpdateCallback | None],
    Awaitable[ToolResult],
]


# =============================================================================
# Tool Schema Validation
# =============================================================================


def validate_json_schema(value: Any, schema: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate a value against a JSON schema.

    This is a simplified validator that handles common cases.
    For production, consider using jsonschema library.

    Args:
        value: The value to validate.
        schema: The JSON schema to validate against.

    Returns:
        A tuple of (is_valid, error_message).
    """
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(value, dict):
            return False, f"Expected object, got {type(value).__name__}"

        # Check required properties
        required = schema.get("required", [])
        for prop in required:
            if prop not in value:
                return False, f"Missing required property: {prop}"

        # Validate properties
        properties = schema.get("properties", {})
        for prop_name, prop_value in value.items():
            if prop_name in properties:
                valid, error = validate_json_schema(prop_value, properties[prop_name])
                if not valid:
                    return False, f"Property '{prop_name}': {error}"

        return True, None

    elif schema_type == "array":
        if not isinstance(value, list):
            return False, f"Expected array, got {type(value).__name__}"

        items_schema = schema.get("items", {})
        for i, item in enumerate(value):
            valid, error = validate_json_schema(item, items_schema)
            if not valid:
                return False, f"Item {i}: {error}"

        return True, None

    elif schema_type == "string":
        if not isinstance(value, str):
            return False, f"Expected string, got {type(value).__name__}"
        return True, None

    elif schema_type == "number":
        if not isinstance(value, (int, float)):
            return False, f"Expected number, got {type(value).__name__}"
        return True, None

    elif schema_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return False, f"Expected integer, got {type(value).__name__}"
        return True, None

    elif schema_type == "boolean":
        if not isinstance(value, bool):
            return False, f"Expected boolean, got {type(value).__name__}"
        return True, None

    elif schema_type == "null":
        if value is not None:
            return False, f"Expected null, got {type(value).__name__}"
        return True, None

    # No type specified or unknown type - accept anything
    return True, None


# =============================================================================
# Tool Class
# =============================================================================


class Tool:
    """A tool that can be executed by the agent.

    Tools have a name, description, JSON schema for parameters, and an
    execute function that runs the tool.

    Attributes:
        name: The unique name of the tool.
        description: Human-readable description of what the tool does.
        parameters: JSON Schema object describing the tool's parameters.
        execute: Async function to execute the tool.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        execute: ExecuteFn,
    ):
        """Initialize a Tool.

        Args:
            name: The unique name of the tool.
            description: Human-readable description of what the tool does.
            parameters: JSON Schema object describing the tool's parameters.
            execute: Async function to execute the tool.
        """
        self.name = name
        self.description = description
        self.parameters = parameters
        self._execute = execute

    def validate_arguments(self, arguments: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate arguments against the tool's parameter schema.

        Args:
            arguments: The arguments to validate.

        Returns:
            A tuple of (is_valid, error_message).
        """
        return validate_json_schema(arguments, self.parameters)

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: ToolUpdateCallback | None = None,
    ) -> ToolResult:
        """Execute the tool with the given arguments.

        Args:
            tool_call_id: Unique identifier for this tool call.
            arguments: The arguments to pass to the tool.
            signal: An asyncio.Event that, when set, signals abortion.
            on_update: Optional callback for streaming updates.

        Returns:
            The result of the tool execution.

        Raises:
            ToolValidationError: If arguments don't match the schema.
        """
        # Validate arguments
        valid, error = self.validate_arguments(arguments)
        if not valid:
            raise ToolValidationError(f"Invalid arguments: {error}")

        return await self._execute(tool_call_id, arguments, signal, on_update)

    def to_schema(self) -> dict[str, Any]:
        """Convert the tool to a JSON-serializable schema for LLM APIs.

        Returns:
            A dictionary containing the tool's schema.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


# =============================================================================
# Exceptions
# =============================================================================


class ToolError(Exception):
    """Base exception for tool-related errors."""

    pass


class ToolValidationError(ToolError):
    """Raised when tool arguments fail validation."""

    pass


class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not found."""

    pass


class ToolExecutionError(ToolError):
    """Raised when tool execution fails."""

    pass


# =============================================================================
# Tool Decorator (convenience)
# =============================================================================


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
) -> Callable[[ExecuteFn], Tool]:
    """Decorator to create a Tool from an async function.

    Example:
        @tool(
            name="get_weather",
            description="Get the current weather",
            parameters={
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city name"}
                },
                "required": ["location"]
            }
        )
        async def get_weather(tool_call_id, params, signal, on_update):
            return ToolResult.text(f"Weather in {params['location']}: Sunny")

    Args:
        name: The unique name of the tool.
        description: Human-readable description.
        parameters: JSON Schema for parameters.

    Returns:
        A decorator that creates a Tool.
    """

    def decorator(fn: ExecuteFn) -> Tool:
        return Tool(
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}},
            execute=fn,
        )

    return decorator


# =============================================================================
# Auto-schema Tool Decorator
# =============================================================================

# Python type → JSON Schema type mapping
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}


def _python_type_to_json_schema(annotation: Any) -> dict[str, Any] | None:
    """Convert a Python type annotation to a JSON Schema type.

    Handles: str, int, float, bool, list[T], T | None, Optional[T].
    Returns None for unsupported types (treated as any).
    """
    # Handle None / NoneType
    if annotation is type(None):
        return {"type": "null"}

    # Direct type mapping
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Handle list[T]
    if origin is list:
        schema: dict[str, Any] = {"type": "array"}
        if args:
            items = _python_type_to_json_schema(args[0])
            if items:
                schema["items"] = items
        return schema

    # Handle X | None (Union with None) → treat as X (optionality handled at required level)
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_type_to_json_schema(non_none[0])
        # Multi-type union without None — not easily representable, skip
        return None

    return None


def _parse_docstring_args(docstring: str) -> tuple[str, dict[str, str]]:
    """Parse a Google-style docstring into description and arg descriptions.

    Returns:
        Tuple of (description, {param_name: param_description}).
    """
    if not docstring:
        return "", {}

    lines = docstring.strip().splitlines()

    # First non-empty line(s) before Args: section = description
    desc_lines: list[str] = []
    arg_descriptions: dict[str, str] = {}
    in_args = False
    current_param: str | None = None

    for line in lines:
        stripped = line.strip()

        if stripped.lower().startswith("args:"):
            in_args = True
            continue

        if in_args:
            # Check for new section headers (Returns:, Raises:, etc.)
            is_section_header = (
                stripped
                and not stripped[0].isspace()
                and stripped.endswith(":")
                and ":" not in stripped[:-1]
            )
            if is_section_header:
                in_args = False
                continue

            # Match "param_name: description" or "param_name (type): description"
            param_match = re.match(r"^\s*(\w+)(?:\s*\([^)]*\))?\s*:\s*(.+)", line)
            if param_match:
                current_param = param_match.group(1)
                arg_descriptions[current_param] = param_match.group(2).strip()
            elif current_param and stripped:
                # Continuation line for current parameter
                arg_descriptions[current_param] += " " + stripped
        elif not in_args:
            if stripped:
                desc_lines.append(stripped)
            elif desc_lines:
                # Empty line after description, stop collecting
                pass

    description = " ".join(desc_lines) if desc_lines else ""
    return description, arg_descriptions


def _is_optional(annotation: Any) -> bool:
    """Check if a type annotation is Optional (X | None or Optional[X])."""
    origin = get_origin(annotation)
    if origin is Union:
        args = get_args(annotation)
        return type(None) in args
    return False


def auto_tool(
    fn: Callable[..., Awaitable[str | ToolResult]] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Tool | Callable[[Callable[..., Awaitable[str | ToolResult]]], Tool]:
    """Decorator that auto-generates a Tool from a function's type hints and docstring.

    Can be used bare or with arguments:

        @auto_tool
        async def grep(pattern: str, path: str = ".") -> str:
            ...

        @auto_tool(name="search", description="Search files")
        async def grep(pattern: str, path: str = ".") -> str:
            ...

    The function signature defines the JSON schema:
    - str → "string", int → "integer", float → "number", bool → "boolean"
    - list[T] → "array" with items
    - X | None → parameter is optional
    - Parameters without defaults → required
    - Parameters with defaults → not required, default value recorded

    The docstring provides:
    - First line → tool description (unless overridden)
    - Args section (Google-style) → parameter descriptions

    The function can return either str (auto-wrapped in ToolResult.text) or ToolResult.
    """

    def _build_tool(func: Callable[..., Awaitable[str | ToolResult]]) -> Tool:
        tool_name = name or func.__name__
        sig = inspect.signature(func)
        docstring = inspect.getdoc(func) or ""
        doc_desc, arg_docs = _parse_docstring_args(docstring)
        tool_desc = description or doc_desc or f"Tool: {tool_name}"

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            annotation = param.annotation
            if annotation is inspect.Parameter.empty:
                continue

            # Build property schema
            prop_schema = _python_type_to_json_schema(annotation) or {}

            # Add description from docstring
            if param_name in arg_docs:
                prop_schema["description"] = arg_docs[param_name]

            # Add default value
            if param.default is not inspect.Parameter.empty and param.default is not None:
                prop_schema["default"] = param.default

            properties[param_name] = prop_schema

            # Determine if required
            if param.default is inspect.Parameter.empty and not _is_optional(annotation):
                required.append(param_name)

        parameters: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters["required"] = required

        # Build the execute wrapper
        async def execute(
            tool_call_id: str,
            params: dict[str, Any],
            signal: asyncio.Event | None = None,
            on_update: ToolUpdateCallback | None = None,
        ) -> ToolResult:
            result = await func(**params)
            if isinstance(result, ToolResult):
                return result
            return ToolResult.text(str(result))

        return Tool(
            name=tool_name,
            description=tool_desc,
            parameters=parameters,
            execute=execute,
        )

    if fn is not None:
        # Used as @auto_tool (bare)
        return _build_tool(fn)
    else:
        # Used as @auto_tool(...) with arguments
        return _build_tool
