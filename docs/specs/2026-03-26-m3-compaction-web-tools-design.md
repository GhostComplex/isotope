# M3: Compaction + Web Tools — Design Doc

**Date:** 2026-03-26
**Status:** Approved
**Owner:** Tachikoma
**Branch:** `user/tachikoma/dev-m3` (from `main`)
**PRD Reference:** §7 (Context Compaction), M3 checklist

---

## Goal

Handle long sessions without context overflow. Add web capabilities. After M3: multi-hour coding sessions work without hitting context limits, and the agent can search the web and fetch URLs.

## Success Criteria

- File operations (read/write/edit) are tracked across the session
- When context exceeds threshold, compaction summarizes old messages while preserving file lists
- Compaction entry is appended to JSONL session file
- `/compact` TUI command triggers manual compaction
- `WebSearchTool` searches the web via DuckDuckGo (no API key needed)
- `WebFetchTool` extracts readable content from URLs
- System prompts for presets are improved based on learnings from M1/M2
- All existing tests still pass + new tests

---

## Subtasks

### M3.1: File operation tracking

**Files:**
- `packages/isotope-core/src/isotope_core/context.py` (add file tracker)
- `packages/isotope-core/src/isotope_core/loop.py` (hook into tool results)

**~120 LOC, S**

Track which files are read and modified during the session:

```python
@dataclass
class FileTracker:
    """Tracks file operations across the session for compaction."""
    files_read: set[str] = field(default_factory=set)
    files_modified: set[str] = field(default_factory=set)

    def record_read(self, path: str) -> None: ...
    def record_write(self, path: str) -> None: ...
    def record_edit(self, path: str) -> None: ...
    def snapshot(self) -> dict[str, list[str]]: ...
    def reset(self) -> None: ...
```

Integration with agent loop:
- After each tool result, inspect tool name + arguments:
  - `read_file` → `record_read(path)`
  - `write_file` → `record_write(path)`
  - `edit_file` → `record_edit(path)`
  - `bash` → parse for common file-writing patterns (optional, best-effort)
- `FileTracker` is stored on the `Agent` instance, survives across turns
- On compaction, the tracker provides the file lists, then resets

Add `FileTracker` to `AgentLoopConfig` so it can be passed through.

**Tests:** `packages/isotope-core/tests/test_file_tracker.py`

**Commit after done.**

---

### M3.2: Compaction engine

**Files:**
- `packages/isotope-agents/src/isotope_agents/compaction.py`

**~200 LOC, M**

```python
@dataclass
class CompactionResult:
    summary: str
    files_read: list[str]
    files_modified: list[str]
    messages_compacted: int
    tokens_before: int
    tokens_after: int

async def compact_messages(
    messages: list[Message],
    provider: Provider,
    file_tracker: FileTracker,
    *,
    keep_last_n: int = 4,
    model: str | None = None,
) -> CompactionResult:
    """Compact older messages into a summary, preserving recent context.

    Steps:
    1. Split messages into [compactable | keep_last_n]
    2. Serialize compactable messages into text
    3. Ask the LLM to summarize, with instructions to preserve:
       - Current task and progress
       - Files read and modified (from FileTracker)
       - Key decisions and errors
    4. Return CompactionResult with summary + metadata
    """
```

The compaction prompt should be clear and structured:
```
Summarize the following conversation. Preserve:
- What the user asked for and current progress
- Files read: {files_read}
- Files modified: {files_modified}
- Key decisions made
- Errors encountered and how they were resolved
- Any pending work or next steps

Do NOT include tool call details — just summarize what was done and learned.
```

**Tests:** `packages/isotope-agents/tests/test_compaction.py` — test with mock provider.

**Commit after done.**

---

### M3.3: Wire compaction into agent + session

**Files:**
- `packages/isotope-agents/src/isotope_agents/agent.py` (add compaction trigger)
- `packages/isotope-agents/src/isotope_agents/session.py` (add compaction entry type)
- `packages/isotope-agents/src/isotope_agents/tui/app.py` (add `/compact` command)

**~100 LOC changes, S**

Auto-compaction trigger:
- After each turn, estimate token count of the conversation
- If estimated tokens > `compaction_threshold` (default: 80% of context window), trigger compaction
- Replace compacted messages with the summary message
- Append `compaction` entry to JSONL session file

Manual compaction:
- `/compact` TUI command triggers compaction immediately
- Shows: "Compacted N messages, saved ~X tokens. Files tracked: read=[...], modified=[...]"

Session entry format:
```jsonl
{"type":"compaction","timestamp":"...","data":{"summary":"...","files_read":["src/auth.py"],"files_modified":["src/auth.py"],"messages_compacted":12,"tokens_before":45000,"tokens_after":8000}}
```

On session resume, compaction entries are treated as system messages with the summary.

**Tests:** Update `test_agent.py` and `test_session.py`.

**Commit after done.**

---

### M3.4: WebSearchTool

**File:** `packages/isotope-agents/src/isotope_agents/tools/web_search.py`

**~80 LOC, S**

Search the web using DuckDuckGo HTML search (no API key needed):

```python
@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return (1-10).
    """
```

Implementation:
- Use `httpx` to query DuckDuckGo HTML (`https://html.duckduckgo.com/html/?q=...`)
- Parse results with basic HTML parsing (regex or html.parser — no heavy deps)
- Return formatted results: title, URL, snippet
- Truncate output via `truncate_output()`
- Add `httpx` as a dependency of isotope-agents

**Tests:** `packages/isotope-agents/tests/test_tools_web.py` — test with mocked HTTP responses.

**Commit after done.**

---

### M3.5: WebFetchTool

**File:** `packages/isotope-agents/src/isotope_agents/tools/web_fetch.py`

**~100 LOC, S**

Fetch a URL and extract readable content:

```python
@tool
async def web_fetch(url: str, max_chars: int = 20000) -> str:
    """Fetch and extract readable content from a URL.

    Args:
        url: HTTP or HTTPS URL to fetch.
        max_chars: Maximum characters to return.
    """
```

Implementation:
- Use `httpx` to fetch the URL (with timeout, user-agent, redirect following)
- Strip HTML tags to extract text content (basic: regex/html.parser)
- For non-HTML content (JSON, plain text), return as-is
- Truncate to `max_chars`
- Handle errors gracefully (timeout, 4xx/5xx, connection errors)

**Tests:** `packages/isotope-agents/tests/test_tools_web.py` — add tests with mocked responses.

**Commit after done.**

---

### M3.6: Improved system prompts

**File:** `packages/isotope-agents/src/isotope_agents/presets.py`

**~50 LOC changes, S**

Improve the preset system prompts based on M1/M2 learnings:

**Coding preset:**
- Add file operation awareness ("when reading files, note the path for your records")
- Add context about available tools
- Add guidance on using web tools effectively
- Add loop avoidance hints ("if an approach isn't working after 2 attempts, try a different strategy")

**Assistant preset:**
- Add web tool guidance
- Add conciseness guidance

Register `web_search` and `web_fetch` tools in coding and assistant presets.

**Tests:** Update `test_presets.py`.

**Commit after done.**

---

### M3.7: Clean up + verify

- Verify all isotope-core tests pass
- Verify all isotope-agents tests pass
- `ruff check` + lint clean
- Update `packages/isotope-agents/pyproject.toml` with `httpx` dependency
- Push, open PR to main

**Commit after done.**

---

## Notes

- File tracking goes in isotope-core — it's core infrastructure for compaction
- Compaction engine goes in isotope-agents — it's opinionated (prompt design, when to trigger)
- Web tools go in isotope-agents (tool implementations always do)
- DuckDuckGo HTML search is chosen because it needs no API key — good for v1. Can add Brave/SerpAPI later
- `httpx` is async-native and already popular in the Python ML/AI ecosystem
- Compaction prompt engineering is critical — it should produce summaries the agent can actually use to continue work
- Token estimation can be rough (chars/4 heuristic) — don't need tiktoken for v1
