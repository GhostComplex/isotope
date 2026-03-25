"""Tests for web search tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from isotope_core.tools import Tool


# Sample DuckDuckGo HTML response with two results
_SAMPLE_HTML = """
<html>
<body>
<div class="results">
  <div class="result">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage1">
      First Result Title
    </a>
    <a class="result__snippet">This is the first snippet.</a>
  </div>
  <div class="result">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage2">
      Second Result Title
    </a>
    <a class="result__snippet">This is the second snippet.</a>
  </div>
  <div class="result">
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage3">
      Third Result Title
    </a>
    <a class="result__snippet">This is the third snippet.</a>
  </div>
</div>
</body>
</html>
"""

# HTML with no search results
_EMPTY_HTML = """
<html>
<body>
<div class="results">
  <div class="no-results">No results found.</div>
</div>
</body>
</html>
"""


def _mock_response(html: str = _SAMPLE_HTML, status_code: int = 200) -> httpx.Response:
    """Create a mock httpx.Response."""
    request = httpx.Request("POST", "https://html.duckduckgo.com/html/")
    return httpx.Response(status_code=status_code, text=html, request=request)


class TestWebSearchTool:
    """Tests for the web_search tool."""

    def _get_tool(self) -> Tool:
        from isotope_agents.tools.web_search import web_search

        return web_search

    @pytest.mark.asyncio
    async def test_basic_search(self) -> None:
        tool = self._get_tool()
        mock_resp = _mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute("call_1", {"query": "python programming"})

        assert not result.is_error
        text = result.content[0].text
        assert "First Result Title" in text
        assert "Second Result Title" in text
        assert "https://example.com/page1" in text
        assert "This is the first snippet" in text

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"query": ""})
        assert result.is_error
        assert "query" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_error(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"query": "   "})
        assert result.is_error

    @pytest.mark.asyncio
    async def test_network_timeout_error(self) -> None:
        tool = self._get_tool()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute("call_1", {"query": "test"})

        assert result.is_error
        assert "timed out" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_network_connection_error(self) -> None:
        tool = self._get_tool()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute("call_1", {"query": "test"})

        assert result.is_error
        assert "failed" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_http_status_error(self) -> None:
        tool = self._get_tool()
        mock_resp = _mock_response(status_code=503)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        # httpx raises HTTPStatusError on raise_for_status()
        mock_resp.raise_for_status = lambda: (_ for _ in ()).throw(  # noqa: E501
            httpx.HTTPStatusError(
                "Server Error",
                request=mock_resp.request,
                response=mock_resp,
            )
        )

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute("call_1", {"query": "test"})

        assert result.is_error
        assert "503" in result.content[0].text

    @pytest.mark.asyncio
    async def test_max_results_clamped_to_upper_bound(self) -> None:
        tool = self._get_tool()
        mock_resp = _mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute(
                "call_1", {"query": "test", "max_results": 50}
            )

        assert not result.is_error
        # Should still work — clamped to 10, but HTML only has 3 results
        text = result.content[0].text
        assert "First Result Title" in text

    @pytest.mark.asyncio
    async def test_max_results_clamped_to_lower_bound(self) -> None:
        tool = self._get_tool()
        mock_resp = _mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute(
                "call_1", {"query": "test", "max_results": -5}
            )

        assert not result.is_error
        text = result.content[0].text
        # Clamped to 1, should only have the first result
        assert "First Result Title" in text
        assert "Second Result Title" not in text

    @pytest.mark.asyncio
    async def test_no_results_found(self) -> None:
        tool = self._get_tool()
        mock_resp = _mock_response(html=_EMPTY_HTML)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute("call_1", {"query": "xyznonexistent"})

        assert not result.is_error
        assert "no results" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_output_formatting(self) -> None:
        tool = self._get_tool()
        mock_resp = _mock_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("isotope_agents.tools.web_search.httpx.AsyncClient", return_value=mock_client):
            result = await tool.execute(
                "call_1", {"query": "test", "max_results": 3}
            )

        assert not result.is_error
        text = result.content[0].text
        # Check numbered format
        assert text.startswith("1.")
        assert "2." in text
        assert "3." in text
        # Check URL format
        assert "URL: https://example.com/page1" in text
