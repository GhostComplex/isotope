"""Tests for MCP client integration."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from isotope_agents.config import McpServerConfig, load_config
from isotope_agents.mcp_client import McpToolLoader, _ensure_mcp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_UNSET = object()


def _make_mcp_tool(
    name: str = "read_file",
    description: str = "Read a file from disk",
    input_schema: dict[str, Any] | None = _UNSET,
) -> SimpleNamespace:
    """Create a fake MCP tool definition that quacks like ``mcp.types.Tool``."""
    if input_schema is _UNSET:
        input_schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
            },
            "required": ["path"],
        }
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema=input_schema,
    )


def _make_call_result(texts: list[str], is_error: bool = False) -> SimpleNamespace:
    """Create a fake ``CallToolResult``."""
    content = [SimpleNamespace(text=t) for t in texts]
    return SimpleNamespace(content=content, isError=is_error)


# ---------------------------------------------------------------------------
# _ensure_mcp
# ---------------------------------------------------------------------------


class TestEnsureMcp:
    """Tests for the _ensure_mcp guard."""

    def test_raises_when_mcp_missing(self) -> None:
        """Raise ImportError with a helpful message when mcp is absent."""
        with patch.dict(sys.modules, {"mcp": None}):
            with pytest.raises(ImportError, match="mcp"):
                _ensure_mcp()

    def test_passes_when_mcp_available(self) -> None:
        """No error when mcp is importable."""
        fake_mcp = MagicMock()
        with patch.dict(sys.modules, {"mcp": fake_mcp}):
            _ensure_mcp()  # should not raise


# ---------------------------------------------------------------------------
# _mcp_tool_to_isotope_tool
# ---------------------------------------------------------------------------


class TestMcpToolConversion:
    """Tests for McpToolLoader._mcp_tool_to_isotope_tool."""

    def test_basic_conversion(self) -> None:
        """Converts name, description, and inputSchema."""
        loader = McpToolLoader()
        mcp_tool = _make_mcp_tool()
        client = AsyncMock()

        tool = loader._mcp_tool_to_isotope_tool(mcp_tool, client)

        assert tool.name == "read_file"
        assert tool.description == "Read a file from disk"
        assert tool.parameters["type"] == "object"
        assert "path" in tool.parameters["properties"]

    def test_missing_description_uses_fallback(self) -> None:
        """When description is None, a fallback is generated."""
        loader = McpToolLoader()
        mcp_tool = _make_mcp_tool(description=None)
        client = AsyncMock()

        tool = loader._mcp_tool_to_isotope_tool(mcp_tool, client)

        assert "read_file" in tool.description

    def test_missing_input_schema_uses_empty(self) -> None:
        """When inputSchema is None, an empty object schema is used."""
        loader = McpToolLoader()
        mcp_tool = _make_mcp_tool(input_schema=None)
        client = AsyncMock()

        tool = loader._mcp_tool_to_isotope_tool(mcp_tool, client)

        assert tool.parameters == {"type": "object", "properties": {}}

    @pytest.mark.asyncio
    async def test_execute_calls_mcp_server(self) -> None:
        """Tool.execute proxies to the MCP client session."""
        loader = McpToolLoader()
        client = AsyncMock()
        client.call_tool = AsyncMock(
            return_value=_make_call_result(["file contents here"])
        )

        mcp_tool = _make_mcp_tool()
        tool = loader._mcp_tool_to_isotope_tool(mcp_tool, client)

        result = await tool._execute("call-1", {"path": "/tmp/a.txt"}, None, None)

        client.call_tool.assert_awaited_once_with("read_file", {"path": "/tmp/a.txt"})
        assert result.is_error is False
        assert result.content[0].text == "file contents here"

    @pytest.mark.asyncio
    async def test_execute_handles_error_result(self) -> None:
        """When the MCP server returns isError=True, ToolResult.is_error is set."""
        loader = McpToolLoader()
        client = AsyncMock()
        client.call_tool = AsyncMock(
            return_value=_make_call_result(["permission denied"], is_error=True)
        )

        mcp_tool = _make_mcp_tool()
        tool = loader._mcp_tool_to_isotope_tool(mcp_tool, client)

        result = await tool._execute("call-2", {"path": "/root/secret"}, None, None)

        assert result.is_error is True
        assert "permission denied" in result.content[0].text

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self) -> None:
        """When call_tool raises, return an error ToolResult."""
        loader = McpToolLoader()
        client = AsyncMock()
        client.call_tool = AsyncMock(side_effect=RuntimeError("connection lost"))

        mcp_tool = _make_mcp_tool()
        tool = loader._mcp_tool_to_isotope_tool(mcp_tool, client)

        result = await tool._execute("call-3", {"path": "/tmp/x"}, None, None)

        assert result.is_error is True
        assert "connection lost" in result.content[0].text


# ---------------------------------------------------------------------------
# load_from_server
# ---------------------------------------------------------------------------


class TestLoadFromServer:
    """Tests for McpToolLoader.load_from_server."""

    @pytest.mark.asyncio
    async def test_invalid_config_raises_value_error(self) -> None:
        """Config with neither command nor url raises ValueError."""
        loader = McpToolLoader()
        with patch("isotope_agents.mcp_client._ensure_mcp"):
            with pytest.raises(ValueError, match="command.*url"):
                await loader.load_from_server({"name": "bad"})

    @pytest.mark.asyncio
    async def test_import_error_when_mcp_missing(self) -> None:
        """ImportError is raised when mcp package is unavailable."""
        loader = McpToolLoader()
        with patch.dict(sys.modules, {"mcp": None}):
            with pytest.raises(ImportError, match="mcp"):
                await loader.load_from_server({"command": "echo"})

    @pytest.mark.asyncio
    async def test_stdio_transport(self) -> None:
        """Command-based config uses stdio transport."""
        loader = McpToolLoader()

        fake_tool = _make_mcp_tool(name="list_dir")
        fake_response = SimpleNamespace(tools=[fake_tool])

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=fake_response)
        mock_session.call_tool = AsyncMock(return_value=_make_call_result(["ok"]))

        # Build async context-manager mocks
        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_stdio_ctx = AsyncMock()
        mock_stdio_ctx.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_stdio_ctx.__aexit__ = AsyncMock(return_value=False)

        # Create fake mcp modules in sys.modules so imports inside
        # _load_stdio resolve without the real mcp package.
        mock_mcp = MagicMock()
        mock_mcp.ClientSession = MagicMock(return_value=mock_session_ctx)
        mock_stdio_mod = MagicMock()
        mock_stdio_mod.StdioServerParameters = lambda **kw: SimpleNamespace(**kw)
        mock_stdio_mod.stdio_client = MagicMock(return_value=mock_stdio_ctx)

        with (
            patch("isotope_agents.mcp_client._ensure_mcp"),
            patch.dict(
                sys.modules,
                {
                    "mcp": mock_mcp,
                    "mcp.client": MagicMock(),
                    "mcp.client.stdio": mock_stdio_mod,
                },
            ),
        ):
            tools = await loader.load_from_server(
                {"command": "npx", "args": ["-y", "server-fs", "/tmp"]}
            )

        assert len(tools) == 1
        assert tools[0].name == "list_dir"

    @pytest.mark.asyncio
    async def test_sse_transport(self) -> None:
        """URL-based config uses SSE transport."""
        loader = McpToolLoader()

        fake_tool = _make_mcp_tool(name="search")
        fake_response = SimpleNamespace(tools=[fake_tool])

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=fake_response)
        mock_session.call_tool = AsyncMock(return_value=_make_call_result(["result"]))

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_sse_ctx = AsyncMock()
        mock_sse_ctx.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock()))
        mock_sse_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_mcp = MagicMock()
        mock_mcp.ClientSession = MagicMock(return_value=mock_session_ctx)
        mock_sse_mod = MagicMock()
        mock_sse_mod.sse_client = MagicMock(return_value=mock_sse_ctx)

        with (
            patch("isotope_agents.mcp_client._ensure_mcp"),
            patch.dict(
                sys.modules,
                {
                    "mcp": mock_mcp,
                    "mcp.client": MagicMock(),
                    "mcp.client.sse": mock_sse_mod,
                },
            ),
        ):
            tools = await loader.load_from_server({"url": "http://localhost:3000/mcp"})

        assert len(tools) == 1
        assert tools[0].name == "search"


# ---------------------------------------------------------------------------
# Config integration
# ---------------------------------------------------------------------------


class TestMcpConfig:
    """Tests for MCP server configuration loading."""

    def test_default_config_has_empty_mcp_servers(self) -> None:
        """Default config has no MCP servers."""
        from isotope_agents.config import IsotopeConfig

        config = IsotopeConfig()
        assert config.mcp_servers == []

    def test_load_mcp_servers_from_yaml(self, tmp_path: Path) -> None:
        """MCP servers are parsed from YAML config."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "mcp:\n"
            "  servers:\n"
            "    - name: filesystem\n"
            "      command: npx\n"
            '      args: ["-y", "@mcp/server-fs", "/tmp"]\n'
            "    - name: web\n"
            "      url: http://localhost:3000/mcp\n"
        )
        config = load_config(cfg_file)

        assert len(config.mcp_servers) == 2

        fs = config.mcp_servers[0]
        assert fs.name == "filesystem"
        assert fs.command == "npx"
        assert fs.args == ["-y", "@mcp/server-fs", "/tmp"]
        assert fs.url == ""

        web = config.mcp_servers[1]
        assert web.name == "web"
        assert web.command == ""
        assert web.url == "http://localhost:3000/mcp"

    def test_missing_mcp_section_gives_empty_list(self, tmp_path: Path) -> None:
        """Config without mcp section has empty mcp_servers."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("model: gpt-4o\n")
        config = load_config(cfg_file)
        assert config.mcp_servers == []

    def test_mcp_server_config_dataclass(self) -> None:
        """McpServerConfig fields have sensible defaults."""
        srv = McpServerConfig()
        assert srv.name == ""
        assert srv.command == ""
        assert srv.args == []
        assert srv.url == ""

        srv2 = McpServerConfig(name="fs", command="npx", args=["-y", "server"])
        assert srv2.name == "fs"
        assert srv2.command == "npx"
        assert srv2.args == ["-y", "server"]
