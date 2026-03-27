"""Web search tool for isotope-agents — search the web via DuckDuckGo HTML."""

from __future__ import annotations

import urllib.parse
from html.parser import HTMLParser

import httpx

from isotope_core.tools import ToolResult, auto_tool

from isotope_agents.tools import truncate_output

# Limits
DEFAULT_MAX_RESULTS = 5
MAX_RESULTS_CAP = 10
MIN_RESULTS = 1
REQUEST_TIMEOUT = 10

_USER_AGENT = "Mozilla/5.0 (compatible; IsotopeAgent/0.1; +https://github.com/GhostComplex/isotope)"

_DDG_URL = "https://html.duckduckgo.com/html/"


class _DDGResultParser(HTMLParser):
    """Minimal HTML parser to extract DuckDuckGo search results."""

    def __init__(self, max_results: int) -> None:
        super().__init__()
        self.max_results = max_results
        self.results: list[dict[str, str]] = []

        # Parser state
        self._in_result_link = False
        self._in_snippet = False
        self._current_title = ""
        self._current_url = ""
        self._current_snippet = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self.results) >= self.max_results:
            return
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "") or ""

        # Result title link: <a class="result__a" href="...">
        if tag == "a" and "result__a" in cls:
            self._in_result_link = True
            self._current_title = ""
            href = attr_dict.get("href", "") or ""
            # DuckDuckGo wraps URLs in a redirect; extract the actual URL
            if "uddg=" in href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                self._current_url = parsed.get("uddg", [href])[0]
            else:
                self._current_url = href

        # Snippet: <a class="result__snippet" ...>
        if tag == "a" and "result__snippet" in cls:
            self._in_snippet = True
            self._current_snippet = ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_result_link:
            self._in_result_link = False
        elif tag == "a" and self._in_snippet:
            self._in_snippet = False
            if self._current_title.strip() and self._current_url:
                self.results.append(
                    {
                        "title": self._current_title.strip(),
                        "url": self._current_url.strip(),
                        "snippet": self._current_snippet.strip(),
                    }
                )

    def handle_data(self, data: str) -> None:
        if self._in_result_link:
            self._current_title += data
        elif self._in_snippet:
            self._current_snippet += data


def _format_results(results: list[dict[str, str]]) -> str:
    """Format parsed results as numbered text."""
    if not results:
        return "No results found."
    lines: list[str] = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   URL: {r['url']}")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
        lines.append("")
    return "\n".join(lines).rstrip()


@auto_tool
async def web_search(query: str, max_results: int = DEFAULT_MAX_RESULTS) -> ToolResult:
    """Search the web using DuckDuckGo.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return (1-10).
    """
    if not query or not query.strip():
        return ToolResult.error("Missing required parameter: query")

    # Clamp max_results to valid range
    max_results = max(MIN_RESULTS, min(max_results, MAX_RESULTS_CAP))

    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                _DDG_URL,
                data={"q": query.strip()},
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
    except httpx.TimeoutException:
        return ToolResult.error(f"Search request timed out after {REQUEST_TIMEOUT}s")
    except httpx.HTTPStatusError as exc:
        return ToolResult.error(
            f"Search request failed: HTTP {exc.response.status_code}"
        )
    except httpx.HTTPError as exc:
        return ToolResult.error(f"Search request failed: {exc}")

    parser = _DDGResultParser(max_results)
    parser.feed(resp.text)

    output = _format_results(parser.results)
    output = truncate_output(output)
    return ToolResult.text(output)
