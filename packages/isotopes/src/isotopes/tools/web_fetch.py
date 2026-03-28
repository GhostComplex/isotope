"""Web fetch tool for isotopes — fetch and extract readable content from URLs."""

from __future__ import annotations

import urllib.parse
from html.parser import HTMLParser

import httpx

from isotopes_core.tools import ToolResult, auto_tool

from isotopes.tools import truncate_output

# Limits
DEFAULT_MAX_CHARS = 20_000
REQUEST_TIMEOUT = 15

_USER_AGENT = "Mozilla/5.0 (compatible; IsotopeAgent/0.1; +https://github.com/GhostComplex/isotope)"

_ALLOWED_SCHEMES = {"http", "https"}


class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML parser that strips tags and extracts text content."""

    # Tags whose content should be skipped entirely
    _SKIP_TAGS = {"script", "style", "head", "noscript", "svg", "template"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._SKIP_TAGS:
            self._skip_depth += 1
        # Insert whitespace for block-level elements to avoid merging text
        if tag.lower() in {
            "p",
            "div",
            "br",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "tr",
            "td",
            "th",
            "blockquote",
            "pre",
            "hr",
            "section",
            "article",
            "header",
            "footer",
            "nav",
            "main",
        }:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        """Return the extracted text, with excess whitespace collapsed."""
        raw = "".join(self._chunks)
        # Collapse runs of whitespace into single spaces, preserve newlines
        lines = raw.splitlines()
        cleaned = "\n".join(" ".join(line.split()) for line in lines)
        # Collapse multiple blank lines
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")
        return cleaned.strip()


def _extract_text_from_html(html: str) -> str:
    """Strip HTML tags and return readable text content."""
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.get_text()


def _validate_url(url: str) -> str | None:
    """Validate URL and return an error message if invalid, None if valid."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return f"Invalid URL: {url}"

    if not parsed.scheme:
        return (
            f"Invalid URL (missing scheme): {url} — only http and https are supported"
        )

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return f"Unsupported URL scheme: {parsed.scheme} — only http and https are supported"

    if not parsed.netloc:
        return f"Invalid URL (missing host): {url}"

    return None


@auto_tool
async def web_fetch(url: str, max_chars: int = DEFAULT_MAX_CHARS) -> ToolResult:
    """Fetch and extract readable content from a URL.

    Args:
        url: HTTP or HTTPS URL to fetch.
        max_chars: Maximum characters to return.
    """
    if not url or not url.strip():
        return ToolResult.error("Missing required parameter: url")

    url = url.strip()

    # Validate URL scheme
    validation_error = _validate_url(url)
    if validation_error:
        return ToolResult.error(validation_error)

    # Fetch the URL
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": _USER_AGENT},
            )
            resp.raise_for_status()
    except httpx.TimeoutException:
        return ToolResult.error(f"Request timed out after {REQUEST_TIMEOUT}s")
    except httpx.HTTPStatusError as exc:
        return ToolResult.error(f"HTTP error {exc.response.status_code} fetching {url}")
    except httpx.HTTPError as exc:
        return ToolResult.error(f"Failed to fetch URL: {exc}")

    # Determine content type and extract text
    content_type = resp.headers.get("content-type", "")

    if "html" in content_type:
        output = _extract_text_from_html(resp.text)
    else:
        # JSON, plain text, and other non-HTML: return as-is
        output = resp.text

    if not output.strip():
        return ToolResult.text("(no readable content extracted)")

    output = truncate_output(output, max_chars=max_chars, strategy="head")
    return ToolResult.text(output)
