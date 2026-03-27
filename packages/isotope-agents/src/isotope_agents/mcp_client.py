"""MCP client integration for isotope-agents.

Loads tools from MCP (Model Context Protocol) servers and converts them
to isotope-core Tool objects so they can be used in agent loops.

Requires the optional ``mcp`` dependency::

    pip install isotope-agents[mcp]
"""

from __future__ import annotations

import asyncio
import json
from typing import Any


def _ensure_mcp() -> None:
    """Raise a helpful error if the ``mcp`` package is not installed."""
    try:
        import mcp  # noqa: F401
    except ImportError:
        raise ImportError(
            "The 'mcp' package is required for MCP client integration. "
            "Install it with: pip install isotope-agents[mcp]"
        ) from None


class McpToolLoader:
    """Loads tools from MCP servers and converts them to isotope Tool objects.

    Example usage::

        loader = McpToolLoader()
        tools = await loader.load_from_server(
            {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]}
        )
    """

    async def load_from_server(self, server_config: dict[str, Any]) -> list[Any]:
        """Connect to an MCP server, list its tools, and wrap them as isotope Tools.

        Args:
            server_config: Server connection configuration. Supported forms:
                - ``{"command": "...", "args": [...]}`` — stdio subprocess transport
                - ``{"url": "http://..."}`` — SSE HTTP transport

        Returns:
            A list of isotope-core ``Tool`` objects backed by the MCP server.

        Raises:
            ImportError: If the ``mcp`` package is not installed.
            ValueError: If the config contains neither ``command`` nor ``url``.
        """
        _ensure_mcp()

        if "command" in server_config:
            return await self._load_stdio(server_config)
        elif "url" in server_config:
            return await self._load_sse(server_config)
        else:
            raise ValueError(
                "MCP server config must contain either 'command' (for stdio) "
                "or 'url' (for SSE). Got: " + repr(server_config)
            )

    # ------------------------------------------------------------------
    # Stdio transport
    # ------------------------------------------------------------------

    async def _load_stdio(self, config: dict[str, Any]) -> list[Any]:
        """Load tools via stdio subprocess transport."""
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
        )

        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.list_tools()
                return [
                    self._mcp_tool_to_isotope_tool(t, session)
                    for t in response.tools
                ]

    # ------------------------------------------------------------------
    # SSE transport
    # ------------------------------------------------------------------

    async def _load_sse(self, config: dict[str, Any]) -> list[Any]:
        """Load tools via SSE HTTP transport."""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(config["url"]) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                response = await session.list_tools()
                return [
                    self._mcp_tool_to_isotope_tool(t, session)
                    for t in response.tools
                ]

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def _mcp_tool_to_isotope_tool(self, mcp_tool: Any, client: Any) -> Any:
        """Convert an MCP tool definition to an isotope-core ``Tool``.

        The returned ``Tool.execute`` calls back into the MCP session to
        actually run the tool on the remote server.

        Args:
            mcp_tool: An MCP ``Tool`` object with name, description, and inputSchema.
            client: The ``ClientSession`` used to call the tool.

        Returns:
            An isotope-core ``Tool`` instance.
        """
        from isotope_core.tools import Tool, ToolResult

        name: str = mcp_tool.name
        description: str = mcp_tool.description or f"MCP tool: {name}"
        input_schema: dict[str, Any] = mcp_tool.inputSchema or {
            "type": "object",
            "properties": {},
        }

        # Capture references for the closure
        _client = client
        _name = name

        async def execute(
            tool_call_id: str,
            params: dict[str, Any],
            signal: asyncio.Event | None = None,
            on_update: Any | None = None,
        ) -> ToolResult:
            """Execute the tool on the MCP server."""
            try:
                result = await _client.call_tool(_name, params)
            except Exception as exc:
                return ToolResult.error(f"MCP tool '{_name}' failed: {exc}")

            # Convert MCP result content to text
            texts: list[str] = []
            for block in result.content:
                if hasattr(block, "text"):
                    texts.append(block.text)
                else:
                    texts.append(json.dumps(block.model_dump(), default=str))

            output = "\n".join(texts) if texts else ""
            is_error = getattr(result, "isError", False)
            return ToolResult.text(output, is_error=is_error)

        return Tool(
            name=name,
            description=description,
            parameters=input_schema,
            execute=execute,
        )
