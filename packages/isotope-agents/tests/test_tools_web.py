"""Tests for web search and web fetch tools."""

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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute("call_1", {"query": "test", "max_results": 50})

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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute("call_1", {"query": "test", "max_results": -5})

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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
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

        with patch(
            "isotope_agents.tools.web_search.httpx.AsyncClient",
            return_value=mock_client,
        ):
            result = await tool.execute("call_1", {"query": "test", "max_results": 3})

        assert not result.is_error
        text = result.content[0].text
        # Check numbered format
        assert text.startswith("1.")
        assert "2." in text
        assert "3." in text
        # Check URL format
        assert "URL: https://example.com/page1" in text


# =========================================================================
# WebFetchTool tests
# =========================================================================

# Sample HTML page with typical structure
_FETCH_HTML = """
<html>
<head><title>Test Page</title><style>body { color: red; }</style></head>
<body>
<script>var x = 1;</script>
<h1>Hello World</h1>
<p>This is a test paragraph with <b>bold</b> and <i>italic</i> text.</p>
<div>Another section here.</div>
</body>
</html>
"""

_FETCH_JSON = '{"name": "isotope", "version": "0.1.0"}'

_FETCH_PLAIN = "This is plain text content.\nWith multiple lines."


def _mock_fetch_response(
    body: str = _FETCH_HTML,
    status_code: int = 200,
    content_type: str = "text/html; charset=utf-8",
) -> httpx.Response:
    """Create a mock httpx.Response for web_fetch tests."""
    request = httpx.Request("GET", "https://example.com/page")
    return httpx.Response(
        status_code=status_code,
        text=body,
        request=request,
        headers={"content-type": content_type},
    )


class TestWebFetchTool:
    """Tests for the web_fetch tool."""

    def _get_tool(self) -> Tool:
        from isotope_agents.tools.web_fetch import web_fetch

        return web_fetch

    @pytest.mark.asyncio
    async def test_fetch_html_strips_tags(self) -> None:
        """HTML tags should be stripped, leaving only readable text."""
        tool = self._get_tool()
        mock_resp = _mock_fetch_response()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute("call_1", {"url": "https://example.com/page"})

        assert not result.is_error
        text = result.content[0].text
        assert "Hello World" in text
        assert "test paragraph" in text
        assert "bold" in text
        assert "Another section" in text
        # Tags and script/style content should be stripped
        assert "<h1>" not in text
        assert "<p>" not in text
        assert "var x = 1" not in text
        assert "color: red" not in text

    @pytest.mark.asyncio
    async def test_fetch_json_returned_as_is(self) -> None:
        """JSON content should be returned without modification."""
        tool = self._get_tool()
        mock_resp = _mock_fetch_response(
            body=_FETCH_JSON, content_type="application/json"
        )

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute("call_1", {"url": "https://example.com/api"})

        assert not result.is_error
        text = result.content[0].text
        assert '"name": "isotope"' in text
        assert '"version": "0.1.0"' in text

    @pytest.mark.asyncio
    async def test_fetch_plain_text(self) -> None:
        """Plain text content should be returned as-is."""
        tool = self._get_tool()
        mock_resp = _mock_fetch_response(body=_FETCH_PLAIN, content_type="text/plain")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute(
                "call_1", {"url": "https://example.com/file.txt"}
            )

        assert not result.is_error
        text = result.content[0].text
        assert "plain text content" in text
        assert "multiple lines" in text

    @pytest.mark.asyncio
    async def test_invalid_url_scheme(self) -> None:
        """Non-http/https URLs should be rejected."""
        tool = self._get_tool()

        result = await tool.execute("call_1", {"url": "ftp://example.com/file"})
        assert result.is_error
        assert "ftp" in result.content[0].text.lower()

        result = await tool.execute("call_1", {"url": "file:///etc/passwd"})
        assert result.is_error
        assert "file" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_timeout_handling(self) -> None:
        """Timeout errors should return a descriptive error."""
        tool = self._get_tool()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute("call_1", {"url": "https://example.com"})

        assert result.is_error
        assert "timed out" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_http_error_404(self) -> None:
        """404 errors should be reported."""
        tool = self._get_tool()
        mock_resp = _mock_fetch_response(body="Not Found", status_code=404)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        mock_resp.raise_for_status = lambda: (_ for _ in ()).throw(  # noqa: E501
            httpx.HTTPStatusError(
                "Not Found",
                request=mock_resp.request,
                response=mock_resp,
            )
        )

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute(
                "call_1", {"url": "https://example.com/missing"}
            )

        assert result.is_error
        assert "404" in result.content[0].text

    @pytest.mark.asyncio
    async def test_http_error_500(self) -> None:
        """500 errors should be reported."""
        tool = self._get_tool()
        mock_resp = _mock_fetch_response(body="Internal Server Error", status_code=500)

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        mock_resp.raise_for_status = lambda: (_ for _ in ()).throw(  # noqa: E501
            httpx.HTTPStatusError(
                "Server Error",
                request=mock_resp.request,
                response=mock_resp,
            )
        )

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute("call_1", {"url": "https://example.com/error"})

        assert result.is_error
        assert "500" in result.content[0].text

    @pytest.mark.asyncio
    async def test_max_chars_truncation(self) -> None:
        """Output should be truncated when it exceeds max_chars."""
        tool = self._get_tool()
        long_text = "A" * 50_000
        mock_resp = _mock_fetch_response(body=long_text, content_type="text/plain")

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute(
                "call_1", {"url": "https://example.com/big", "max_chars": 100}
            )

        assert not result.is_error
        text = result.content[0].text
        # Should be truncated — output must be shorter than the original
        assert len(text) < 50_000
        assert "truncated" in text.lower()

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        """Connection errors should return a descriptive error."""
        tool = self._get_tool()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with patch(
            "isotope_agents.tools.web_fetch.httpx.AsyncClient", return_value=mock_client
        ):
            result = await tool.execute("call_1", {"url": "https://example.com"})

        assert result.is_error
        assert "failed" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_empty_url_returns_error(self) -> None:
        """Empty URL should return an error."""
        tool = self._get_tool()
        result = await tool.execute("call_1", {"url": ""})
        assert result.is_error
        assert "url" in result.content[0].text.lower()
